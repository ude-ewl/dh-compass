"""Export final working files, including owned ratios, without provider data or Git history."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

from release_audit import inspect_entry
from release_files import release_paths

ROOT = Path(__file__).resolve().parents[1]


def export(destination: Path) -> int:
    entries = []
    for path in release_paths(ROOT):
        name = path.relative_to(ROOT).as_posix()
        content = path.read_bytes()
        findings = inspect_entry(name, content)
        if findings:
            raise ValueError("\n".join(findings))
        entries.append((name, content))
    required = {"LICENSE", "DATA_LICENSES.md", "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md",
                "data/reference/slp_parameters.json", "data/reference/sh_to_wh_ratio.csv"}
    missing = required - {name for name, _ in entries}
    if missing:
        raise ValueError(f"Missing release documents: {', '.join(sorted(missing))}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            entry = zipfile.ZipInfo(f"DH-COMPASS/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        f"{digest}  {destination.name}\n", encoding="utf-8"
    )
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "release" / "DH-COMPASS-source.zip")
    args = parser.parse_args()
    print(f"Exported {export(args.output.resolve())} files to {args.output.resolve()}")


if __name__ == "__main__":
    main()
