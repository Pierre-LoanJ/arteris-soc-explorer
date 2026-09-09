# Required scenarios (candidate-facing)

These scenarios are executed by `scripts/run_required_scenarios.py` against
**your** adapter (`soc_explorer.adapter:get_adapter` by default).

You must ship the generated `artifacts/scenario_results.json`.

| ID | Intent | What reviewers check (high level) |
|----|--------|-----------------------------------|
| S1 | List components | `ok`, non-empty list, stable ids |
| S2 | Get `cpu0` | `ok`, component id/kind consistent with design |
| S3 | Get missing id | `ok: false` with a clear error payload (not a crash) |
| S4 | Validate design | Returns a structured list/object (content is your responsibility) |
| S5 | Search `r0` | Returns structured hits (inspect carefully — search quality matters) |
| S6 / S6b | Update + re-read | Mutation path works; read-back reflects change when applicable |
| S7 | Report | Human/agent-readable summary mentioning the design |

## Rules

1. Wire the adapter to **the same logic** your MCP tools use.
2. Do not manually invent `scenario_results.json` — regenerate it.
3. Prefer `persist: false` for S6 if you support dry-run / non-persistent updates, so you do not dirty the shared fixture. If you only support persistent updates, document restore steps in `NOTES.md`.
4. In `NOTES.md`, write observations you made **by running** the design (unexpected validation results, odd search hits, missing fields, etc.).

## Optional but valued

- Extra scenarios in your own tests (path finding, dry-run diff, referential checks…).
- Error **codes** stable enough for an agent to branch on.
