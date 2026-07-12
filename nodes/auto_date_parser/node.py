import polars as pl

from flowfile import node_designer as nd


class AutoDateParserSettings(nd.NodeSettings):
    parse: nd.Section = nd.Section(
        title="Parse date column",
        description="Auto-detect the format of a string date column and convert it to a real date/datetime.",
        layout="vertical",
        date_column=nd.ColumnSelector(
            label="Date column",
            data_types=nd.Types.String,
            required=True,
        ),
        output_type=nd.SingleSelect(
            label="Convert to",
            options=[("date", "Date"), ("datetime", "Datetime")],
            default="date",
        ),
        output_column=nd.TextInput(
            label="Output column",
            default="",
            placeholder="leave empty to overwrite the source column",
        ),
        day_first=nd.ToggleSwitch(
            label="Day first",
            default=False,
            description="For ambiguous values like 03/04/2021, read as day/month (4 March) instead of month/day.",
        ),
        on_error=nd.SingleSelect(
            label="On unparseable value",
            options=[("null", "Set to null"), ("error", "Raise an error")],
            default="null",
        ),
    )


class AutoDateParser(nd.CustomNodeBase):
    node_name: str = "Auto Date Parser"
    node_category: str = "Date & Time"
    node_icon: str = "auto_date_parser.png"
    title: str = "Auto Date Parser"
    intro: str = "Detect the format of a string date column automatically and convert it to a Date or Datetime."
    author: str = "Edwardvaneechoud"
    version: str = "1.0.0"
    tags: list[str] = ["date", "datetime", "parsing", "cleaning"]
    transform_type: str = "narrow"
    example_inputs: list[dict[str, list]] = [
        {
            "raw_date": [
                "2021-03-04",
                "04/03/2021",
                "March 4, 2021",
                "2021-03-04T10:30:00",
                "20210304",
            ],
        },
    ]
    example_settings: dict[str, dict] = {
        "parse": {
            "date_column": "raw_date",
            "output_type": "date",
            "output_column": "parsed_date",
            "day_first": False,
            "on_error": "null",
        },
    }
    settings_schema: AutoDateParserSettings = AutoDateParserSettings()

    def process(self, *inputs: pl.LazyFrame) -> pl.LazyFrame:
        cfg = self.settings_schema.parse
        col = cfg.date_column.value
        out_name = (cfg.output_column.value or "").strip() or col
        to_date = cfg.output_type.value == "date"
        day_first = cfg.day_first.value
        on_error = cfg.on_error.value

        src = pl.col(col).cast(pl.String).str.strip_chars()

        # Unambiguous / ISO-style first so a well-formed value never loses to a
        # looser pattern; coalesce takes the first format that matches each row,
        # so a single column may mix formats.
        iso_formats = [
            "%Y-%m-%dT%H:%M:%S%.f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S%.f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S%.f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%Y%m%d",
        ]
        month_name_formats = [
            "%d %b %Y %H:%M:%S",
            "%d %B %Y %H:%M:%S",
            "%b %d, %Y %H:%M:%S",
            "%B %d, %Y %H:%M:%S",
            "%d %b %Y",
            "%d %B %Y",
            "%d-%b-%Y",
            "%d-%B-%Y",
            "%b %d, %Y",
            "%B %d, %Y",
            "%b %d %Y",
            "%B %d %Y",
            "%Y %b %d",
            "%Y %B %d",
        ]

        # Numeric day/month/year is genuinely ambiguous; the toggle decides which
        # order is tried first for values that both patterns accept.
        numeric_formats = []
        for sep in ("/", "-", "."):
            dm = "%d" + sep + "%m" + sep
            md = "%m" + sep + "%d" + sep
            for year in ("%Y", "%y"):
                for suffix in (" %H:%M:%S", " %H:%M", ""):
                    first = dm + year + suffix if day_first else md + year + suffix
                    second = md + year + suffix if day_first else dm + year + suffix
                    numeric_formats.append(first)
                    numeric_formats.append(second)

        attempts = []
        for fmt in iso_formats + month_name_formats + numeric_formats:
            parsed = src.str.to_datetime(format=fmt, strict=False, exact=True)
            if "%z" in fmt:
                # Timezone-aware parses come back as UTC; drop the zone so every
                # attempt shares one naive Datetime dtype and coalesce can merge them.
                parsed = parsed.dt.replace_time_zone(None)
            attempts.append(parsed)

        parsed_expr = pl.coalesce(attempts)
        if to_date:
            parsed_expr = parsed_expr.dt.date()

        if on_error == "error":
            check = inputs[0].select(
                src.alias("_orig"),
                parsed_expr.alias("_parsed"),
            ).collect()
            bad = check.filter(
                pl.col("_orig").is_not_null()
                & (pl.col("_orig").str.len_chars() > 0)
                & pl.col("_parsed").is_null()
            )
            if bad.height:
                sample = bad.get_column("_orig").head(5).to_list()
                raise ValueError(
                    f"Auto Date Parser could not parse {bad.height} value(s) in column '{col}'. "
                    f"Examples: {sample}"
                )

        return inputs[0].with_columns(parsed_expr.alias(out_name))
