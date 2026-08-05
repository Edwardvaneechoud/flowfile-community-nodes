# AutoML Reuse Model

## What it does

This node loads a model persisted by AutoML Store Model and appends its predictions to new data. It
reuses the stored preprocessing, so the input only needs the same feature columns — no retraining.
Output is the input table plus a prediction column, and optionally one probability column per class.
Runs on a kernel.

## Inputs

One table containing every feature column the stored model was trained on; extra columns are passed
through untouched. The target column is not needed. Missing feature columns raise an error.

## Settings

**Model** — pick a stored model from the artifact picker, or type its name to override the picker
(useful when the model is published by a flow that hasn't run yet in this session). Prediction column
names the appended column; for classification the original class labels are restored. Turn on class
probabilities to also append `<prediction>_proba_<class>` columns — classification only, and only for
models that expose probabilities.
