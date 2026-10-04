# Prompts

- Each file starts with a `version:` line. The loader records the version in `model_calls` and on every verdict.
- `{{double_braces}}` are filled by code. Anything user-supplied is inserted only inside `<user_content>` or `<evidence>` blocks.
- Every prompt asks for JSON matching a model in `schemas/models.py`. Use the Gen AI SDK `response_schema` with the Pydantic model so output is constrained; the text schema here is a reminder for the model.
- Shared rule block `00_shared_rules.md` is prepended to every prompt by the loader.
- Change a prompt: bump its version, run `make test-live` on the acceptance cases, then run the eval candidate suite before deploying.
