import polars as pl
from flowfile import node_designer as nd


class AttributeImportanceSettings(nd.NodeSettings):
    data: nd.Section = nd.Section(
        title="Data",
        description="Pick the attributes to score and the column to explain.",
        layout="horizontal",
        feature_columns=nd.ColumnSelector(
            label="Attribute columns",
            required=True,
            multiple=True,
        ),
        target_column=nd.ColumnSelector(
            label="Target column",
            required=True,
        ),
        task=nd.SingleSelect(
            label="Task",
            options=[
                ("auto", "Auto-detect"),
                ("classification", "Classification"),
                ("regression", "Regression"),
            ],
            default="auto",
        ),
    )

    scoring: nd.Section = nd.Section(
        title="Scoring",
        description="Model-free univariate scoring of each attribute against the target.",
        layout="horizontal",
        method=nd.SingleSelect(
            label="Method",
            options=[
                ("mutual_info", "Mutual information (captures non-linear)"),
                ("f_test", "F-test / ANOVA (linear)"),
            ],
            default="mutual_info",
        ),
        normalize=nd.ToggleSwitch(
            label="Normalize scores to 0-1",
            default=True,
        ),
        top_n=nd.NumericInput(
            label="Show top N attributes",
            default=20.0,
            min_value=1.0,
            max_value=100.0,
        ),
    )

    visualization: nd.Section = nd.Section(
        title="Visualization",
        description="Publish a ranked attribute-importance chart on this node's Artifacts tab.",
        layout="horizontal",
        publish_chart=nd.ToggleSwitch(
            label="Publish importance chart",
            default=True,
        ),
        artifact_name=nd.TextInput(
            label="Chart artifact name",
            default="attribute_importance",
        ),
    )


class AttributeImportance(nd.CustomNodeBase):
    node_name: str = "Attribute Importance"
    node_category: str = "AutoML"
    node_icon: str = "attribute_importance.png"
    title: str = "Rank attribute importance"
    intro: str = "Score each attribute's model-free statistical relationship to the target (mutual information / F-test)."
    author: str = "Flowfile"
    version: str = "1.0.0"
    tags: list[str] = [
        "machine learning",
        "automl",
        "feature selection",
        "explainability",
    ]
    environment: str = "kernel"
    dependencies: list[str] = [
        "scikit-learn",
        "pandas",
        "matplotlib",
    ]
    example_inputs: list[dict[str, list]] = [
        {
            "x1": [
                5.1,
                4.9,
                6.2,
                5.9,
                5,
                6.7,
                4.6,
                6.5,
                5.4,
                6.3,
                4.8,
                6.9,
                5.2,
                6,
                4.7,
                6.4,
                5.5,
                6.1,
                4.4,
                6.8,
                5.3,
                6.6,
                4.5,
                7,
            ],
            "x2": [
                3.5,
                3,
                2.2,
                3.2,
                3.6,
                2.5,
                3.1,
                2.8,
                3.4,
                2.3,
                3,
                2.6,
                3.5,
                2.7,
                3.2,
                2.9,
                3.8,
                2.4,
                2.9,
                2.1,
                3.7,
                3,
                3.3,
                2,
            ],
            "region": [
                "north",
                "north",
                "south",
                "south",
                "north",
                "south",
                "north",
                "south",
                "north",
                "south",
                "north",
                "south",
                "north",
                "south",
                "north",
                "south",
                "north",
                "south",
                "north",
                "south",
                "north",
                "south",
                "north",
                "south",
            ],
            "y": [
                "no",
                "no",
                "yes",
                "yes",
                "no",
                "yes",
                "no",
                "yes",
                "no",
                "yes",
                "no",
                "yes",
                "no",
                "yes",
                "no",
                "yes",
                "no",
                "yes",
                "no",
                "yes",
                "no",
                "yes",
                "no",
                "yes",
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "data": {
            "feature_columns": [
                "x1",
                "x2",
                "region",
            ],
            "target_column": "y",
            "task": "classification",
        },
        "scoring": {
            "method": "mutual_info",
            "normalize": True,
            "top_n": 10,
        },
        "visualization": {
            "publish_chart": True,
            "artifact_name": "attribute_importance",
        },
    }
    settings_schema: AttributeImportanceSettings = AttributeImportanceSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        seed = 42
        cfg_d = self.settings_schema.data
        cfg_s = self.settings_schema.scoring
        cfg_v = self.settings_schema.visualization

        feature_cols = [c for c in list(cfg_d.feature_columns.value) if c != cfg_d.target_column.value]
        target_col = cfg_d.target_column.value
        method = cfg_s.method.value
        normalize = bool(cfg_s.normalize.value)
        top_n = int(cfg_s.top_n.value)

        if not feature_cols:
            raise ValueError("Select at least one attribute column that is not the target.")

        df = inputs[0].collect().filter(pl.col(target_col).is_not_null())
        if df.height == 0:
            raise ValueError("No rows with a non-null target column.")

        task, attrs, scores, pvals = self._score(df, feature_cols, target_col, cfg_d.task.value, method, seed)

        import numpy as np

        scores = np.asarray(scores, dtype=float)
        scores = np.nan_to_num(scores, nan=0.0)
        if normalize and scores.max() > 0:
            scores = scores / scores.max()

        table = {"attribute": attrs, "importance": [round(float(s), 6) for s in scores]}
        if pvals is not None:
            table["p_value"] = [round(float(p), 6) for p in np.nan_to_num(np.asarray(pvals, dtype=float), nan=1.0)]
        out = pl.DataFrame(table).sort("importance", descending=True, nulls_last=True).head(max(1, top_n))
        out = out.with_row_index("rank", offset=1).with_columns(pl.lit(method).alias("method"))
        cols = ["rank", "attribute", "importance", *(["p_value"] if pvals is not None else []), "method"]
        out = out.select(cols)

        if bool(cfg_v.publish_chart.value):
            self._publish_chart(out, method, task, cfg_v.artifact_name.value or "attribute_importance")

        flowfile_ctx.log_info(
            f"Scored {len(attrs)} attributes ({task}, {method}); top: "
            f"'{out.get_column('attribute')[0]}' ({out.get_column('importance')[0]:.4f})."
        )
        return out

    def predict_output_schema(self, *inputs: pl.LazyFrame) -> pl.LazyFrame | None:
        # Inputs are lazy: real upstream data once it has run, schema-only before.
        # Return a frame with the output schema, or None to fall back to running the node.
        return pl.LazyFrame(schema=pl.Schema({'rank': pl.UInt32, 'attribute': pl.String, 'importance': pl.Float64, 'method': pl.String}))

    def _detect_task(self, y, task_setting):
        import pandas as pd
        from pandas.api import types as ptypes

        if task_setting in ("classification", "regression"):
            return task_setting
        if (
            ptypes.is_bool_dtype(y)
            or ptypes.is_object_dtype(y)
            or ptypes.is_string_dtype(y)
            or isinstance(y.dtype, pd.CategoricalDtype)
        ):
            return "classification"
        if ptypes.is_integer_dtype(y) and y.nunique(dropna=True) <= 20:
            return "classification"
        return "regression"

    def _score(self, df, feature_cols, target_col, task_setting, method, seed):
        import numpy as np
        import pandas as pd
        from pandas.api import types as ptypes
        from sklearn.preprocessing import LabelEncoder

        pdf = df.to_pandas()
        X = pdf[feature_cols]
        y_raw = pdf[target_col]
        task = self._detect_task(y_raw, task_setting)

        X_enc = pd.DataFrame(index=X.index)
        discrete_mask = []
        for c in feature_cols:
            s = X[c]
            if ptypes.is_numeric_dtype(s) and not ptypes.is_bool_dtype(s):
                s = pd.to_numeric(s, errors="coerce")
                X_enc[c] = s.fillna(s.median() if s.notna().any() else 0.0)
                discrete_mask.append(False)
            else:
                s = s.astype("object").where(s.notna(), "__missing__")
                X_enc[c] = LabelEncoder().fit_transform(s.astype(str))
                discrete_mask.append(True)

        Xv = X_enc.to_numpy(dtype=float)
        if task == "classification":
            y = LabelEncoder().fit_transform(y_raw.astype(str))
        else:
            if not ptypes.is_numeric_dtype(y_raw):
                raise ValueError("Regression needs a numeric target column.")
            y = pd.to_numeric(y_raw, errors="coerce").fillna(0.0).to_numpy(dtype=float)

        if method == "f_test":
            from sklearn.feature_selection import f_classif, f_regression

            fn = f_classif if task == "classification" else f_regression
            scores, pvals = fn(Xv, y)
            return task, feature_cols, scores, pvals

        from sklearn.feature_selection import mutual_info_classif, mutual_info_regression

        fn = mutual_info_classif if task == "classification" else mutual_info_regression
        scores = fn(Xv, y, discrete_features=np.array(discrete_mask, dtype=bool), random_state=seed)
        return task, feature_cols, scores, None

    def _publish_chart(self, table, method, task, artifact_name):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        attrs = table.get_column("attribute").to_list()
        vals = [float(v) for v in table.get_column("importance").to_list()]
        y_pos = np.arange(len(attrs))
        label = "mutual information" if method == "mutual_info" else "F-score"

        fig, ax = plt.subplots(figsize=(9, max(3.0, 0.5 * len(attrs) + 1.0)))
        ax.barh(y_pos, vals, color="#4C78A8")
        for yv, val in zip(y_pos, vals):
            ax.text(val, yv, f" {val:.3f}", va="center", fontsize=8)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(attrs)
        ax.invert_yaxis()
        ax.set_xlabel(label)
        ax.set_title(f"Attribute importance — {task} ({method})")
        ax.grid(True, axis="x", alpha=0.3)
        fig.tight_layout()

        flowfile_ctx.publish_artifact(artifact_name, fig, preview=True)
