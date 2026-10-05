"""Building clustering used by the decentral benchmark."""

from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans


def cluster_buildings_to_typgebaeude(
    building_demands: list[float],
    building_types: list[str],
    n_clusters: int = 5,
    random_state: int = 42,
) -> dict[int, dict[str, object]]:
    """Cluster buildings into representative demand/type groups."""

    if len(building_demands) <= n_clusters:
        building_types_filled = (
            building_types if building_types else ["Unknown"] * len(building_demands)
        )
        return {
            i: {
                "centroid_demand": building_demands[i],
                "dominant_type": building_types_filled[i],
                "building_indices": [i],
                "total_demand": building_demands[i],
                "n_buildings": 1,
            }
            for i in range(len(building_demands))
        }

    values = np.array([[demand, 0] for demand in building_demands])
    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    labels = kmeans.fit_predict(values)
    centroids = kmeans.cluster_centers_
    building_types_filled = (
        building_types if building_types else ["Unknown"] * len(building_demands)
    )

    clusters: dict[int, dict[str, object]] = {}
    for cluster_id in range(n_clusters):
        mask = labels == cluster_id
        demands = [
            building_demands[i]
            for i in range(len(building_demands))
            if mask[i]
        ]
        types = [
            building_types_filled[i]
            for i in range(len(building_demands))
            if mask[i]
        ]
        if not demands:
            continue
        counts: dict[str, int] = {}
        for building_type in types:
            counts[building_type] = counts.get(building_type, 0) + 1
        clusters[cluster_id] = {
            "centroid_demand": float(centroids[cluster_id][0]),
            "dominant_type": max(counts, key=counts.get),
            "building_indices": [i for i in range(len(building_demands)) if mask[i]],
            "total_demand": sum(demands),
            "n_buildings": len(demands),
        }
    return clusters


__all__ = ["cluster_buildings_to_typgebaeude"]
