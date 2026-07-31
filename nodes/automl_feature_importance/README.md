# AutoML Feature Importance

## What it does

This node fits a model on your table and ranks which columns actually drive the target. It handles the
preprocessing, trains on a 75/25 split, and measures importance by permutation or from the model's own
scores. Output is the ranking (`rank`, `feature`, `importance`, `importance_std`, `method`), plus an
optional bar chart on the Artifacts tab. Runs on a kernel.

## Inputs

One table: any mix of numeric, string, boolean or categorical feature columns, plus a target column.
Rows with a null target are dropped. Classification needs two or more classes, regression a numeric
target.

## Settings

**Data** — the feature columns and the target. Task is auto-detected (strings, booleans and
low-cardinality integers become classification); set it yourself if the guess is wrong.

**Model** — which estimator you're explaining, linear through the tree ensembles to XGBoost and
LightGBM. Different models rank differently. Balancing only applies to classification: class weights
by default, or over/undersample the training split.

**Importance** — permutation works for any model and gives you a std, built-in is faster but has
neither (and KNN has none at all). The scoring metric is what permutation degrades; more repeats means
a steadier ranking and longer runtime. Top N truncates the output.

**Visualization** — publish the ranked bar chart under a name you pick, or turn it off for table only.
