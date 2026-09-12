# Spatial Join

## What it does

Tags each row with the area it falls inside - every customer with its district, every incident with
its region. Matched and unmatched rows come out of separate outputs. Shapes travel as WKT text in
longitude/latitude degrees (EPSG:4326); the node also reads hex WKB or binary WKB. Runs in the
compute worker, on DuckDB's spatial extension, which downloads once on first use.

## Inputs

Two tables. Rows to tag holds the rows being matched; Areas holds the shapes they are matched
against. Every row of the first input is matched against the second by where it sits on the map.
Both shape columns must hold text or bytes.

## Outputs

matched - the rows that found a match, with the second input's columns attached (a colliding name
gets a `_right` suffix). unmatched - the rows that matched nothing, unchanged.

## Settings

**Match** - Shape column picks the shape column on the first input. Second shape column is typed in,
because the picker can only read the first input. Rule picks how the two shapes must relate: falls
inside the second shape, surrounds it, or touches or overlaps it. Match within a distance ignores
the rule above and matches anything within a set distance instead.

**Distance** - shown when Match within a distance is on. Distance and Unit (metres, kilometres,
miles) set how far apart two shapes may be and still count as a match, measured between their
nearest edges on the ground, so any mix of points, lines and areas works.
