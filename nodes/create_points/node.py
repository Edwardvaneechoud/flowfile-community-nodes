import polars as pl
from flowfile import node_designer as nd
import threading


WKT_PRECISION = 7


class CreatePointsSettings(nd.NodeSettings):
    coordinates: nd.Section = nd.Section(
        title="Coordinates",
        description="Pick the two columns holding latitude and longitude. Every row becomes a point in a new shape column that Buffer, Distance, Measure, Spatial Join and Map Preview all read.",
        latitude=nd.ColumnSelector(
            label="Latitude",
            required=True,
            data_types=[
                "Numeric",
            ],
        ),
        longitude=nd.ColumnSelector(
            label="Longitude",
            required=True,
            data_types=[
                "Numeric",
            ],
        ),
        output_column=nd.TextInput(
            label="Shape column",
            default="geometry",
        ),
        other_crs=nd.ToggleSwitch(
            label="Other coordinate system",
            description="Leave off for ordinary latitude and longitude in degrees, which is what phones, spreadsheets and web maps produce. Turn on only if your numbers are a national grid, such as Dutch RD or British National Grid; they are then converted to degrees.",
        ),
    )

    system: nd.Section = nd.Section(
        title="Coordinate system",
        description="The system the numbers are already in, as an EPSG code. They are converted to plain latitude/longitude, so every later node measures in real distances. With a national grid the 'Longitude' picker holds the easting (X) and 'Latitude' the northing (Y). Needs the map extension, which downloads once.",
        visible_when=nd.VisibleWhen(
            field="coordinates.other_crs",
        ),
        crs=nd.TextInput(
            label="Coordinate system",
            default="EPSG:28992",
            placeholder="EPSG:28992",
        ),
    )


class CreatePoints(nd.CustomNodeBase):
    node_name: str = "Create Points"
    node_category: str = "Geospatial"
    node_icon: str = "geo_point_from_coordinates.png"
    title: str = "Create points from coordinates"
    intro: str = "Turns latitude and longitude columns into map points, so a plain spreadsheet can be buffered, measured, joined and drawn. Runs offline with no setup."
    author: str = "edwardvaneechoud"
    version: str = "0.3.0"
    tags: list[str] = [
        "geospatial",
        "points",
        "coordinates",
        "latitude",
        "longitude",
    ]
    example_inputs: list[dict[str, list]] = [
        {
            "name": [
                "Amsterdam",
                "Rotterdam",
                "Tromso",
            ],
            "lat": [
                52.3676,
                51.9244,
                69.6496,
            ],
            "lon": [
                4.9041,
                4.4777,
                18.956,
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "coordinates": {
            "latitude": "lat",
            "longitude": "lon",
            "output_column": "geometry",
            "other_crs": False,
        },
        "system": {
            "crs": "EPSG:28992",
        },
    }
    settings_schema: CreatePointsSettings = CreatePointsSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        latitude, longitude, output, source = self._resolve()
        lf = inputs[0]
        schema = dict(lf.collect_schema())
        for label, column in (("Latitude", latitude), ("Longitude", longitude)):
            if column not in schema:
                raise ValueError(f"'{label}' column '{column}' is not in the data. Columns: {', '.join(schema)}")
        if output in schema:
            raise ValueError(
                f"The data already has a column named '{output}'. Pick another name for 'Shape column'."
            )
        lf = lf.with_columns(
            pl.col(latitude).cast(pl.Float64, strict=False),
            pl.col(longitude).cast(pl.Float64, strict=False),
        )

        if source != "EPSG:4326":
            schema.update({latitude: pl.Float64, longitude: pl.Float64, output: pl.Utf8})

            def work(chunk: pl.DataFrame, con) -> pl.DataFrame:
                return chunk.with_columns(self._to_degrees(chunk, longitude, latitude, source, con).alias(output))

            return self._stream(lf, schema, work)

        # Infinities and NaN are not places; they would otherwise render as 'POINT (inf 52)'.
        usable = pl.col(latitude).is_finite() & pl.col(longitude).is_finite()
        checked = pl.col(latitude).map_batches(
            self._latitude_guard(latitude), return_dtype=pl.Float64, is_elementwise=True
        )
        point = self._as_wkt(pl.col(longitude), checked)
        return lf.with_columns(pl.when(usable).then(point).otherwise(None).alias(output))

    def predict_output_schema(self, *inputs: pl.LazyFrame) -> pl.LazyFrame | None:
        latitude, longitude, output, _ = self._resolve()
        return inputs[0].with_columns(
            pl.col(latitude).cast(pl.Float64, strict=False),
            pl.col(longitude).cast(pl.Float64, strict=False),
            pl.lit(None, dtype=pl.Utf8).alias(output),
        )

    def _resolve(self) -> tuple[str, str, str, str]:
        """Latitude column, longitude column, output column, and the source coordinate system."""
        cfg = self.settings_schema.coordinates
        latitude = (cfg.latitude.value or "").strip()
        longitude = (cfg.longitude.value or "").strip()
        if not latitude:
            raise ValueError("'Latitude' is not set. Pick the column holding latitude.")
        if not longitude:
            raise ValueError("'Longitude' is not set. Pick the column holding longitude.")
        output = (cfg.output_column.value or "geometry").strip() or "geometry"
        source = "EPSG:4326"
        if cfg.other_crs.value:
            source = (self.settings_schema.system.crs.value or "").strip()
            if not source:
                raise ValueError("'Coordinate system' is not set. Give the system the numbers are in.")
        return latitude, longitude, output, source

    def _as_wkt(self, x: pl.Expr, y: pl.Expr) -> pl.Expr:
        """POINT (x y), null when either ordinate is null."""
        digits = WKT_PRECISION
        return pl.concat_str(
            pl.lit("POINT ("),
            x.round(digits).cast(pl.Utf8),
            pl.lit(" "),
            y.round(digits).cast(pl.Utf8),
            pl.lit(")"),
        )

    def _latitude_guard(self, name: str):
        """A pass-through that raises on an impossible latitude, evaluated inside the lazy plan.

        |latitude| > 90 almost always means the two columns are the wrong way round, or that these
        are projected metres and 'Other coordinate system' is still off. Values that are not finite
        are left alone; they become empty shapes.
        """

        def check(values: pl.Series) -> pl.Series:
            finite = values.filter(values.is_finite())
            bad = finite.filter(finite.abs() > 90)
            if len(bad):
                raise ValueError(
                    f"'{name}' contains {bad[0]:g}, which is not a valid latitude (it must be between "
                    "-90 and 90). Either the Latitude and Longitude columns are swapped, or these are a "
                    "national grid rather than degrees - turn on 'Other coordinate system'."
                )
            return values

        return check

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

    def _to_degrees(self, df: pl.DataFrame, x: str, y: str, source: str, con) -> pl.Series:
        """Reproject x/y in `source` into longitude/latitude WKT, via DuckDB."""
        try:
            con.register("_xy", df.select(pl.col(x).alias("x"), pl.col(y).alias("y")).with_row_index("_i"))
            converted = con.execute(
                "SELECT ST_AsText(ST_Transform(ST_Point(x, y), ?, 'EPSG:4326', true)) AS wkt "
                "FROM _xy ORDER BY _i",
                [source],
            ).pl()["wkt"]
        except Exception as exc:
            raise ValueError(f"'Coordinate system' is '{source}', which could not be used: {exc}") from exc

        # An unrecognised-but-parseable name (e.g. 'Amersfoort' rather than 'EPSG:28992') does not
        # raise - it silently yields infinite coordinates. Catch that rather than emit invalid shapes.
        broken = converted.is_not_null() & converted.str.contains(r"(?i)inf|nan")
        if broken.any():
            raise ValueError(
                f"'Coordinate system' is '{source}', which does not convert these numbers to "
                "latitude/longitude. Use an EPSG code, such as EPSG:28992."
            )
        return converted
