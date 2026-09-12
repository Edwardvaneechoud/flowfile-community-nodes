import threading

import polars as pl

from flowfile import node_designer as nd

# Shared Geospatial contract: shapes travel as WKT text in a plain string column, always in
# longitude/latitude degrees (EPSG:4326). Every node reads WKT, hex WKB or binary WKB, writes WKT.
WGS84_RADIUS_M = 6378137.0
WGS84_FLATTENING = 1 / 298.257223563
UNIT_IN_METRES = {"kilometers": 1000.0, "meters": 1.0, "miles": 1609.344}


class DistanceSettings(nd.NodeSettings):
    mode: nd.Section = nd.Section(
        title="Measure between",
        description="Each row holds both places, and the distance is added as a new column on that row.",
        use_shapes=nd.ToggleSwitch(
            label="Use shape columns",
            default=False,
            description=(
                "Off: pick four latitude/longitude columns, which is what a spreadsheet normally has. "
                "On: pick two shape columns instead, and the distance is measured centre to centre."
            ),
        ),
    )

    points: nd.Section = nd.Section(
        title="Coordinates",
        description="The two places on each row, as latitude and longitude in degrees.",
        visible_when=nd.VisibleWhen(field="mode.use_shapes", equals=False),
        from_latitude=nd.ColumnSelector(label="From latitude", data_types=nd.Types.Numeric),
        from_longitude=nd.ColumnSelector(label="From longitude", data_types=nd.Types.Numeric),
        to_latitude=nd.ColumnSelector(label="To latitude", data_types=nd.Types.Numeric),
        to_longitude=nd.ColumnSelector(label="To longitude", data_types=nd.Types.Numeric),
    )

    shapes: nd.Section = nd.Section(
        title="Shapes",
        description=(
            "The two shape columns to measure between. Areas and lines are measured from their centre "
            "point. Needs the map extension, which downloads once."
        ),
        visible_when=nd.VisibleWhen(field="mode.use_shapes", equals=True),
        from_geometry=nd.ColumnSelector(
            label="From shape", data_types=[nd.Types.String, nd.Types.Binary], required=True
        ),
        to_geometry=nd.ColumnSelector(
            label="To shape", data_types=[nd.Types.String, nd.Types.Binary], required=True
        ),
    )

    output: nd.Section = nd.Section(
        title="Result",
        output_column=nd.TextInput(label="New column", default="distance"),
        unit=nd.SingleSelect(
            label="Unit",
            options=[("kilometers", "Kilometres"), ("meters", "Metres"), ("miles", "Miles")],
            default="kilometers",
        ),
    )


class Distance(nd.CustomNodeBase):
    node_name: str = "Distance"
    node_category: str = "Geospatial"
    node_icon: str = "geo_distance_between.png"
    title: str = "Measure the distance between two places"
    intro: str = (
        "Adds the real ground distance between two places on each row, in kilometres, metres or miles. "
        "Works straight off latitude and longitude columns, with no setup."
    )
    author: str = "edwardvaneechoud"
    version: str = "0.3.0"
    tags: list[str] = ["geospatial", "distance", "latitude", "longitude", "measure"]
    example_inputs: list[dict[str, list]] = [
        {
            "route": ["Amsterdam-Rotterdam", "Oslo-Bergen", "Tromso east"],
            "from_lat": [52.3676, 59.9139, 69.6496],
            "from_lon": [4.9041, 10.7522, 18.9560],
            "to_lat": [51.9244, 60.3913, 69.6496],
            "to_lon": [4.4777, 5.3221, 19.9560],
        },
    ]
    example_settings: dict[str, dict] = {
        "mode": {"use_shapes": False},
        "points": {
            "from_latitude": "from_lat",
            "from_longitude": "from_lon",
            "to_latitude": "to_lat",
            "to_longitude": "to_lon",
        },
        "shapes": {"from_geometry": "", "to_geometry": ""},
        "output": {"output_column": "distance", "unit": "kilometers"},
    }
    settings_schema: DistanceSettings = DistanceSettings()

    def _output(self) -> tuple[str, float]:
        cfg = self.settings_schema.output
        column = (cfg.output_column.value or "distance").strip() or "distance"
        unit = cfg.unit.value or "kilometers"
        if unit not in UNIT_IN_METRES:
            raise ValueError(f"'Unit' is '{unit}', which is not one of: kilometres, metres, miles.")
        return column, UNIT_IN_METRES[unit]

    def _distance(
        self, from_lat: pl.Expr, from_lon: pl.Expr, to_lat: pl.Expr, to_lon: pl.Expr, metres: float
    ) -> pl.Expr:
        """Lambert's formula: distance across the WGS84 ellipsoid, within a few metres.

        A plain great-circle (haversine) distance treats the earth as a sphere and runs 0.1-0.4%
        short at these latitudes; the flattening correction below removes that, to roughly 1 part
        in a million. Accuracy degrades for near-antipodal pairs, where the formula is weakest.
        """
        flattening = WGS84_FLATTENING
        reduced_from = ((1 - flattening) * from_lat.radians().tan()).arctan()
        reduced_to = ((1 - flattening) * to_lat.radians().tan()).arctan()
        half_lat = ((reduced_to - reduced_from) / 2).sin()
        half_lon = ((to_lon - from_lon).radians() / 2).sin()
        chord = half_lat.pow(2) + reduced_from.cos() * reduced_to.cos() * half_lon.pow(2)
        central = 2 * chord.sqrt().arcsin()

        mean, difference = (reduced_from + reduced_to) / 2, (reduced_to - reduced_from) / 2
        x = (central - central.sin()) * mean.sin().pow(2) * difference.cos().pow(2) / (central / 2).cos().pow(2)
        y = (central + central.sin()) * mean.cos().pow(2) * difference.sin().pow(2) / (central / 2).sin().pow(2)
        distance = WGS84_RADIUS_M * (central - (flattening / 2) * (x + y))
        return pl.when(central == 0).then(0.0).otherwise(distance) / metres

    def _latitude_guard(self, label: str, name: str):
        """A pass-through that raises on an impossible latitude, evaluated inside the lazy plan.

        |latitude| > 90 almost always means latitude and longitude are the wrong way round. Values
        that are not finite are left alone; they simply produce no distance.
        """

        def check(values: pl.Series) -> pl.Series:
            finite = values.filter(values.is_finite())
            bad = finite.filter(finite.abs() > 90)
            if len(bad):
                raise ValueError(
                    f"'{label}' column '{name}' contains {bad[0]:g}, which is not a valid latitude (it "
                    "must be between -90 and 90). Latitude and longitude may be swapped."
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

    def _centres(self, df: pl.DataFrame, names: list[str], con) -> pl.DataFrame:
        """Centre latitude/longitude of each shape column."""
        try:
            con.register(
                "_shapes",
                df.select([pl.col(name).alias(f"g{index}") for index, name in enumerate(names)]).with_row_index("_i"),
            )
            parts = []
            for index in range(len(names)):
                centre = f"ST_Centroid(ST_GeomFromText(g{index}))"
                parts.append(f"ST_Y({centre}) AS lat{index}, ST_X({centre}) AS lon{index}")
            return con.execute(f"SELECT {', '.join(parts)} FROM _shapes ORDER BY _i").pl()
        except Exception as exc:
            raise RuntimeError(f"Could not read the shape columns: {exc}") from exc

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        column, metres = self._output()
        lf = inputs[0]
        schema = dict(lf.collect_schema())
        if column in schema:
            raise ValueError(f"The data already has a column named '{column}'. Pick another 'New column'.")

        if self.settings_schema.mode.use_shapes.value:
            cfg = self.settings_schema.shapes
            labels = ("From shape", "To shape")
            names = [(cfg.from_geometry.value or "").strip(), (cfg.to_geometry.value or "").strip()]
            for label, name in zip(labels, names, strict=True):
                self._check_shape_column(schema, name, label)
            for name in names:
                schema[name] = pl.Utf8
            schema[column] = pl.Float64
            distance = self._distance(pl.col("lat0"), pl.col("lon0"), pl.col("lat1"), pl.col("lon1"), metres)

            def work(chunk: pl.DataFrame, con) -> pl.DataFrame:
                prepared = chunk
                for name in names:
                    prepared = self._geometry(prepared, name, con)
                centres = self._centres(prepared, names, con)
                return prepared.with_columns(centres.select(distance.alias(column)).to_series())

            return self._stream(lf, schema, work)

        cfg = self.settings_schema.points
        labels = ("From latitude", "From longitude", "To latitude", "To longitude")
        names = [
            (cfg.from_latitude.value or "").strip(),
            (cfg.from_longitude.value or "").strip(),
            (cfg.to_latitude.value or "").strip(),
            (cfg.to_longitude.value or "").strip(),
        ]
        for label, name in zip(labels, names, strict=True):
            if not name:
                raise ValueError(f"'{label}' is not set. Pick the column holding that coordinate.")
            if name not in schema:
                raise ValueError(f"'{label}' column '{name}' is not in the data. Columns: {', '.join(schema)}")

        def coordinate(label: str, name: str) -> pl.Expr:
            value = pl.col(name).cast(pl.Float64, strict=False)
            if "latitude" not in label:
                return value
            return value.map_batches(self._latitude_guard(label, name), return_dtype=pl.Float64, is_elementwise=True)

        ordinates = [coordinate(label, name) for label, name in zip(labels, names, strict=True)]
        return lf.with_columns(self._distance(*ordinates, metres).alias(column))

    def predict_output_schema(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        column, _ = self._output()
        columns = []
        if self.settings_schema.mode.use_shapes.value:
            cfg = self.settings_schema.shapes
            names = inputs[0].collect_schema().names()
            for value in (cfg.from_geometry.value, cfg.to_geometry.value):
                name = (value or "").strip()
                if name in names:
                    columns.append(pl.col(name).cast(pl.Utf8))
        columns.append(pl.lit(None, dtype=pl.Float64).alias(column))
        return inputs[0].with_columns(columns)
