from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from dh_compass.preprocessing.street_network import (
    download_street_network,
    street_network_cache_path,
)


def _config(cache_root: Path):
    return SimpleNamespace(
        scenario=SimpleNamespace(
            bbox=(8.7, 52.1, 8.8, 52.2),
            geodata_frame="bbox",
        ),
        paths=SimpleNamespace(cache_root=cache_root),
    )


def test_street_network_uses_existing_graphml_cache(monkeypatch, tmp_path: Path) -> None:
    cache_path = street_network_cache_path(_config(tmp_path))
    cache_path.touch()
    graph = Mock()
    graph.to_undirected.return_value = "cached-network"
    ox = SimpleNamespace(
        load_graphml=Mock(return_value=graph),
        graph_from_bbox=Mock(),
        save_graphml=Mock(),
    )
    monkeypatch.setitem(sys.modules, "osmnx", ox)

    result = download_street_network(_config(tmp_path))

    assert result == "cached-network"
    ox.load_graphml.assert_called_once_with(filepath=cache_path)
    ox.graph_from_bbox.assert_not_called()


def test_street_network_cache_is_scoped_to_its_bbox(tmp_path: Path) -> None:
    first = street_network_cache_path(_config(tmp_path))
    second_config = _config(tmp_path)
    second_config.scenario.bbox = (8.8, 52.1, 8.9, 52.2)

    assert first != street_network_cache_path(second_config)


def test_street_network_downloads_and_persists_a_missing_cache(monkeypatch, tmp_path: Path) -> None:
    graph = Mock()
    graph.to_undirected.return_value = "downloaded-network"
    ox = SimpleNamespace(
        load_graphml=Mock(),
        graph_from_bbox=Mock(return_value=graph),
        save_graphml=Mock(),
    )
    monkeypatch.setitem(sys.modules, "osmnx", ox)

    result = download_street_network(_config(tmp_path))

    assert result == "downloaded-network"
    ox.graph_from_bbox.assert_called_once_with(
        (8.7, 52.1, 8.8, 52.2), network_type="drive"
    )
    ox.save_graphml.assert_called_once_with(
        graph, filepath=street_network_cache_path(_config(tmp_path))
    )
