# Basic Example

What it shows: running gandalf over a repository and reading the RAG scorecard.

## Run

From any git repository (here, gandalf itself):

```sh
PYTHONPATH=src python -m gandalf
```

Scan only a subfolder:

```sh
PYTHONPATH=src python -m gandalf --path src/gandalf/gates
```

Exit code is `1` if the overall verdict is red, `0` otherwise.
