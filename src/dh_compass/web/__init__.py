"""HTTP application boundary for the DH-COMPASS browser client.

The web package is deliberately kept at the application edge.  Domain and
pipeline modules do not import it; the API delegates to those modules through
explicit services as features are added.
"""

from .settings import WebSettings


def __getattr__(name: str):
    if name == "create_app":
        # Keep importing the optional FastAPI stack lazy for CLI-only users.
        from .app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["WebSettings", "create_app"]
