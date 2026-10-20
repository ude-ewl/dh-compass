import json
import sqlite3
from contextlib import closing

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from dh_compass.resources.municipalities import (
    BiomassAllocationError,
    file_sha256,
    load_population,
)


@pytest.fixture
def bkg_fixture(tmp_path, monkeypatch):
    import dh_compass.resources.municipalities as module

    monkeypatch.setattr(module, "NRW_MUNICIPALITY_COUNTS", {"DEA5": 2})
    path = tmp_path / "VG250.gpkg"
    # GF=2 is a duplicate water record and must never enter population sums.
    gpd.GeoDataFrame({
        "AGS": ["05958012", "05958013", "05958012"],
        "ARS": ["059580000012", "059580000013", "059580000012"],
        "GEN": ["Brilon", "Neighbour", "Brilon"], "EWZ": [1000, 9000, 1000], "GF": [4, 4, 2],
    }, geometry=[box(8, 51, 8.1, 51.1), box(8.1, 51, 8.2, 51.1), box(8, 51, 8.1, 51.1)],
        crs=4326).to_file(path, layer="vg250_gem", driver="GPKG", index=False)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("UPDATE gpkg_contents SET description='2024-12-31' WHERE table_name='vg250_gem'")
        pd.DataFrame({"ARS_G": ["059580000012", "059580000013"],
                      "AGS_G": ["05958012", "05958013"], "NUTS2_CODE": ["DEA5", "DEA5"]}).to_sql(
                          "vgtb_vz_gem", connection, index=False)
        pd.DataFrame({"NUTS": ["DEA5"], "GEN": ["Arnsberg"], "EWZ": [10000], "GF": [4]}).to_sql(
            "vg250_rbz", connection, index=False)
        connection.commit()
    return path


def test_local_bkg_loader_uses_explicit_assignments_and_land_records(bkg_fixture):
    data = load_population(bkg_fixture)
    assert len(data.municipalities) == 2
    assert set(data.municipalities.ags) == {"05958012", "05958013"}
    assert set(data.municipalities.nuts2) == {"DEA5"}
    assert data.regions.population.sum() == 10000
    assert data.metadata["population_date"] == "2024-12-31"
    assert data.metadata["sha256"] == file_sha256(bkg_fixture)
    assert data.metadata["license"] == "dl-de/by-2-0"
    # SQLite readers must close; on Windows an open reader prevents renaming.
    renamed = bkg_fixture.with_name("renamed.gpkg")
    bkg_fixture.rename(renamed)
    assert renamed.exists()


def test_cached_population_frames_are_isolated(bkg_fixture):
    first = load_population(bkg_fixture)
    first.municipalities.loc[0, "population"] = 5
    assert load_population(bkg_fixture).municipalities.population.sum() == 10000


@pytest.mark.parametrize("sql", [
    "DELETE FROM vgtb_vz_gem WHERE AGS_G='05958012'",
    "UPDATE vg250_rbz SET EWZ=9999",
    "DELETE FROM vg250_gem WHERE AGS='05958013'",
    "UPDATE gpkg_contents SET description='2023-12-31' WHERE table_name='vg250_gem'",
])
def test_invalid_or_incomplete_local_bkg_data_is_rejected(bkg_fixture, sql):
    with closing(sqlite3.connect(bkg_fixture)) as connection:
        connection.execute(sql)
        connection.commit()
    with pytest.raises(BiomassAllocationError):
        load_population(bkg_fixture)


def test_prepared_population_roundtrip_and_manifest_validation(bkg_fixture, tmp_path):
    # Importing a script is safe: no I/O or argument parsing happens on import.
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts/prepare_biomass_population.py"
    spec = importlib.util.spec_from_file_location("prepare_population_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    potential = tmp_path / "potential.gpkg"
    gpd.GeoDataFrame({"NUTS_2": ["DEA5"], "Bio_TWh": [1.0]},
                     geometry=[box(8, 51, 8.2, 51.1)], crs=4326).to_file(potential, driver="GPKG")
    output = tmp_path / "prepared.gpkg"
    manifest = module.prepare_population(bkg_fixture, output, potential)
    data = load_population(output)
    assert data.metadata["source_sha256"] == file_sha256(bkg_fixture)
    assert len(data.municipalities) == 2
    assert data.regions.population.sum() == 10000
    manifest_path = output.with_suffix(".manifest.json")
    manifest["sha256"] = "incorrect"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BiomassAllocationError, match="checksum"):
        load_population(output)


def test_missing_population_file_does_not_create_it(tmp_path):
    path = tmp_path / "missing.gpkg"
    with pytest.raises(BiomassAllocationError):
        load_population(path)
    assert not path.exists()
