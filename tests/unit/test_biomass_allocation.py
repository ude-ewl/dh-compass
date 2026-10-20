from dataclasses import replace

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, box

from dh_compass.config import ConfigurationError, load_config
from dh_compass.resources.biomass import (
    BiomassAllocationError,
    allocate_biomass_population,
    assess_biomass,
    assess_configured_biomass,
)


@pytest.fixture
def allocation_frames():
    municipalities = gpd.GeoDataFrame(
        {"ags": ["05958012", "05958013"], "name": ["Brilon", "Neighbour"],
         "nuts2": ["DEA5", "DEA5"], "population": [1000, 9000]},
        geometry=[box(8, 51, 8.1, 51.1), box(8.1, 51, 8.2, 51.1)], crs=4326,
    )
    regions = pd.DataFrame({"nuts2": ["DEA5"], "population": [10000]})
    potential = gpd.GeoDataFrame(
        {"NUTS_2": ["DEA5"], "Bio_TWh": [1.0]},
        geometry=[box(8, 51, 8.2, 51.1)], crs=4326,
    )
    return potential, municipalities, regions


def allocate(frames, area=None, **kwargs):
    return allocate_biomass_population(
        *frames, area if area is not None else box(8.02, 51.02, 8.03, 51.03),
        "Bio_TWh", **kwargs,
    )


def test_full_municipality_population_not_neighbourhood_area(allocation_frames):
    result = allocate(allocation_frames)
    assert result.limit_mwh == pytest.approx(100000)
    assert result.available
    assert result.metadata["energy_basis"] == "fuel"
    municipal = result.metadata["municipalities"][0]
    assert municipal["ags"] == "05958012"
    assert municipal["population_share"] == 0.1
    assert municipal["region_population"] == 10000
    assert result.metadata["budget_fraction"] == 1
    # Independent runs do not reserve fuel or reduce the next study's budget.
    assert allocate(allocation_frames, box(8.05, 51.05, 8.09, 51.09)).limit_mwh == result.limit_mwh


def test_all_unique_municipalities_conserve_regional_budget(allocation_frames):
    result = allocate(allocation_frames, box(8, 51, 8.2, 51.1),
                      municipality_ags=("05958012", "05958013"))
    assert result.limit_mwh == pytest.approx(1_000_000)


def test_cross_region_selection_has_separate_denominators(allocation_frames):
    potential, municipalities, regions = allocation_frames
    municipalities.loc[1, "nuts2"] = "DEA4"
    regions = pd.DataFrame({"nuts2": ["DEA5", "DEA4"], "population": [1000, 9000]})
    potential = gpd.GeoDataFrame(
        {"NUTS_2": ["DEA5", "DEA4"], "Bio_TWh": [1, 2]},
        geometry=municipalities.geometry.copy(), crs=4326,
    )
    result = allocate((potential, municipalities, regions), box(8, 51, 8.2, 51.1),
                      municipality_ags=("05958012", "05958013"))
    assert result.limit_mwh == pytest.approx(3_000_000)


def test_largest_overlap_selects_one_whole_municipality(allocation_frames):
    result = allocate(allocation_frames, box(8.08, 51.02, 8.11, 51.03))
    assert [m["ags"] for m in result.metadata["municipalities"]] == ["05958012"]
    assert result.limit_mwh == pytest.approx(100000)
    assert len(result.metadata["municipality_candidates"]) == 2
    result = allocate(allocation_frames, box(8.09, 51.02, 8.12, 51.03))
    assert [m["ags"] for m in result.metadata["municipalities"]] == ["05958013"]
    assert result.limit_mwh == pytest.approx(900000)


def test_explicit_selection_overrides_largest_overlap(allocation_frames):
    result = allocate(allocation_frames, box(8.09, 51.02, 8.12, 51.03),
                      municipality_ags=("05958012",))
    assert result.limit_mwh == pytest.approx(100000)


def test_boundary_only_contact_does_not_claim_neighbour(allocation_frames):
    # Identical projection of the shared vertices prevents artificial slivers.
    result = allocate(allocation_frames, box(8, 51, 8.1, 51.1))
    assert len(result.metadata["municipalities"]) == 1


def test_multipart_municipality_is_counted_once(allocation_frames):
    potential, municipalities, regions = allocation_frames
    municipalities.loc[0, "geometry"] = MultiPolygon([
        box(8, 51, 8.04, 51.1), box(8.06, 51, 8.1, 51.1),
    ])
    result = allocate((potential, municipalities, regions), box(8.01, 51.01, 8.02, 51.02))
    assert result.limit_mwh == pytest.approx(100000)


@pytest.mark.parametrize("fraction,expected", [(0.4, 40000), (0, 0)])
def test_explicit_project_fraction(allocation_frames, fraction, expected):
    result = allocate(allocation_frames, budget_fraction=fraction)
    assert result.limit_mwh == pytest.approx(expected)
    assert result.available == (expected > 0)


@pytest.mark.parametrize("fraction", [-0.1, 1.1, float("nan"), float("inf"), True])
def test_invalid_fraction_rejected(allocation_frames, fraction):
    with pytest.raises(ValueError, match="fraction"):
        allocate(allocation_frames, budget_fraction=fraction)


@pytest.mark.parametrize("ags", [("05958012", "05958012"), ("05958013",), ("00000000",)])
def test_invalid_or_unrelated_explicit_ags_rejected(allocation_frames, ags):
    with pytest.raises(BiomassAllocationError):
        allocate(allocation_frames, municipality_ags=ags)


@pytest.mark.parametrize("target,value", [("population", -1), ("population", float("nan")),
                                         ("ags", "05958013"), ("nuts2", "UNKNOWN")])
def test_invalid_population_inputs_rejected(allocation_frames, target, value):
    allocation_frames[1].loc[0, target] = value
    with pytest.raises(BiomassAllocationError):
        allocate(allocation_frames)


def test_incomplete_region_denominator_rejected(allocation_frames):
    potential, municipalities, regions = allocation_frames
    with pytest.raises(BiomassAllocationError, match="population"):
        allocate((potential, municipalities.iloc[:1], regions))


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_selected_potential_rejected(allocation_frames, value):
    allocation_frames[0].loc[0, "Bio_TWh"] = value
    with pytest.raises(BiomassAllocationError):
        allocate(allocation_frames)


def test_missing_potential_mapping_rejected(allocation_frames):
    allocation_frames[0].loc[0, "NUTS_2"] = "DEA4"
    with pytest.raises(BiomassAllocationError):
        allocate(allocation_frames)


def test_outside_or_partially_uncovered_area_rejected(allocation_frames):
    for area in (box(10, 51, 11, 52), box(7.99, 51.02, 8.03, 51.03)):
        with pytest.raises(BiomassAllocationError, match="cover"):
            allocate(allocation_frames, area)


def test_allocation_does_not_mutate_frames(allocation_frames):
    before = [frame.copy(deep=True) for frame in allocation_frames]
    allocate(allocation_frames)
    for actual, expected in zip(allocation_frames, before, strict=True):
        pd.testing.assert_frame_equal(actual, expected)


def test_zero_population_contributes_zero(allocation_frames):
    allocation_frames[1].loc[0, "population"] = 0
    allocation_frames[2].loc[0, "population"] = 9000
    assert allocate(allocation_frames).limit_mwh == 0


def test_legacy_area_helper_preserves_area_weighting(allocation_frames):
    potential = allocation_frames[0]
    area = box(8, 51, 8.1, 51.1)
    original = potential.copy(deep=True)
    projected = potential.to_crs(25832)
    study = gpd.GeoSeries([area], crs=4326).to_crs(25832).iloc[0]
    expected = projected.geometry.iloc[0].intersection(study).area / projected.area.iloc[0] * 1e6
    available, limit = assess_biomass(potential, area, "Bio_TWh")
    assert available
    assert limit == pytest.approx(expected)
    pd.testing.assert_frame_equal(potential, original)


def test_config_defaults_and_paths_are_explicit(project_root, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config = load_config(project_root=project_root)
    assert config.resources.biomass_allocation_method == "municipality_population"
    assert config.resources.biomass_population_path == (
        project_root / "data/external/vg250-ew_ebenen_1231/DE_VG250.gpkg"
    )
    assert config.resources.biomass_municipality_ags == ()
    assert config.resources.biomass_budget_fraction == 1


@pytest.mark.parametrize("override", [
    {"biomass_allocation_method": "unknown"}, {"biomass_budget_fraction": -1},
    {"biomass_budget_fraction": 1.1}, {"biomass_budget_fraction": True},
    {"biomass_municipality_ags": [5958012]}, {"biomass_municipality_ags": ["5958012"]},
    {"biomass_municipality_ags": ["05958012", "05958012"]},
])
def test_invalid_biomass_configuration(override, project_root):
    from dh_compass.config import load_config_from_document

    with pytest.raises(ConfigurationError, match="biomass"):
        load_config_from_document({"resources": override}, project_root=project_root)


def test_legacy_mode_does_not_load_population(project_root, monkeypatch, allocation_frames):
    import dh_compass.resources.biomass as biomass

    config = load_config(project_root=project_root)
    resources = replace(config.resources, biomass_allocation_method="area",
                        biomass_population_path=project_root / "missing.gpkg",
                        biomass_budget_fraction=0.5)
    monkeypatch.setattr(biomass, "read_biomass_potential", lambda _: allocation_frames[0])
    result = assess_configured_biomass(resources, box(8, 51, 8.1, 51.1))
    assert result.limit_mwh == pytest.approx(assess_biomass(
        allocation_frames[0], box(8, 51, 8.1, 51.1), "Bio_TWh"
    )[1] * 0.5)
    assert result.metadata["method"] == "area"
