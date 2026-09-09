"""SoC Design Explorer — agent-facing tool layer over ``mini_eda``.

Layout:

- ``tools``      — the tool implementations (single source of truth)
- ``registry``   — name -> schema + handler + mutates, and the response envelope
- ``adapter``    — proof 1: in-process entry point for the scenario runner
- ``mcp_server`` — proof 2: the same registry served over MCP (stdio)
- ``validators`` — consistency checks
- ``graph``      — derived topology index (adjacency, paths, bandwidth)
- ``search``     — ranked search and its weights
- ``report``     — text/markdown rendering of the report
- ``schemas``    — pydantic input models (validation + MCP inputSchema)
- ``errors``     — stable, agent-branchable error codes

``mcp_server`` is intentionally *not* imported here, so the scenario runner
never needs the MCP SDK to be installed.
"""

from .adapter import SocExplorerAdapter, get_adapter
from .tools import SocExplorer

__all__ = ["SocExplorer", "SocExplorerAdapter", "get_adapter"]
