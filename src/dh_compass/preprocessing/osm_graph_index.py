"""Spatially index a GraphML street graph for bbox based reads."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from xml.sax import ContentHandler, make_parser
from xml.sax.handler import feature_external_ges, feature_namespaces

from shapely import wkb, wkt

_INDEX_VERSION = "1"
_BUILD_LOCK = threading.Lock()


def _node_key(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def _edge_key(value: str) -> int | str:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _source_signature(path: Path) -> tuple[str, str, str]:
    stat = path.stat()
    return str(path.resolve()), str(stat.st_size), str(stat.st_mtime_ns)


def spatial_index_path(cache_root: Path) -> Path:
    """Return the shared index path for the local NRW driving graph."""
    return cache_root / "street_network_spatial_index.sqlite3"


def _index_is_current(index_path: Path, source_path: Path) -> bool:
    if not index_path.is_file():
        return False
    try:
        with sqlite3.connect(index_path) as connection:
            values = dict(connection.execute("SELECT key, value FROM metadata"))
        source, size, modified = _source_signature(source_path)
    except (OSError, sqlite3.Error, ValueError):
        return False
    expected = {
        "version": _INDEX_VERSION,
        "source_path": source,
        "source_size": size,
        "source_mtime_ns": modified,
    }
    return all(values.get(key) == value for key, value in expected.items())


class _GraphMLIndexHandler(ContentHandler):
    """Stream only node coordinates and edge geometry/length from GraphML."""

    def __init__(self, connection: sqlite3.Connection, *, batch_size: int = 10000):
        super().__init__()
        self.connection = connection
        self.batch_size = batch_size
        self.keys: dict[str, str] = {}
        self.current: dict[str, object] | None = None
        self.current_tag: str | None = None
        self.data_key: str | None = None
        self.data_chars: list[str] = []
        self.nodes: list[tuple[str, float, float]] = []
        self.edges: list[tuple[object, ...]] = []
        self.edge_sequence = 0
        self.node_count = 0
        self.edge_count = 0

    @staticmethod
    def _attr(attrs, key: str) -> str | None:
        return attrs.get((None, key))

    def startElementNS(self, name, _qname, attrs):  # noqa: N802 - SAX API
        tag = name[1]
        if tag == "key":
            key_id = self._attr(attrs, "id")
            key_name = self._attr(attrs, "attr.name")
            if key_id and key_name:
                self.keys[key_id] = key_name
        elif tag in {"node", "edge"}:
            self.current_tag = tag
            self.current = {"attrs": dict(attrs.items()), "data": {}}
        elif tag == "data" and self.current is not None:
            self.data_key = self._attr(attrs, "key")
            self.data_chars = []

    def characters(self, content: str) -> None:
        if self.data_key is not None:
            self.data_chars.append(content)

    def endElementNS(self, name, _qname):  # noqa: N802 - SAX API
        tag = name[1]
        if tag == "data" and self.current is not None and self.data_key is not None:
            data = self.current["data"]
            assert isinstance(data, dict)
            data[self.keys.get(self.data_key, self.data_key)] = "".join(self.data_chars).strip()
            self.data_key = None
            self.data_chars = []
        elif tag in {"node", "edge"} and self.current is not None:
            attrs = self.current["attrs"]
            data = self.current["data"]
            assert isinstance(attrs, dict) and isinstance(data, dict)
            if tag == "node":
                node_id = attrs.get((None, "id"))
                if node_id is not None and "x" in data and "y" in data:
                    self.nodes.append((node_id, float(data["x"]), float(data["y"])))
                    self.node_count += 1
                    if len(self.nodes) >= self.batch_size:
                        self.connection.executemany(
                            "INSERT INTO nodes(node_id, x, y) VALUES (?, ?, ?)", self.nodes
                        )
                        self.nodes.clear()
            else:
                source = attrs.get((None, "source"))
                target = attrs.get((None, "target"))
                if source is not None and target is not None:
                    edge_id = attrs.get((None, "id")) or str(self.edge_sequence)
                    self.edge_sequence += 1
                    length_text = data.get("length")
                    length = float(length_text) if length_text not in (None, "") else None
                    geometry_blob = None
                    bounds = (None, None, None, None)
                    geometry_text = data.get("geometry")
                    if geometry_text and geometry_text != "None":
                        geometry = wkt.loads(str(geometry_text))
                        geometry_blob = sqlite3.Binary(geometry.wkb)
                        minx, miny, maxx, maxy = geometry.bounds
                        bounds = (minx, maxx, miny, maxy)
                    self.edges.append((
                        source, target, edge_id, length, geometry_blob, *bounds
                    ))
                    self.edge_count += 1
                    if self.edge_count % 1_000_000 == 0:
                        print(f"Indexed {self.edge_count:,} local OSM street edges...")
                    if len(self.edges) >= self.batch_size:
                        self.connection.executemany(
                            """INSERT INTO edges(u, v, edge_key, length, geometry,
                               minx, maxx, miny, maxy) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            self.edges,
                        )
                        self.edges.clear()
            self.current = None
            self.current_tag = None


def build_graphml_spatial_index(source_path: Path, index_path: Path) -> None:
    """Build a disk based RTree index by streaming the source GraphML once."""
    source_path = Path(source_path)
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    source, size, modified = _source_signature(source_path)
    with sqlite3.connect(index_path) as connection:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("CREATE TABLE nodes (node_id TEXT PRIMARY KEY, x REAL NOT NULL, y REAL NOT NULL)")
        connection.execute(
            """CREATE TABLE edges (
                id INTEGER PRIMARY KEY,
                u TEXT NOT NULL,
                v TEXT NOT NULL,
                edge_key TEXT NOT NULL,
                length REAL,
                geometry BLOB,
                minx REAL,
                maxx REAL,
                miny REAL,
                maxy REAL
            )"""
        )
        handler = _GraphMLIndexHandler(connection)
        parser = make_parser()
        parser.setFeature(feature_namespaces, True)
        parser.setFeature(feature_external_ges, False)
        parser.setContentHandler(handler)
        with source_path.open("rb") as source_file:
            parser.parse(source_file)
        if handler.nodes:
            connection.executemany(
                "INSERT INTO nodes(node_id, x, y) VALUES (?, ?, ?)", handler.nodes
            )
        if handler.edges:
            connection.executemany(
                """INSERT INTO edges(u, v, edge_key, length, geometry,
                   minx, maxx, miny, maxy) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                handler.edges,
            )
        connection.execute("CREATE VIRTUAL TABLE edge_spatial_index USING rtree(id, minx, maxx, miny, maxy)")
        connection.execute(
            """INSERT INTO edge_spatial_index(id, minx, maxx, miny, maxy)
               SELECT e.id,
                   COALESCE(e.minx, MIN(u.x, v.x)),
                   COALESCE(e.maxx, MAX(u.x, v.x)),
                   COALESCE(e.miny, MIN(u.y, v.y)),
                   COALESCE(e.maxy, MAX(u.y, v.y))
               FROM edges e
               JOIN nodes u ON u.node_id = e.u
               JOIN nodes v ON v.node_id = e.v"""
        )
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [
                ("version", _INDEX_VERSION),
                ("source_path", source),
                ("source_size", size),
                ("source_mtime_ns", modified),
                ("node_count", str(handler.node_count)),
                ("edge_count", str(handler.edge_count)),
                ("crs", "EPSG:4326"),
            ],
        )


def ensure_graphml_spatial_index(source_path: Path, index_path: Path) -> Path:
    """Create or refresh the shared spatial index when its source has changed."""
    source_path = Path(source_path)
    index_path = Path(index_path)
    if _index_is_current(index_path, source_path):
        return index_path
    with _BUILD_LOCK:
        if _index_is_current(index_path, source_path):
            return index_path
        temporary = index_path.with_name(f"{index_path.name}.{os.getpid()}.tmp")
        temporary.unlink(missing_ok=True)
        try:
            print(
                "Building the shared street-network spatial index from the local "
                "GraphML file (one-time full-file scan)..."
            )
            build_graphml_spatial_index(source_path, temporary)
            temporary.replace(index_path)
        finally:
            temporary.unlink(missing_ok=True)
    return index_path


def load_graphml_bbox(
    index_path: Path,
    bbox: tuple[float, float, float, float],
    *,
    margin: float = 0.005,
):
    """Load only indexed edges intersecting the bbox plus a small routing margin."""
    import networkx as nx

    west, south, east, north = (float(value) for value in bbox)
    west -= margin
    south -= margin
    east += margin
    north += margin
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    with sqlite3.connect(index_path) as connection:
        rows = connection.execute(
            """SELECT e.u, e.v, e.edge_key, e.length, e.geometry,
                      u.x, u.y, v.x, v.y
               FROM edge_spatial_index r
               JOIN edges e ON e.id = r.id
               JOIN nodes u ON u.node_id = e.u
               JOIN nodes v ON v.node_id = e.v
               WHERE r.minx <= ? AND r.maxx >= ?
                 AND r.miny <= ? AND r.maxy >= ?""",
            (east, west, north, south),
        )
        for u, v, edge_key, length, geometry_blob, ux, uy, vx, vy in rows:
            u_key, v_key = _node_key(u), _node_key(v)
            if u_key not in graph:
                graph.add_node(u_key, x=float(ux), y=float(uy))
            if v_key not in graph:
                graph.add_node(v_key, x=float(vx), y=float(vy))
            attrs = {}
            if length is not None:
                attrs["length"] = float(length)
            if geometry_blob is not None:
                attrs["geometry"] = wkb.loads(geometry_blob)
            graph.add_edge(u_key, v_key, key=_edge_key(edge_key), **attrs)
    return graph


__all__ = [
    "build_graphml_spatial_index",
    "ensure_graphml_spatial_index",
    "load_graphml_bbox",
    "spatial_index_path",
]
