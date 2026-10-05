"""Compatibility launcher; use ``dh-compass run`` for new invocations."""

import sys

from dh_compass.cli import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:] or ["run"]))
