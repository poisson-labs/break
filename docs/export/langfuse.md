# Exporting cases from Langfuse

Break reads its cases from a file: JSON Lines, one case a line, each with an `input`. If your
agent already sends its traces to Langfuse, the requests your users made are there, and they make
better cases than invented ones. This page turns recent requests into a case file in two steps.
Break does not call Langfuse itself.

## 1. Export recent requests with Langfuse's own client

Langfuse's query returns observations, the steps of a trace, and not whole traces. The
observation with no parent is the trace's root, and its input is what the user asked. This
writes the observations of the last seven days to `langfuse-export.json`.

```python service
import json
from datetime import datetime, timedelta, timezone

from langfuse import get_client

langfuse = get_client()   # uses environment variables to authenticate
end = datetime.now(timezone.utc)
start = end - timedelta(days=7)

rows, cursor = [], None
while True:
    page = langfuse.api.observations.get_many(
        from_start_time=start,
        to_start_time=end,
        fields="core,basic,io",
        limit=1000,
        cursor=cursor,
    )
    for row in page.data:
        rows.append({"trace_id": row.trace_id,
                     "parent_observation_id": row.parent_observation_id,
                     "input": row.input})
    cursor = getattr(page.meta, "cursor", None)
    if not cursor:
        break

with open("langfuse-export.json", "w", encoding="utf-8") as out:
    json.dump(rows, out)
```

This block is shown, not run: it needs your key and your project. It follows Langfuse's
documentation as read on 2026-11-09 (https://langfuse.com/docs/api-and-data-platform/features/query-via-sdk). Langfuse's pages say this
call replaces `api.trace.list`, which is deprecated and removed in version 5 of the Python
SDK. The `io` field group is what returns `input`; check the row's field names against the SDK
version you run.

The export is one JSON list. Each row is an observation: the trace it belongs to, its parent
(`null` for the root) and its input as raw text. The conversion keeps the roots, reads an input
that is a JSON string as that string, and leaves out a root whose input is not plain text. If
your root input is a list of messages, change the conversion to take the text you want from it.

## 2. Convert the export into a case file

Run this in the folder that holds `langfuse-export.json`. It uses the standard library only and
writes `langfuse.jsonl`.

```python
import json

with open("langfuse-export.json", encoding="utf-8") as held:
    rows = json.load(held)

with open("langfuse.jsonl", "w", encoding="utf-8") as cases:
    for row in rows:
        if row["parent_observation_id"] is not None:
            continue   # not the trace's root: a step inside the request
        request = row["input"]
        try:
            request = json.loads(request)   # the input arrives as raw text, often JSON
        except (TypeError, ValueError):
            pass
        if isinstance(request, str) and request.strip():
            case = {"id": row["trace_id"], "input": request}
            cases.write(json.dumps(case, ensure_ascii=False) + "\n")
```

Every release runs this program on a stored export,
[samples/langfuse-export.json](samples/langfuse-export.json), and checks that it writes
[samples/langfuse.jsonl](samples/langfuse.jsonl) byte for byte, and that Break reads that file as
cases. The stored export was written by hand in the shape step 1 writes. It was not taken from
a live Langfuse project.

## Use the file

Point `[target] cases` in `break.toml` at the file, or pass it to `init` with `--cases`.
`poisson-break doctor` reads it and says how many cases it holds. A case needs only `input`;
the `id` is kept so that a finding's cases can be traced back to where they came from. Read the
file before you hunt on it: these are real requests, and a request that asks for something you
do not want run many times against your test environment should come out.
