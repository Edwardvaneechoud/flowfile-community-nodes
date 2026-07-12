import polars as pl
from flowfile import node_designer as nd


class CourtneysNodeSettings(nd.NodeSettings):
    settings: nd.Section = nd.Section(
        title="Settings",
    )


class CourtneysNode(nd.CustomNodeBase):
    node_name: str = "courtneys_node"
    node_category: str = "Fun"
    title: str = "courtneys_node"
    intro: str = "My example node that is cool"
    author: str = "edwardvaneechoud"
    version: str = "1.0.0"
    tags: list[str] = [
        "fun",
    ]
    example_inputs: list[dict[str, list]] = [
        {
            "column_1": [
                "edward",
            ],
        },
    ]
    example_settings: dict[str, dict] = {}
    settings_schema: CourtneysNodeSettings = CourtneysNodeSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        # Get the first input LazyFrame
        lf = inputs[0]

        # Your transformation logic here
        # Example: lf = lf.filter(pl.col("column") > 0)

        return lf
