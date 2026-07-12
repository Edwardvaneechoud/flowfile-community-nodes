# Auto Date Parser

Detect the format of a string date column **automatically** and convert it to a
real `Date` or `Datetime` — no need to know or specify the format up front.

Detection is done **per row**: the node tries a battery of ~50 common date/time
formats and keeps the first that matches each value. Because the match is
per-value, a single column may even contain a **mix** of formats.

## Inputs

| Port | Description |
|------|-------------|
| `input[0]` | A table containing a string column of dates. |

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| **Date column** | column (String) | — | The string column to parse. *(required)* |
| **Convert to** | choice | `Date` | Output as a `Date` (day precision) or `Datetime` (with time). |
| **Output column** | text | *(empty)* | Name for the parsed column. Leave empty to **overwrite** the source column. |
| **Day first** | toggle | `off` | For ambiguous values like `03/04/2021`, read as **day/month** (4 March) instead of month/day. |
| **On unparseable value** | choice | `Set to null` | `Set to null` leaves bad values empty; `Raise an error` fails the node and reports up to 5 offending values. |

## Output

The chosen column, converted to `Date` or `Datetime`. Values that no format
matches become `null` (or raise, depending on **On unparseable value**).

## How detection works

Formats are tried in priority order and coalesced (first match wins per row):

1. **Unambiguous / ISO first** — `2021-03-04`, `2021-03-04T10:30:00`,
   `2021-03-04T10:30:00+02:00`, `2021/03/04`, `20210304`, …
2. **Month names** — `March 4, 2021`, `4 Mar 2021`, `04-Mar-2021`, …
3. **Ambiguous numeric** — `04/03/2021`, `03-04-21`, `03.04.2021` across `/`,
   `-`, `.` separators and 2-/4-digit years, with or without a time part. The
   **Day first** toggle decides the order these are tried in.

Timezone-aware values (e.g. `+02:00`) are normalized to **UTC** and returned as
naive datetimes, so the whole column shares one dtype.

## Examples

With **Convert to = Date**, **Day first = off**:

| `raw_date` | → `parsed_date` |
|------------|-----------------|
| `2021-03-04` | `2021-03-04` |
| `04/03/2021` | `2021-04-03` *(month-first)* |
| `March 4, 2021` | `2021-03-04` |
| `2021-03-04T10:30:00` | `2021-03-04` |
| `20210304` | `2021-03-04` |
| `not a date` | `null` |

Turning **Day first = on** flips the ambiguous case: `04/03/2021` → `2021-03-04`
(4 March).

## Notes & edge cases

- **Mixed formats in one column** are supported — each value is matched
  independently.
- **Ambiguous dates** (e.g. `03/04/2021`) are genuinely undecidable from the
  value alone; use **Day first** to pick the interpretation.
- **2-digit years with dashes**: `04-03-21` parses to year **0004** (the 4-digit
  year pattern claims the leading `04` before the 2-digit variant is tried). If
  your data uses 2-digit years, prefer an unambiguous 4-digit source.
- Runs **locally** (in the worker) — no kernel or Docker required.

## Metadata

- **Category:** Date & Time
- **Author:** Edwardvaneechoud
- **Version:** 1.0.0
- **Tags:** date, datetime, parsing, cleaning
