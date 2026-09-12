import polars as pl

from flowfile import node_designer as nd

# Shared Geospatial contract: shapes travel as WKT text in a plain string column, always in
# longitude/latitude degrees (EPSG:4326). Every node reads WKT, hex WKB or binary WKB, writes WKT.
FORMATS_BY_EXTENSION = {
    ".shp": "shapefile",
    ".geojson": "geojson",
    ".json": "geojson",
    ".parquet": "geoparquet",
    ".geoparquet": "geoparquet",
    ".fgb": "flatgeobuf",
    ".gpkg": "gpkg",
    ".kml": "kml",
    ".kmz": "kml",
}


class SpatialReadSettings(nd.NodeSettings):
    source: nd.Section = nd.Section(
        title="File",
        description=(
            "Every row of the result is one shape with its attributes, like a normal table. Coordinates "
            "are converted to plain latitude/longitude, so the other map nodes measure correctly."
        ),
        path=nd.TextInput(label="File path", default="", placeholder="/data/districts.shp"),
        file_format=nd.SingleSelect(
            label="File type",
            options=[
                ("auto", "Detect from the file name"),
                ("shapefile", "Shapefile (.shp)"),
                ("geojson", "GeoJSON (.geojson / .json)"),
                ("geoparquet", "GeoParquet (.parquet)"),
                ("flatgeobuf", "FlatGeobuf (.fgb)"),
                ("gpkg", "GeoPackage (.gpkg)"),
                ("kml", "KML (.kml / .kmz)"),
            ],
            default="auto",
        ),
        geometry_column=nd.TextInput(label="Shape column", default="geometry"),
        row_limit=nd.NumericInput(label="First N rows only (0 = all)", default=0.0, min_value=0.0),
        advanced=nd.ToggleSwitch(
            label="More options",
            default=False,
            description="A layer name for multi-layer files, and the system to assume when the file "
            "does not record one.",
        ),
    )

    options: nd.Section = nd.Section(
        title="More options",
        description=(
            "Most files record their own coordinate system and need nothing here. 'Coordinates in the "
            "file are' is only consulted when the file records none - it never overrides one that is set."
        ),
        visible_when=nd.VisibleWhen(field="source.advanced"),
        layer=nd.TextInput(label="Layer name", default="", placeholder="districts"),
        assume_crs=nd.TextInput(
            label="Coordinates in the file are", default="", placeholder="EPSG:28992"
        ),
    )


class SpatialRead(nd.CustomNodeBase):
    node_name: str = "Spatial Read"
    node_category: str = "Geospatial"
    node_icon: str = "geo_spatial_read.png"
    node_type: str = "input"
    title: str = "Read shapes from a map file"
    intro: str = (
        "Loads a Shapefile, GeoJSON, GeoParquet, FlatGeobuf, GeoPackage or KML as a table, one row per "
        "shape. Reads from this machine, and needs internet once to fetch the map extension."
    )
    author: str = "edwardvaneechoud"
    version: str = "0.2.0"
    tags: list[str] = ["geospatial", "reader", "shapefile", "geojson", "duckdb"]
    number_of_inputs: int = 0
    number_of_outputs: int = 1
    example_inputs: list[dict[str, list]] = []
    example_settings: dict[str, dict] = {
        "source": {
            "path": "",
            "file_format": "auto",
            "geometry_column": "geometry",
            "row_limit": 0,
            "advanced": False,
        },
        "options": {"layer": "", "assume_crs": ""},
    }
    settings_schema: SpatialReadSettings = SpatialReadSettings()

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

    def _quote(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _detect_format(self, path: str, requested: str) -> str:
        if requested and requested != "auto":
            return requested
        lowered = path.lower()
        for extension, name in FORMATS_BY_EXTENSION.items():
            if lowered.endswith(extension):
                return name
        raise ValueError(
            f"Could not tell the file type of '{path}' from its name. Pick it under 'File type': "
            "Shapefile, GeoJSON, GeoParquet, FlatGeobuf, GeoPackage or KML."
        )

    def _source_crs(self, con, path: str, fmt: str, layer: str, geometry_type: str) -> str | None:
        """The file's own coordinate system: from the typed geometry column, else layer metadata."""
        import re

        match = re.match(r"GEOMETRY\('(.+)'\)$", geometry_type)
        if match:
            return match.group(1)
        if fmt == "geoparquet":
            # ST_Read_Meta segfaults the process on a .parquet path in DuckDB 1.5.5 - an
            # uncatchable crash, not an exception. A typed GEOMETRY column is handled above;
            # anything else falls through to the 'Coordinates in the file are' setting.
            return None
        try:
            rows = con.execute("SELECT layers FROM ST_Read_Meta(?)", [path]).fetchall()
        except Exception:
            return None
        if not rows:
            return None
        layers = rows[0][0] or []
        chosen = None
        for candidate in layers:
            if not layer or candidate.get("name") == layer:
                chosen = candidate
                break
        if not chosen:
            return None
        for field in chosen.get("geometry_fields") or []:
            crs = field.get("crs") or {}
            if crs.get("auth_name") and crs.get("auth_code"):
                return f"{crs['auth_name']}:{crs['auth_code']}"
        return None

    def _dry_run_sample(self) -> str:
        """A three-district GeoJSON to read when a dry run has no path, so the real read path still runs.

        Only the dry-run harness binds `flowfile_ctx`; a real run never does, so a blank path there
        stays an error rather than quietly reading sample data. DuckDB writes the file itself.
        """
        try:
            ctx = flowfile_ctx  # noqa: F821
        except NameError:
            return ""
        if not ctx.is_dry_run():
            return ""
        path = ctx.get_shared_location("spatial_read_sample.geojson")
        districts = [
            ("West", "POLYGON ((4.80 52.33, 4.88 52.37, 4.87 52.43, 4.80 52.43, 4.80 52.33))"),
            ("Centrum", "POLYGON ((4.88 52.37, 4.92 52.38, 4.90 52.35, 4.88 52.34, 4.88 52.37))"),
            ("Zuid", "POLYGON ((4.80 52.33, 4.88 52.34, 4.90 52.35, 4.86 52.31, 4.80 52.31, 4.80 52.33))"),
        ]
        rows = ", ".join(f"('{name}', ST_GeomFromText('{wkt}'))" for name, wkt in districts)
        con = self._connect()
        try:
            con.execute(
                f"COPY (SELECT * FROM (VALUES {rows}) AS t(district, geom)) "
                f"TO '{path.replace(chr(39), chr(39) * 2)}' WITH (FORMAT GDAL, DRIVER 'GeoJSON')"
            )
        finally:
            con.close()
        return path

    def _settings(self) -> tuple[str, str, str, int, str]:
        import os

        cfg = self.settings_schema.source
        path = os.path.expanduser((cfg.path.value or "").strip()) or self._dry_run_sample()
        if not path:
            raise ValueError("'File path' is not set. Give the path to the map file.")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No file found at '{path}'. Check 'File path' in the settings.")
        geometry_column = (cfg.geometry_column.value or "geometry").strip() or "geometry"
        row_limit = int(cfg.row_limit.value or 0)
        layer, assume = "", ""
        if cfg.advanced.value:
            layer = (self.settings_schema.options.layer.value or "").strip()
            assume = (self.settings_schema.options.assume_crs.value or "").strip()
        return path, geometry_column, layer, row_limit, assume

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        path, geometry_column, layer, row_limit, assume = self._settings()
        fmt = self._detect_format(path, self.settings_schema.source.file_format.value)

        con = self._connect()
        try:
            if fmt == "geoparquet":
                base_sql, base_params = "read_parquet(?)", [path]
            elif layer:
                base_sql, base_params = "ST_Read(?, layer=?)", [path, layer]
            else:
                base_sql, base_params = "ST_Read(?)", [path]

            try:
                described = con.execute(f"DESCRIBE SELECT * FROM {base_sql}", base_params).fetchall()
            except Exception as exc:
                raise RuntimeError(f"Could not open '{path}' as a {fmt} file: {exc}") from exc

            columns = [(row[0], row[1]) for row in described]
            typed = [name for name, kind in columns if kind.upper().startswith("GEOMETRY")]
            blobs = [
                name
                for name, kind in columns
                if kind.upper() == "BLOB" and name.lower() in ("geometry", "geom", "wkb")
            ]
            if typed:
                source_geometry = geometry_column if geometry_column in typed else typed[0]
                source_type = dict(columns)[source_geometry]
                already_wkb = False
            elif blobs:
                source_geometry, source_type, already_wkb = blobs[0], "BLOB", True
            else:
                raise ValueError(
                    f"'{path}' contains no shapes (no geometry column). Columns found: "
                    + ", ".join(f"{name} ({kind})" for name, kind in columns)
                )

            source_crs = self._source_crs(con, path, fmt, layer, source_type) or assume
            if not source_crs:
                raise ValueError(
                    f"'{path}' does not record which coordinate system it uses. Turn on 'More options' "
                    "and set 'Coordinates in the file are' to the system they are in - usually "
                    "EPSG:4326 for latitude/longitude."
                )

            for name, _ in columns:
                if name == geometry_column and name != source_geometry:
                    raise ValueError(
                        f"The file already has a column named '{geometry_column}'; pick another name "
                        "for 'Shape column'."
                    )

            geom_ref = self._quote(source_geometry)
            geom = f"ST_GeomFromWKB({geom_ref})" if already_wkb else geom_ref
            select_parts: list[str] = []
            params: list = []
            for name, _ in columns:
                if name != source_geometry:
                    select_parts.append(self._quote(name))
                    continue
                if source_crs == "EPSG:4326":
                    expression = f"ST_AsText({geom})"
                else:
                    expression = f"ST_AsText(ST_Transform({geom}, ?, 'EPSG:4326', true))"
                    params.append(source_crs)
                select_parts.append(f"{expression} AS {self._quote(geometry_column)}")

            # Positional parameters bind in textual order: select list, then FROM, then LIMIT.
            sql = f"SELECT {', '.join(select_parts)} FROM {base_sql}"
            params.extend(base_params)
            if row_limit > 0:
                sql += " LIMIT ?"
                params.append(row_limit)
            try:
                df = con.execute(sql, params).pl()
            except Exception as exc:
                raise RuntimeError(f"Could not read '{path}' ({fmt}): {exc}") from exc
        finally:
            con.close()

        return df.lazy()
