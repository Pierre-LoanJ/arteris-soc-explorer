# Architecture & evolution note

## 1. Shape of the solution

```
                    ┌──────────────────────────────┐
   proof 1          │  scripts/run_required_...py  │
   (in-process)     └──────────────┬───────────────┘
                                   │ get_adapter()
                    ┌──────────────▼───────────────┐
                    │  soc_explorer/adapter.py     │  ~30 lines
                    └──────────────┬───────────────┘
                                   │
   proof 2          ┌──────────────▼───────────────┐        ┌──────────────────┐
   (MCP stdio) ─────►  soc_explorer/registry.py    ◄────────┤  mcp_server.py   │
                    │  name → schema+handler+      │        │  MCP types only  │
                    │  mutates, response envelope  │        └──────────────────┘
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  tools.py  (SocExplorer)     │  the only behavior
                    ├────────┬────────┬────────┬────────┤
                    │schemas │ graph  │validat.│ search │
                    │pydantic│derived │9 checks│ranking │
                    │        │topology│        │ report │
                    └────────┴───┬────┴────────┴────────┘
                                    │ reads & writes through
                    ┌───────────────▼──────────────┐
                    │  mini_eda (unchanged)        │
                    └──────────────────────────────┘
```

**One registry, two consumers.** The exercise asks for the adapter to be wired
to the same functions the MCP server exposes. Rather than promising it in a
README, the design makes drift impossible: a tool's name, input schema,
handler and `mutates` flag are declared once in `registry.py`. `adapter.py` is
30 lines, `mcp_server.py` only translates MCP types, and both share
`registry.invoke()` — which owns argument validation, the response envelope and
the error mapping. A tool that misbehaves in the scenarios misbehaves
identically over MCP, by construction.

**`mini_eda` stays the source of truth.** It still owns loading, dotted-path
assignment, saving and its own `validate()` — which our `builtin_bandwidth`
check *delegates to* rather than reimplements. Everything we add is the layer
it does not have: resolution hints, ranked search, a topology index, richer
checks, and a write path that previews before it commits.

**Pydantic models are the contract.** One declaration yields the validation,
the MCP `inputSchema`, and the descriptions an LLM reads when picking a tool.
`extra="forbid"` turns a misspelled argument into an `INVALID_ARGUMENT` with
the list of violations instead of a silently ignored key.

## 2. Decisions worth challenging

| Decision | Why | Cost |
|----------|-----|------|
| Failures are **values**, not exceptions (`{"ok": false, ...}` with a stable `code`) | An agent must branch without parsing prose; over MCP a tool failure is `isError=true` **with** a payload, which is what lets a model retry | Callers must check `ok`; a bug can hide behind a well-formed error |
| Errors carry `did_you_mean` | Orion deliberately confuses ids and display names (`sram_l2` vs `sram0`); the demo's agent recovers from a `NOT_FOUND` using nothing but that field | Suggestions are heuristic (substring + `difflib`) and could mislead |
| Mutations **preview by default** (`persist=false`) | The design file is a shared artifact with no lock and no transaction; a preview that returns the diff *and* the validation delta is enough to decide | Two round trips for a real edit |
| A write that introduces an `error`-severity issue is **refused** unless `force=true` | The safety policy is driven by the validators, not by ad-hoc rules about specific fields; adding a check automatically hardens the write path | A new noisy check could block legitimate edits |
| Only one structural edit (`set_link_endpoint`) | Property edits cannot repair the defect the checks actually find; retargeting is enough to close the loop diagnose → propose → apply | Not a general graph editor: no add/remove of components or links |
| Traversal is **directed** | That is the semantics of a link; `find_path("cpu0","sram0")` returning "no path" is the true answer on broken Orion | An agent asking about physical adjacency needs `get_neighbors` instead |
| Outputs are plain dicts, inputs are typed models | Input validation is where the failures are; typing 12 output shapes would have cost more than it returns inside the timebox | Output shapes are documented, not enforced — see limits |
| Ranked search with `matched_fields` | `MiniEda.search` cannot distinguish the router `r0` from the incidental substring in `ddr0`; scores plus the matching field make that legible to a model | Weights are hand-tuned judgment, not learned |

## 3. Evolution towards an R&D assistant

**Next (hours).** Typed output models (pydantic) published as per-tool
`outputSchema`, so clients validate results as strictly as arguments. A
`reload_design` tool, since the server currently holds state for its whole
lifetime and an external edit goes unnoticed. Pagination tokens on the list
tools; today they only truncate and say so.

**Then (days).** *Transactions*: a `plan_changes` / `apply_plan` pair so an
agent can batch several edits and get one validation verdict and one atomic
write, instead of N previews and N backups. *Provenance*: every mutation
appends to an audit log (who, when, which tool, the diff, the validation
delta) — the current single `.bak.json` is a floor, not a story. *Resources
and prompts*: MCP resources for the design file and the report so a host can
attach them as context without a tool call, plus prompt templates for the
recurring questions ("review this design", "explain this CDC path").

**Structural (weeks).** The real bottleneck is not the tool surface, it is
**state**: one JSON file, one process, no concurrency control. A real assistant
sits in front of a design database with revisions, so tools take a revision id
and mutations become proposals a human can review — the difference between an
agent that edits your design and an agent that opens a merge request. Two more
axes matter once that exists: a **check plugin API** so domain experts add
rules without touching the server (the check registry is already the seam),
and **evaluation** — a scenario corpus with expected tool sequences, scored
automatically, because the only way to know an agent got *better* is to
measure it on tasks like "find why this memory is unreachable" rather than to
read its transcript.

**What I would not build.** An LLM inside the server. Ranking, validation and
safety belong in deterministic code that can be tested; the model belongs on
the other side of the protocol, which is exactly what MCP is for.
