from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pyogrio
import pytest
from pyproj import Transformer
from shapely.geometry import Point

from dh_compass.preprocessing.buildings import building_column_sources, load_buildings


def test_building_loader_does_not_require_undeclared_pyarrow(monkeypatch, tmp_path):
    building_path = tmp_path / "buildings.gdb"
    building_path.mkdir()
    config = SimpleNamespace(
        paths=SimpleNamespace(building_data=building_path),
        scenario=SimpleNamespace(
            bbox=(8.7, 52.1, 8.8, 52.2),
            building_layer="buildings",
            building_columns=("beheizt", "RW_WW", "geometry"),
        ),
    )

    def fake_read_file(*args, **kwargs):
        if kwargs.get("use_arrow"):
            raise RuntimeError("pyarrow required to read using 'read_arrow'")
        return gpd.GeoDataFrame(
            {"beheizt": [1], "RW_WW": [1000.0]},
            geometry=[Point(450000, 5700000)],
            crs=25832,
        )

    monkeypatch.setattr(gpd, "read_file", fake_read_file)
    monkeypatch.setattr(pyogrio, "read_info", lambda *args, **kwargs: {
        "fields": ["beheizt", "RW_WW"], "geometry_name": "geometry",
    })

    buildings, bbox = load_buildings(config)

    assert len(buildings) == 1
    assert buildings.crs.to_epsg() == 4326
    assert bbox.bounds == (8.7, 52.1, 8.8, 52.2)


def test_new_nrw_floor_area_alias_keeps_values_and_heat_filter(tmp_path):
    path = tmp_path / "new.gdb"
    x, y = Transformer.from_crs(4326, 25832, always_xy=True).transform(8.798, 52.198)
    frame = gpd.GeoDataFrame(
        {"beheizt": np.array([1, 0], dtype="int32"), "RW_WW": [12345.67, 999.0],
         "Nutzflaeche": [987.6543210987654, 10.0]},
        geometry=[Point(x, y), Point(x + 1, y + 1)], crs=25832,
    )
    pyogrio.write_dataframe(frame, path, layer="Raumwaermebedarf_ist", driver="OpenFileGDB")
    config = SimpleNamespace(
        paths=SimpleNamespace(building_data=path),
        scenario=SimpleNamespace(
            bbox=(8.795, 52.195, 8.800, 52.200), building_layer="Raumwaermebedarf_ist",
            building_columns=("Shape", "beheizt", "RW_WW", "NF"),
        ),
    )

    buildings, _ = load_buildings(config)

    assert buildings["RW_WW"].tolist() == [12345.67]
    assert buildings["NF"].tolist() == [987.6543210987654]
    assert "Nutzflaeche" not in buildings
    assert buildings.crs.to_epsg() == 4326


def test_floor_area_alias_prefers_existing_nf_and_rejects_missing_values():
    assert building_column_sources(["NF"], ["NF", "Nutzflaeche"]) == {"NF": "NF"}
    with pytest.raises(ValueError, match="NF"):
        building_column_sources(["NF"], ["RW_WW"])
