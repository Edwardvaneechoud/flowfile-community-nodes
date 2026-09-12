# Spatial Read

## What it does

Loads a Shapefile, GeoJSON, GeoParquet, FlatGeobuf, GeoPackage or KML as a table, one row per shape
with its attributes. Shapes travel as WKT text in longitude/latitude degrees (EPSG:4326); the node
also reads hex WKB or binary WKB, and converts the file's own coordinates to EPSG:4326 so the other
map nodes measure correctly. Runs in the compute worker. It uses DuckDB's spatial extension, which
is downloaded once on first use, so the machine needs internet that one time.

## Source file

No input table. It reads one file from the machine Flowfile runs on, at the path you give. The file
must record which coordinate system it uses, or you have to say so under More options. The
community CI's dry run, which has no files, reads a built-in three-district sample instead.

## Settings

**File** — the path to read and how to read it. Give the File path; File type defaults to detecting
from the file name and can be set to Shapefile, GeoJSON, GeoParquet, FlatGeobuf, GeoPackage or KML.
Shape column names the WKT column in the result (default `geometry`), and the file must not already
have a column by that name. First N rows only (0 = all) caps the read. More options reveals the
section below.

**More options** — a layer name for multi-layer files, and the system to assume when the file does
not record one. Layer name picks the layer to read. Coordinates in the file are is only consulted
when the file records none — it never overrides one that is set.
