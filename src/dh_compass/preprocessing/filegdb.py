"""Explicit repair for the malformed OBJECTID metadata in the NRW 2025 GDB.

GDAL requires the OBJECTID field's flags to be MASK_REQUIRED (2). The provider
export has flags=0 in two tables. Only that flag byte is repaired; feature rows,
indexes, coordinate metadata and all other bytes are left untouched.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


def _objectid_metadata(table: Path):
    with table.open("rb") as handle:
        header = handle.read(40)
        if len(header) != 40 or struct.unpack_from("<I", header)[0] != 3:
            return None
        descriptor_offset = struct.unpack_from("<Q", header, 32)[0]
        handle.seek(descriptor_offset)
        prefix = handle.read(14)
        if len(prefix) != 14:
            return None
        size, version = struct.unpack_from("<II", prefix)
        if version != 4 or not 14 <= size <= 10 * 1024 * 1024:
            return None
        descriptor = prefix + handle.read(size - 10)
    if len(descriptor) != size + 4:
        return None
    cursor = 14
    if cursor >= len(descriptor):
        return None
    name_length = descriptor[cursor]
    cursor += 1
    if cursor + 2 * name_length >= len(descriptor):
        return None
    name = descriptor[cursor:cursor + 2 * name_length].decode("utf-16le")
    cursor += 2 * name_length
    alias_length = descriptor[cursor]
    cursor += 1 + 2 * alias_length
    if cursor + 3 > len(descriptor):
        return None
    # OID type (6), width (4), flags. Only the known first-field layout qualifies.
    if name != "OBJECTID" or descriptor[cursor:cursor + 2] != b"\x06\x04":
        return None
    return descriptor_offset + cursor + 2, descriptor[cursor + 2], descriptor


def repair_nrw_objectid_metadata(path: Path) -> list[dict]:
    """Repair recognized invalid OID flags, writing a portable undo journal.

    This operation is explicit, never called automatically by data readers.
    Repeating it on a repaired database does nothing.
    """
    path = Path(path)
    if not path.is_dir() or path.suffix.lower() != ".gdb":
        raise ValueError("Expected an extracted File Geodatabase directory")
    changes = []
    for table in sorted(path.glob("*.gdbtable")):
        metadata = _objectid_metadata(table)
        if metadata is None or metadata[1] != 0:
            continue
        offset, original, descriptor = metadata
        changes.append({
            "table": table.name, "offset": offset, "original": original, "repaired": 2,
            "file_size": table.stat().st_size,
            "descriptor_sha256_before": hashlib.sha256(descriptor).hexdigest(),
        })
    if not changes:
        return []
    journal = path.with_name(path.name + ".objectid-repair.json")
    if journal.exists():
        raise ValueError("A repair journal already exists; preserve it before repairing again")
    # Preserve original flag values before the first write. The journal permits
    # undoing the exact byte changes without copying the 27 GB database.
    journal.write_text(json.dumps({"changes": changes}, indent=2) + "\n", encoding="utf-8")
    for change in changes:
        with (path / change["table"]).open("r+b") as handle:
            handle.seek(change["offset"])
            if handle.read(1) != bytes([change["original"]]):
                raise ValueError("Metadata changed since inspection")
            handle.seek(change["offset"])
            handle.write(bytes([change["repaired"]]))
    return changes
