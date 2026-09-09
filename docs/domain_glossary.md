# Domain glossary (short)

| Term | Meaning in this exercise |
|------|---------------------------|
| **SoC** | System on Chip — the overall design under exploration |
| **Component** | A block in the design (CPU, memory, router, peripheral, …) |
| **Initiator** | Master that starts transactions (CPU, GPU, DMA…) |
| **Target** | Endpoint that responds (SRAM, DDR, peripherals…) |
| **Router / interconnect node** | Forwards traffic between components |
| **Link** | Directed connection from `src` to `dst` with properties |
| **QoS** | Quality-of-service class / priority hint |
| **Clock domain** | Timing island; crossing domains has design implications |
| **MCP** | Model Context Protocol — standard way to expose *tools* to AI agents |
| **Tool** | A typed function an agent can call (list, get, validate…) |

You do **not** need prior interconnect expertise. Treat the JSON as a typed graph of a SoC design and build agent-facing tools that make it operable.
