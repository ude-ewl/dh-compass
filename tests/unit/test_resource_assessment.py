import geopandas as gpd
from shapely.geometry import Point, box

from dh_compass.resources.industrial_heat import assess_industrial_heat
from dh_compass.resources.waste_to_energy import assess_waste_to_energy
from dh_compass.resources.water_heat import assess_river_heat, assess_wwtp_heat


def test_point_resource_limits_are_explicit_and_spatially_filtered():
    frame = gpd.GeoDataFrame(
        {
            "potential": [2.0, 5.0],
            "EH100PJ": [1.0, 3.0],
            "Capa in MW": [0.5, 2.0],
            "Power in k": [100.0, 300.0],
        },
        geometry=[Point(0, 0), Point(10, 10)],
        crs=4326,
    )
    area = box(-1, -1, 1, 1)

    assert assess_industrial_heat(frame, area, "potential") == (True, 2000.0)
    assert assess_waste_to_energy(frame, area, "EH100PJ") == (True, 277778.0)
    assert assess_river_heat(frame, area) == (True, 500.0)
    assert assess_wwtp_heat(frame, area) == (True, 100.0)
