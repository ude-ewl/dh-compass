"""Command-line interface for DH-COMPASS."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from .config import load_config


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dh-compass")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run a configured heat-grid scenario")
    run.add_argument("--config", type=Path, help="scenario TOML file")
    run.add_argument("--output-dir", type=Path, help="override generated output directory")

    charts = subparsers.add_parser("charts", help="generate charts from full_results.json")
    charts.add_argument("results", type=Path, help="path to full_results.json")
    charts.add_argument("--output-dir", type=Path, help="chart output directory")

    web = subparsers.add_parser(
        "web",
        help="start the local browser application",
        description="Start the FastAPI browser application and serve the compiled frontend when available.",
    )
    web.add_argument("--host", default="127.0.0.1", help="interface to bind (default: 127.0.0.1)")
    web.add_argument("--port", type=_port, default=8000, help="port to bind (default: 8000)")
    web.add_argument(
        "--open-browser",
        "--open",
        action="store_true",
        dest="open_browser",
        help="open the application URL in the default browser",
    )
    web.add_argument("--project-root", type=Path, help="repository or deployment root")
    web.add_argument(
        "--database-path",
        type=str,
        help="metadata SQLite database path (use :memory: for an ephemeral database)",
    )
    web.add_argument("--output-root", type=Path, help="managed output root")
    web.add_argument(
        "--frontend-static-path",
        type=Path,
        help="compiled frontend directory (normally frontend/dist)",
    )
    web.add_argument(
        "--worker-concurrency",
        type=int,
        help="maximum number of optimization workers",
    )
    web.add_argument(
        "--cors-origin",
        action="append",
        dest="cors_origins",
        help="development CORS origin; may be supplied more than once",
    )
    web.add_argument(
        "--strict-startup-checks",
        action="store_true",
        help="fail startup when data, solver, or frontend checks are degraded",
    )
    web.add_argument(
        "--log-level",
        default="info",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        help="Uvicorn log level",
    )
    return parser


def _web_settings(args: argparse.Namespace):
    """Build web settings while keeping web dependencies out of CLI imports."""

    from .web.settings import WebSettings

    base = WebSettings.from_environment(project_root=args.project_root)
    return WebSettings(
        project_root=base.project_root,
        metadata_database_path=(
            args.database_path if args.database_path is not None else base.metadata_database_path
        ),
        output_root=args.output_root if args.output_root is not None else base.output_root,
        worker_concurrency=(
            args.worker_concurrency
            if args.worker_concurrency is not None
            else base.worker_concurrency
        ),
        frontend_static_path=(
            args.frontend_static_path
            if args.frontend_static_path is not None
            else base.frontend_static_path
        ),
        development_cors_origins=(
            tuple(args.cors_origins)
            if args.cors_origins is not None
            else base.development_cors_origins
        ),
        artifact_retention_days=base.artifact_retention_days,
        geocoding_endpoint=base.geocoding_endpoint,
        strict_startup_checks=args.strict_startup_checks or base.strict_startup_checks,
    )


def _run_web(args: argparse.Namespace) -> int:
    """Start Uvicorn for the packaged/local browser application."""

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            "The web dependencies are not installed. Run `uv sync --extra web` first."
        ) from exc

    from .web.app import create_app

    settings = _web_settings(args)
    app = create_app(settings)
    browser_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    if ":" in browser_host and not browser_host.startswith("["):
        browser_host = f"[{browser_host}]"
    url = f"http://{browser_host}:{args.port}/"
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level=args.log_level)

    if args.open_browser:
        import webbrowser

        class BrowserOpeningServer(uvicorn.Server):
            """Open the browser only after Uvicorn has bound its listener."""

            async def startup(self, sockets=None) -> None:  # type: ignore[no-untyped-def]
                await super().startup(sockets=sockets)
                if self.started:
                    webbrowser.open(url)

        server = BrowserOpeningServer(config)
    else:
        server = uvicorn.Server(config)
    server.run()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning a process exit code."""

    parser = _parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "run":
        from .pipeline import run_pipeline

        config = load_config(args.config)
        artifacts = run_pipeline(config, output_dir=args.output_dir)
        logging.getLogger(__name__).info("run written to %s", artifacts.output_dir)
        return 0

    if args.command == "charts":
        from .reporting.charts import generate_all_charts

        result_path = args.results.expanduser().resolve()
        with result_path.open("r", encoding="utf-8") as handle:
            results = json.load(handle)
        output_dir = args.output_dir or result_path.parent
        generate_all_charts(results, str(output_dir))
        return 0

    if args.command == "web":
        return _run_web(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
