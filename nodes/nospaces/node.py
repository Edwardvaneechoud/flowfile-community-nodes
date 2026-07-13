import polars as pl
from flowfile import node_designer as nd


class NospacesSettings(nd.NodeSettings):
    settings: nd.Section = nd.Section(
        title="Give you rsettings",
        columns=nd.ColumnSelector(
            label="Pick your columns",
            required=True,
            multiple=True,
            data_types=[
                "String",
            ],
        ),
        secret_selector_2=nd.SecretSelector(
            label="secret_selector_2",
        ),
    )


class Nospaces(nd.CustomNodeBase):
    node_name: str = "nospaces"
    node_category: str = "Transform"
    node_icon: str = "catalog_reader.svg"
    title: str = "nospaces"
    intro: str = "I want no spacess"
    author: str = "edwardvaneechoud"
    version: str = "1.0.0"
    tags: list[str] = [
        "text",
    ]
    example_inputs: list[dict[str, list]] = [
        {
            "column_1": [
                "ed ward",
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "settings": {
            "columns": [
                "column_1",
            ],
            "secret_selector_2": None,
        },
    }
    settings_schema: NospacesSettings = NospacesSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        # Get the first input LazyFrame
        columns = self.settings_schema.settings.columns.value
        lf = inputs[0]
        return lf.with_columns([pl.col(c).str.replace(" ", "") for c in columns])
