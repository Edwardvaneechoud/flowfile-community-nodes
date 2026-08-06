import polars as pl
from flowfile import node_designer as nd


class TextEmbedderSettings(nd.NodeSettings):
    source: nd.Section = nd.Section(
        title="Text",
        description="The column to embed, and how empty values are treated.",
        layout="horizontal",
        text_column=nd.ColumnSelector(
            label="Text column",
            required=True,
            data_types=[
                "String",
            ],
        ),
        instruction_prefix=nd.TextInput(
            label="Instruction prefix",
            default="",
            placeholder="e5 models want 'query: ' — MiniLM and mpnet want nothing",
        ),
        empty_placeholder=nd.TextInput(
            label="Stand-in for empty text",
            default="",
            placeholder="Leave blank to embed an empty string",
        ),
    )

    model: nd.Section = nd.Section(
        title="Model",
        description="Select the model\n",
        layout="horizontal",
        model_name=nd.SingleSelect(
            label="Model",
            options=[
                ("sentence-transformers/all-MiniLM-L6-v2", "MiniLM-L6-v2 — 384 dim, fastest (Apache-2.0)"),
                ("sentence-transformers/all-mpnet-base-v2", "mpnet-base-v2 — 768 dim, stronger (Apache-2.0)"),
                ("BAAI/bge-small-en-v1.5", "bge-small-en-v1.5 — 384 dim (MIT)"),
                ("BAAI/bge-base-en-v1.5", "bge-base-en-v1.5 — 768 dim (MIT)"),
                ("intfloat/e5-small-v2", "e5-small-v2 — 384 dim, needs 'query: ' prefix (MIT)"),
                ("intfloat/e5-base-v2", "e5-base-v2 — 768 dim, needs 'query: ' prefix (MIT)"),
            ],
            default="sentence-transformers/all-MiniLM-L6-v2",
        ),
        batch_size=nd.NumericInput(
            label="Batch size",
            default=64.0,
            min_value=1.0,
            max_value=1024.0,
        ),
        normalize=nd.ToggleSwitch(
            label="L2-normalize vectors",
            default=True,
            description="Leave on if anything downstream uses cosine similarity or k-means.",
        ),
    )

    output: nd.Section = nd.Section(
        title="Output",
        output_column=nd.TextInput(
            label="Embedding column",
            default="embedding",
        ),
    )


class TextEmbedder(nd.CustomNodeBase):
    node_name: str = "Text Embedder"
    node_category: str = "ML"
    node_icon: str = "text_embedder.png"
    title: str = "Embed text locally"
    intro: str = "Turn a text column into vectors with a local sentence-transformers model. Nothing leaves the machine."
    author: str = "edwardvaneechoud"
    version: str = "1.0.0"
    tags: list[str] = [
        "machine learning",
        "nlp",
        "embeddings",
        "local",
    ]
    environment: str = "kernel"
    dependencies: list[str] = [
        "sentence-transformers>=3.0",
        "numpy>=1.26",
    ]
    example_inputs: list[dict[str, list]] = [
        {
            "complaint_id": [
                1,
                2,
                3,
            ],
            "narrative": [
                "I was charged twice for the same payment and nobody will fix it.",
                "Please stop calling me at work about this account.",
                None,
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "source": {
            "text_column": "narrative",
            "instruction_prefix": "",
            "empty_placeholder": "",
        },
        "model": {
            "model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "batch_size": 64,
            "normalize": True,
        },
        "output": {
            "output_column": "embedding",
        },
    }
    settings_schema: TextEmbedderSettings = TextEmbedderSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        import time

        import numpy as np
        from sentence_transformers import SentenceTransformer

        dimensions = {
            "sentence-transformers/all-MiniLM-L6-v2": 384,
            "sentence-transformers/all-mpnet-base-v2": 768,
            "BAAI/bge-small-en-v1.5": 384,
            "BAAI/bge-base-en-v1.5": 768,
            "intfloat/e5-small-v2": 384,
            "intfloat/e5-base-v2": 768,
        }

        def warn_on_truncation(texts, loaded_model):
            """Report how much text the model will silently cut off.

            Sentence-transformers truncates past max_seq_length without complaint, which
            quietly discards the end of long complaint narratives. Measured on a sample
            with the real tokenizer rather than a characters-per-token guess.
            """
            max_tokens = getattr(loaded_model, "max_seq_length", None)
            if not max_tokens:
                return
            sample = texts[:: max(1, len(texts) // 1000)][:1000]
            if not sample:
                return
            lengths = [len(ids) for ids in loaded_model.tokenizer(sample, truncation=False)["input_ids"]]
            over = sum(1 for n in lengths if n > max_tokens)
            if not over:
                flowfile_ctx.log_info(  # noqa: F821
                    f"No truncation: longest of {len(sample):,} sampled rows is {max(lengths)} tokens "
                    f"against a {max_tokens}-token window."
                )
                return
            flowfile_ctx.log_warning(  # noqa: F821
                f"{over / len(sample):.1%} of a {len(sample):,}-row sample exceeds this model's "
                f"{max_tokens}-token window (longest {max(lengths)}) and will be truncated. "
                f"Only the first {max_tokens} tokens of those rows are represented."
            )

        text_col = self.settings_schema.source.text_column.value
        prefix = self.settings_schema.source.instruction_prefix.value or ""
        placeholder = self.settings_schema.source.empty_placeholder.value or ""
        model_name = self.settings_schema.model.model_name.value
        batch_size = int(self.settings_schema.model.batch_size.value)
        normalize = bool(self.settings_schema.model.normalize.value)
        out_col = self.settings_schema.output.output_column.value

        df = inputs[0].collect()
        if df.height == 0:
            return df.with_columns(
                pl.Series(out_col, [], dtype=pl.Array(pl.Float32, dimensions.get(model_name, 384)))
            ).lazy()

        # Null and whitespace-only text both count as empty — the model would happily
        # embed "   " into a meaningless-but-confident vector otherwise.
        blank = pl.col(text_col).is_null() | (pl.col(text_col).str.strip_chars() == "")
        n_blank = int(df.select(blank.sum()).item())
        if n_blank:
            flowfile_ctx.log_warning(  # noqa: F821
                f"{n_blank:,} of {df.height:,} rows ({n_blank / df.height:.1%}) have empty text "
                f"and will be embedded as {placeholder!r}."
            )

        prepared = df.select(
            (pl.lit(prefix) + pl.when(blank).then(pl.lit(placeholder)).otherwise(pl.col(text_col))).alias("_ff_text")
        )["_ff_text"].to_list()

        # Cache the model in the kernel's per-flow namespace. Survives reruns of this flow
        # on this kernel; lost on kernel restart, /clear_namespace, or LRU eviction.
        cache = globals().setdefault("_ff_text_embedder_models", {})
        if model_name in cache:
            model = cache[model_name]
        else:
            load_started = time.perf_counter()
            model = SentenceTransformer(model_name)
            cache[model_name] = model
            flowfile_ctx.log_info(f"Loaded {model_name} in {time.perf_counter() - load_started:.1f}s")  # noqa: F821

        warn_on_truncation(prepared, model)

            # Sort by length once so every chunk is homogeneous, then chunk for progress logging.
        order = np.argsort([-len(t) for t in prepared])
        prepared_sorted = [prepared[i] for i in order]

        chunk_rows = 500
        embed_started = last_report = time.perf_counter()
        parts = []
        for start in range(0, len(prepared_sorted), chunk_rows):
            parts.append(
                model.encode(
                    prepared_sorted[start : start + chunk_rows],
                    batch_size=batch_size,
                    normalize_embeddings=normalize,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
            )
            now = time.perf_counter()
            done = min(start + chunk_rows, len(prepared_sorted))
            if now - last_report >= 60 and done < len(prepared_sorted):
                rate = done / (now - embed_started)
                flowfile_ctx.log_info(  # noqa: F821
                    f"Embedded {done:,}/{len(prepared_sorted):,} ({done / len(prepared_sorted):.0%}) — "
                    f"{rate:,.0f} rows/s, ~{(len(prepared_sorted) - done) / max(rate, 1e-9) / 60:.0f} min remaining"
                )
                last_report = now
        vectors = np.vstack(parts).astype(np.float32)[np.argsort(order)]
        elapsed = time.perf_counter() - embed_started

        dim = int(vectors.shape[1])
        flowfile_ctx.log_info(  # noqa: F821
            f"Embedded {df.height:,} rows to {dim} dimensions in {elapsed:.1f}s "
            f"({df.height / max(elapsed, 1e-9):,.0f} rows/s)"
        )

        return df.with_columns(pl.Series(out_col, vectors, dtype=pl.Array(pl.Float32, dim))).lazy()

    def predict_output_schema(self, *inputs: pl.LazyFrame) -> pl.LazyFrame | None:
        """Declare the output schema so downstream nodes resolve without running the kernel.

        Without this, a kernel node's columns stay unknown until it has actually run, and
        everything downstream shows "run it to resolve" — which for an embedder means the
        whole rest of the flow.
        """
        dimensions = {
            "sentence-transformers/all-MiniLM-L6-v2": 384,
            "sentence-transformers/all-mpnet-base-v2": 768,
            "BAAI/bge-small-en-v1.5": 384,
            "BAAI/bge-base-en-v1.5": 768,
            "intfloat/e5-small-v2": 384,
            "intfloat/e5-base-v2": 768,
        }
        dim = dimensions.get(self.settings_schema.model.model_name.value)
        if dim is None:
            return None

        schema = dict(inputs[0].collect_schema())
        schema[self.settings_schema.output.output_column.value] = pl.Array(pl.Float32, dim)
        return pl.LazyFrame(schema=schema)
