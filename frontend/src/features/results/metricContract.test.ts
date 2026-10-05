import {
  METRIC_CONTRACT_VERSION,
  RESULT_METRIC_CONTRACT,
} from "./metricContract";

describe("result metric contract", () => {
  it("requires interpretation metadata for every registered result value", () => {
    expect(METRIC_CONTRACT_VERSION).toBe("1");
    expect(Object.keys(RESULT_METRIC_CONTRACT).length).toBeGreaterThan(10);

    Object.values(RESULT_METRIC_CONTRACT).forEach((metric) => {
      expect(metric.unit).not.toBe("");
      expect(metric.scope).not.toBe("");
      expect(metric.timeBasis).not.toBe("");
      expect(metric.calculationStage).not.toBe("");
      expect(metric.basis).not.toBe("");
      expect(metric.provenance.length).toBeGreaterThan(0);
    });
  });

  it("keeps capital and annualized candidate costs distinct", () => {
    expect(RESULT_METRIC_CONTRACT["candidate.central_grid_cost_raw"].unit).toBe(
      "€",
    );
    expect(RESULT_METRIC_CONTRACT["candidate.central_cost"].unit).toBe("€/a");
  });
});
