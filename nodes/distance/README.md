# Distance

## What it does

Adds the real ground distance between two places on each row, in kilometres, metres or miles. It
works straight off latitude and longitude columns with no setup, or between two shape columns, which
are measured centre to centre. Shapes travel as WKT text in longitude/latitude degrees (EPSG:4326);
the node also reads hex WKB or binary WKB. Runs in the compute worker; the shape mode uses DuckDB's
map extension, which downloads once on first use.

## Inputs

One table. Each row holds both places: either four numeric latitude/longitude columns in degrees, or
two shape columns holding text or bytes. A latitude outside -90 to 90 stops the run, because it
usually means latitude and longitude are the wrong way round.

## Settings

**Measure between** — each row holds both places, and the distance is added as a new column on that
row. Use shape columns off: pick four latitude/longitude columns, which is what a spreadsheet
normally has. On: pick two shape columns instead, and the distance is measured centre to centre.

**Coordinates** — the two places on each row, as latitude and longitude in degrees: From latitude,
From longitude, To latitude and To longitude.

**Shapes** — From shape and To shape, the two shape columns to measure between. Areas and lines are
measured from their centre point.

**Result** — New column is the name of the added column, default distance; Unit is Kilometres,
Metres or Miles.
