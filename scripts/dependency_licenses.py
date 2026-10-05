"""Generate review inventories from installed Python metadata and npm lockfile."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "license-reports")
    parser.add_argument("--strict-binaries", action="store_true",
                        help="Fail if any installed wheel lacks license texts; required before bundling environments")
    args = parser.parse_args()
    python = []
    notices = []
    missing = []
    for dist in importlib.metadata.distributions():
        metadata = dist.metadata
        if metadata["Name"].lower() == "dh-compass":
            continue
        license_files = [file for file in (dist.files or [])
                         if any(part.lower().startswith(("license", "licence", "copying", "notice"))
                                for part in file.parts)]
        texts = []
        for file in license_files:
            path = Path(dist.locate_file(file))
            if path.is_file():
                texts.append(f"{file}\n{path.read_text(encoding='utf-8', errors='replace')}")
        if not texts:
            missing.append(metadata["Name"])
        notices.append(f"\n{metadata['Name']} {dist.version}\n" + "\n".join(texts))
        python.append({
            "name": metadata["Name"], "version": dist.version,
            "license_expression": metadata.get("License-Expression"),
            "license": (metadata.get("License") or "").splitlines()[0:1],
            "classifiers": [item for item in metadata.get_all("Classifier", []) if "License" in item],
            "license_files": metadata.get_all("License-File", []),
            "project_urls": metadata.get_all("Project-URL", []),
            "installed_notice_files": [str(file) for file in license_files],
            "notice_status": "present" if texts else "missing; do not redistribute binaries without review",
        })
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    npm = [{"path": name, "version": item.get("version"), "license": item.get("license"),
            "dev": item.get("dev", False), "resolved": item.get("resolved")}
           for name, item in lock["packages"].items() if name]
    args.output.mkdir(parents=True, exist_ok=True)
    for name, rows in [("python", sorted(python, key=lambda row: row["name"].lower())), ("npm", npm)]:
        (args.output / f"{name}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"{name}: {len(rows)} distributions; review {args.output / (name + '.json')}")
    (args.output / "PYTHON_THIRD_PARTY_LICENSES.txt").write_text(
        "Installed dependency notices; includes native notices where supplied by wheel.\n" +
        "\n".join(notices), encoding="utf-8"
    )
    if missing:
        message = f"Installed distributions lack license files: {', '.join(sorted(missing))}"
        print(message)
        if args.strict_binaries:
            raise ValueError(message)


if __name__ == "__main__":
    main()
