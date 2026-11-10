# Exporting cases from LangSmith

Break reads its cases from a file: JSON Lines, one case a line, each with an `input`. If your
agent already sends its traces to LangSmith, the requests your users made are there, and they make
better cases than invented ones. This page turns recent requests into a case file in two steps.
Break does not call LangSmith itself.

## 1. Export recent requests with LangSmith's own client

A root run is one whole request to your agent, and its `inputs` hold what the user asked. This
writes the root runs of the last seven days to `langsmith-export.json`.

```python service
import asyncio
import json
from datetime import datetime, timedelta, timezone

from langsmith import Client


async def export() -> None:
    client = Client()
    project_id = str(client.read_project(project_name="<your_project>").id)
    since = datetime.now(timezone.utc) - timedelta(days=7)
    root_runs = client.runs.query(
        project_ids=[project_id],
        min_start_time=since,
        is_root=True,
        selects=["ID", "INPUTS"],
    )
    runs = []
    async for run in root_runs:
        runs.append({"id": str(run.id), "inputs": run.inputs or {}})
    with open("langsmith-export.json", "w", encoding="utf-8") as out:
        json.dump(runs, out)


asyncio.run(export())
```

This block is shown, not run: it needs your key and your project. It follows LangSmith's
documentation as read on 2026-11-09 (https://docs.langchain.com/langsmith/export-traces). `runs.query` needs
`langsmith` 0.10.15 or later; LangSmith's page says it replaces `list_runs`, which is
deprecated. The client reads your API key from the environment, as LangSmith's own setup
describes.

The export is one JSON list. Each item is one run: its `id`, and its `inputs` as your
application sent them.
The conversion takes the request from one key of `inputs`. Set `INPUT_KEY` to the key your
application uses. A run with no text under that key is left out.

## 2. Convert the export into a case file

Run this in the folder that holds `langsmith-export.json`. It uses the standard library only and
writes `langsmith.jsonl`.

```python
import json

INPUT_KEY = "input"   # the key of `inputs` that holds the user's request in your project

with open("langsmith-export.json", encoding="utf-8") as held:
    runs = json.load(held)

with open("langsmith.jsonl", "w", encoding="utf-8") as cases:
    for run in runs:
        request = run["inputs"].get(INPUT_KEY)
        if isinstance(request, str) and request.strip():
            case = {"id": run["id"], "input": request}
            cases.write(json.dumps(case, ensure_ascii=False) + "\n")
```

Every release runs this program on a stored export,
[samples/langsmith-export.json](samples/langsmith-export.json), and checks that it writes
[samples/langsmith.jsonl](samples/langsmith.jsonl) byte for byte, and that Break reads that file as
cases. The stored export was written by hand in the shape step 1 writes. It was not taken from
a live LangSmith project.

## Use the file

Point `[target] cases` in `break.toml` at the file, or pass it to `init` with `--cases`.
`poisson-break doctor` reads it and says how many cases it holds. A case needs only `input`;
the `id` is kept so that a finding's cases can be traced back to where they came from. Read the
file before you hunt on it: these are real requests, and a request that asks for something you
do not want run many times against your test environment should come out.
