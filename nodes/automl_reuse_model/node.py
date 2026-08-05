import polars as pl
from flowfile import node_designer as nd


class AutoMLReuseSettings(nd.NodeSettings):
    model: nd.Section = nd.Section(
        title="Model",
        description="Load a model stored by AutoML Store Model and apply it to this data.",
        layout="horizontal",
        model_artifact=nd.SingleSelect(
            label="Stored model",
            options=nd.AvailableArtifacts(
                scope="global",
            ),
        ),
        artifact_name=nd.TextInput(
            label="…or model name (overrides the picker)",
            default="",
            placeholder="automl_model",
        ),
        prediction_column=nd.TextInput(
            label="Prediction column name",
            default="prediction",
        ),
        include_probabilities=nd.ToggleSwitch(
            label="Add class probability columns (classification)",
        ),
    )


class AutoMLReuseModel(nd.CustomNodeBase):
    node_name: str = "AutoML Reuse Model"
    node_category: str = "AutoML"
    node_icon: str = "automl_reuse_model.png"
    title: str = "Load a stored model and predict"
    intro: str = "Load a model persisted by AutoML Store Model and append its predictions to new data."
    author: str = "Flowfile"
    version: str = "1.0.0"
    tags: list[str] = [
        "machine learning",
        "automl",
        "prediction",
    ]
    environment: str = "kernel"
    dependencies: list[str] = [
        "scikit-learn",
        "xgboost",
        "lightgbm",
        "pandas",
    ]
    example_inputs: list[dict[str, list]] = [
        {
            "x1": [
                5.0,
                6.5,
                4.7,
                6.9,
            ],
            "x2": [
                3.4,
                2.4,
                3.3,
                2.2,
            ],
            "region": [
                "north",
                "south",
                "north",
                "south",
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "model": {
            "model_artifact": "automl_model",
            "artifact_name": "",
            "prediction_column": "prediction",
            "include_probabilities": True,
        },
    }
    settings_schema: AutoMLReuseSettings = AutoMLReuseSettings()

    def example_artifacts(self) -> dict[str, object]:
        """Model bundle the dry-run seeds into the artifact store.

        Mirrors the bundle AutoML Store Model persists, fitted on this node's own
        example_inputs so the dry-run exercises the real predict / predict_proba path
        instead of short-circuiting on a missing artifact.
        """
        import pandas as pd
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler

        features = ["x1", "x2", "region"]
        frame = pd.DataFrame(self.example_inputs[0])[features]
        label_encoder = LabelEncoder()
        y = label_encoder.fit_transform(["no", "yes", "no", "yes"])

        prep = ColumnTransformer(
            [
                (
                    "num",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="median")),
                            ("scaler", StandardScaler()),
                        ]
                    ),
                    ["x1", "x2"],
                ),
                (
                    "cat",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                        ]
                    ),
                    ["region"],
                ),
            ],
            remainder="drop",
        )
        pipeline = Pipeline(
            [
                ("prep", prep),
                ("model", RandomForestClassifier(n_estimators=10, random_state=42)),
            ]
        )
        pipeline.fit(frame, y)

        return {
            "automl_model": {
                "flowfile_automl_version": 1,
                "pipeline": pipeline,
                "label_encoder": label_encoder,
                "task": "classification",
                "features": features,
                "target": "y",
                "model_name": "Random Forest",
                "classes": [str(c) for c in label_encoder.classes_],
                "primary_metric": "accuracy",
                "cv_score": None,
            }
        }

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        cfg = self.settings_schema.model
        name = (cfg.artifact_name.value or "").strip() or (cfg.model_artifact.value or "")
        if not name:
            raise ValueError("Pick a stored model or type its name.")
        pred_col = cfg.prediction_column.value or "prediction"
        include_proba = bool(cfg.include_probabilities.value)

        flowfile_ctx.log_info(f"Loading stored model '{name}'...")
        try:
            bundle = flowfile_ctx.get_global(name)
        except Exception as exc:  # noqa: BLE001 - surface a friendly, actionable message
            raise ValueError(
                f"Could not load model '{name}'. Run the AutoML Store Model node first so the "
                f"model is persisted. ({exc})"
            ) from exc

        if not isinstance(bundle, dict) or "pipeline" not in bundle:
            raise ValueError(f"Artifact '{name}' is not an AutoML model bundle.")

        pipeline = bundle["pipeline"]
        label_encoder = bundle.get("label_encoder")
        task = bundle.get("task", "regression")
        features = list(bundle.get("features", []))
        flowfile_ctx.log_info(
            f"Loaded model '{bundle.get('model_name', name)}' ({task}); {len(features)} features."
        )

        df = inputs[0].collect()
        missing = [c for c in features if c not in df.columns]
        if missing:
            raise ValueError(f"Input is missing model feature columns: {missing}")

        X_new = df.to_pandas()[features]
        preds = pipeline.predict(X_new)
        if task == "classification" and label_encoder is not None:
            preds = label_encoder.inverse_transform(preds)
        out = df.with_columns(pl.Series(pred_col, preds))

        if include_proba and task == "classification" and hasattr(pipeline, "predict_proba"):
            proba = pipeline.predict_proba(X_new)
            classes = (
                label_encoder.inverse_transform(pipeline.classes_)
                if label_encoder is not None
                else pipeline.classes_
            )
            for i, cls in enumerate(classes):
                out = out.with_columns(pl.Series(f"{pred_col}_proba_{cls}", proba[:, i]))

        flowfile_ctx.log_info(
            f"Applied stored model '{bundle.get('model_name', name)}' ({task}) to {df.height} rows."
        )
        return out
