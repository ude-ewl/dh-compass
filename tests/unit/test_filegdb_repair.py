import struct

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import Point

from dh_compass.preprocessing.filegdb import (
    _objectid_metadata,
    repair_nrw_objectid_metadata,
)


def test_repair_changes_only_bad_flag_and_restores_native_reader(tmp_path):
    path = tmp_path / "buildings.gdb"
    expected = gpd.GeoDataFrame(
        {"beheizt": np.array([1, 0], dtype="int32"),
         "RW_WW": [12345.678901234567, 0.0]},
        geometry=[Point(450000, 5700000), Point(450001, 5700001)], crs=25832,
    )
    pyogrio.write_dataframe(expected, path, layer="buildings", driver="OpenFileGDB")
    # GDAL writes geometry before OID; the NRW exporter puts OID first.
    # OID consumes neither feature-row bytes nor a null bit, so moving its
    # descriptor reproduces the provider layout without changing feature data.
    table = path / "a00000009.gdbtable"
    with table.open("r+b") as handle:
        descriptor_offset = struct.unpack_from("<Q", handle.read(40), 32)[0]
        handle.seek(descriptor_offset)
        size = struct.unpack("<I", handle.read(4))[0]
        handle.seek(descriptor_offset)
        descriptor = handle.read(size + 4)
        oid = b"\x08" + "OBJECTID".encode("utf-16le") + b"\x00\x06\x04\x02"
        assert descriptor.count(oid) == 1
        reordered = descriptor[:14] + oid + descriptor[14:].replace(oid, b"")
        handle.seek(descriptor_offset)
        handle.write(reordered)
    pd.testing.assert_frame_equal(
        pyogrio.read_dataframe(path, layer="buildings"), expected, check_exact=True,
    )
    offset, flag, _ = _objectid_metadata(table)
    assert flag == 2
    with table.open("r+b") as handle:
        handle.seek(offset)
        handle.write(b"\x00")
    before = {file.name: file.read_bytes() for file in path.iterdir() if file.is_file()}
    assert len(pyogrio.read_info(path, layer="buildings")["fields"]) == 0

    changes = repair_nrw_objectid_metadata(path)

    assert len(changes) == 1
    assert changes[0]["offset"] == offset
    pd.testing.assert_frame_equal(
        pyogrio.read_dataframe(path, layer="buildings"), expected, check_exact=True,
    )
    changed_bytes = 0
    for file in path.iterdir():
        if file.is_file():
            original = before[file.name]
            repaired = file.read_bytes()
            assert len(original) == len(repaired)
            changed_bytes += sum(a != b for a, b in zip(original, repaired, strict=True))
    assert changed_bytes == 1
    journal = path.with_name(path.name + ".objectid-repair.json")
    assert journal.exists()
    saved_journal = journal.read_bytes()
    assert repair_nrw_objectid_metadata(path) == []
    assert journal.read_bytes() == saved_journal


def test_valid_database_is_not_changed(tmp_path):
    path = tmp_path / "valid.gdb"
    frame = gpd.GeoDataFrame({"demand": [1.0]}, geometry=[Point(1, 2)], crs=25832)
    pyogrio.write_dataframe(frame, path, layer="buildings", driver="OpenFileGDB")
    before = {file.name: file.read_bytes() for file in path.iterdir() if file.is_file()}

    assert repair_nrw_objectid_metadata(path) == []
    assert before == {file.name: file.read_bytes() for file in path.iterdir() if file.is_file()}
    assert not path.with_name(path.name + ".objectid-repair.json").exists()
