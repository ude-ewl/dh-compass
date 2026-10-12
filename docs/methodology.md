# DH-COMPASS methodology

DH-COMPASS compares district-heating expansion with decentralized heat supply in **North Rhine-Westphalia (NRW), Germany**. It combines regional building demand, streets, temperature-dependent demand, technology/cost assumptions and local heat potentials. Candidate ordering and connection form a heuristic: a solver optimum for a supply model does not imply a globally optimal network topology.

## Inputs and configuration

`configs/default.toml` is the source of defaults; scenario TOML files inherit and override selected choices. Typed configuration flows into runtime factories, cost functions and an explicit optimization context. The browser submits only a selected bbox and uses server-owned defaults. See [configuration.md](configuration.md) to change assumptions for new runs.

Original workbooks and geospatial data are external local inputs, not bundled datasets. OSM streets determine routing; Open-Meteo ERA5-Land weather is loaded for the selected location/year and cached with provenance. NRW building-demand/resource data defines current coverage. See [input schemas](../data/README.md) and [DATA_LICENSES.md](../DATA_LICENSES.md).

## Pipeline

1. Load configured buildings and streets, assign buildings to street edges and aggregate demand.
2. Calculate linear heat density (annual demand divided by edge length), screen using the configured threshold and form/order candidate subgraphs.
3. Build normalized temperature-dependent SLP profiles and heat-pump COP on one timeline. German local dates determine weekdays and holidays. Market series, cost curves and resource availability enter the optimization context.
4. Optimize central supply for the accumulated network plus a candidate, including distribution/connection costs. Compare incremental annualized central cost with that candidate's decentralized benchmark. Apply the existing connection decision and update the accepted network.
5. Report JSON, charts, viewer data, provenance, performance metrics and available network GeoJSON.

Configured timesteps, technology options, storage and resource constraints remain unchanged. Gurobi is preferred when installed and usable; HiGHS is the installed fallback. See [architecture.md](architecture.md).

## District-heating heat balance

Central models include constant fractional distribution losses, configured by
`network.heat_loss_fraction` (default 12.5%). At each timestep network input is
`delivered demand / (1 - loss fraction)`; the difference is distribution loss.
This also raises the supply capacity reference peak and source-side pump sizing.
Only model-ready central demand is converted: cumulative accepted demand and
building/decentralized profiles stay unscaled, preventing repeated application
as the network expands. Resource limits, generator efficiencies, COP and storage
losses remain separate. Heat-density screening and building-side infrastructure
costs still use delivered demand; detailed spatial pipe losses/hydraulics are
outside this approximation. Results distinguish delivered demand, network input
and distribution losses. Setting the fraction to zero restores the previous
loss-free behavior.

## Interpretation

Annual heat is MWh/a; peak/installed power is kW; annualized cost is €/a; raw capital is €. Do not mix candidate alternatives with final-network totals or apply a second annuity to annualized costs. See [metric semantics](frontend/metric-contract.md).

Map playback uses green for accepted candidates, red for rejected, yellow for the current evaluation and gray for pending. Results depend on inputs and assumptions and support an initial planning comparison rather than detailed engineering design. English/German changes presentation only. Beyond NRW, regional inputs and loading/coverage checks must be adapted, not only the bbox.
