# Buffer

## What it does

This node grows each shape by a set distance, answering questions like "which homes are within
500 m of a station?". The distance is measured on the ground, so it holds up far from the equator,
and a negative distance shrinks the shape instead. Shapes travel as WKT text in longitude/latitude
degrees (EPSG:4326); the node also reads hex WKB or binary WKB. Runs in the compute worker, on
DuckDB's spatial extension, which downloads once on first use.

## Inputs

One table with a column of shapes — text (WKT or hex WKB) or binary WKB. Blank values are treated
as missing. A zone that reaches across the +/-180 line cannot be drawn as a single shape, so those
rows raise an error rather than pass on a zone spanning the planet.

## Settings

**Zone** — grows every shape outwards by a real ground distance, so 500 m is 500 m whether the data
is at the equator or in Norway. A negative distance shrinks the shape instead. Shape column is the
column holding the shapes, Distance and Unit (Metres, Kilometres, Miles) say how far to grow them,
and the zone lands in New column — clear it to replace the original shape rather than add one.
Adjust smoothness reveals the next section; curves are drawn as straight segments, so turn it on to
trade speed for roundness.

**Smoothness** — segments used per quarter circle. Higher is rounder and slower; 8 is the default.
Set it with Segments, between 1 and 64.
