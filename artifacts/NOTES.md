# Submission notes

## Time spent

- **~4 h** (target 3–5 h). Rough split: reading the starter and running it
  ~0.5 h · domain core (graph, checks, errors) ~1 h · tool layer, schemas,
  registry, mutation safety ~1.5 h · MCP server + client demo ~1 h · tests,
  docs, artifacts ~1 h.

## AI assistance

**Assistant:** Claude Code (Opus 5), one interactive session.

**What the assistant produced.** Essentially all of the code text — module
bodies, docstrings, the test suite — and the documentation prose in
`SUBMISSION.md`, `docs/ARCHITECTURE.md`, `docs/TOOLS.md` and the first draft of
this file. The architectural proposals were also the assistant's: the single
shared registry, the named-check registry, the preview-by-default mutation
policy. They were argued to me step by step rather than handed over, which is
how I ended up able to account for them.

**What I decided.** Two choices at the outset shaped everything after:

- a **scripted, offline MCP client** for proof 2 rather than an LLM-driven
  agent — reproducible in front of a reviewer, no API key, and explicitly
  allowed by the exercise;
- a **step-by-step build with an explanation at each stage** rather than one
  hand-off, precisely because I have to defend this code out loud.

Later, in the same spirit: I declined a Nix/devenv setup so the submission
keeps the single documented `venv + pip` path, and I asked for the untouched
starter to be committed first so `git diff` shows exactly what was added.

**What I did myself.** Ran the scenario runner and the test suite; wired the
server into an MCP host through `.mcp.json` to exercise it outside the shipped
demo; reviewed the diff against the starter baseline.

**How the numbers here were obtained.** Every figure in this file comes from
running the design, not from reasoning about it. Three defects were caught that
way rather than by reading the code — by the test suite and by running the
tools:

- a `degree()` that counted the self-loop twice and reported `link_count: 8`
  for `r0` — a graph-theoretic answer to a question nobody asked; the fix
  distinguishes "links attached" from "capacity consumed";
- a `_backup()` that crashed on a design outside the repository, which the
  tests hit because they work on copies in `tmp_path`;
- leftover draft lines in two files.

I can explain each of the three and why the fix is what it is. None of them
was spotted by inspection — which is itself the argument for the test suite.

### Representative requests I made to the assistant

Verbatim in intent, translated from French:

1. *"Let's explore this repo. I know nothing about it — it was given to me for
   a technical interview and I have to take it over and build what is asked."*
2. Chose, when offered the alternatives: **scripted offline MCP client** for
   proof 2, and **step-by-step with explanations** rather than a single
   hand-off.
3. *"Go ahead, continue."* — repeatedly, once the direction was agreed.
4. *"How can the scenarios validate the adapter's results?"*
5. *"Before a modification is written, who decides? What is actually modified?
   Where does the source of truth live?"*
6. *"I can't see the difference between the original sources and what we edited
   together"* — which produced the baseline commit of the untouched starter.

Questions 4 to 6 are the ones that changed the submission — 6 in particular
exposed that the starter ships CRLF line endings and that my early edits had
silently rewritten four of the recruiter's files (see item 12 below).

### The method, and what it trades

The exercise authorises AI assistants, requires that I can explain and modify
every significant piece, and sets a 3–5 h budget. Those three pull against each
other: without an assistant the budget goes, with one the ownership does. How a
candidate resolves that is itself a choice, so I will state mine rather than
leave it to be inferred.

**Delegate the writing, own the constraints and the account.**

The two architectural constraints that shape this submission are not mine —
they are in the statement: *"wire the adapter to the same functions your MCP
tools use"* and *"do not replace `MiniEda` wholesale"*. Read together they
force the tool logic below both entry points and force a case-by-case treatment
of the engine's weaknesses; the shared registry and the delegate / wrap /
bypass / extend split follow from them rather than from taste. What I did was
hold the work to those constraints, decide what the statement leaves open — an
offline reproducible demo rather than an LLM-driven one, a step-by-step build
rather than a hand-off — and then interrogate every result until I could
account for it.

**What that buys.** I can say why each decision is what it is and what it
costs. `docs/ARCHITECTURE.md` pairs every significant choice with its price,
and the limits listed in `SUBMISSION.md` are the ones I actually hit, not a
generic disclaimer.

**What it costs, plainly.** I did not type this code. My fluency is in the
reasoning behind it, not in the keystrokes, and those are not the same skill.
If that distinction matters for the role it is a fair thing to probe — I would
rather you probe it knowing where I stand than discover it.


## What running Orion actually revealed

Facts, each reproducible from the artifacts or a one-liner:

1. **`MiniEda.validate()` returns 0 issues** on a design that has a dangling
   link, an unreachable memory, a self-loop and a component with no clock
   domain. Our checks report **11** (2 error, 4 warning, 5 info). The report
   prints both counts side by side for that reason.
2. **The built-in `DUPLICATE_COMPONENT_ID` check is dead code.** It iterates
   over the keys of a `dict`, where a duplicate is structurally impossible.
   Worse, `DesignStore.load()` collapses duplicates silently: a file with two
   components sharing an id loads as **one** component (verified with a
   synthetic fixture in `tests/test_validators.py`). Duplicates can only be
   caught on the raw JSON, which is what `duplicate_id_in_source` does.
3. **`L7` points at `sram_l2`, which does not exist** — the component id is
   `sram0` and its *display name* is `SRAM_L2`. The fixture's own notes warn
   that "display names are not necessarily equal to ids"; the trap is that the
   broken value looks exactly like a lowercased display name.
4. **Consequence: `sram0` is unreachable.** `find_path("cpu0", "sram0")`
   returns `found: false`; the only link into the L2 SRAM is the broken one.
   `list_components` shows `link_count: 0` for it.
5. **`MiniEda.search` is case-sensitive and unranked.** `search("r0")` returns
   9 undifferentiated hits including `ddr0`; `search("SRAM")` finds `sram0` but
   `search("sram")` finds it *and* the broken link `L7`, which is the more
   useful answer and only appears with the other casing. `search("AXI4")`
   returns **nothing** at all — properties are not searched, although the
   protocol is the most obvious thing to look for in this design. Hence ranked,
   case-insensitive, property-aware search with `matched_fields`.
6. **`update_property` cannot repair `L7`, and fails silently if you try.**
   `prop_path` is relative to `properties`, so `prop_path="dst"` creates
   `properties.dst` and leaves the structural `dst` untouched — no error, no
   effect. That is why `set_link_endpoint` exists (test:
   `test_structural_fields_are_out_of_reach`).
7. **Repairing `L7` has a side effect the preview surfaces:** it resolves
   `DANGLING_LINK_ENDPOINT` and `UNCONNECTED_COMPONENT`, and *creates* a new
   `CLOCK_DOMAIN_CROSSING` (`r1` is in `cd_noc`, `sram0` in `cd_sys`). A fix
   that silently adds a CDC path is exactly what a preview should show before
   the write, not after.
8. **`r0` and `r1` are oversubscribed** (39 628 in / 36 200 out, and 19 200 in
   / 10 400 out). The `r0` figure is only well-defined once you decide how a
   self-loop counts: `L_loop` consumes switching capacity in both directions,
   so `bandwidth_balance` counts it twice — while `link_count` counts it once,
   because "how many links touch this node" is a different question. Both
   choices are documented in `graph.py`; the issue payload lists the links so
   the number can be audited.
9. **`dbg_probe` is an `observer` used as the `src` of `L8`** and is the only
   component with no `clock_domain`. The missing clock domain is flagged; the
   "an observer initiates traffic" smell is **not** — I was not willing to
   invent a domain rule I could not defend. It is a candidate check.
10. **The starter's `.gitignore` excluded three of the four mandatory
    artifacts** (`scenario_results.json`, `tools_manifest.json`,
    `pytest_stdout.txt`) while the README requires them in the submission. It
    also pre-ignores `data/designs/*.bak.json`, which is where the backup
    naming convention in `_backup()` comes from.
11. **`pip install "mcp>=1.0"` now resolves to 2.x**, where `FastMCP` was
    renamed to `MCPServer` and the `@server.list_tools()` decorators were
    replaced by `on_list_tools` / `on_call_tool` callbacks. Code written
    against 1.x examples does not import. `pyproject.toml` pins
    `mcp>=2.0,<3` and the server is written against the 2.x API.

12. **The whole starter ships with CRLF line endings.** Python's text mode
    silently rewrites them: reading a file with `read_text()` and writing it
    back with `write_text()` converts CRLF to LF, so my first edits made four
    of the recruiter's files look entirely rewritten in `git diff`. I restored
    CRLF in the files I only extended (`README.md`, `pyproject.toml`,
    `.gitignore`, this file) so the diff shows what I actually changed. Files I
    wrote from scratch use LF. I deliberately did **not** renormalise the
    repository: that would have modified `mini_eda/` and the other files I am
    supposed to leave as the source of truth.

## Known limits

Full list in [`SUBMISSION.md`](../SUBMISSION.md#known-limits). The four that
matter most:

- **Outputs are not typed.** Inputs are pydantic models; results are plain
  dicts behind one generic `outputSchema`. Deliberate timebox call.
- **No `reload` tool.** The server holds the design in memory for its whole
  lifetime; an external edit to the file goes unnoticed until restart.
- **Single writer, no transaction.** `DesignStore.save()` has no lock. Preview
  plus `.bak.json` is a mitigation, not a solution; batched atomic edits are in
  the evolution note.
- **The demo agent has no LLM.** It proves the tool responses carry enough
  structure for a caller to self-correct; it does not prove a model would pick
  the right tools.

## Restoring the fixture

Nothing here writes to `data/designs/orion_soc.json`: tests and the demo work
on copies. If you *do* run a tool with `persist=true` against it, the previous
content is in `data/designs/orion_soc.bak.json` — restore with
`mv data/designs/orion_soc.bak.json data/designs/orion_soc.json`. The design
fingerprint recorded in `scenario_results.json` will tell you if it moved.
