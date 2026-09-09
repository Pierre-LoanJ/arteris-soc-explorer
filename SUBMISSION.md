# Submission — SoC Design Explorer MCP

> Candidate deliverable for the Arteris exercise. The exercise statement is in
> [README.md](README.md); this file is the operating manual.

## Install & run

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # pydantic + mcp 2.x + pytest
```

```bash
pytest -q                                    # 74 tests
python scripts/run_required_scenarios.py     # proof 1 → artifacts/
python examples/agent_demo.py                # proof 2 → artifacts/mcp_session.md
python -m soc_explorer.mcp_server            # the MCP server itself (stdio)
```

Everything is offline. Python 3.11+ (developed on 3.14).

## The two proofs

**Proof 1 — tool behavior.** `soc_explorer/adapter.py` routes `list_tools()` /
`call()` into `soc_explorer/registry.py`, the same table
`soc_explorer/mcp_server.py` serves. Result:
[`artifacts/scenario_results.json`](artifacts/scenario_results.json) — S1→S7,
all `ok` except S3, which is a deliberate structured `NOT_FOUND`.

**Proof 2 — MCP usability.** `python examples/agent_demo.py` launches the
server as a subprocess and speaks real MCP over stdio: `initialize`,
`tools/list`, then 12 `tools/call`. Transcript:
[`artifacts/mcp_session.md`](artifacts/mcp_session.md).

The demo has no LLM (allowed by the exercise, and it makes the run
reproducible), but its decisions are *not* hardcoded — it reads the broken id
out of a validation issue, recovers from a `NOT_FOUND` via
`details.did_you_mean`, and repairs an invalid argument using the list of check
names the server returned. Neither `sram0` nor `L7` appears as a literal in the
agent's logic. The design is copied to a temp directory first, so the run can
go all the way through a persisted repair without touching the fixture.

## Where to look first

| File | Why |
|------|-----|
| [`soc_explorer/registry.py`](soc_explorer/registry.py) | The single tool table + the response envelope. Start here. |
| [`soc_explorer/tools.py`](soc_explorer/tools.py) | All behavior. `update_property` / `_guarded_mutation` is the interesting part. |
| [`soc_explorer/validators.py`](soc_explorer/validators.py) | The 9 checks and why the built-in one is delegated to. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Design decisions, their costs, evolution note. |
| [`docs/TOOLS.md`](docs/TOOLS.md) | Tool catalog, error codes, checks. |
| [`artifacts/NOTES.md`](artifacts/NOTES.md) | Time spent, AI assistance, what running Orion revealed. |

## Connecting an MCP host (optional)

Not required for proof 2, but the server is a normal stdio MCP server. For
Claude Desktop (`claude_desktop_config.json`) or Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "soc-explorer": {
      "command": "/absolute/path/to/arteris-soc-explorer-starter/.venv/bin/python",
      "args": ["-m", "soc_explorer.mcp_server"],
      "cwd": "/absolute/path/to/arteris-soc-explorer-starter"
    }
  }
}
```

`pip install -e .` also exposes a `soc-explorer-mcp` console script, usable as
`command` instead. Add `"--design", "/path/to/other.json"` to `args` to point
at another design.

## Assumptions

- **One design per server process**, loaded at startup and held in memory. No
  `reload` tool: an external edit to the file goes unnoticed until restart.
- **Single writer.** `DesignStore.save()` has no lock and no transaction, so
  concurrent servers on one file would clobber each other. Mitigated, not
  solved, by previewing and by the `.bak.json` copy.
- **The design fixture is read-only ground truth.** Every test works on a
  `tmp_path` copy; the demo works on a temp copy. Nothing in this submission
  writes to `data/designs/orion_soc.json` unless you explicitly call a tool
  with `persist=true` on it.
- **`error`-severity issues define "unsafe".** Warnings and info never block a
  write.

## Known limits

- **Output schemas are documented, not enforced.** Inputs are pydantic models;
  results are plain dicts and every tool advertises the same generic envelope
  as `outputSchema`. Typing 12 output shapes was out of the timebox.
- **No add/remove of components or links.** `set_link_endpoint` retargets an
  existing link; that is the only structural edit.
- **Search weights are hand-tuned judgment.** They order Orion's cases the way
  a human would, and `matched_fields` exposes the reasoning, but they are not
  validated against a labelled corpus.
- **`bandwidth_oversubscription` compares static sums**, not concurrent
  traffic; it is a smell, hence `warning`. It also counts a dangling link's
  bandwidth (`L7` in `r1`'s egress), which the payload makes auditable.
- **`protocol_mismatch` reports nothing on Orion** — verified, not assumed. It
  is covered by a synthetic test instead.
- **The demo agent is scripted.** It proves the tools carry enough structure
  for a caller to self-correct; it does not prove an LLM would.
- **`.gitignore` was modified.** The starter ignored the three mandatory
  artifacts; they are now tracked.
