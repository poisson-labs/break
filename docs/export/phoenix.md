# Exporting cases from Phoenix

Break reads its cases from a file: JSON Lines, one case a line, each with an `input`. If your
agent already sends its traces to Phoenix, the requests your users made are there, and they make
better cases than invented ones. This page turns recent requests into a case file in two steps.
Break does not call Phoenix itself.

## 1. Export recent requests with Phoenix's own client

Phoenix hands spans back as a dataframe. This selects the input of each span of one kind from
the last seven days and writes it to `phoenix-export.csv`. Pick the kind your agent's top span
has, so that each row is one whole request.

```python service
from datetime import datetime, timedelta

from phoenix.client import Client
from phoenix.trace.dsl import SpanQuery

client = Client()
query = SpanQuery().where(
    "span_kind == 'CHAIN'",   # the kind of span your agent opens for a whole request
).select(
    input="input.value",
)
spans = client.spans.get_spans_dataframe(
    query=query,
    project_name="your project name",
    start_time=datetime.now() - timedelta(days=7),
)
spans.to_csv("phoenix-export.csv")
```

This block is shown, not run: it needs your key and your project. It follows Phoenix's
documentation as read on 2026-11-09 (https://arize.com/docs/phoenix/tracing/how-to-tracing/importing-and-exporting-traces/extract-data-from-spans). The client reads
`PHOENIX_COLLECTOR_ENDPOINT`, and `PHOENIX_API_KEY` where the deployment asks for one. Writing the
dataframe to CSV needs pandas, which the dataframe call already uses.

The export is a CSV file. Its first column is the dataframe's index, the span's id, and its
`input` column is the span's input. The conversion reads the first column as the id whatever
its heading is, and leaves out a span with no input.

## 2. Convert the export into a case file

Run this in the folder that holds `phoenix-export.csv`. It uses the standard library only and
writes `phoenix.jsonl`.

```python
import csv
import json

with open("phoenix-export.csv", encoding="utf-8", newline="") as held, \
        open("phoenix.jsonl", "w", encoding="utf-8") as cases:
    spans = csv.DictReader(held)
    span_id = spans.fieldnames[0]   # the dataframe's index, written as the first column
    for span in spans:
        request = span["input"]
        if request and request.strip():
            case = {"id": span[span_id], "input": request}
            cases.write(json.dumps(case, ensure_ascii=False) + "\n")
```

Every release runs this program on a stored export,
[samples/phoenix-export.csv](samples/phoenix-export.csv), and checks that it writes
[samples/phoenix.jsonl](samples/phoenix.jsonl) byte for byte, and that Break reads that file as
cases. The stored export was written by hand in the shape step 1 writes. It was not taken from
a live Phoenix project.

## Use the file

Point `[target] cases` in `break.toml` at the file, or pass it to `init` with `--cases`.
`poisson-break doctor` reads it and says how many cases it holds. A case needs only `input`;
the `id` is kept so that a finding's cases can be traced back to where they came from. Read the
file before you hunt on it: these are real requests, and a request that asks for something you
do not want run many times against your test environment should come out.
