# Measure

## What it does

This node adds the area, length and centre point of every shape as ordinary columns, so you can sort,
filter and total them, measured on the ground and accurate at any latitude. Shapes travel as WKT text
in longitude/latitude degrees (EPSG:4326); the node also reads hex WKB or binary WKB, and writes the
shape column back as WKT. Runs in the compute worker. It uses DuckDB's spatial extension, which
downloads once on first use, so that first run needs an internet connection.

## Inputs

One table with a column of shapes, held as text or as bytes. Blank shapes are treated as missing. The
node fails if the table already has a column named after one of the measurements it would add.

## Settings

**Measure** — adds a column for each thing you tick. Shape column is the text or binary column holding
the shapes. Add lists the measurements: Area, Length or perimeter, Centre, as a shape, Centre, as
latitude and longitude (two columns, latitude and longitude), and Number of corners; area and length
are ticked to start with. Area is zero for points and lines; length is the perimeter of an area, the
length of a line, and zero for a point. Mixed collections are left blank rather than guessed at. Units
switches area and length together between kilometres and square kilometres, metres and square metres,
or miles and square miles, and starts on kilometres.
