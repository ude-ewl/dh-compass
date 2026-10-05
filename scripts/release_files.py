"""Small, explicit source-release boundary, also usable without a Git checkout."""

from pathlib import Path

ROOT_FILES = {
    ".gitignore", ".python-version", "AGENTS.md", "LICENSE", "README.md",
    "DATA_LICENSES.md", "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md",
    "MANIFEST.in", "pyproject.toml", "uv.lock", "main.py",
}
DIRECTORIES = {
    "src/dh_compass": {".py"},
    "tests": {".py", ".json"},
    "scripts": {".py"},
    "configs": {".toml", ".md"},
    "docs": {".md", ".json", ".txt"},
    "templates": {".html"},
    "frontend/src": {".ts", ".tsx", ".css"},
    "frontend/tests": {".ts"},
    "frontend/scripts": {".mjs"},
    ".github/workflows": {".yml", ".yaml"},
}
FRONTEND_FILES = {
    "package.json", "package-lock.json", "README.md", "index.html",
    "eslint.config.js", "playwright.config.ts", "playwright.legacy.config.ts",
    "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json",
    "vite.config.ts", "vitest.config.ts",
}


def release_paths(root: Path) -> list[Path]:
    paths = [root / name for name in ROOT_FILES]
    paths.extend(root / "frontend" / name for name in FRONTEND_FILES)
    paths.extend([root / "data/README.md", root / "data/reference/sh_to_wh_ratio.csv",
                  root / "data/reference/slp_parameters.json"])
    for directory, suffixes in DIRECTORIES.items():
        for path in (root / directory).rglob("*"):
            if path.suffix in suffixes and "__pycache__" not in path.parts:
                paths.append(path)
    result = []
    for path in sorted(set(paths)):
        if path.is_symlink():
            raise ValueError(f"Release source cannot be a symbolic link: {path.relative_to(root)}")
        if path.is_file():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Release source escapes project root")
            result.append(path)
    return result
