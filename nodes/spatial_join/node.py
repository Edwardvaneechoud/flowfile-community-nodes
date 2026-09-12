import polars as pl
from flowfile import node_designer as nd
import threading


METRES_PER_UNIT = {"meters": 1.0, "kilometers": 1000.0, "miles": 1609.344}


PREDICATES = {
    "inside": "ST_Within(lhs.g, rhs.g)",
    "contains": "ST_Contains(lhs.g, rhs.g)",
    "overlaps": "ST_Intersects(lhs.g, rhs.g)",
}


class SpatialJoinSettings(nd.NodeSettings):
    match: nd.Section = nd.Section(
        title="Match",
        description="Every row of the first input is matched against the second by where it sits on the map. Matched rows come out of the top output with the second input's columns attached; rows that matched nothing come out of the bottom output unchanged. The second input's shape column has to be typed in, because the picker can only read the first input.",
        left_geometry=nd.ColumnSelector(
            label="Shape column",
            required=True,
            data_types=[
                "Binary",
                "String",
            ],
        ),
        right_geometry=nd.TextInput(
            label="Second shape column",
            default="geometry",
        ),
        method=nd.SingleSelect(
            label="Rule",
            options=[
                ("inside", "Falls inside the second shape"),
                ("contains", "Surrounds the second shape"),
                ("overlaps", "Touches or overlaps the second shape"),
            ],
            default="inside",
        ),
        use_distance=nd.ToggleSwitch(
            label="Match within a distance",
            description="Ignores the rule above and matches anything within a set distance instead.",
        ),
    )

    nearby: nd.Section = nd.Section(
        title="Distance",
        description="How far apart two shapes may be and still count as a match. Measured between their nearest edges on the ground, so any mix of points, lines and areas works.",
        visible_when=nd.VisibleWhen(
            field="match.use_distance",
        ),
        distance=nd.NumericInput(
            label="Distance",
            default=1000.0,
            min_value=0.0,
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
    )


class SpatialJoin(nd.CustomNodeBase):
    node_name: str = "Spatial Join"
    node_category: str = "Geospatial"
    node_icon: str = "geo_spatial_join.png"
    title: str = "Join two tables by where they are"
    intro: str = "Tags each row with the area it falls inside - every customer with its district, every incident with its region. Matched and unmatched rows come out of separate outputs."
    author: str = "edwardvaneechoud"
    version: str = "0.3.0"
    tags: list[str] = [
        "geospatial",
        "join",
        "point in polygon",
        "match",
        "duckdb",
    ]
    number_of_inputs: int = 2
    number_of_outputs: int = 2
    output_names: list[str] = [
        "matched",
        "unmatched",
    ]
    input_labels: list[str] = [
        "Rows to tag",
        "Areas",
    ]
    example_inputs: list[dict[str, list]] = [
        {
            "customer": [
                "Ada",
                "Bo",
                "Cy",
            ],
            "geometry": [
                "POINT (4.91 52.37)",
                "POINT (4.88 52.33)",
                "POINT (9.00 52.00)",
            ],
        },
        {
            "district": [
                "Centrum",
                "Zuid",
            ],
            "geometry": [
                "POLYGON ((4.90 52.36, 4.93 52.36, 4.93 52.39, 4.90 52.39, 4.90 52.36))",
                "POLYGON ((4.86 52.31, 4.90 52.31, 4.90 52.35, 4.86 52.35, 4.86 52.31))",
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "match": {
            "left_geometry": "geometry",
            "right_geometry": "geometry",
            "method": "inside",
            "use_distance": False,
        },
        "nearby": {
            "distance": 1000,
            "unit": "meters",
        },
    }
    settings_schema: SpatialJoinSettings = SpatialJoinSettings()

    def process(self, *inputs: pl.LazyFrame) -> dict[str, pl.LazyFrame]:
        if len(inputs) < 2:
            raise ValueError(
                "Spatial Join needs both inputs connected: the rows to tag, and the areas to tag "
                "them with."
            )
        left_name, right_name = self._names()
        left_lf, right_lf = inputs[0], inputs[1]
        left_schema = dict(left_lf.collect_schema())
        right_schema = dict(right_lf.collect_schema())
        self._check_shape_column(left_schema, left_name, "Shape column")
        self._check_shape_column(right_schema, right_name, "Second shape column")
        predicate, metres = self._predicate()

        # Suffix any right-hand column that would collide, the way an ordinary join does.
        renames = {column: f"{column}_right" for column in set(left_schema) & set(right_schema)}
        taken = set(left_schema) | set(right_schema) | set(renames.values())
        left_key = self._free_name(taken, "_ff_left")
        right_key = self._free_name(taken | {left_key}, "_ff_right")
        hit = self._free_name(taken | {left_key, right_key}, "_ff_hit")

        schema = {**left_schema, left_name: pl.Utf8}
        for column, dtype in right_schema.items():
            schema[renames.get(column, column)] = pl.Utf8 if column == right_name else dtype
        schema[hit] = pl.Boolean

        left_geom = "ST_GeomFromText(g)"
        lhs = f'"{left_key}", {left_geom} AS g, {self._local_crs_sql(left_geom)} AS zone'
        if metres is not None:
            lhs += f", {self._envelope_sql(left_geom, metres)} AS env"
        sql = (
            f'SELECT lhs."{left_key}" AS "{left_key}", rhs."{right_key}" AS "{right_key}" FROM '
            f"(SELECT {lhs} FROM _left) lhs "
            f'JOIN (SELECT "{right_key}", ST_GeomFromText(g) AS g FROM _right) rhs ON {predicate} '
            f'ORDER BY lhs."{left_key}", rhs."{right_key}"'
        )

        # The second input is needed whole. It is read here, once, and registered on the first chunk.
        right = right_lf.collect()
        ready: dict = {}

        def work(chunk: pl.DataFrame, con) -> pl.DataFrame:
            if "right" not in ready:
                prepared = self._geometry(right, right_name, con)
                con.register("_right", prepared.select(pl.col(right_name).alias("g")).with_row_index(right_key))
                ready["right"] = prepared.rename(renames).with_row_index(right_key)
            left = self._geometry(chunk, left_name, con)
            con.register("_left", left.select(pl.col(left_name).alias("g")).with_row_index(left_key))
            try:
                pairs = con.execute(sql).pl()
            except Exception as exc:
                raise RuntimeError(f"Could not match the shapes: {exc}") from exc
            return (
                left.with_row_index(left_key)
                .join(pairs, on=left_key, how="left", maintain_order="left")
                .join(ready["right"], on=right_key, how="left", maintain_order="left")
                .with_columns(pl.col(right_key).is_not_null().alias(hit))
                .drop(left_key, right_key)
            )

        tagged = self._stream(left_lf, schema, work)
        return {
            "matched": tagged.filter(pl.col(hit)).drop(hit),
            "unmatched": tagged.filter(~pl.col(hit)).select(list(left_schema)),
        }

    def predict_output_schema(self, *inputs: pl.LazyFrame) -> dict[str, pl.LazyFrame] | None:
        if len(inputs) < 2:
            return None
        left_name, right_name = self._names()
        left_names = inputs[0].collect_schema().names()
        right_names = inputs[1].collect_schema().names()
        left = inputs[0]
        if left_name in left_names:
            left = left.with_columns(pl.col(left_name).cast(pl.Utf8))
        right = inputs[1]
        if right_name in right_names:
            right = right.with_columns(pl.col(right_name).cast(pl.Utf8))
        collisions = set(left_names) & set(right_names)
        matched = left.join(right.rename({column: f"{column}_right" for column in collisions}), how="cross")
        return {"matched": matched, "unmatched": left}

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
        """A metre-based system for a feature: its UTM zone, or azimuthal equidistant near the poles."""
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

    def _envelope_sql(self, geom: str, metres: float) -> str:
        """The shape's box in degrees, grown by the distance, so the spatial index finds every candidate.

        A degree of latitude is 110,574 m and a degree of longitude shrinks with cos(latitude). The
        5% margin covers the gap between that spherical estimate and the exact metric check that
        follows; near the poles cos is clamped, so the box simply grows.
        """
        latitude = f"ST_Y(ST_Centroid({geom}))"
        dy = f"{metres * 1.05} / 110574.0"
        dx = f"{metres * 1.05} / (111320.0 * greatest(cos(radians({latitude})), 0.01))"
        return (
            f"ST_MakeEnvelope(ST_XMin({geom}) - {dx}, ST_YMin({geom}) - {dy}, "
            f"ST_XMax({geom}) + {dx}, ST_YMax({geom}) + {dy})"
        )

    def _free_name(self, taken: set, wanted: str) -> str:
        """A helper column name that cannot collide with the user's own columns."""
        name = wanted
        while name in taken:
            name += "_"
        return name

    def _predicate(self) -> tuple[str, float | None]:
        """The DuckDB match condition over aliases `lhs` and `rhs`, and the distance if one applies."""
        cfg = self.settings_schema.match
        if cfg.use_distance.value:
            nearby = self.settings_schema.nearby
            if nearby.distance.value is None:
                raise ValueError("'Distance' is not set. Give the distance that still counts as a match.")
            unit = nearby.unit.value or "meters"
            if unit not in METRES_PER_UNIT:
                raise ValueError(f"'Unit' is '{unit}', which is not one of: metres, kilometres, miles.")
            metres = float(nearby.distance.value) * METRES_PER_UNIT[unit]
            # ST_DWithin_Spheroid only accepts POINTs, so measure in the left row's own metre-based
            # system instead. That per-pair projection cannot use the spatial index, so a cheap box
            # test in degrees goes first and only candidates pay for the exact check.
            return (
                "ST_Intersects(lhs.env, rhs.g) AND ST_DWithin("
                "ST_Transform(lhs.g, 'EPSG:4326', lhs.zone, true), "
                "ST_Transform(rhs.g, 'EPSG:4326', lhs.zone, true), "
                f"{metres})"
            ), metres
        method = cfg.method.value or "inside"
        if method not in PREDICATES:
            raise ValueError(f"'Rule' is '{method}', which is not one of: {', '.join(PREDICATES)}.")
        return PREDICATES[method], None

    def _names(self) -> tuple[str, str]:
        cfg = self.settings_schema.match
        return (cfg.left_geometry.value or "").strip(), (cfg.right_geometry.value or "geometry").strip()
