# Mathematical modelling contract

## Sets, graph, and units

Let `G=(V,E)` be a directed road multigraph. Each edge `e` has length `l_e` in metres and travel
time `τ_e` in seconds. The user supplies depot `0`, delivery set `S={1,…,N}`, vehicle count `K`,
non-negative demand `q_i`, optional capacity `Q`, and service time `s_i`. Version 1 requires
`1 ≤ N ≤ 50` and `1 ≤ K ≤ N`.

Shortest-path cost is

\[
d_G(i,j)=\min_{p:i\leadsto j}\sum_{e\in p}\tau_e.
\]

Because `G` is directed, generally `d_G(i,j) ≠ d_G(j,i)`. The matrix and every route move retain
this asymmetry.

## Objective and constraints

For vehicle routes `R_k=(0,r_{k1},…,r_{km_k},0)`, the primary objective is

\[
\min \sum_{k=1}^{K}\left(\sum_{j=0}^{m_k}d_G(r_{kj},r_{k,j+1})
+\sum_{j=1}^{m_k}s_{r_{kj}}\right).
\]

Every delivery appears exactly once, every route begins/ends at the selected depot, and, when
capacity is present, `Σ q_i ≤ Q` on each vehicle route. Service time is constant across route
orders, but remains included in reported operational time and replan state. Time windows exist in
the schema but are not optimised in v1.

## Primary heuristic

Nearest neighbour greedily chooses the lowest directed cost from the current point. Local search
then evaluates complete directed route cost for each 2-opt reversal and one-customer relocate;
it never applies the symmetric-TSP boundary-edge shortcut. Only strictly improving moves are
accepted, so the trajectory is monotone. For `K>1`, directed Clarke-Wright merges capacity-safe
routes. OR-Tools implements the same solver interface only as a benchmark.

These methods are transparent and deterministic, but they do not prove global optimality.

## Disruption comparison

`T1` is the baseline route cost on normal graph `G`. A scenario creates disrupted graph `G'`.

- `T2 reactive` (headline default): follow the original edge path until the first blocked edge;
  from that actual node, detour to the next planned stop on `G'`, while freezing stop order.
- `T2 omniscient`: know `G'` at time zero but freeze stop order; use a shortest path on `G'` for
  each leg.
- Infeasible: if a required next stop/depot is unreachable, store structured partial service and
  no finite `T2`; never discard the observation.
- `T3`: at first reactive discovery, retain sunk distance/time, optimise remaining unserved stops
  from the actual node, and return to the original depot.
- `T3_oracle`: optimise all stops on `G'` at time zero. It is reported separately and is never
  substituted for the headline `T3`.

\[
\operatorname{Saving}(\%)=100\frac{T2-T3}{T2}.
\]

A no-regret policy compares the candidate replan with the frozen detour and chooses the latter if
the heuristic is worse. Consequently every finite reported `T3 ≤ T2`; an assertion protects this
contract. With a non-touching disruption, the regression contract is exactly `T1=T2=T3`.

## Sustainability estimates

For route distance `D` metres, default estimates are:

\[
\text{fuel L}=\frac{D}{1000}\frac{8.5}{100},\qquad
\text{CO₂ kg}=\text{fuel L}\times2.68.
\]

The 2.68 kg CO₂/L factor rounds SEAI's 2.682 direct-combustion factor for petroleum diesel.
The 8.5 L/100 km efficiency and €1.75/L price are user-changeable scenario assumptions, not
measured fleet data. These are tailpipe/direct-combustion estimates, not life-cycle emissions.

## Statistical summaries

Batch output keeps one row per instance/scenario/seed. Finite savings are grouped by scenario and
reported with mean, median, interquartile range, and a seeded 2,000-resample percentile 95%
bootstrap confidence interval for the mean. Helped/neutral/hurt use tolerance `10⁻⁹`. Infeasible
cases remain in the raw CSV and are excluded only from statistics that mathematically require a
finite percentage.
