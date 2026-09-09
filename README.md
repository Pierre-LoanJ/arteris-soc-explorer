# Arteris — AI Software Engineer technical exercise

**Subject:** SoC Design Explorer MCP  
**Timebox:** 3–5 hours · **Follow-up:** 45–60 min live interview

## Context

Arteris builds solutions used in complex **SoC** designs. R&D teams rely on EDA workflows daily. We are investing in AI tooling (MCP servers, assistants, agents) to speed up design exploration, diagnosis, and carefully controlled edits.

This exercise gives you a **local fictional mini-EDA** and a sample SoC design (`orion_soc`). You will **not** need Arteris internal tools.

Your job: design and implement a **working MCP server** (Model Context Protocol) — or a clearly MCP-equivalent abstraction — so an AI agent can usefully explore and act on that SoC design.

We evaluate **engineering judgment and verified behavior**, not the ability to generate code that merely looks like an MCP wrapper.

## Objectives

1. Understand the mini-EDA data model and Python API quickly.
2. Expose coherent, agent-usable **tools** with structured inputs/outputs.
3. Handle errors predictably; document install & usage.
4. Ship automated tests **and measurable run artifacts** (see below).
5. Write a short note on evolving this toward a fuller R&D assistant.

## What you should build

At minimum, tools that allow an agent to:

- list design elements (components, links, …);
- search for an element;
- fetch properties of an element;
- detect simple inconsistencies;
- update a parameter in a controlled way;
- produce a short usable report.

You may add more tools if they clearly help.

### Two complementary proofs

We evaluate your work along two separate axes. Do both.

#### 1. Tool behavior (required scenarios — not via MCP wire protocol)

Automated scenarios check that your tools behave correctly on `orion_soc`
(list, get, search, validate, update, report, and error paths).

How it works:

1. Implement your tool layer (the same logic your MCP server will expose).
2. Wire `soc_explorer/adapter.py` so `get_adapter()` routes `list_tools()` /
   `call(...)` to **your** tools — not only the template `MiniEda` wrappers.
3. Run `python scripts/run_required_scenarios.py`. The runner imports your
   adapter and invokes tools **in-process** (plain Python). It does **not**
   speak the MCP protocol; that is intentional so we can score behavior
   without starting a server.

Wire the adapter to the **same** functions/schemas your MCP tools use, so
scenario results reflect your real contracts (errors, validation, shapes).

See `docs/REQUIRED_SCENARIOS.md` and comments in `soc_explorer/adapter.py`.

#### 2. MCP integration & agent usability

Separately, show that an agent can **discover and use** your tools over MCP.

Acceptable demos (pick one or combine):

- a **small custom agent/client** that connects to your MCP server and runs a
  short exploration task; **or**
- an **existing orchestrator** (e.g. Cursor, Claude Desktop, or another MCP
  host) with your server configured — document how to connect it and show a
  short transcript / screenshots of meaningful tool use on `orion_soc`.

A remote LLM is optional; offline or scripted clients are fine if they still
exercise discovery + tool calls through your MCP surface.

Also provide:

- **automated tests** — the starter already ships a baseline suite under `tests/`;
  keep it green. Add more tests if useful for your tools; if the existing
  coverage already meets the minimum for your submission, passing that suite
  is enough;
- **documentation** (install, run, tool catalog, MCP host setup if you use one,
  assumptions & limits);
- a **short architecture / evolution note** (≤ 2 pages);
- the **measurable artifacts** listed below (mandatory).

## Measurable artifacts (mandatory)

Your submission is reviewed partly by **scripts and checklists**, not only by reading code. Produce:

| Artifact | Purpose |
|----------|---------|
| `artifacts/tools_manifest.json` | Machine-readable list of your tools (name, arity, mutates?) |
| `artifacts/scenario_results.json` | Output of the required scenarios runner |
| `artifacts/pytest_stdout.txt` | Exact console capture of `pytest -q` on your suite |
| `artifacts/NOTES.md` | Time spent, AI-assisted parts, limits you observed **by running the design** |

### How to generate scenario results

1. Complete proof **1** above: wire the adapter to **your** tools (not only `mini_eda`). See `soc_explorer/adapter.py` and comments inside.
2. Run:

```bash
python scripts/run_required_scenarios.py
pytest -q | tee artifacts/pytest_stdout.txt
```

3. Commit/send the generated files under `artifacts/`.

Required scenarios are defined in `docs/REQUIRED_SCENARIOS.md`.  
**Do not hand-write fake scenario results.** The runner embeds a design file fingerprint; mismatches are a review flag.

## Constraints

- Python 3.11+ recommended (starter is Python); other stacks OK if justified and documented — you must still provide the artifacts (adapt the runner if needed).
- Keep `mini_eda` as the design source of truth — do not replace `MiniEda`
  wholesale. Your tools sit on top of it. You are **not** required to expose
  the stock methods as-is: adapting or extending behavior (wrappers, richer
  validation, clearer errors, different shapes) so tools are agent-usable is
  expected; thin adaptation layers are fine.
- Core functionality must work offline against the local design file.
- A remote LLM is optional for proof **2** (custom agent or MCP host demo); do not commit secrets (see `.env.example`).
- Stay within ~3–5 hours. Prefer a sharp, **working** prototype over a shallow feature dump.
- **Do not try to do everything.** Not every item needs deep, complete treatment —
  especially extra tests, polish documentation, and the evolution note. Ship a
  solid core (tools + the two proofs + measurable artifacts) and leave honest
  gaps. 

## Free choices

Tool list & granularity, schemas, whether/how to use a LLM, mutation safety strategy (dry-run, etc.), repo layout, and improvements you think matter — **call them out** in the docs.

## AI tooling policy

You **may** use AI assistants (Cursor, Copilot, ChatGPT, …).

In exchange you must:

- be able to explain and **modify** every significant piece in the live session;
- state in `artifacts/NOTES.md` what was AI-assisted vs. designed/validated by you;
- actually run your tools on `orion_soc` and report what you observed (including anything surprising).

In the live interview you will be asked to **discuss the requests** you made to
the assistant(s) and how you steered the work. Optionally, leave a short note of
those prompts in `artifacts/NOTES.md` (or a small companion file under
`artifacts/`) so the discussion is easier — a few representative requests are
enough; a full chat dump is not required.

Submitting code you cannot operate or debug is a hard fail signal.

## Quickstart (starter only)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
python examples/smoke_eda.py
python scripts/run_required_scenarios.py   # works on the template adapter; replace with yours
```

Scenarios exercise the adapter in-process; they do not replace the MCP demo (proof 2).

Design fixture: `data/designs/orion_soc.json`  
API entrypoint: `mini_eda.MiniEda`  
Glossary: `docs/domain_glossary.md`  
MCP hints (optional): `examples/mcp_stub_notes.md`

## Success criteria

A submission succeeds if it is **runnable**, **structured**, **understandable**,
**honest about limits**, ships **consistent measurable artifacts**, passes the
required scenarios via **your** adapter (proof 1), and demonstrates **MCP agent
usability** (proof 2). Perfection is not required — incomplete docs, thin
extra tests, or a short evolution note are fine when you can discuss them
orally. We are not scoring a production product.

## Submission

Send a repo link or archive **before** the interview, including the `artifacts/` directory. Mention approximate time spent.

Good luck — we look forward to your approach.
