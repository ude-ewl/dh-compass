
from pathlib import Path
import ast
import gc
import math
import re
import warnings

import networkx as nx
import osmnx as ox
from pyrosm import OSM


# ============================================================
# Pfade
# ============================================================

ROOT = Path(__file__).resolve().parent

PBF = ROOT / "data" / "external" / "nordrhein-westfalen-261020.osm.pbf"
SOURCE_DIR = ROOT / "data" / "processed" / "osm_nrw"
OUTPUT_DIR = ROOT / "data" / "external" / "osm"

BUILDINGS_FILE = OUTPUT_DIR / "buildings_nrw.gpkg"
ROADS_FILE = OUTPUT_DIR / "roads_nrw.gpkg"
GRAPH_FILE = OUTPUT_DIR / "driving_network_nrw.graphml"

ORIGINAL_GRAPH = SOURCE_DIR / "driving_network_nrw.graphml"


# ============================================================
# Hilfsfunktionen
# ============================================================

def output_exists(path: Path) -> bool:
    """Prüft, ob eine Ausgabedatei bereits vorhanden ist."""
    return path.exists() and path.stat().st_size > 0


def parse_osm_value(value):
    """Wandelt serialisierte GraphML-Werte bei Bedarf in Python-Werte um."""
    if not isinstance(value, str):
        return value

    value = value.strip()

    if not value:
        return value

    # Listen und Dictionaries, sofern sie als Text gespeichert sind
    if value.startswith(("[", "{", "(")):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            pass

    return value


def normalize_boolean_attribute(value):
    """
    Vereinheitlicht eindeutig erkennbare boolesche Werte.

    Unbekannte Werte wie 'alternating' oder '-1' bleiben unverändert,
    damit ihre Bedeutung nicht versehentlich verfälscht wird.
    """
    value = parse_osm_value(value)

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return value

    if isinstance(value, (list, tuple)):
        normalized = [
            normalize_boolean_attribute(item)
            for item in value
        ]
        return normalized

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"yes", "true", "1"}:
            return True

        if normalized in {"no", "false", "0"}:
            return False

    return value


def normalize_graph_attributes(graph):
    """
    Bereinigt Graphattribute, ohne unbekannte Werte pauschal
    in True oder False umzuwandeln.
    """
    boolean_attributes = {
        "oneway",
        "reversed",
        "access",
        "bridge",
        "tunnel",
        "junction",
    }

    for _, _, _, data in graph.edges(keys=True, data=True):
        for attribute in boolean_attributes:
            if attribute in data:
                data[attribute] = normalize_boolean_attribute(
                    data[attribute]
                )

    return graph


# ============================================================
# Gebäude extrahieren
# ============================================================

def extract_buildings():
    if output_exists(BUILDINGS_FILE):
        print(f"[Übersprungen] Gebäude existieren bereits: {BUILDINGS_FILE}")
        return

    if not PBF.is_file():
        raise FileNotFoundError(f"PBF-Datei nicht gefunden: {PBF}")

    print("[Start] Gebäude aus der PBF-Datei extrahieren ...")

    osm = OSM(str(PBF))
    buildings = osm.get_buildings()

    if buildings is None or buildings.empty:
        raise RuntimeError("Es wurden keine Gebäudedaten gefunden.")

    buildings.to_file(BUILDINGS_FILE, driver="GPKG")

    print(f"[Fertig] Gebäude gespeichert: {BUILDINGS_FILE}")

    del osm, buildings
    gc.collect()


# ============================================================
# Straßen extrahieren
# ============================================================

def extract_roads():
    if output_exists(ROADS_FILE):
        print(f"[Übersprungen] Straßen existieren bereits: {ROADS_FILE}")
        return

    if not PBF.is_file():
        raise FileNotFoundError(f"PBF-Datei nicht gefunden: {PBF}")

    print("[Start] Straßendaten aus der PBF-Datei extrahieren ...")

    osm = OSM(str(PBF))
    roads = osm.get_network(
        network_type="driving",
        nodes=False,
    )

    if roads is None or roads.empty:
        raise RuntimeError("Es wurden keine Straßendaten gefunden.")

    roads.to_file(ROADS_FILE, driver="GPKG")

    print(f"[Fertig] Straßen gespeichert: {ROADS_FILE}")

    del osm, roads
    gc.collect()


# ============================================================
# Straßennetz laden
# ============================================================

def load_source_graph():
    """
    Verwendet den vorhandenen Graph, wenn er existiert.
    Andernfalls wird er aus der PBF-Datei aufgebaut.
    """
    if output_exists(ORIGINAL_GRAPH):
        print(f"[Start] Vorhandenen Graph laden: {ORIGINAL_GRAPH}")

        graph = nx.read_graphml(
            ORIGINAL_GRAPH,
            force_multigraph=True,
        )

        print(
            f"[Geladen] {graph.number_of_nodes():,} Knoten, "
            f"{graph.number_of_edges():,} Kanten"
        )

        return graph

    if not PBF.is_file():
        raise FileNotFoundError(
            "Weder der ursprüngliche Graph noch die PBF-Datei "
            f"wurden gefunden.\nGraph: {ORIGINAL_GRAPH}\nPBF: {PBF}"
        )

    print("[Start] Straßennetz aus der PBF-Datei aufbauen ...")

    osm = OSM(str(PBF))

    nodes, edges = osm.get_network(
        network_type="driving",
        nodes=True,
    )

    graph = osm.to_graph(
        nodes,
        edges,
        graph_type="networkx",
        retain_all=True,
        osmnx_compatible=True,
    )

    del osm, nodes, edges
    gc.collect()

    print(
        f"[Erstellt] {graph.number_of_nodes():,} Knoten, "
        f"{graph.number_of_edges():,} Kanten"
    )

    return graph


# ============================================================
# Graph speichern
# ============================================================

def prepare_graph():
    if output_exists(GRAPH_FILE):
        print(f"[Übersprungen] Graph existiert bereits: {GRAPH_FILE}")
        return

    print("[Start] Straßennetz vorbereiten ...")

    graph = load_source_graph()
    graph = normalize_graph_attributes(graph)

    print("[Start] GraphML-Datei speichern ...")

    ox.save_graphml(
        graph,
        filepath=GRAPH_FILE,
    )

    print(f"[Fertig] Straßennetz gespeichert: {GRAPH_FILE}")
    print(
        f"[Info] {graph.number_of_nodes():,} Knoten, "
        f"{graph.number_of_edges():,} Kanten"
    )

    del graph
    gc.collect()


# ============================================================
# Hauptprogramm
# ============================================================

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("NRW-OSM-Daten vorbereiten")
    print("=" * 60)
    print(f"Quelle: {PBF}")
    print(f"Ziel:   {OUTPUT_DIR}")
    print()

    extract_buildings()
    extract_roads()
    prepare_graph()

    print()
    print("=" * 60)
    print("Alle Verarbeitungsschritte abgeschlossen.")
    print("=" * 60)


if __name__ == "__main__":
    main()
