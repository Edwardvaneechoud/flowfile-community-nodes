# kmeans clustering

Do a kmeans clustering with sklearn

## What it does

Groups the rows of a table into *K* clusters with scikit-learn's
[`KMeans`](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html),
then adds a column holding each row's cluster label (`0` … `K-1`). Reach for it to segment
records by similarity — customers by behaviour, observations by shape — when you have a few
numeric columns and want an unsupervised grouping rather than a rule you write by hand.

The node runs in the **kernel** environment (it needs `scikit-learn`). Clustering is
deterministic: `n_init=10` and a fixed `random_state=42`, so the same input and settings
always produce the same labels.

## Inputs

A single table. It must contain the numeric columns you select as features; other columns
are passed through unchanged.

## Settings

- **Feature Columns** (required) — one or more numeric columns to cluster on. Only these
  columns feed the model.
- **Number of clusters** — *K*, the number of clusters to fit (2–20, default 3).
- **Cluster column name** — name of the label column added to the output (default `cluster`).
- **Standardize** (default on) — z-score the features with `StandardScaler` before fitting,
  so columns on different scales (e.g. age vs. income) contribute evenly. Turn off to cluster
  on the raw values.

## Output

The input table with one extra integer column (named by **Cluster column name**) giving the
cluster each row was assigned to.
