import type { ConfigurationField } from "../../api/projects";
import {
  coerceFieldInput,
  fieldErrorFor,
  isCostCurveField,
  isTechnologyMapField,
  resetConfigurationValue,
  serializeConfigurationToml,
  setConfigurationValue,
} from "./configuration";

function field(overrides: Partial<ConfigurationField>): ConfigurationField {
  return {
    key: "network.linear_heat_density_threshold",
    section: "network",
    section_label: "Network",
    label: "Threshold",
    description: "",
    data_type: "number",
    unit: null,
    default: 2,
    has_default: true,
    value: 2,
    changed_from_default: false,
    changed_from_parent: false,
    expert_only: false,
    editable: true,
    runtime_only: false,
    impact: "preview",
    preprocessing_impact: true,
    sensitive: false,
    path_policy: null,
    constraints: {},
    ...overrides,
  };
}

describe("configuration editing utilities", () => {
  it("updates a nested value without mutating the draft", () => {
    const original = { network: { linear_heat_density_threshold: 2 } };
    const updated = setConfigurationValue(
      original,
      "network.linear_heat_density_threshold",
      3,
    );

    expect(updated).toEqual({ network: { linear_heat_density_threshold: 3 } });
    expect(original).toEqual({ network: { linear_heat_density_threshold: 2 } });
  });

  it("removes dynamic map entries when they have no inherited default", () => {
    const original = {
      economics: { cost_structures: { chp: { 300: 1017, 350: 999 } } },
    };

    expect(
      resetConfigurationValue(
        original,
        "economics.cost_structures.chp.350",
        null,
        false,
      ),
    ).toEqual({ economics: { cost_structures: { chp: { 300: 1017 } } } });
  });

  it("coerces typed inputs and serializes nested TOML", () => {
    expect(coerceFieldInput(field({ data_type: "integer" }), "4")).toBe(4);
    expect(
      coerceFieldInput(field({ data_type: "array" }), '["biomass"]'),
    ).toEqual(["biomass"]);
    expect(
      serializeConfigurationToml({
        network: { linear_heat_density_threshold: 2 },
        scenario: { enabled_resources: ["biomass"] },
      }),
    ).toContain("[network]\nlinear_heat_density_threshold = 2");
  });

  it("recognizes grouped editors and maps nested server errors", () => {
    expect(
      isCostCurveField(field({ key: "economics.cost_structures.chp.300" })),
    ).toBe(true);
    expect(
      isTechnologyMapField(
        field({ key: "technologies.boiler_central.0.efficiency" }),
      ),
    ).toBe(true);
    expect(
      fieldErrorFor(
        [{ path: "technologies.boiler_central.0", message: "Invalid map" }],
        "technologies.boiler_central.0.efficiency",
      ),
    ).toBe("Invalid map");
  });
});
