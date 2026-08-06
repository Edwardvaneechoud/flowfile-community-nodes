import polars as pl
from flowfile import node_designer as nd


class AutoMLStoreSettings(nd.NodeSettings):
    data: nd.Section = nd.Section(
        title="Data",
        description="Pick the columns to learn from and the column to predict.",
        layout="horizontal",
        feature_columns=nd.ColumnSelector(
            label="Feature columns",
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

    training: nd.Section = nd.Section(
        title="Model",
        description="Train a specific model, or let AutoML pick the best by cross-validation.",
        layout="horizontal",
        model=nd.SingleSelect(
            label="Model",
            options=[
                "Auto (best)",
                "Linear Model",
                "Random Forest",
                "Extra Trees",
                "Gradient Boosting",
                "Hist Gradient Boosting",
                "Decision Tree",
                "K-Nearest Neighbors",
                "XGBoost",
                "LightGBM",
            ],
            default="Auto (best)",
        ),
        balance_method=nd.SingleSelect(
            label="Balance data (classification)",
            options=[
                ("class_weight", "Balanced (class weights)"),
                ("none", "None"),
                ("oversample", "Oversample minority"),
                ("undersample", "Undersample majority"),
            ],
            default="class_weight",
        ),
        cv_folds=nd.NumericInput(
            label="Cross-validation folds",
            default=5.0,
            min_value=2.0,
            max_value=10.0,
        ),
        primary_metric=nd.SingleSelect(
            label="Selection / report metric",
            options=[
                ("auto", "Auto (Accuracy / R²)"),
                ("accuracy", "Accuracy"),
                ("f1", "F1 (macro)"),
                ("roc_auc", "ROC AUC"),
                ("precision", "Precision (macro)"),
                ("recall", "Recall (macro)"),
                ("r2", "R²"),
                ("rmse", "RMSE"),
                ("mae", "MAE"),
                ("mape", "MAPE"),
            ],
            default="auto",
        ),
    )

    storage: nd.Section = nd.Section(
        title="Storage",
        description="The trained model is persisted globally under this name and can be loaded by AutoML Reuse Model.",
        artifact_name=nd.TextInput(
            label="Model name",
            default="automl_model",
        ),
    )

    visualization: nd.Section = nd.Section(
        title="Visualization",
        description="Publish a feature-importance chart on this node's Artifacts tab (tree/linear models).",
        layout="horizontal",
        publish_importance=nd.ToggleSwitch(
            label="Publish feature importance",
            default=True,
        ),
        importance_artifact_name=nd.TextInput(
            label="Chart artifact name",
            default="feature_importance",
        ),
    )


class AutoMLStoreModel(nd.CustomNodeBase):
    node_name: str = "AutoML Store Model"
    node_category: str = "AutoML"
    node_icon: str = "automl_store_model.png"
    title: str = "Train and store a model"
    intro: str = "Train (or auto-select) a model on all input rows and persist it for reuse in other flows."
    author: str = "Flowfile"
    version: str = "1.0.0"
    tags: list[str] = [
        "machine learning",
        "automl",
        "model store",
    ]
    environment: str = "kernel"
    dependencies: list[str] = [
        "scikit-learn",
        "xgboost",
        "lightgbm",
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
        "training": {
            "model": "Random Forest",
            "balance_method": "class_weight",
            "cv_folds": 3,
            "primary_metric": "accuracy",
        },
        "storage": {
            "artifact_name": "automl_model",
        },
        "visualization": {
            "publish_importance": True,
            "importance_artifact_name": "feature_importance",
        },
    }
    settings_schema: AutoMLStoreSettings = AutoMLStoreSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        seed = 42
        cfg_d = self.settings_schema.data
        cfg_t = self.settings_schema.training
        cfg_s = self.settings_schema.storage
        cfg_v = self.settings_schema.visualization

        feature_cols = list(cfg_d.feature_columns.value)
        target_col = cfg_d.target_column.value
        model_choice = cfg_t.model.value
        folds = int(cfg_t.cv_folds.value)
        balance_method = cfg_t.balance_method.value
        name = (cfg_s.artifact_name.value or "automl_model").strip()

        df = inputs[0].collect()
        X, y, task, label_encoder, num, cat = self._prepare_xy(df, feature_cols, target_col, cfg_d.task.value)
        metric = self._resolve_metric(cfg_t.primary_metric.value, task)
        flowfile_ctx.log_info(
            f"Loaded {X.shape[0]} rows; task={task}; model='{model_choice}', balance='{balance_method}'."
        )

        if model_choice == "Auto (best)":
            candidates = ["Linear Model", "Random Forest", "XGBoost", "LightGBM"]
            best_name, results = self._select_best(X, y, task, candidates, folds, balance_method, metric, seed)
            cv_agg = next((r["scores"] for r in results if r["model"] == best_name), {})
        else:
            best_name = model_choice
            flowfile_ctx.log_info(f"Cross-validating '{best_name}' ({int(folds)}-fold)...")
            cv_agg = self._cv_evaluate(X, y, task, best_name, folds, balance_method, seed)
        cv_score = round(cv_agg[metric][0], 6) if metric in cv_agg else None

        flowfile_ctx.log_info(f"Fitting final '{best_name}' on all {X.shape[0]} rows...")
        X_full, y_full = self._resample(X, y, task, balance_method, seed)
        pipeline = self._fit(self._build_pipeline(num, cat, task, best_name), X_full, y_full, task, balance_method)

        features = num + cat
        classes = [self._py(v) for v in label_encoder.classes_] if label_encoder is not None else None
        bundle = {
            "flowfile_automl_version": 1,
            "pipeline": pipeline,
            "label_encoder": label_encoder,
            "task": task,
            "features": features,
            "target": target_col,
            "model_name": best_name,
            "classes": classes,
            "primary_metric": metric,
            "cv_score": cv_score,
        }
        artifact_id = flowfile_ctx.publish_global(
            name, bundle, description=f"AutoML {task} model ({best_name})", tags=["ml", "automl"],
        )
        if artifact_id is None or artifact_id == -1:
            raise RuntimeError(f"Failed to persist model '{name}' to the global artifact store.")

        if bool(cfg_v.publish_importance.value):
            self._publish_importance(pipeline, best_name, cfg_v.importance_artifact_name.value or "feature_importance")

        flowfile_ctx.log_info(
            f"Stored '{best_name}' ({task}) as global artifact '{name}' (id={artifact_id}); {metric}={cv_score}."
        )
        flowfile_ctx.publish_artifact(name+"_local", bundle)
        return pl.DataFrame(
            {
                "artifact_name": [name],
                "artifact_id": [int(artifact_id)],
                "model": [best_name],
                "task": [task],
                "primary_metric": [metric],
                "cv_score": [cv_score],
                "n_train_rows": [int(X.shape[0])],
                "n_features": [len(features)],
                "n_classes": [len(classes) if classes is not None else None],
                "balancing": [balance_method],
            }
        )

    def _py(self, v):
        try:
            return v.item()
        except AttributeError:
            return v

    def _publish_importance(self, pipeline, model_name, artifact_name):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        model = pipeline.named_steps["model"]
        importances = None
        if hasattr(model, "feature_importances_"):
            importances = np.asarray(model.feature_importances_, dtype=float)
        elif hasattr(model, "coef_"):
            coef = np.asarray(model.coef_, dtype=float)
            importances = np.abs(coef).mean(axis=0) if coef.ndim > 1 else np.abs(coef)
        if importances is None:
            flowfile_ctx.log_info(f"Model '{model_name}' exposes no feature importances; skipping chart.")
            return

        try:
            names = list(pipeline.named_steps["prep"].get_feature_names_out())
        except Exception:  # noqa: BLE001 - fall back to positional names
            names = None
        if names is None or len(names) != len(importances):
            names = [f"feature_{i}" for i in range(len(importances))]

        order = np.argsort(importances)[::-1][:20]
        top_names = [names[i] for i in order]
        top_vals = [float(importances[i]) for i in order]
        y_pos = np.arange(len(top_names))

        fig, ax = plt.subplots(figsize=(9, max(3.0, 0.5 * len(top_names) + 1.0)))
        ax.barh(y_pos, top_vals, color="#4C78A8")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(top_names)
        ax.invert_yaxis()
        ax.set_xlabel("importance")
        ax.set_title(f"Feature importance ({model_name})")
        ax.grid(True, axis="x", alpha=0.3)
        fig.tight_layout()

        flowfile_ctx.publish_artifact(artifact_name, fig, preview=True)

    def _prepare_xy(self, df, feature_cols, target_col, task_setting):
        import numpy as np
        from pandas.api import types as ptypes
        from sklearn.preprocessing import LabelEncoder

        feature_cols = [c for c in feature_cols if c != target_col]
        if not feature_cols:
            raise ValueError("Select at least one feature column that is not the target.")
        df = df.filter(pl.col(target_col).is_not_null())
        if df.height == 0:
            raise ValueError("No rows with a non-null target column.")

        pdf = df.to_pandas()
        X = pdf[feature_cols].copy()
        y_raw = pdf[target_col]
        task = self._detect_task(y_raw, task_setting)

        label_encoder = None
        if task == "classification":
            label_encoder = LabelEncoder()
            y = label_encoder.fit_transform(y_raw)
            if len(label_encoder.classes_) < 2:
                raise ValueError("Classification needs at least two distinct target classes.")
        else:
            if not ptypes.is_numeric_dtype(y_raw):
                raise ValueError("Regression needs a numeric target column.")
            y = y_raw.to_numpy().astype(float)

        num, cat = self._split_features(X, feature_cols)
        return X, np.asarray(y), task, label_encoder, num, cat

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

    def _split_features(self, X, feature_cols):
        from pandas.api import types as ptypes

        num, cat = [], []
        for c in feature_cols:
            s = X[c]
            if ptypes.is_bool_dtype(s):
                cat.append(c)
            elif ptypes.is_numeric_dtype(s):
                num.append(c)
            else:
                cat.append(c)
        return num, cat

    def _resolve_metric(self, metric, task):
        if metric == "auto":
            return "accuracy" if task == "classification" else "r2"
        class_metrics = {"accuracy", "precision", "recall", "f1", "roc_auc"}
        reg_metrics = {"r2", "rmse", "mae", "mape", "mse"}
        if task == "classification" and metric not in class_metrics:
            flowfile_ctx.log_info(f"Metric '{metric}' is not a classification metric; using accuracy.")
            return "accuracy"
        if task == "regression" and metric not in reg_metrics:
            flowfile_ctx.log_info(f"Metric '{metric}' is not a regression metric; using R².")
            return "r2"
        return metric

    def _build_estimator(self, task, model_name):
        if task == "classification":
            if model_name == "Linear Model":
                from sklearn.linear_model import LogisticRegression
                return LogisticRegression(max_iter=1000)
            if model_name == "Random Forest":
                from sklearn.ensemble import RandomForestClassifier
                return RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
            if model_name == "Extra Trees":
                from sklearn.ensemble import ExtraTreesClassifier
                return ExtraTreesClassifier(n_estimators=200, random_state=42, n_jobs=-1)
            if model_name == "Gradient Boosting":
                from sklearn.ensemble import GradientBoostingClassifier
                return GradientBoostingClassifier(random_state=42)
            if model_name == "Hist Gradient Boosting":
                from sklearn.ensemble import HistGradientBoostingClassifier
                return HistGradientBoostingClassifier(random_state=42)
            if model_name == "Decision Tree":
                from sklearn.tree import DecisionTreeClassifier
                return DecisionTreeClassifier(random_state=42)
            if model_name == "K-Nearest Neighbors":
                from sklearn.neighbors import KNeighborsClassifier
                return KNeighborsClassifier()
            if model_name == "XGBoost":
                from xgboost import XGBClassifier
                return XGBClassifier(
                    n_estimators=300, max_depth=6, learning_rate=0.1,
                    random_state=42, verbosity=0, tree_method="hist",
                )
            if model_name == "LightGBM":
                from lightgbm import LGBMClassifier
                return LGBMClassifier(n_estimators=300, random_state=42, verbosity=-1)
        else:
            if model_name == "Linear Model":
                from sklearn.linear_model import LinearRegression
                return LinearRegression()
            if model_name == "Random Forest":
                from sklearn.ensemble import RandomForestRegressor
                return RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1)
            if model_name == "Extra Trees":
                from sklearn.ensemble import ExtraTreesRegressor
                return ExtraTreesRegressor(n_estimators=200, random_state=42, n_jobs=-1)
            if model_name == "Gradient Boosting":
                from sklearn.ensemble import GradientBoostingRegressor
                return GradientBoostingRegressor(random_state=42)
            if model_name == "Hist Gradient Boosting":
                from sklearn.ensemble import HistGradientBoostingRegressor
                return HistGradientBoostingRegressor(random_state=42)
            if model_name == "Decision Tree":
                from sklearn.tree import DecisionTreeRegressor
                return DecisionTreeRegressor(random_state=42)
            if model_name == "K-Nearest Neighbors":
                from sklearn.neighbors import KNeighborsRegressor
                return KNeighborsRegressor()
            if model_name == "XGBoost":
                from xgboost import XGBRegressor
                return XGBRegressor(
                    n_estimators=300, max_depth=6, learning_rate=0.1,
                    random_state=42, verbosity=0, tree_method="hist",
                )
            if model_name == "LightGBM":
                from lightgbm import LGBMRegressor
                return LGBMRegressor(n_estimators=300, random_state=42, verbosity=-1)
        raise ValueError(f"Unknown model '{model_name}'.")

    def _build_pipeline(self, num_features, cat_features, task, model_name):
        from sklearn.compose import ColumnTransformer
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder, StandardScaler

        try:
            ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        except TypeError:
            ohe = OneHotEncoder(handle_unknown="ignore", sparse=False)

        transformers = []
        if num_features:
            transformers.append((
                "num",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]),
                num_features,
            ))
        if cat_features:
            transformers.append((
                "cat",
                Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", ohe)]),
                cat_features,
            ))
        if not transformers:
            raise ValueError("No usable feature columns.")
        pre = ColumnTransformer(transformers, remainder="drop")
        return Pipeline([("prep", pre), ("model", self._build_estimator(task, model_name))])

    def _resample(self, X, y, task, balance_method, seed):
        if task != "classification" or balance_method not in ("oversample", "undersample"):
            return X, y
        import numpy as np
        from sklearn.utils import resample

        classes, counts = np.unique(y, return_counts=True)
        target_n = int(counts.max()) if balance_method == "oversample" else int(counts.min())
        parts = []
        for cls in classes:
            idx = np.where(y == cls)[0]
            parts.append(resample(idx, replace=len(idx) < target_n, n_samples=target_n, random_state=seed))
        sel = np.concatenate(parts)
        return X.iloc[sel], y[sel]

    def _fit(self, pipeline, X, y, task, balance_method):
        if task == "classification" and balance_method == "class_weight":
            from sklearn.utils.class_weight import compute_sample_weight

            sw = compute_sample_weight(class_weight="balanced", y=y)
            try:
                pipeline.fit(X, y, model__sample_weight=sw)
                return pipeline
            except (TypeError, ValueError):
                pipeline.fit(X, y)
                return pipeline
        pipeline.fit(X, y)
        return pipeline

    def _min_class_count(self, y):
        import numpy as np

        _, counts = np.unique(y, return_counts=True)
        return int(counts.min())

    def _score(self, pipe, X_val, y_val, task):
        import numpy as np

        preds = pipe.predict(X_val)
        if task == "classification":
            from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

            out = {
                "accuracy": accuracy_score(y_val, preds),
                "precision": precision_score(y_val, preds, average="macro", zero_division=0),
                "recall": recall_score(y_val, preds, average="macro", zero_division=0),
                "f1": f1_score(y_val, preds, average="macro", zero_division=0),
            }
            try:
                from sklearn.metrics import roc_auc_score

                if hasattr(pipe, "predict_proba"):
                    proba = pipe.predict_proba(X_val)
                    if proba.shape[1] == 2:
                        out["roc_auc"] = roc_auc_score(y_val, proba[:, 1])
                    else:
                        out["roc_auc"] = roc_auc_score(y_val, proba, multi_class="ovr", average="macro")
            except Exception:  # noqa: BLE001 - roc_auc is best-effort (needs all classes present in a fold)
                pass
            return out

        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

        y_arr = np.asarray(y_val, dtype=float)
        p_arr = np.asarray(preds, dtype=float)
        mse = float(mean_squared_error(y_arr, p_arr))
        mask = y_arr != 0
        mape = float(np.mean(np.abs((y_arr[mask] - p_arr[mask]) / y_arr[mask])) * 100) if mask.any() else float("nan")
        return {
            "mae": float(mean_absolute_error(y_arr, p_arr)),
            "mse": mse,
            "rmse": float(np.sqrt(mse)),
            "r2": float(r2_score(y_arr, p_arr)),
            "mape": mape,
        }

    def _cv_evaluate(self, X, y, task, model_name, folds, balance_method, seed):
        import time

        import numpy as np
        from sklearn.base import clone
        from sklearn.model_selection import KFold, StratifiedKFold

        folds = int(folds)
        if task == "classification":
            n_splits = max(2, min(folds, self._min_class_count(y)))
            splits = list(StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed).split(X, y))
        else:
            n_splits = max(2, min(folds, len(y)))
            splits = list(KFold(n_splits=n_splits, shuffle=True, random_state=seed).split(X))

        num, cat = self._split_features(X, list(X.columns))
        template = self._build_pipeline(num, cat, task, model_name)

        per_metric = {}
        fit_times = []
        for tr_idx, val_idx in splits:
            X_tr, X_val = X.iloc[tr_idx], X.iloc[val_idx]
            y_tr, y_val = y[tr_idx], y[val_idx]
            X_tr, y_tr = self._resample(X_tr, y_tr, task, balance_method, seed)
            pipe = clone(template)
            t0 = time.perf_counter()
            pipe = self._fit(pipe, X_tr, y_tr, task, balance_method)
            fit_times.append(time.perf_counter() - t0)
            for k, v in self._score(pipe, X_val, y_val, task).items():
                per_metric.setdefault(k, []).append(v)

        agg = {k: (float(np.nanmean(vs)), float(np.nanstd(vs))) for k, vs in per_metric.items()}
        agg["fit_time_s"] = (float(np.mean(fit_times)), float(np.std(fit_times)))
        return agg

    def _select_best(self, X, y, task, model_names, folds, balance_method, metric, seed):
        higher = metric in {"accuracy", "precision", "recall", "f1", "roc_auc", "r2"}
        results = []
        for name in model_names:
            flowfile_ctx.log_info(f"Evaluating '{name}' ({int(folds)}-fold CV)...")
            try:
                agg = self._cv_evaluate(X, y, task, name, folds, balance_method, seed)
                results.append({"model": name, "scores": agg, "error": None})
                shown = agg.get(metric, (float("nan"),))[0]
                flowfile_ctx.log_info(f"  {name}: {metric}={shown:.4f} (fit {agg['fit_time_s'][0]:.2f}s)")
            except Exception as exc:  # noqa: BLE001 - collect failures, keep evaluating the rest
                results.append({"model": name, "scores": {}, "error": str(exc)})
                flowfile_ctx.log_info(f"  {name} failed: {exc}")

        ok = [r for r in results if r["error"] is None and metric in r["scores"]]
        if not ok:
            fallback = "accuracy" if task == "classification" else "r2"
            ok = [r for r in results if r["error"] is None and fallback in r["scores"]]
            metric, higher = fallback, True
        if not ok:
            errs = "; ".join(f"{r['model']}: {r['error']}" for r in results if r["error"]) or "no usable metric"
            raise ValueError(f"Could not evaluate any candidate model. {errs}")

        def score_of(r):
            val = r["scores"][metric][0]
            if val != val:
                return float("-inf") if higher else float("inf")
            return val

        ok.sort(key=score_of, reverse=higher)
        flowfile_ctx.log_info(f"Selected '{ok[0]['model']}' (best {metric}).")
        return ok[0]["model"], results
