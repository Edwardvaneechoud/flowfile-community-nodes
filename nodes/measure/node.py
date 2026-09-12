import threading

import polars as pl

from flowfile import node_designer as nd

# Shared Geospatial contract: shapes travel as WKT text in a plain string column, always in
# longitude/latitude degrees (EPSG:4326). Every node reads WKT, hex WKB or binary WKB, writes WKT.
AREA_DIVISOR = {"kilometers": 1_000_000.0, "meters": 1.0, "miles": 2_589_988.110336}
LENGTH_DIVISOR = {"kilometers": 1000.0, "meters": 1.0, "miles": 1609.344}
MEASUREMENTS = {
    "area": ("area", pl.Float64),
    "length": ("length", pl.Float64),
    "centre_point": ("centre", pl.Utf8),
    "centre_coords": ("centre_lat", pl.Float64),
    "points": ("points", pl.Int64),  # cast to BIGINT in SQL; ST_NPoints is UInt32
}


class MeasureSettings(nd.NodeSettings):
    measure: nd.Section = nd.Section(
        title="Measure",
        description=(
            "Adds a column for each thing you tick. Area is zero for points and lines; length is the "
            "perimeter of an area, the length of a line, and zero for a point. Mixed collections are "
            "left blank rather than guessed at."
        ),
        geometry_column=nd.ColumnSelector(
            label="Shape column", data_types=[nd.Types.String, nd.Types.Binary], required=True
        ),
        measurements=nd.MultiSelect(
            label="Add",
            options=[
                ("area", "Area"),
                ("length", "Length or perimeter"),
                ("centre_point", "Centre, as a shape"),
                ("centre_coords", "Centre, as latitude and longitude"),
                ("points", "Number of corners"),
            ],
            default=["area", "length"],
        ),
        units=nd.SingleSelect(
            label="Units",
            options=[
                ("kilometers", "Kilometres and square kilometres"),
                ("meters", "Metres and square metres"),
                ("miles", "Miles and square miles"),
            ],
            default="kilometers",
        ),
    )


class Measure(nd.CustomNodeBase):
    node_name: str = "Measure"
    node_category: str = "Geospatial"
    node_icon: str = "geo_geometry_measures.png"
    title: str = "Measure the size of each shape"
    intro: str = (
        "Adds the area, length and centre point of every shape as ordinary columns, so you can sort, "
        "filter and total them. Measured on the ground, accurate at any latitude."
    )
    author: str = "edwardvaneechoud"
    version: str = "0.2.0"
    tags: list[str] = ["geospatial", "measure", "area", "length", "centroid"]
    example_inputs: list[dict[str, list]] = [
        {
            "name": ["District", "Canal", "Station"],
            "geometry": [
                "POLYGON ((4.90 52.36, 4.92 52.36, 4.92 52.38, 4.90 52.38, 4.90 52.36))",
                "LINESTRING (4.9041 52.3676, 4.4777 51.9244)",
                "POINT (4.9001 52.3789)",
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "measure": {
            "geometry_column": "geometry",
            "measurements": ["area", "length", "centre_coords"],
            "units": "kilometers",
        },
    }
    settings_schema: MeasureSettings = MeasureSettings()

    def _connect(self):
        """A DuckDB connection with the spatial extension installed and loaded."""
        import duckdb

        con = duckdb.connect()
        try:
            con.execute("INSTALL spatial")
            con.execute("LOAD spatial")
        except Exception as exc:
            con.close()
            raise RuntimeError(
                "Could not load DuckDB's map extension ('spatial'). The first use on a machine downloads "
                "it from https://extensions.duckdb.org, so an internet connection is needed once. "
                f"Underlying error: {exc}"
            ) from exc
        return con

    def _stream(self, lf: pl.LazyFrame, schema: dict, work) -> pl.LazyFrame:
        """Apply `work(chunk, con)` chunk by chunk, so the plan stays lazy and the worker streams it.

        One DuckDB connection per call, opened on the first chunk. Polars may call from several
        threads and a connection is not thread-safe, hence the lock.
        """
        lock = threading.Lock()
        state: dict = {}

        def apply(chunk: pl.DataFrame) -> pl.DataFrame:
            with lock:
                if "con" not in state:
                    state["con"] = self._connect()
                return work(chunk, state["con"])

        return lf.map_batches(apply, schema=schema, streamable=True)

    def _check_shape_column(self, schema: dict, name: str, label: str) -> None:
        """The upfront half of `_geometry`: the column exists and holds text or bytes."""
        if not name:
            raise ValueError(f"'{label}' is not set. Pick the column holding the shapes.")
        if name not in schema:
            raise ValueError(f"'{label}' column '{name}' is not in the data. Columns: {', '.join(schema)}")
        if schema[name] not in (pl.Utf8, pl.Binary):
            raise ValueError(
                f"'{label}' column '{name}' holds {schema[name]}, not shapes. Use a column made by "
                "Create Points or Spatial Read."
            )

    def _to_wkt(self, df: pl.DataFrame, name: str, con) -> pl.DataFrame:
        """Rewrite a binary WKB shape column as WKT text, so it stays readable downstream."""
        try:
            con.register("_wkb", df.select(pl.col(name).alias("g")).with_row_index("_i"))
            text = con.execute("SELECT ST_AsText(ST_GeomFromWKB(g)) AS w FROM _wkb ORDER BY _i").pl()["w"]
        except Exception as exc:
            raise RuntimeError(f"Could not read the shapes in '{name}': {exc}") from exc
        return df.with_columns(text.alias(name))

    def _geometry(self, df: pl.DataFrame, name: str, con) -> pl.DataFrame:
        """Normalise a shape column to WKT text. Accepts WKT, hex WKB or binary WKB."""
        if df.schema[name] == pl.Binary:
            return self._to_wkt(df, name, con)
        # Blanks are not shapes; treat them as missing so they cannot decide the format below.
        df = df.with_columns(
            pl.when(pl.col(name).str.strip_chars() == "").then(None).otherwise(pl.col(name)).alias(name)
        )
        sample = df.get_column(name).drop_nulls().head(1).to_list()
        if sample:
            candidate = sample[0].strip()
            is_hex = len(candidate) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in candidate)
            if is_hex:
                return self._to_wkt(df.with_columns(pl.col(name).str.decode("hex", strict=False)), name, con)
        return df

    def _settings(self) -> tuple[str, list[str], str]:
        cfg = self.settings_schema.measure
        name = (cfg.geometry_column.value or "").strip()
        chosen = list(cfg.measurements.value or [])
        if not chosen:
            raise ValueError("'Add' is empty. Tick at least one thing to measure.")
        unknown = [item for item in chosen if item not in MEASUREMENTS]
        if unknown:
            raise ValueError(f"'Add' contains unknown measurements: {', '.join(unknown)}.")
        units = cfg.units.value or "kilometers"
        if units not in AREA_DIVISOR:
            raise ValueError(f"'Units' is '{units}', which is not one of: kilometres, metres, miles.")
        return name, chosen, units

    def _new_columns(self, chosen: list[str]) -> list[tuple[str, object]]:
        """Output column names and dtypes, in the order they are added."""
        columns: list[tuple[str, object]] = []
        for item in chosen:
            if item == "centre_coords":
                columns.extend([("centre_lat", pl.Float64), ("centre_lon", pl.Float64)])
            else:
                columns.append(MEASUREMENTS[item])
        return columns

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        name, chosen, units = self._settings()
        lf = inputs[0]
        schema = dict(lf.collect_schema())
        self._check_shape_column(schema, name, "Shape column")
        clashes = [column for column, _ in self._new_columns(chosen) if column in schema]
        if clashes:
            raise ValueError(
                f"The data already has a column named {', '.join(repr(c) for c in clashes)}. "
                "Rename it, or untick that measurement."
            )
        schema[name] = pl.Utf8
        for column, dtype in self._new_columns(chosen):
            schema[column] = dtype

        geom = "ST_GeomFromText(g)"
        flipped = f"ST_FlipCoordinates({geom})"
        kind = f"ST_GeometryType({geom})::VARCHAR"
        selects = {
            "area": f"ST_Area_Spheroid({flipped}) / {AREA_DIVISOR[units]} AS area",
            "length": (
                f"CASE WHEN {geom} IS NULL THEN NULL "
                f"WHEN {kind} IN ('POLYGON','MULTIPOLYGON') THEN ST_Perimeter_Spheroid({flipped}) "
                f"WHEN {kind} IN ('LINESTRING','MULTILINESTRING') THEN ST_Length_Spheroid({flipped}) "
                f"WHEN {kind} IN ('POINT','MULTIPOINT') THEN 0.0 "
                f"ELSE NULL END / {LENGTH_DIVISOR[units]} AS length"
            ),
            "centre_point": f"ST_AsText(ST_Centroid({geom})) AS centre",
            "centre_coords": (
                f"ST_Y(ST_Centroid({geom})) AS centre_lat, ST_X(ST_Centroid({geom})) AS centre_lon"
            ),
            "points": f"ST_NPoints({geom})::BIGINT AS points",
        }
        sql = f"SELECT {', '.join(selects[item] for item in chosen)} FROM _geoms ORDER BY _i"

        def work(chunk: pl.DataFrame, con) -> pl.DataFrame:
            prepared = self._geometry(chunk, name, con)
            con.register("_geoms", prepared.select(pl.col(name).alias("g")).with_row_index("_i"))
            try:
                measured = con.execute(sql).pl()
            except Exception as exc:
                raise RuntimeError(f"Could not measure the shapes: {exc}") from exc
            return prepared.hstack(measured)

        return self._stream(lf, schema, work)

    def predict_output_schema(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        name, chosen, _ = self._settings()
        return inputs[0].with_columns(
            [pl.col(name).cast(pl.Utf8)]
            + [pl.lit(None, dtype=dtype).alias(column) for column, dtype in self._new_columns(chosen)]
        )
