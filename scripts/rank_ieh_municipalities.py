"""Rank NRW municipalities (population 10k-100k) by industrial excess heat (IEH) potential.

Ranks municipalities by
  1. absolute IEH potential (GWh/a, EH_95 scenario)
  2. IEH potential per capita (MWh/a per inhabitant)

Data sources:
  - IEH potentials:   data/external/heat_supply_potentials/industrial_eh.gpkg (Hotmaps, EPSG:3035)
  - Municipality boundaries: OSM (admin_level=8, AGS 05*, cached as data/gemeinden_nrw.gpkg)
  - Population:       Destatis Gemeindeverzeichnis (cached as data/gemeindeverzeichnis.xlsx)

Output:
  - outputs/ieh_ranking/ieh_ranking_absolute.csv
  - outputs/ieh_ranking/ieh_ranking_per_capita.csv
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import openpyxl
import osmnx as ox
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
IEH_PATH = ROOT / "data" / "external" / "heat_supply_potentials" / "industrial_eh.gpkg"
GEMEINDEN_CACHE = ROOT / "data" / "cache" / "gemeinden_nrw.gpkg"
GV_CACHE = ROOT / "data" / "cache" / "gemeindeverzeichnis.xlsx"
GV_URL = (
    "https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/Gemeindeverzeichnis/"
    "Administrativ/Archiv/GVAuszugQ/AuszugGV3QAktuell.xlsx?__blob=publicationFile&v=21"
)
OUT_DIR = ROOT / "outputs" / "ieh_ranking"

POP_MIN = 10_000
POP_MAX = 100_000
IEH_SCENARIO = "EH_95_GWh"  # matches INDUSTRIAL_EH_SCENARIO in configs/default.toml and src/dh_compass/config/

HEADERS = {"User-Agent": "DH-COMPASS-IEH-ranking/0.1 (research)"}


def load_municipalities() -> gpd.GeoDataFrame:
    """Load NRW municipality polygons (OSM, admin_level=8) deduped by AGS."""
    if GEMEINDEN_CACHE.exists():
        return gpd.read_file(GEMEINDEN_CACHE)

    ox.settings.timeout = 300
    ox.settings.max_query_area_size = 50_000_000_000
    gdf = ox.features_from_place(
        "Nordrhein-Westfalen, Germany",
        tags={"boundary": "administrative", "admin_level": "8"},
    )
    ags = gdf["de:amtlicher_gemeindeschluessel"]
    gdf = gdf[ags.astype(str).str.startswith("05", na=False) & (ags.astype(str).str.len() == 8)]
    gdf = gdf[["name", "de:amtlicher_gemeindeschluessel", "geometry"]].rename(
        columns={"name": "Gemeinde", "de:amtlicher_gemeindeschluessel": "AGS"}
    )
    gdf["area_m2"] = gdf.to_crs(25832).area
    gdf = gdf.sort_values("area_m2", ascending=False).drop_duplicates(subset="AGS")
    gdf = gdf.drop(columns=["area_m2"]).reset_index(drop=True)
    gdf.to_file(GEMEINDEN_CACHE, driver="GPKG")
    return gdf


def load_population() -> pd.DataFrame:
    """Load official population per NRW municipality from Destatis Gemeindeverzeichnis."""
    if not GV_CACHE.exists():
        r = requests.get(GV_URL, headers=HEADERS, timeout=180)
        r.raise_for_status()
        GV_CACHE.write_bytes(r.content)

    wb = openpyxl.load_workbook(GV_CACHE, read_only=True)
    ws = wb["Onlineprodukt_Gemeinden30092025"]
    rows = []
    for row in ws.iter_rows(min_row=6, values_only=True):
        if row[0] == "60" and str(row[2]) == "05":
            ags = "".join(str(x) for x in (row[2], row[3], row[4], row[6]))
            rows.append(
                {
                    "AGS": ags,
                    "Gemeinde": row[7],
                    "Flaeche_km2": row[8],
                    "Einwohner": row[9],
                }
            )
    wb.close()
    return pd.DataFrame(rows)


def load_ieh() -> gpd.GeoDataFrame:
    ieh = gpd.read_file(IEH_PATH)
    # geometry is EPSG:3035; filter NRW via the WGS84 lat/lon columns
    in_nrw = (
        (ieh["Latitude"] >= 50.3)
        & (ieh["Latitude"] <= 52.0)
        & (ieh["Longitude"] >= 5.8)
        & (ieh["Longitude"] <= 9.5)
    )
    ieh = ieh[in_nrw]
    ieh = ieh[["EH_55_GWh", "EH_95_GWh", "geometry"]].to_crs(25832)
    return ieh


def main() -> None:
    print("Loading municipality boundaries (OSM)...")
    gemeinden = load_municipalities()
    print(f"  {len(gemeinden)} municipalities")

    print("Loading population (Destatis Gemeindeverzeichnis)...")
    pop = load_population()
    print(f"  {len(pop)} municipalities with official population")
    assert len(gemeinden) == len(pop) == 396, "municipality count mismatch"

    print("Loading IEH potentials...")
    ieh = load_ieh()
    print(f"  {len(ieh)} IEH sites within NRW bbox")

    print("Spatial join: IEH sites -> municipalities...")
    join = gpd.sjoin(ieh, gemeinden.to_crs(25832), how="left", predicate="within")
    agg = (
        join.groupby("AGS")[["EH_55_GWh", "EH_95_GWh"]]
        .sum()
        .reset_index()
    )
    df = (
        gemeinden.merge(agg, on="AGS", how="left")
        .merge(pop, on="AGS", how="left", suffixes=("", "_destatis"))
    )
    df["EH_95_GWh"] = df["EH_95_GWh"].fillna(0.0)
    df["EH_55_GWh"] = df["EH_55_GWh"].fillna(0.0)
    df["EH_95_MWh_cap"] = df["EH_95_GWh"] * 1000 / df["Einwohner"]
    df["EH_55_MWh_cap"] = df["EH_55_GWh"] * 1000 / df["Einwohner"]

    sel = df[
        (df["Einwohner"] >= POP_MIN) & (df["Einwohner"] <= POP_MAX)
    ].copy()
    sel["Gemeinde"] = sel["Gemeinde"].str.replace(", Stadt", "").str.replace(", Kreisstadt", "")
    print(f"Municipalities with {POP_MIN}-{POP_MAX} inhabitants: {len(sel)}")
    print(f"  with IEH potential > 0: {(sel['EH_95_GWh'] > 0).sum()}")

    cols = [
        "AGS", "Gemeinde", "Einwohner", "Flaeche_km2",
        "EH_95_GWh", "EH_55_GWh", "EH_95_MWh_cap", "EH_55_MWh_cap",
    ]
    abs_rank = sel.sort_values("EH_95_GWh", ascending=False)[cols]
    per_cap_rank = sel.sort_values("EH_95_MWh_cap", ascending=False)[cols]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, df_out in (("ieh_ranking_absolute.csv", abs_rank), ("ieh_ranking_per_capita.csv", per_cap_rank)):
        path = OUT_DIR / name
        try:
            df_out.to_csv(path, index=False)
        except PermissionError:
            path = OUT_DIR / name.replace(".csv", "_new.csv")
            df_out.to_csv(path, index=False)
            print(f"WARNING: {name} is open in another program; wrote {path.name} instead")
    with pd.ExcelWriter(OUT_DIR / "ieh_ranking.xlsx") as xl:
        abs_rank.to_excel(xl, sheet_name="absolute", index=False)
        per_cap_rank.to_excel(xl, sheet_name="per_capita", index=False)

    print(f"\nSaved CSVs to {OUT_DIR}")

    def fmt(data):
        return data.round(2).to_string(index=False)

    print("\n=== TOP 25 BY ABSOLUTE IEH POTENTIAL (EH_95, GWh/a) ===")
    print(fmt(abs_rank.head(25)))
    print("\n=== TOP 25 BY IEH POTENTIAL PER CAPITA (EH_95, MWh/a per inhabitant) ===")
    print(fmt(per_cap_rank.head(25)))
    print("\n=== BOTTOM 10 BY IEH POTENTIAL PER CAPITA ===")
    print(fmt(per_cap_rank.tail(10)))


if __name__ == "__main__":
    main()
