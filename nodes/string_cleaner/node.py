import polars as pl
from flowfile import node_designer as nd


class StringCleanerSettings(nd.NodeSettings):
    cleaning: nd.Section = nd.Section(
        title="Clean String Columns",
        description="Select string columns and the operations to apply (in place).",
        columns=nd.ColumnSelector(
            label="Columns to clean",
            required=True,
            multiple=True,
            data_types=[
                "String",
            ],
        ),
        operations=nd.MultiSelect(
            label="Operations",
            options=[
                ("trim", "Trim leading/trailing whitespace"),
                ("collapse_spaces", "Collapse repeated whitespace"),
                ("remove_all_whitespace", "Remove all whitespace"),
                ("remove_punctuation", "Remove punctuation"),
                ("remove_digits", "Remove digits"),
                ("lowercase", "Lowercase"),
                ("uppercase", "Uppercase"),
                ("titlecase", "Title case"),
            ],
            default=[
                "trim",
                "collapse_spaces",
            ],
        ),
    )


class StringCleaner(nd.CustomNodeBase):
    node_name: str = "String Cleaner"
    node_category: str = "Text Processing"
    node_icon: str = "image-1783862812217.png"
    title: str = "Clean string columns"
    intro: str = "Trim, collapse spaces, change case, and strip characters from selected string columns."
    author: str = "edwardvaneechoud"
    version: str = "1.0.0"
    tags: list[str] = [
        "text",
        "text-cleaning",
    ]
    example_inputs: list[dict[str, list]] = [
        {
            "text": [
                "  Hello   World  ",
                "FOO\tbar",
                "Café  99!",
            ],
            "id": [
                1,
                2,
                3,
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "cleaning": {
            "columns": [
                "text",
            ],
            "operations": [
                "trim",
                "collapse_spaces",
                "lowercase",
                "remove_punctuation",
                "remove_digits",
            ],
        },
    }
    settings_schema: StringCleanerSettings = StringCleanerSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        lf = inputs[0]
        columns = self.settings_schema.cleaning.columns.value or []
        operations = self.settings_schema.cleaning.operations.value or []
        if not columns or not operations:
            return lf

        def clean(name: str) -> pl.Expr:
            expr = pl.col(name)
            if "remove_punctuation" in operations:
                expr = expr.str.replace_all(r"[^\w\s]", "")
            if "remove_digits" in operations:
                expr = expr.str.replace_all(r"[0-9]", "")
            if "remove_all_whitespace" in operations:
                expr = expr.str.replace_all(r"\s", "")
            elif "collapse_spaces" in operations:
                expr = expr.str.replace_all(r"\s+", " ")
            if "trim" in operations:
                expr = expr.str.strip_chars()
            if "lowercase" in operations:
                expr = expr.str.to_lowercase()
            if "uppercase" in operations:
                expr = expr.str.to_uppercase()
            if "titlecase" in operations:
                expr = expr.str.to_titlecase()
            return expr.alias(name)

        return lf.with_columns([clean(c) for c in columns])
