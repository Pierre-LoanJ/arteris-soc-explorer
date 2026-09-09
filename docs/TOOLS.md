# Tool catalog

Machine-readable source of truth: [`artifacts/tools_manifest.json`](../artifacts/tools_manifest.json)
(generated from the registry, with the full JSON Schema of every input).

Every tool returns the same envelope:

```json
{"ok": true,  "result": <tool-specific payload>}
{"ok": false, "error": {"type": "...", "code": "...", "message": "...", "details": {...}}}
```

| Tool | Mutates | Required | Optional |
|------|---------|----------|----------|
| `describe_design` | no | — | — |
| `list_components` | no | — | `kind`, `limit` |
| `get_component` | no | `component_id` | — |
| `list_links` | no | — | `src`, `dst`, `limit` |
| `get_link` | no | `link_id` | — |
| `search` | no | `query` | `types`, `case_sensitive`, `search_properties`, `limit` |
| `get_neighbors` | no | `component_id` | `direction` |
| `find_path` | no | `src`, `dst` | `max_hops` |
| `validate_design` | no | — | `checks`, `min_severity` |
| `update_property` | **yes** | `element_id`, `prop_path`, `value` | `persist`, `force` |
| `set_link_endpoint` | **yes** | `link_id`, `role`, `component_id` | `persist`, `force` |
| `export_report` | no | — | `format` (`text` \| `markdown` \| `json`) |

## What each tool adds over `mini_eda`

| Tool | Beyond the stock API |
|------|----------------------|
| `describe_design` | New. Inventory + property keys + clock domains + the names of the available checks, so an agent can plan without guessing. |
| `list_components` | Adds `link_count` per component (Orion's `sram0` shows `0`), the list of known kinds, and an explanatory `note` when a `kind` filter matches nothing. |
| `get_component` | Adds clock domain, attached link ids and the component's bandwidth balance. |
| `list_links` / `get_link` | Adds `src_exists` / `dst_exists` and clock-domain crossing, so a broken link is visible in the payload. |
| `search` | Case-insensitive by default, ranked, reaches properties, and every hit reports **which field matched and how** (`exact` / `prefix` / `substring`). `MiniEda.search` is case-sensitive, unranked, ignores properties and returns `[]` for an empty query — here that is an `INVALID_ARGUMENT`. |
| `get_neighbors`, `find_path` | New. `mini_eda` has no topology query at all. |
| `validate_design` | 9 named checks instead of 2 (the built-in ones are delegated to, not reimplemented), with severities, per-issue `details`, check selection and severity filtering. |
| `update_property` | Preview by default, diff, validation impact, refusal of writes that introduce errors, backup before overwrite. `MiniEda.update_property` persists immediately with no backup. |
| `set_link_endpoint` | New. The one structural edit exposed, because a dangling endpoint cannot be repaired through `properties`. |
| `export_report` | Adds the extended issue count **next to** the built-in one, the actionable issues and the oversubscribed nodes; markdown output. |

## Error codes

Branch on `error.code` — the strings are stable.

| Code | Meaning | Useful `details` |
|------|---------|------------------|
| `NOT_FOUND` | Id does not resolve | `did_you_mean`, `exists_as`, `use_tool` |
| `INVALID_ARGUMENT` | Schema or precondition violation | `violations`, `expected_schema`, `available_checks` |
| `UNKNOWN_TOOL` | No such tool | `available_tools` |
| `UNSAFE_MUTATION` | Write refused by the safety policy | `blocking_issues`, `retry_with` |
| `INTERNAL_ERROR` | Bug on our side, never a raw traceback | — |

## Validation checks

| Check | Severity | Fires on Orion |
|-------|----------|----------------|
| `builtin_bandwidth` (delegates to `MiniEda.validate`) | error | no |
| `duplicate_id_in_source` | error | no |
| `dangling_link_endpoint` | error | **yes** — `L7 → sram_l2` |
| `unconnected_component` | error (initiator/target) · warning | **yes** — `sram0` |
| `self_loop` | warning | **yes** — `L_loop` |
| `missing_clock_domain` | warning | **yes** — `dbg_probe` |
| `bandwidth_oversubscription` | warning | **yes** — `r0`, `r1` |
| `protocol_mismatch` | warning | no (routers declare no protocol) |
| `clock_domain_crossing` | info | **yes** — 5 links |
