# Result metric semantics

The machine-readable [metric-contract.json](metric-contract.json) records field,
unit, scope, time basis, calculation stage and provenance. It is derived from
the frontend's RESULT_METRIC_CONTRACT registry.

Annual heat/production is MWh/a, installed and peak capacity is kW, and annualized
cost is EUR/a. Raw investment is EUR. Candidate alternatives and the final
connected network represent different scopes. Do not add alternatives to final
network totals or annualize costs that are already annualized.
