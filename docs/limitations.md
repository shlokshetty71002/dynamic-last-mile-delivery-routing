# Known limitations and interpretation guardrails

## Data limitations

- OpenStreetMap is community-maintained and time-varying; missing or incorrect one-way,
  `maxspeed`, access, turn-restriction, name, and geometry tags can affect routes.
- The rectangular M50 catchment includes Dublin Bay and peripheral areas and is not a formal
  catchment boundary. The strong-component step intentionally excludes unreachable fragments.
- Missing speeds are imputed by broad road class. The resulting shortest-time paths are planning
  approximations, not navigation instructions.
- Nominatim candidates and curated reference coordinates may not represent the best vehicle
  entrance. The snap-distance guard detects gross mistakes, not every entrance error.

## Operational limitations

- No live traffic, observed incident feed, queue propagation, traffic-signal delay, parking,
  loading-bay availability, weather, driver breaks, or stochastic travel times.
- Scenario files are simulated closures/slow zones. Polygon intersection can close both
  directions or several adjacent carriageways depending on OSM geometry.
- The reactive driver discovers a disruption exactly at the first blocked edge. Real drivers may
  receive partial information earlier or discover multiple sequential incidents.
- Replanning occurs once at first discovery for each affected route. Continuous rolling-horizon
  dispatch and new customer requests are out of scope.
- Service time is a fixed 180 seconds by default. Time-window fields are preserved but v1 does
  not optimise lateness or enforce appointment windows.

## Optimisation limitations

- NN, directed local search, and Clarke-Wright are deterministic heuristics; they do not certify a
  global optimum. OR-Tools is a bounded-time benchmark, not proof of optimality.
- `N≤50` controls all-pairs path storage and interactive latency. Larger commercial instances
  need sparse/on-demand routing and more scalable VRP methods.
- Vehicle capacities are homogeneous; there are no vehicle-specific costs, skills, shifts,
  fixed-use costs, split deliveries, pickup-and-delivery precedence, or depot reloads.
- A no-regret fallback guarantees finite `T3≤T2` by policy. It measures the benefit of offering a
  replan with fallback, not the unconstrained quality of every heuristic candidate.

## Environmental limitations

- Fuel and CO₂ are linear functions of distance. Vehicle mass, load, speed, idling, cold starts,
  road gradient, and driving style are absent.
- The CO₂ factor is direct diesel combustion only. The calculation is not CO₂e, well-to-wheel,
  or a life-cycle assessment.
- Default efficiency and fuel price are illustrative assumptions. Replace them with fleet data
  before financial or environmental decision-making.

## Evidence limitations

- The Streamlit **feasible saving demonstration** is deliberately selection-conditioned: it
  searches closures on the chosen baseline route, rejects disconnected candidates, and retains
  only a complete positive-saving comparison. It explains T1/T2/T3 clearly, but its saving must
  not be pooled with the unbiased committed/random experiment results.
- Deterministic CI uses a hand-built directed fixture so it cannot validate current OSM counts or
  visual plausibility. The separate manual live-network workflow records that external evidence.
- Runtime numbers vary with hardware, cache warmth, OSM graph size, and process concurrency.
- Bootstrap intervals describe the committed/generated scenario sample, not all future Dublin
  disruptions. Correlation and scenario-selection bias limit population claims.
- The UI is an academic demonstration, not a secure dispatch service: no authentication,
  concurrent editing, audit retention, hosted SLA, or turn-by-turn navigation.
