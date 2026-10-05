"""Scan current source or release archives without printing secret values."""

from __future__ import annotations

import argparse
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from release_files import release_paths

ROOT = Path(__file__).resolve().parents[1]
RESTRICTED = {
    "heat_sink_weights.csv", "space_to_water_ratio.xlsx", "space_to_water_ratio_2012.xlsx",
    "historischelastgaenge_roadmap.xlsx", "reprÃ¤sentative profile vdew.xls",
    "slp-gas_pramter_tagesfaktoren.xlsx",
}
SECRET_PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb'''(?i)(?:api_?key|token|password)\s*[=:]\s*["'][0-9a-f]{8}-[0-9a-f-]{27,}["']'''),
    re.compile(rb"[A-Za-z]:[\\/]+Users[\\/]+[^\s\"']+"),
]


def inspect_entry(name: str, content: bytes) -> list[str]:
    path = PurePosixPath(name.replace("\\", "/"))
    lower = path.name.lower()
    failures = []
    if (
        path.is_absolute() or ".." in path.parts
        or
        lower.startswith((".cdsapirc", ".env", "eex phelix", "epex spot", "20200624_kov"))
        or "vertraulich" in lower
        or ("kww" in lower and "katalog" in lower)
        or any(part.lower().endswith(".gdb") for part in path.parts)
        or lower in RESTRICTED
        or lower.startswith("20131122-nachweispflicht")
        or path.suffix.lower() in {".grib", ".db", ".sqlite", ".sqlite3", ".xlsx", ".xls", ".xlsm", ".gpkg", ".tif", ".tiff", ".zip", ".whl", ".exe", ".dll", ".pyc", ".pyo"}
        or any(part in {"node_modules", "outputs", ".git", ".venv", "__pycache__", "dist", "build"} or part.endswith(".egg-info") for part in path.parts)
    ):
        failures.append(f"{name}: forbidden release path")
    if "data" in path.parts:
        data_path = PurePosixPath(*path.parts[path.parts.index("data"):]).as_posix()
        if data_path not in {"data/README.md", "data/reference/sh_to_wh_ratio.csv",
                             "data/reference/slp_parameters.json", "data/reference/.gitkeep"}:
            failures.append(f"{name}: unreviewed data is excluded from source releases")
    if any(pattern.search(content) for pattern in SECRET_PATTERNS):
        failures.append(f"{name}: potential credential or personal filesystem path (redacted)")
    return failures


def archive_entries(path: Path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if not entry.is_dir():
                    yield entry.filename, archive.read(entry)
    else:
        with tarfile.open(path) as archive:
            for entry in archive:
                if entry.isfile():
                    handle = archive.extractfile(entry)
                    if handle:
                        yield entry.name, handle.read()


def source_entries():
    # Scan index paths plus new, non-ignored work. Excluded local provider data
    # must never be opened; staged removals are honored without rewriting refs.
    if not (ROOT / ".git").exists():
        for path in release_paths(ROOT):
            yield path.relative_to(ROOT).as_posix(), path.read_bytes()
        return
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT
    )
    for name in sorted(set(output.decode("utf-8").split("\0")) - {""}):
        path = ROOT / name
        if path.is_file():
            yield name, path.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    entries = archive_entries(args.archive) if args.archive else source_entries()
    failures = []
    names = []
    for name, content in entries:
        names.append(name)
        failures.extend(inspect_entry(name, content))
    if args.archive and not any(
        re.fullmatch(r"(?:[^/]+/)?LICENSE", name)
        or re.fullmatch(r"[^/]+\.dist-info/licenses/LICENSE", name)
        for name in names
    ):
        failures.append("Archive lacks the project LICENSE.")
    for failure in failures:
        print(failure)
    print(f"Scanned {len(names)} files; {len(failures)} findings. History was not scanned.")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
