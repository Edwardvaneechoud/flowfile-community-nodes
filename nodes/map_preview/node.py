import polars as pl

from flowfile import node_designer as nd


class MapPreviewSettings(nd.NodeSettings):
    map: nd.Section = nd.Section(
        title="Map",
        description=(
            "Draws the shapes on a map you can open from this node's Artifacts tab after a run. "
            "The data itself passes through unchanged."
        ),
        geometry_column=nd.ColumnSelector(
            label="Shape column", data_types=[nd.Types.String, nd.Types.Binary], required=True
        ),
        label_columns=nd.ColumnSelector(label="Show on hover", multiple=True),
        label_column=nd.ColumnSelector(label="Write next to shape"),
        color_by_column=nd.ColumnSelector(label="Colour by"),
        max_features=nd.NumericInput(label="Draw at most", default=2000.0, min_value=1.0),
    )

    style: nd.Section = nd.Section(
        title="Style",
        description=(
            "A street background downloads images from another organisation's server. "
            "OpenStreetMap's free tiles are for light use only; for anything heavier, point the map "
            "at your own tile server. Simplify is in degrees, so 0.001 is roughly 100 m of detail; "
            "leave it at 0 to keep every outline."
        ),
        basemap=nd.SingleSelect(
            label="Background",
            options=[("none", "Plain"), ("osm", "OpenStreetMap streets")],
            default="none",
        ),
        fill_color=nd.TextInput(label="Shape colour", default="#3D9BF2"),
        stroke_color=nd.TextInput(label="Outline colour", default="#1B4F9C"),
        simplify_tolerance=nd.NumericInput(
            label="Simplify (degrees)", default=0.0, min_value=0.0, max_value=1.0
        ),
        own_tiles=nd.ToggleSwitch(
            label="Use my own tile server",
            default=False,
            description="Replaces the background above with a tile server you host or pay for.",
        ),
    )

    tiles: nd.Section = nd.Section(
        title="Tile server",
        description="The address of your tile server, with {z}, {x} and {y} standing in for the tile.",
        visible_when=nd.VisibleWhen(field="style.own_tiles"),
        tile_url_template=nd.TextInput(
            label="Address", default="", placeholder="https://tiles.example.com/{z}/{x}/{y}.png"
        ),
    )

    artifact: nd.Section = nd.Section(
        title="Saved map",
        artifact_name=nd.TextInput(label="Name", default="map_preview"),
    )


class MapPreview(nd.CustomNodeBase):
    node_name: str = "Map Preview"
    node_category: str = "Geospatial"
    node_icon: str = "geo_map_preview.png"
    title: str = "Show the shapes on a map"
    intro: str = (
        "Draws the shapes on a map you can open from this node's Artifacts tab after a run. "
        "The data passes through unchanged, so you can drop it anywhere in a flow."
    )
    author: str = "edwardvaneechoud"
    version: str = "0.1.0"
    tags: list[str] = ["geospatial", "map", "visualization", "artifact-preview"]
    environment: str = "kernel"
    dependencies: list[str] = []
    number_of_inputs: int = 1
    number_of_outputs: int = 1
    example_inputs: list[dict[str, list]] = [
        {
            "name": ["Centrum", "Zuid", "Station", "Canal"],
            "kind": ["district", "district", "stop", "water"],
            "geometry": [
                "POLYGON ((4.88 52.36, 4.92 52.36, 4.92 52.39, 4.88 52.39, 4.88 52.36))",
                "POLYGON ((4.86 52.32, 4.90 52.32, 4.90 52.35, 4.86 52.35, 4.86 52.32))",
                "POINT (4.9001 52.3789)",
                "LINESTRING (4.8850 52.3650, 4.8950 52.3700, 4.9050 52.3760)",
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "map": {
            "geometry_column": "geometry",
            "label_columns": ["name", "kind"],
            "label_column": "name",
            "color_by_column": "kind",
            "max_features": 2000,
        },
        "style": {
            "basemap": "none",
            "fill_color": "#3D9BF2",
            "stroke_color": "#1B4F9C",
            "simplify_tolerance": 0,
            "own_tiles": False,
        },
        "tiles": {"tile_url_template": ""},
        "artifact": {"artifact_name": "map_preview"},
    }
    settings_schema: MapPreviewSettings = MapPreviewSettings()

    def _decode_wkb(self, data: bytes) -> dict | None:
        """Decode WKB/EWKB into {'type': ..., 'coords': ...} using the stdlib only.

        Points -> (x, y); lines -> [(x, y), ...]; polygons -> [ring, ...];
        multi-geometries -> a list of the member dicts. Z/M ordinates are dropped.
        Returns None for unsupported or malformed input.
        """
        import struct

        pos = 0

        def read_geometry() -> dict | None:
            nonlocal pos
            if pos + 5 > len(data):
                return None
            little = data[pos] == 1
            prefix = "<" if little else ">"
            (type_code,) = struct.unpack_from(prefix + "I", data, pos + 1)
            pos += 5
            has_z = bool(type_code & 0x80000000)
            has_m = bool(type_code & 0x40000000)
            has_srid = bool(type_code & 0x20000000)
            base = type_code & 0x0FFFFFFF
            if base >= 1000:
                dims_flag, base = divmod(base, 1000)
                has_z = has_z or dims_flag in (1, 3)
                has_m = has_m or dims_flag in (2, 3)
            if has_srid:
                pos += 4
            ndim = 2 + int(has_z) + int(has_m)
            fmt = prefix + "d" * ndim
            size = 8 * ndim

            def read_point() -> tuple:
                nonlocal pos
                values = struct.unpack_from(fmt, data, pos)
                pos += size
                return (values[0], values[1])

            def read_ring() -> list:
                nonlocal pos
                (count,) = struct.unpack_from(prefix + "I", data, pos)
                pos += 4
                return [read_point() for _ in range(count)]

            if base == 1:
                return {"type": "Point", "coords": read_point()}
            if base == 2:
                return {"type": "LineString", "coords": read_ring()}
            if base == 3:
                (rings,) = struct.unpack_from(prefix + "I", data, pos)
                pos += 4
                return {"type": "Polygon", "coords": [read_ring() for _ in range(rings)]}
            if base in (4, 5, 6, 7):
                (count,) = struct.unpack_from(prefix + "I", data, pos)
                pos += 4
                members = []
                for _ in range(count):
                    member = read_geometry()
                    if member is None:
                        return None
                    members.append(member)
                name = {4: "MultiPoint", 5: "MultiLineString", 6: "MultiPolygon", 7: "GeometryCollection"}[base]
                return {"type": name, "coords": members}
            return None

        try:
            return read_geometry()
        except (struct.error, IndexError, KeyError):
            return None

    def _decode_wkt(self, text: str) -> dict | None:
        """Parse 2D WKT into the same shape as _decode_wkb. Z/M are dropped; EMPTY returns None."""
        import re

        tokens = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?|[A-Za-z]+|[(),]", text or "")
        position = 0

        def peek():
            return tokens[position] if position < len(tokens) else None

        def take():
            nonlocal position
            token = tokens[position]
            position += 1
            return token

        def parse_point():
            if peek() == "(":
                take()
                point = parse_point()
                take()
                return point
            numbers = []
            while peek() not in (",", ")", None):
                numbers.append(float(take()))
            return (numbers[0], numbers[1])

        def parse_list(depth):
            take()
            items = []
            while True:
                items.append(parse_point() if depth == 0 else parse_list(depth - 1))
                if take() == ")":
                    return items

        def parse_geometry():
            name = take().upper()
            while peek() and peek().upper() in ("Z", "M", "ZM"):
                take()
            if peek() and peek().upper() == "EMPTY":
                take()
                return None
            if name == "POINT":
                take()
                point = parse_point()
                take()
                return {"type": "Point", "coords": point}
            if name == "LINESTRING":
                return {"type": "LineString", "coords": parse_list(0)}
            if name == "POLYGON":
                return {"type": "Polygon", "coords": parse_list(1)}
            if name == "MULTIPOINT":
                return {
                    "type": "MultiPoint",
                    "coords": [{"type": "Point", "coords": c} for c in parse_list(0)],
                }
            if name == "MULTILINESTRING":
                return {
                    "type": "MultiLineString",
                    "coords": [{"type": "LineString", "coords": c} for c in parse_list(1)],
                }
            if name == "MULTIPOLYGON":
                return {
                    "type": "MultiPolygon",
                    "coords": [{"type": "Polygon", "coords": c} for c in parse_list(2)],
                }
            if name == "GEOMETRYCOLLECTION":
                take()
                members = []
                while True:
                    member = parse_geometry()
                    if member is not None:
                        members.append(member)
                    if take() == ")":
                        return {"type": "GeometryCollection", "coords": members}
            return None

        try:
            return parse_geometry()
        except (IndexError, ValueError):
            return None

    def _flatten(self, geom: dict) -> list:
        """Break a geometry into drawable primitives: ('point', (x,y)) / ('line', [...]) / ('polygon', [rings])."""
        kind = geom["type"]
        if kind == "Point":
            return [("point", geom["coords"])]
        if kind == "LineString":
            return [("line", geom["coords"])]
        if kind == "Polygon":
            return [("polygon", geom["coords"])]
        out = []
        for member in geom["coords"]:
            out.extend(self._flatten(member))
        return out

    def _simplify(self, points: list, tolerance: float) -> list:
        """Douglas-Peucker; keeps at least the end points."""
        if tolerance <= 0 or len(points) < 3:
            return points

        def perpendicular(p, a, b) -> float:
            (x, y), (x1, y1), (x2, y2) = p, a, b
            dx, dy = x2 - x1, y2 - y1
            if dx == 0 and dy == 0:
                return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
            px, py = x1 + t * dx, y1 + t * dy
            return ((x - px) ** 2 + (y - py) ** 2) ** 0.5

        keep = [False] * len(points)
        keep[0] = keep[-1] = True
        stack = [(0, len(points) - 1)]
        while stack:
            start, end = stack.pop()
            best, index = 0.0, -1
            for i in range(start + 1, end):
                d = perpendicular(points[i], points[start], points[end])
                if d > best:
                    best, index = d, i
            if index >= 0 and best > tolerance:
                keep[index] = True
                stack.append((start, index))
                stack.append((index, end))
        return [p for p, k in zip(points, keep, strict=True) if k]

    def _to_mercator(self, x: float, y: float) -> tuple:
        import math

        radius = 6378137.0
        lat = max(-85.05112878, min(85.05112878, y))
        lon = max(-180.0, min(180.0, x))
        return (
            radius * math.radians(lon),
            radius * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)),
        )

    def _html_page(self, title: str, body: str) -> str:
        import html

        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'><title>" + html.escape(title) + "</title><style>"
            "body{margin:0;padding:12px;font:13px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',"
            "Helvetica,Arial,sans-serif;"
            "color:#1f2937;background:#fff}"
            ".meta{margin:0 0 8px;color:#4b5563}"
            ".map{position:relative;overflow:hidden;border:1px solid #d1d5db;border-radius:6px;background:#f3f4f6}"
            ".map img{position:absolute;width:256px;height:256px;user-select:none;pointer-events:none}"
            ".map svg{position:absolute;left:0;top:0}"
            ".legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin:8px 0 0}"
            ".legend span{display:inline-flex;align-items:center;gap:6px}"
            ".swatch{display:inline-block;width:12px;height:12px;border-radius:2px;border:1px solid rgba(0,0,0,.35)}"
            ".note{margin:8px 0 0;color:#6b7280;font-size:12px}"
            ".lbl{font-size:11px;fill:#111;paint-order:stroke;stroke:#fff;stroke-width:3px;"
            "stroke-linejoin:round;pointer-events:none}"
            ".tip{display:none;pointer-events:none}.tip rect{fill:#fff;fill-opacity:.96;stroke:#9ca3af}"
            ".tip text{font-size:11px;fill:#111}.tip tspan.k{fill:#6b7280}"
            ".empty{padding:32px;border:1px dashed #9ca3af;border-radius:6px;color:#374151;background:#f9fafb}"
            "</style></head><body>" + body + "</body></html>"
        )

    def _message_document(self, title: str, message: str) -> str:
        import html

        return self._html_page(
            title,
            "<div class='empty'><strong>" + html.escape(title) + "</strong><br>" + html.escape(message) + "</div>",
        )

    def _render(self, df: pl.DataFrame, cfg, max_features: int) -> tuple:
        """Build the HTML document; returns (html, drawn_count)."""
        import html
        import math

        style = self.settings_schema.style
        geometry_column = (cfg.geometry_column.value or "geometry").strip() or "geometry"
        label_columns = [c for c in (cfg.label_columns.value or []) if c in df.columns and c != geometry_column]
        label_column = cfg.label_column.value or None
        if label_column not in df.columns or label_column == geometry_column:
            label_column = None
        color_column = cfg.color_by_column.value or None
        if color_column not in df.columns:
            color_column = None
        tolerance = float(style.simplify_tolerance.value or 0)
        basemap = style.basemap.value or "none"
        tile_template = ""
        if style.own_tiles.value:
            tile_template = (self.settings_schema.tiles.tile_url_template.value or "").strip()
            basemap = "custom"
        fill = (style.fill_color.value or "#3D9BF2").strip()
        stroke = (style.stroke_color.value or "#1B4F9C").strip()
        total = df.height


        raw = df.get_column(geometry_column)
        decode = self._decode_wkb
        if raw.dtype == pl.Utf8:
            # Blanks are not shapes, and an empty string would pass the all-hex test vacuously.
            raw = pl.Series(
                geometry_column, [None if v is None or not v.strip() else v for v in raw.to_list()]
            )
            sample = raw.drop_nulls().head(1).to_list()
            candidate = sample[0].strip() if sample else ""
            is_hex = (
                bool(candidate)
                and len(candidate) % 2 == 0
                and all(c in "0123456789abcdefABCDEF" for c in candidate)
            )
            raw = raw.str.decode("hex", strict=False) if is_hex else raw
            decode = self._decode_wkb if is_hex else self._decode_wkt
        if raw.dtype not in (pl.Binary, pl.Utf8):
            return self._message_document(
                "This column does not contain shapes",
                f"Column '{geometry_column}' holds {raw.dtype} data, not shapes. "
                "Use a column made by Create Points or Spatial Read.",
            ), 0

        # Deterministic, evenly spaced downsample over the full frame.
        if total > max_features:
            indices = [int(i * total / max_features) for i in range(max_features)]
        else:
            indices = list(range(total))
        wkb_values = raw.to_list()
        label_values = {c: df.get_column(c).to_list() for c in label_columns}
        text_values = df.get_column(label_column).to_list() if label_column else None
        max_labels = 300
        labelled = 0
        color_values = df.get_column(color_column).to_list() if color_column else None

        project = self._to_mercator
        features = []
        null_count = 0
        unsupported = 0
        bbox = [math.inf, math.inf, -math.inf, -math.inf]
        for i in indices:
            blob = wkb_values[i]
            if blob is None:
                null_count += 1
                continue
            geom = decode(blob)
            if geom is None:
                unsupported += 1
                continue
            primitives = []
            for kind, coords in self._flatten(geom):
                if kind == "point":
                    projected = [project(*coords)]
                elif kind == "line":
                    projected = [project(*p) for p in self._simplify(coords, tolerance)]
                else:
                    projected = [[project(*p) for p in self._simplify(ring, tolerance)] for ring in coords]
                flat = projected if kind != "polygon" else [p for ring in projected for p in ring]
                for x, y in flat:
                    if x < bbox[0]:
                        bbox[0] = x
                    if y < bbox[1]:
                        bbox[1] = y
                    if x > bbox[2]:
                        bbox[2] = x
                    if y > bbox[3]:
                        bbox[3] = y
                primitives.append((kind, projected))
            features.append((i, primitives))

        if not features:
            reason = (
                f"All {total} shapes are empty."
                if total and null_count == total
                else f"No drawable shapes ({null_count} empty, {unsupported} unreadable of {total})."
            )
            return self._message_document("Nothing to draw", reason), 0

        width, height = 960.0, 600.0
        span_x = max(bbox[2] - bbox[0], 1e-9)
        span_y = max(bbox[3] - bbox[1], 1e-9)
        if bbox[2] - bbox[0] < 1e-9 and bbox[3] - bbox[1] < 1e-9:
            pad = 200.0
            bbox = [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad]
            span_x = span_y = 2 * pad
        center_x = (bbox[0] + bbox[2]) / 2.0
        center_y = (bbox[1] + bbox[3]) / 2.0

        tiles_html = ""
        basemap_note = ""
        use_tiles = basemap in ("osm", "custom")
        if basemap == "custom" and not tile_template:
            use_tiles = False
            basemap_note = "Background map off: no tile server address given."
        if use_tiles:
            template = "https://tile.openstreetmap.org/{z}/{x}/{y}.png" if basemap == "osm" else tile_template
            world = 2 * math.pi * 6378137.0
            zoom = 0
            for z in range(0, 19):
                px_per_m = 256.0 * (2**z) / world
                if span_x * px_per_m > width - 24 or span_y * px_per_m > height - 24:
                    break
                zoom = z
            scale = 256.0 * (2**zoom) / world
            origin_px = (center_x + world / 2.0) * scale - width / 2.0
            origin_py = (world / 2.0 - center_y) * scale - height / 2.0
            n_tiles = 2**zoom
            parts = []
            for tx in range(int(math.floor(origin_px / 256.0)), int(math.floor((origin_px + width) / 256.0)) + 1):
                for ty in range(int(math.floor(origin_py / 256.0)), int(math.floor((origin_py + height) / 256.0)) + 1):
                    if ty < 0 or ty >= n_tiles:
                        continue
                    url = template.replace("{z}", str(zoom)).replace("{x}", str(tx % n_tiles)).replace("{y}", str(ty))
                    left = tx * 256.0 - origin_px
                    top = ty * 256.0 - origin_py
                    parts.append(
                        f"<img src='{html.escape(url, quote=True)}' style='left:{left:.1f}px;top:{top:.1f}px' alt=''>"
                    )
            tiles_html = "".join(parts)

            def to_px(x, y):
                return ((x + world / 2.0) * scale - origin_px, (world / 2.0 - y) * scale - origin_py)

        else:
            scale = min(width * 0.9 / span_x, height * 0.9 / span_y)

            def to_px(x, y):
                return (width / 2.0 + (x - center_x) * scale, height / 2.0 - (y - center_y) * scale)

        palette = [
            "#3D9BF2",
            "#F28C3D",
            "#3DC97C",
            "#E0459A",
            "#9A6FF8",
            "#E8C13D",
            "#15B6C9",
            "#D94A4A",
            "#6E7DF7",
            "#8C6D3F",
        ]
        color_index: dict = {}
        legend_extra = 0
        if color_values is not None:
            for i, _ in features:
                key = "null" if color_values[i] is None else str(color_values[i])
                if key not in color_index:
                    if len(color_index) < len(palette):
                        color_index[key] = palette[len(color_index)]
                    else:
                        legend_extra += 1
                        color_index[key] = "#9ca3af"

        def fmt_path(points, close: bool) -> str:
            last = None
            out = []
            for x, y in points:
                px, py = to_px(x, y)
                rounded = (round(px, 1), round(py, 1))
                if rounded == last:
                    continue
                out.append(("M" if last is None else "L") + f"{rounded[0]:g} {rounded[1]:g}")
                last = rounded
            if close and out:
                out.append("Z")
            return "".join(out)

        def label_tag(primitives, text: str) -> str:
            """Text beside a point, or centred on the vertices of a line or area."""
            points = [
                p
                for kind, coords in primitives
                for p in (coords if kind != "polygon" else [q for ring in coords for q in ring])
            ]
            ax, ay = to_px(sum(x for x, _ in points) / len(points), sum(y for _, y in points) / len(points))
            if len(primitives) == 1 and primitives[0][0] == "point":
                return f"<text class='lbl' x='{ax + 7:.1f}' y='{ay + 4:.1f}'>{html.escape(text)}</text>"
            return f"<text class='lbl' text-anchor='middle' x='{ax:.1f}' y='{ay + 4:.1f}'>{html.escape(text)}</text>"

        def shown(value) -> str:
            """Numbers trimmed to three decimals; everything else as is."""
            if isinstance(value, float):
                return f"{value:.3f}".rstrip("0").rstrip(".")
            return str(value)

        def hover_card(index: int, primitives, lines: list) -> str:
            """A small white card near the shape, listing the hover columns; shown by CSS on :hover."""
            points = [
                p
                for kind, coords in primitives
                for p in (coords if kind != "polygon" else [q for ring in coords for q in ring])
            ]
            ax, ay = to_px(sum(x for x, _ in points) / len(points), sum(y for _, y in points) / len(points))
            longest = max(len(f"{k}: {shown(v)}") for k, v in lines)
            box_w, box_h = min(6.4 * longest + 16, width - 16), 15 * len(lines) + 10
            x = ax + 12 if ax + 12 + box_w <= width else max(4.0, ax - 12 - box_w)
            y = ay - box_h / 2
            y = min(max(4.0, y), height - box_h - 4)
            rows = "".join(
                f"<tspan x='{x + 8:.1f}' dy='{0 if n == 0 else 15}'>"
                f"<tspan class='k'>{html.escape(str(k))}: </tspan>{html.escape(shown(v))}</tspan>"
                for n, (k, v) in enumerate(lines)
            )
            return (
                f"<g class='tip' id='t{index}'><rect x='{x:.1f}' y='{y:.1f}' width='{box_w:.1f}' "
                f"height='{box_h:.1f}' rx='4'/><text x='{x + 8:.1f}' y='{y + 17:.1f}'>{rows}</text></g>"
            )

        cards: list = []
        rules: list = []
        svg = [
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width:g}' height='{height:g}' "
            f"viewBox='0 0 {width:g} {height:g}'>"
        ]
        for n, (i, primitives) in enumerate(features):
            color = fill
            if color_values is not None:
                key = "null" if color_values[i] is None else str(color_values[i])
                color = color_index.get(key, fill)
            tip = ""
            if label_columns:
                lines = [(c, label_values[c][i]) for c in label_columns]
                tip = "<title>" + html.escape("\n".join(f"{k}: {shown(v)}" for k, v in lines)) + "</title>"
                cards.append(hover_card(n, primitives, lines))
                rules.append(f".map:has(#f{n}:hover) #t{n}{{display:block}}")
            svg.append(f"<g id='f{n}'>" + tip)
            for kind, coords in primitives:
                if kind == "point":
                    px, py = to_px(*coords[0])
                    svg.append(
                        f"<circle cx='{px:.1f}' cy='{py:.1f}' r='4' fill='{html.escape(color)}' "
                        f"stroke='{html.escape(stroke)}' stroke-width='1'/>"
                    )
                elif kind == "line":
                    svg.append(
                        f"<path d='{fmt_path(coords, False)}' fill='none' stroke='{html.escape(color)}' "
                        "stroke-width='2' stroke-linejoin='round' stroke-linecap='round'/>"
                    )
                else:
                    d = "".join(fmt_path(ring, True) for ring in coords if ring)
                    svg.append(
                        f"<path d='{d}' fill='{html.escape(color)}' fill-opacity='0.35' fill-rule='evenodd' "
                        f"stroke='{html.escape(stroke)}' stroke-width='1'/>"
                    )
            if text_values is not None and labelled < max_labels and text_values[i] is not None:
                svg.append(label_tag(primitives, shown(text_values[i])))
                labelled += 1
            svg.append("</g>")
        svg.extend(cards)
        svg.append("</svg>")

        body = [
            f"<p class='meta'>Showing <strong>{len(features)}</strong> of <strong>{total}</strong> shapes"
            + "</p>",
            ("<style>" + "".join(rules) + "</style>" if rules else "")
            + f"<div class='map' style='width:{width:g}px;height:{height:g}px'>" + tiles_html + "".join(svg) + "</div>",
        ]
        if color_values is not None:
            items = "".join(
                f"<span><i class='swatch' style='background:{c}'></i>{html.escape(k)}</span>"
                for k, c in list(color_index.items())[: len(palette)]
            )
            more = f"<span>&hellip; {legend_extra} more values in grey</span>" if legend_extra else ""
            body.append(
                f"<div class='legend'><span><strong>{html.escape(str(color_column))}</strong></span>{items}{more}</div>"
            )
        notes = []
        if null_count:
            notes.append(f"{null_count} empty shapes skipped")
        if unsupported:
            notes.append(f"{unsupported} unreadable shapes skipped")
        if text_values is not None and len(features) > max_labels:
            notes.append(f"labels written for the first {max_labels} shapes only")
        if basemap_note:
            notes.append(basemap_note)
        if use_tiles and basemap == "osm":
            notes.append("Basemap &copy; OpenStreetMap contributors (tiles fetched from tile.openstreetmap.org)")
        elif use_tiles:
            notes.append("Basemap tiles fetched from " + html.escape(tile_template))
        if notes:
            body.append("<p class='note'>" + " &middot; ".join(notes) + "</p>")
        return self._html_page("Map preview", "".join(body)), len(features)

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        cfg = self.settings_schema.map
        artifact_name = (self.settings_schema.artifact.artifact_name.value or "map_preview").strip() or "map_preview"
        geometry_column = (cfg.geometry_column.value or "geometry").strip() or "geometry"
        max_features = max(1, int(cfg.max_features.value or 2000))

        lf = inputs[0]
        df = lf.collect()
        if geometry_column not in df.columns:
            document = self._message_document(
                "Shape column not found",
                f"There is no column '{geometry_column}' in the input. Columns: {', '.join(df.columns) or '(none)'}.",
            )
        elif df.height == 0:
            document = self._message_document("Nothing to draw", "The input has no rows.")
        else:
            document, drawn = self._render(df, cfg, max_features)
            while len(document) > 2_000_000 and drawn > 50:
                max_features = max(50, drawn // 2)
                document, drawn = self._render(df, cfg, max_features)

        flowfile_ctx.publish_artifact(artifact_name, document, preview=True)  # noqa: F821
        flowfile_ctx.log_info(f"Published map artifact '{artifact_name}' ({len(document)} bytes)")  # noqa: F821
        return lf

    def predict_output_schema(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        """The data passes through unchanged, so downstream columns resolve without running the kernel."""
        return inputs[0]
