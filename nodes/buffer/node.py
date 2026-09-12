import polars as pl
from flowfile import node_designer as nd
import threading


METRES_PER_UNIT = {"meters": 1.0, "kilometers": 1000.0, "miles": 1609.344}


class BufferSettings(nd.NodeSettings):
    buffer: nd.Section = nd.Section(
        title="Zone",
        description="Grows every shape outwards by a real ground distance, so 500 m is 500 m whether the data is at the equator or in Norway. A negative distance shrinks the shape instead. Clear 'New column' to replace the original shape rather than add one.",
        geometry_column=nd.ColumnSelector(
            label="Shape column",
            required=True,
            data_types=[
                "Binary",
                "String",
            ],
        ),
        distance=nd.NumericInput(
            label="Distance",
            default=500.0,
        ),
        unit=nd.SingleSelect(
            label="Unit",
            options=[
                ("meters", "Metres"),
                ("kilometers", "Kilometres"),
                ("miles", "Miles"),
            ],
            default="meters",
        ),
        output_column=nd.TextInput(
            label="New column",
            default="zone",
        ),
        smoother=nd.ToggleSwitch(
            label="Adjust smoothness",
            description="Curves are drawn as straight segments. Turn on to trade speed for roundness.",
        ),
    )

    shape: nd.Section = nd.Section(
        title="Smoothness",
        description="Segments used per quarter circle. Higher is rounder and slower; 8 is the default.",
        visible_when=nd.VisibleWhen(
            field="buffer.smoother",
        ),
        quad_segments=nd.NumericInput(
            label="Segments",
            default=8.0,
            min_value=1.0,
            max_value=64.0,
        ),
    )


class Buffer(nd.CustomNodeBase):
    node_name: str = "Buffer"
    node_category: str = "Geospatial"
    node_icon: str = "geo_buffer_geometry.png"
    title: str = "Draw a zone around each shape"
    intro: str = "Grows each shape by a set distance, answering questions like 'which homes are within 500 m of a station?'. Measured on the ground, so it holds up far from the equator."
    author: str = "edwardvaneechoud"
    version: str = "0.3.0"
    tags: list[str] = [
        "geospatial",
        "buffer",
        "zone",
        "catchment",
        "duckdb",
    ]
    example_inputs: list[dict[str, list]] = [
        {
            "name": [
                "Station",
                "Museum",
                "Harbour",
            ],
            "geometry": [
                "POINT (4.9001 52.3789)",
                "POINT (4.8852 52.3600)",
                "POINT (4.9100 52.3200)",
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "buffer": {
            "geometry_column": "geometry",
            "distance": 500,
            "unit": "meters",
            "output_column": "zone",
            "smoother": False,
        },
        "shape": {
            "quad_segments": 8,
        },
    }
    settings_schema: BufferSettings = BufferSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        name, distance, output, segments = self._settings()
        lf = inputs[0]
        schema = dict(lf.collect_schema())
        self._check_shape_column(schema, name, "Shape column")
        if output != name and output in schema:
            raise ValueError(f"The data already has a column named '{output}'. Pick another 'New column'.")
        schema[name] = pl.Utf8
        schema[output] = pl.Utf8

        geom = "ST_GeomFromText(g)"
        buffered = "ST_Transform(ST_Buffer(ST_Transform(src, 'EPSG:4326', zone, true), ?, ?), zone, 'EPSG:4326', true)"
        sql = (
            "SELECT ST_AsText(b) AS zone_wkt, ST_XMax(b) - ST_XMin(b) AS span FROM "
            f"(SELECT _i, {buffered} AS b FROM "
            f"(SELECT _i, {geom} AS src, {self._local_crs_sql(geom)} AS zone FROM _geoms)) ORDER BY _i"
        )

        def work(chunk: pl.DataFrame, con) -> pl.DataFrame:
            prepared = self._geometry(chunk, name, con)
            con.register("_geoms", prepared.select(pl.col(name).alias("g")).with_row_index("_i"))
            try:
                zones = con.execute(sql, [distance, segments]).pl()
            except Exception as exc:
                raise RuntimeError(f"Could not draw the zone: {exc}") from exc
            # A zone reaching across the +/-180 line comes back as one ring wrapped the wrong way
            # round the globe. Representing it properly needs a split shape, so refuse rather than
            # hand downstream nodes a zone that silently spans the planet.
            wrapped = zones.get_column("span") > 180
            if wrapped.any():
                raise ValueError(
                    f"{wrapped.sum()} zones reach across the +/-180 line, which this node cannot draw "
                    "as a single shape. Filter those rows out, or buffer them in a separate flow."
                )
            return prepared.with_columns(zones.get_column("zone_wkt").alias(output))

        return self._stream(lf, schema, work)

    def predict_output_schema(self, *inputs: pl.LazyFrame) -> pl.LazyFrame | None:
        name, _, output, _ = self._settings()
        columns = [pl.col(name).cast(pl.Utf8)]
        if output != name:
            columns.append(pl.lit(None, dtype=pl.Utf8).alias(output))
        return inputs[0].with_columns(columns)

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

    def _local_crs_sql(self, geom: str) -> str:
        """A metre-based system for each feature: the UTM zone of its centroid.

        Beyond the UTM limits the fixed polar systems run about 3% oversize, so those rows fall back
        to an azimuthal-equidistant projection centred on the feature itself, which is exact. That
        fallback builds a projection per row and is ~40x slower, hence only past 84N / 80S where
        rows are rare.
        """
        longitude = f"ST_X(ST_Centroid({geom}))"
        latitude = f"ST_Y(ST_Centroid({geom}))"
        zone = f"least(60, greatest(1, floor(({longitude} + 180.0) / 6.0)::INTEGER + 1))"
        polar = (
            f"'+proj=aeqd +lat_0=' || {latitude} || ' +lon_0=' || {longitude} "
            "|| ' +datum=WGS84 +units=m +no_defs'"
        )
        return (
            f"CASE WHEN {latitude} > 84.0 OR {latitude} < -80.0 THEN {polar} "
            f"ELSE 'EPSG:' || ((CASE WHEN {latitude} >= 0 THEN 32600 ELSE 32700 END) + {zone}) END"
        )

    def _settings(self) -> tuple[str, float, str, int]:
        cfg = self.settings_schema.buffer
        name = (cfg.geometry_column.value or "").strip()
        if not name:
            raise ValueError("'Shape column' is not set. Pick the column holding the shapes.")
        if cfg.distance.value is None:
            raise ValueError("'Distance' is not set. Give the distance to grow each shape by.")
        unit = cfg.unit.value or "meters"
        if unit not in METRES_PER_UNIT:
            raise ValueError(f"'Unit' is '{unit}', which is not one of: metres, kilometres, miles.")
        distance = float(cfg.distance.value) * METRES_PER_UNIT[unit]
        output = (cfg.output_column.value or "").strip() or name
        segments = 8
        if cfg.smoother.value:
            segments = max(1, int(self.settings_schema.shape.quad_segments.value or 8))
        return name, distance, output, segments
