# Create Points

## What it does

Turns latitude and longitude columns into map points, so a plain spreadsheet can be buffered,
measured, joined and drawn. Every row becomes a point in a new shape column that Buffer, Distance,
Measure, Spatial Join and Map Preview all read. Shapes travel as WKT text in longitude/latitude
degrees (EPSG:4326); the nodes also read hex WKB or binary WKB. Runs in the compute worker.

## Inputs

One table with numeric latitude and longitude columns. For plain degrees, rows where either value
is missing or not finite get an empty shape, and a latitude outside -90 to 90 stops the run —
usually the columns are swapped, or the numbers are a national grid.

## Settings

**Coordinates** — pick the two columns holding latitude and longitude: **Latitude** and
**Longitude**. **Shape column** names the new column (default geometry; the run stops if that
column already exists). Leave **Other coordinate system** off for ordinary degrees, which is what
phones, spreadsheets and web maps produce; turn it on only for a national grid, such as Dutch RD or
British National Grid.

**Coordinate system** — shown only with that toggle on. **Coordinate system** takes the EPSG code
the numbers are already in (default EPSG:28992); they are converted to plain latitude/longitude, so
every later node measures in real distances. Here the Longitude picker holds the easting (X) and
Latitude the northing (Y). Needs the map extension, which downloads once on first use.
