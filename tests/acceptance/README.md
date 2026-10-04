# Acceptance cases (`make accept`)

One YAML file per case. `make accept` runs every case through the real pipeline in-process and
prints a pass/fail table with latency and cost. Run it after every prompt change.

```yaml
id: 05-ta-health-remedy        # also the fixture folder name for make record / make test
case: 5                        # row in tests/acceptance-cases.md
input:
  text: "..."                  # and/or file: path (repo-relative or gs://...), url: https://...
language: ta                   # expected content language (primary subtag, compared case-insensitively)
expected: [FALSE]              # any of these labels passes; NOT_CHECKABLE for greetings, satire, etc.
budget_s: 90                   # optional, defaults to the pipeline's total budget
```

A case passes when the label is one of `expected`, the language matches and latency is within
budget. Real media inputs for cases 1 to 4, 6, 8 to 10 and 12 to 14 live in
`gs://{project}-eval/acceptance/` (not in this public repo); add them here as the media and link
lanes land.
