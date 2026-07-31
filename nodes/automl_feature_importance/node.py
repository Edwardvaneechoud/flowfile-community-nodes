import polars as pl
from flowfile import node_designer as nd


class AutoMLFeatureImportanceSettings(nd.NodeSettings):
    data: nd.Section = nd.Section(
        title="Data",
        description="Pick the columns to learn from and the column to explain.",
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

    model: nd.Section = nd.Section(
        title="Model",
        description="The model whose feature importance is measured.",
        model=nd.SingleSelect(
            label="Model",
            options=[
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
            default="Random Forest",
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
    )

    importance: nd.Section = nd.Section(
        title="Importance",
        description="Permutation is model-agnostic and reported per original feature; built-in uses the model's own scores.",
        method=nd.SingleSelect(
            label="Method",
            options=[
                ("permutation", "Permutation (model-agnostic)"),
                ("model", "Model built-in"),
            ],
            default="permutation",
        ),
        scoring_metric=nd.SingleSelect(
            label="Permutation scoring metric",
            options=[
                ("auto", "Auto (Accuracy / R²)"),
                ("accuracy", "Accuracy"),
                ("f1", "F1 (macro)"),
                ("roc_auc", "ROC AUC"),
                ("r2", "R²"),
                ("rmse", "RMSE"),
                ("mae", "MAE"),
            ],
            default="auto",
        ),
        n_repeats=nd.NumericInput(
            label="Permutation repeats",
            default=10.0,
            min_value=1.0,
            max_value=50.0,
        ),
        top_n=nd.NumericInput(
            label="Show top N features",
            default=20.0,
            min_value=1.0,
            max_value=100.0,
        ),
    )

    visualization: nd.Section = nd.Section(
        title="Visualization",
        description="Publish a ranked feature-importance chart on this node's Artifacts tab.",
        publish_chart=nd.ToggleSwitch(
            label="Publish importance chart",
            default=True,
        ),
        artifact_name=nd.TextInput(
            label="Chart artifact name",
            default="feature_importance",
        ),
    )


class AutoMLFeatureImportance(nd.CustomNodeBase):
    node_name: str = "AutoML Feature Importance"
    node_category: str = "AutoML"
    node_icon: str = "automl_feature_importance.png"
    title: str = "Explain feature importance"
    intro: str = "Rank the features that most drive the model (permutation or built-in) and publish a chart."
    author: str = "Flowfile"
    version: str = "1.0.0"
    tags: list[str] = [
        "machine learning",
        "automl",
        "explainability",
        "feature importance",
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
        "model": {
            "model": "Random Forest",
            "balance_method": "class_weight",
        },
        "importance": {
            "method": "permutation",
            "scoring_metric": "auto",
            "n_repeats": 5,
            "top_n": 10,
        },
        "visualization": {
            "publish_chart": True,
            "artifact_name": "feature_importance",
        },
    }
    settings_schema: AutoMLFeatureImportanceSettings = AutoMLFeatureImportanceSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        seed = 42
        cfg_d = self.settings_schema.data
        cfg_m = self.settings_schema.model
        cfg_i = self.settings_schema.importance
        cfg_v = self.settings_schema.visualization

        feature_cols = list(cfg_d.feature_columns.value)
        target_col = cfg_d.target_column.value
        model_name = cfg_m.model.value
        balance_method = cfg_m.balance_method.value
        method = cfg_i.method.value
        n_repeats = int(cfg_i.n_repeats.value)
        top_n = int(cfg_i.top_n.value)

        df = inputs[0].collect()
        X, y, task, _label_encoder, _num, _cat = self._prepare_xy(df, feature_cols, target_col, cfg_d.task.value)
        metric = self._resolve_metric(cfg_i.scoring_metric.value, task)
        flowfile_ctx.log_info(
            f"Loaded {X.shape[0]} rows; task={task}; explaining '{model_name}' via {method} importance."
        )

        feats = list(X.columns)
        means, stds = self._compute_importance(X, y, task, model_name, balance_method, method, metric, n_repeats, seed)

        imp = pl.DataFrame(
            {
                "feature": feats,
                "importance": [float(m) for m in means],
                "importance_std": [float(s) for s in stds],
            }
        )
        imp = imp.sort("importance", descending=True, nulls_last=True).head(max(1, top_n))
        imp = imp.with_row_index("rank", offset=1).with_columns(pl.lit(method).alias("method"))
        imp = imp.select(["rank", "feature", "importance", "importance_std", "method"])

        if bool(cfg_v.publish_chart.value):
            self._publish_importance_chart(imp, model_name, method, cfg_v.artifact_name.value or "feature_importance")

        top_feat = imp.get_column("feature")[0]
        top_val = imp.get_column("importance")[0]
        flowfile_ctx.log_info(f"Most important feature: '{top_feat}' (importance={top_val:.4f}).")
        return imp

    def _compute_importance(self, X, y, task, model_name, balance_method, method, metric, n_repeats, seed):
        from sklearn.model_selection import train_test_split

        feats = list(X.columns)
        if X.shape[0] >= 8:
            try:
                strat = y if task == "classification" else None
                X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=seed, stratify=strat)
            except ValueError:
                X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=seed)
        else:
            X_tr, X_te, y_tr, y_te = X, X, y, y

        num, cat = self._split_features(X, feats)
        X_trb, y_trb = self._resample(X_tr, y_tr, task, balance_method, seed)
        pipe = self._fit(self._build_pipeline(num, cat, task, model_name), X_trb, y_trb, task, balance_method)

        if method == "model":
            return self._native_importance(pipe, cat, feats)

        from sklearn.inspection import permutation_importance

        scorer = self._scorer(metric, task)
        try:
            r = permutation_importance(pipe, X_te, y_te, scoring=scorer, n_repeats=n_repeats, random_state=seed)
        except Exception as exc:  # noqa: BLE001 - fall back to a robust default scorer
            fallback = "accuracy" if task == "classification" else "r2"
            flowfile_ctx.log_info(f"Permutation scoring '{scorer}' failed ({exc}); retrying with '{fallback}'.")
            r = permutation_importance(pipe, X_te, y_te, scoring=fallback, n_repeats=n_repeats, random_state=seed)
        return list(r.importances_mean), list(r.importances_std)

    def _native_importance(self, pipe, cat, feats):
        import numpy as np

        model = pipe.named_steps["model"]
        if hasattr(model, "feature_importances_"):
            imp = np.asarray(model.feature_importances_, dtype=float)
        elif hasattr(model, "coef_"):
            coef = np.asarray(model.coef_, dtype=float)
            imp = np.abs(coef).mean(axis=0) if coef.ndim > 1 else np.abs(coef)
        else:
            raise ValueError(f"'{model.__class__.__name__}' has no built-in importances; use the permutation method.")

        try:
            names = list(pipe.named_steps["prep"].get_feature_names_out())
        except Exception:  # noqa: BLE001 - fall back to positional names
            names = [f"feature_{i}" for i in range(len(imp))]

        agg = {f: 0.0 for f in feats}
        for nm, val in zip(names, imp):
            body = nm.split("__", 1)[1] if "__" in nm else nm
            if body in agg:
                agg[body] += float(val)
                continue
            matched = next((cf for cf in cat if body == cf or body.startswith(cf + "_")), None)
            if matched is not None:
                agg[matched] += float(val)
        return [agg.get(f, 0.0) for f in feats], [0.0 for _ in feats]

    def _scorer(self, metric, task):
        if metric == "auto":
            return "accuracy" if task == "classification" else "r2"
        mapping = {
            "accuracy": "accuracy",
            "f1": "f1_macro",
            "roc_auc": "roc_auc",
            "precision": "precision_macro",
            "recall": "recall_macro",
            "r2": "r2",
            "rmse": "neg_root_mean_squared_error",
            "mae": "neg_mean_absolute_error",
            "mape": "neg_mean_absolute_percentage_error",
        }
        return mapping.get(metric, "accuracy" if task == "classification" else "r2")

    def _publish_importance_chart(self, imp_df, model_name, method, artifact_name):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        feats = imp_df.get_column("feature").to_list()
        vals = [float(v) for v in imp_df.get_column("importance").to_list()]
        errs = [float(v) for v in imp_df.get_column("importance_std").to_list()]
        y_pos = np.arange(len(feats))
        has_err = any(e > 0 for e in errs)

        fig, ax = plt.subplots(figsize=(9, max(3.0, 0.5 * len(feats) + 1.0)))
        ax.barh(y_pos, vals, xerr=errs if has_err else None, color="#4C78A8", ecolor="#888888", capsize=3)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(feats)
        ax.invert_yaxis()
        ax.set_xlabel(f"{method} importance")
        ax.set_title(f"Feature importance — {model_name} ({method})")
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
