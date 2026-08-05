# Attribute Importance

## What it does

This node scores how strongly each attribute relates to the target, without fitting a model. It ranks
the attributes by mutual information or an F-test and returns the ranking (`rank`, `attribute`,
`importance`, `p_value` for the F-test, `method`), plus an optional bar chart on the Artifacts tab.
Runs on a kernel.

## Inputs

One table: any mix of numeric, string, boolean or categorical attribute columns, plus a target column.
Rows with a null target are dropped. Numeric attributes have missing values filled with the median;
non-numeric ones are label-encoded. Regression needs a numeric target.

## Settings

**Data** — the attribute columns and the target. The target is excluded from the attributes if you
pick it twice. Task is auto-detected (strings, booleans and low-cardinality integers become
classification); set it yourself if the guess is wrong.

**Scoring** — mutual information captures non-linear relationships and is the default; the F-test /
ANOVA only measures linear association but returns a p-value alongside each score. Normalizing divides
by the top score so importances land in 0–1. Top N truncates the output.

**Visualization** — publish the ranked bar chart under a name you pick, or turn it off for table only.
