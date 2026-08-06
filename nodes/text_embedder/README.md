# Text Embedder

## What it does

This node turns a text column into fixed-size numeric vectors using a sentence-transformers model that
runs on your machine. Pick one of six open-weight models (384 or 768 dimensions, MIT or Apache-2.0),
and the node appends one `Array(Float32, dim)` column to the input table — ready for cosine similarity,
clustering, or any downstream ML. The output schema is declared up front, so downstream nodes resolve
their columns without running the flow first. Runs on a kernel.

## Inputs

One table containing the string column to embed; every other column passes through untouched. Nulls and
whitespace-only values are treated as empty and embedded as the stand-in text you configure — the node
logs how many rows that affected.

## Settings

**Text** — the column to embed. Instruction prefix is prepended to every row: the e5 models expect
`query: `, while MiniLM, mpnet and bge want nothing. Stand-in for empty text is what null and blank rows
get embedded as; leave it blank to embed an empty string.

**Model** — MiniLM-L6-v2 is the fastest at 384 dimensions, mpnet-base-v2 the strongest at 768, with
bge and e5 in both sizes in between. Batch size trades memory for throughput. L2-normalize should stay
on if anything downstream uses cosine similarity or k-means.

**Output** — the name of the appended embedding column.

## Output

The input table plus one `Array(Float32, dim)` column, where `dim` is 384 or 768 depending on the model.
Row order is preserved. Switching model changes the output type, so downstream nodes see a new schema.

## Notes

- Text never leaves the machine. Model weights are downloaded from Hugging Face the first time a model
  is used and cached locally after that.
- The loaded model is kept in the kernel namespace, so reruns on the same kernel skip the load. A kernel
  restart or namespace clear reloads it.
- Rows longer than the model's token window are silently truncated by sentence-transformers. The node
  tokenizes a sample of up to 1,000 rows and warns you with the share affected and the longest length.
- Long runs log progress roughly once a minute, with a rows/second rate and an estimated time remaining.
