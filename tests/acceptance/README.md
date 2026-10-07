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
gold: [https://...]            # optional: published fact checks; the table's "gold" column says whether
                               # the pipeline cited that page ("page"), its publisher ("site") or neither
after: <case id>               # optional: run right after that case in one store, with the API's tier 1
expect_cache: T1               #   lookup (re-share tests); the case must come from that cache tier
expect_ai_generation: true     # optional: the verdict must carry an AI-generation assessment
```

Cases whose file is under `samples/` use real third-party posts. `samples/` is gitignored (the repo is
public), those cases are skipped where it is absent, and `make record` never stores their model outputs.

A case passes when the label is one of `expected`, the language matches and latency is within
budget. Real media inputs for cases 1 to 4, 6, 8 to 10 and 12 to 14 live in
`gs://{project}-eval/acceptance/` (not in this public repo); add them here as the media and link
lanes land.
