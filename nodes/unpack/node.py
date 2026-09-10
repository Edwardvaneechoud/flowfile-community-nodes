import polars as pl
from flowfile import node_designer as nd


class UnpackSettings(nd.NodeSettings):
    unpack: nd.Section = nd.Section(
        title="Unpack",
        description="Flatten a nested list or struct column into rows and/or columns.",
        column=nd.ColumnSelector(
            label="Column to unpack",
            required=True,
            data_types=[
                "Complex",
            ],
        ),
        prefix_fields=nd.ToggleSwitch(
            label="Prefix unnested fields with column name",
            default=True,
        ),
        keep_original=nd.ToggleSwitch(
            label="Keep original column",
        ),
        explode_only=nd.ToggleSwitch(
            label="Explode only (skip unnest for List(Struct))",
        ),
    )


class Unpack(nd.CustomNodeBase):
    node_name: str = "Unpack"
    node_category: str = "Transform"
    node_icon: str = "unpack.png"
    title: str = "Unpack nested column"
    intro: str = "Flattens one nested column: a List of scalars explodes into one row per element, a Struct unnests into one column per field, and a List of Structs explodes and then unnests into one row per element with one column per field. Empty lists and nulls follow Polars' default explode semantics and yield a single row with a null value rather than being filtered out."
    author: str = "edwardvaneechoud"
    version: str = "0.1.0"
    tags: list[str] = [
        "explode",
        "unnest",
        "list",
        "struct",
        "json",
        "flatten",
    ]
    example_inputs: list[dict[str, list]] = [
        {
            "station_id": [
                "a",
                "b",
            ],
            "num_docks_available": [
                10,
                4,
            ],
            "vehicle_types_available": [
                [
                    {
                        "vehicle_type_id": "1",
                        "count": 3,
                    },
                    {
                        "vehicle_type_id": "2",
                        "count": 1,
                    },
                ],
                [
                    {
                        "vehicle_type_id": "1",
                        "count": 0,
                    },
                    {
                        "vehicle_type_id": "2",
                        "count": 2,
                    },
                ],
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "unpack": {
            "column": "vehicle_types_available",
            "prefix_fields": True,
            "keep_original": False,
            "explode_only": False,
        },
    }
    settings_schema: UnpackSettings = UnpackSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        """Unpack one nested column, keeping the unpacked columns in the original position.

        With "keep original" on, the untouched nested column stays in place and the
        unpacked columns follow immediately after it.
        """
        lf = inputs[0]
        column = self.settings_schema.unpack.column.value
        prefix_fields = bool(self.settings_schema.unpack.prefix_fields.value)
        keep_original = bool(self.settings_schema.unpack.keep_original.value)
        explode_only = bool(self.settings_schema.unpack.explode_only.value)

        if not column:
            return lf

        schema = lf.collect_schema()
        if column not in schema:
            raise ValueError(f"Column '{column}' is not present in the input.")
        dtype = schema[column]
        names = list(schema.keys())

        if isinstance(dtype, pl.Struct):
            return self._unnest(lf, column, list(dtype.fields), names, prefix_fields, keep_original)

        if isinstance(dtype, pl.List):
            inner = dtype.inner
            if isinstance(inner, pl.Struct) and not explode_only:
                exploded = lf.explode(column)
                return self._unnest(exploded, column, list(inner.fields), names, prefix_fields, keep_original)
            return lf.explode(column)

        raise ValueError(
            f"Column '{column}' has dtype {dtype}, which cannot be unpacked. "
            "Unpack supports List, Struct, and List(Struct) columns."
        )

    @staticmethod
    def _unnest(
        lf: pl.LazyFrame,
        column: str,
        fields: list,
        names: list[str],
        prefix_fields: bool,
        keep_original: bool,
    ) -> pl.LazyFrame:
        """Unnest ``column`` in place, optionally prefixing field names and keeping the original."""
        field_names = [f.name for f in fields]
        new_names = [f"{column}_{name}" for name in field_names] if prefix_fields else list(field_names)

        existing = set(names)
        if not keep_original:
            existing.discard(column)
        collisions = [name for name in new_names if name in existing]
        if collisions:
            hint = (
                "Turn off 'Keep original column' or rename the conflicting columns."
                if prefix_fields
                else "Turn on 'Prefix unnested fields with column name' to disambiguate them."
            )
            raise ValueError(
                f"Unpacking '{column}' would produce column(s) already present in the frame: "
                f"{', '.join(collisions)}. {hint}"
            )

        if not keep_original:
            renamed = lf.with_columns(pl.col(column).struct.rename_fields(new_names))
            return renamed.unnest(column)

        tmp = f"__unpack_tmp__{column}"
        staged = lf.with_columns(pl.col(column).struct.rename_fields(new_names).alias(tmp))
        unnested = staged.unnest(tmp)
        order: list[str] = []
        for name in names:
            order.append(name)
            if name == column:
                order.extend(new_names)
        return unnested.select(order)
