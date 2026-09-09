# MCP implementation notes (optional reading)

You are expected to design the MCP server yourself.

Useful references:
- Model Context Protocol specification and Python SDK
- Prefer structured tool inputs/outputs (e.g. Pydantic models)
- Keep the mini_eda package as the source of truth for design state
- Do not replace `MiniEda` wholesale; tools may adapt/extend stock behavior
  (you need not mirror its methods 1:1)

## How this relates to the two proofs

- **Proof 1 (scenarios):** `scripts/run_required_scenarios.py` calls
  `soc_explorer.adapter:get_adapter` **in-process**. Wire the adapter to the
  same tool functions your MCP server exposes. No MCP wire protocol here.
- **Proof 2 (MCP / agent usability):** expose those tools via a real MCP
  server, then either:
  - write a small client/agent that connects over MCP, **or**
  - connect an existing host (Cursor, Claude Desktop, …) and document a short
    session where the host discovers and uses your tools on `orion_soc`.

Suggested layout (non-prescriptive):

```
src/orion_mcp/
  server.py      # MCP server entrypoint
  tools.py       # tool registrations (shared with the adapter)
  schemas.py     # request/response models
examples/
  agent_demo.py  # optional custom client/agent over MCP
```

Do not commit API keys. Use `.env` locally if you call a remote LLM.
