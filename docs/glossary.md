# Glossary

| Term | Meaning |
|---|---|
| Base graph | Directed Dublin driving network before a simulated disruption. |
| Cache key | Hash of all inputs that determine an expensive artefact. |
| Depot | User-chosen origin and final destination; a special stop with zero service time. |
| Disrupted graph | Non-mutating graph copy with a scenario applied and an audit record attached. |
| Information model | Rule for when the driver knows a disruption: `reactive` or `omniscient`. |
| Instance | Depot, dynamic stops, fleet/capacity, provenance, seed, and schema version. |
| `K` | User-selected vehicle count, constrained to `1≤K≤N`. |
| `N` | Derived delivery-stop count, constrained to `1≤N≤50`; never stored as a constant. |
| No-regret fallback | Use the frozen detour if the candidate T3 replan is worse. |
| Oracle | OR-Tools solver benchmark or `T3_oracle`; context distinguishes solver and information benchmark. |
| Reactive | Follow the original path until a blocked edge is encountered, then detour/replan. |
| SCC | Strongly connected component: each node can reach every other in a directed graph. |
| Scenario | Schema-versioned list of closures/slow zones plus source and description. |
| Saving (%) | `100 × (T2-T3)/T2`, defined only for finite T2 and T3. |
| Stop | User-chosen delivery location snapped to a routable graph node. |
| `T1` | Planned route time under normal graph conditions. |
| `T2` | Frozen planned stop-order time under the selected disruption information model. |
| `T3` | Sunk time plus remaining-stop replan from first reactive discovery. |
| `T3_oracle` | Full-information re-optimisation from time zero, reported separately. |
| Tidy CSV | One batch run per row and one metric per column. |
