from dataclasses import replace

import pytest

from dh_compass.resources.biomass import BiomassAllocationError, BiomassAssessment
from dh_compass.web.services.configuration import ConfigurationAdapter
from dh_compass.web.services.data_readiness import DataReadinessService


@pytest.fixture
def scenario(tmp_path):
    adapter = ConfigurationAdapter(tmp_path)
    document = adapter.defaults
    path = tmp_path / "biomass.gpkg"
    path.touch()
    document["resources"]["biomass_path"] = str(path)
    return adapter, {"revision": {"document": document}}


def test_population_input_required_only_for_enabled_population_method(scenario):
    adapter, document = scenario
    service = DataReadinessService(adapter)
    descriptor = service.validate_one(document, "biomass_population")
    assert descriptor.required
    assert descriptor.status == "missing"
    document["revision"]["document"]["resources"]["biomass_allocation_method"] = "area"
    descriptor = service.validate_one(document, "biomass_population")
    assert not descriptor.required
    assert descriptor.status == "unavailable"
    document["revision"]["document"]["resources"]["biomass_allocation_method"] = "municipality_population"
    document["revision"]["document"]["scenario"]["enabled_resources"] = ["geothermal"]
    descriptor = service.validate_one(document, "biomass_population")
    assert not descriptor.required
    assert descriptor.issues == []


def test_biomass_preflight_returns_choices_and_blocks_ambiguous_selection(scenario, monkeypatch):
    adapter, document = scenario
    choices = [{"ags": "05958012", "name": "Brilon", "population": 25424}]

    def ambiguous(*args):
        raise BiomassAllocationError("Confirm municipality selection.",
                                     code="BIOMASS_MUNICIPALITY_AMBIGUOUS", candidates=choices)

    monkeypatch.setattr("dh_compass.web.services.data_readiness.assess_configured_biomass", ambiguous)
    descriptors, blocking, ready = DataReadinessService(adapter).readiness(document, dataset_ids=["biomass"])
    assert not ready
    assert descriptors[0].metadata["municipality_candidates"] == choices
    assert blocking[0].code == "BIOMASS_MUNICIPALITY_AMBIGUOUS"
    assert blocking[0].details["municipality_candidates"] == choices


def test_readiness_reuses_the_canonical_assessor_and_fingerprints_allocation(scenario, monkeypatch):
    adapter, document = scenario
    captured = []

    def assessment(config, bbox):
        captured.append(config)
        return BiomassAssessment(1000 * config.biomass_budget_fraction, {
            "method": config.biomass_allocation_method,
            "municipalities": list(config.biomass_municipality_ags),
            "budget_fraction": config.biomass_budget_fraction, "potential_sha256": "potential",
            "population_data": {"sha256": "population"},
        })

    monkeypatch.setattr("dh_compass.web.services.data_readiness.assess_configured_biomass", assessment)
    service = DataReadinessService(adapter)
    first = service.validate_one(document, "biomass")
    document["revision"]["document"]["resources"].update({
        "biomass_budget_fraction": 0.5, "biomass_municipality_ags": ["05958012"],
    })
    second = service.validate_one(document, "biomass")
    assert first.status == second.status == "ready"
    assert first.metadata["fingerprint"] != second.metadata["fingerprint"]
    assert second.metadata["biomass_allocation"]["budget_fraction"] == 0.5
    assert captured[-1].biomass_municipality_ags == ("05958012",)


def test_new_fields_have_editor_constraints_and_run_only_impact(scenario):
    adapter, _ = scenario
    config = adapter.to_app_config(adapter.defaults)
    assert replace(config.resources, biomass_budget_fraction=0).biomass_budget_fraction == 0
    # Schema metadata shares the canonical loader's defaults and enum.
    fields = {field["key"]: field for field in adapter.metadata()}
    method = fields["resources.biomass_allocation_method"]
    assert method["constraints"]["allowed_values"] == ["municipality_population", "area"]
    fraction = fields["resources.biomass_budget_fraction"]
    assert fraction["constraints"]["minimum"] == 0
    assert fraction["constraints"]["maximum"] == 1
    assert fraction["impact"] == "run"
    assert fields["resources.biomass_municipality_ags"]["data_type"] == "array"
