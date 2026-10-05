"""Read the slim bundled SLP defaults or an explicitly supplied parameter table."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

COEFFICIENTS = ("A", "B", "C", "D", "m_H", "b_H", "m_w", "b_w")
WEEKDAYS = tuple(range(1, 8))  # Monday through Sunday; holidays use Sunday.


def read_slp_tables(
    path: Path, profiles: tuple[tuple[str, str], ...] = ()
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Accept the historical workbook or the documented, versioned JSON schema."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"SLP parameters missing: {path}. "
            "Restore the bundled JSON or supply a local input; see docs/slp-inputs.md "
            "and paths.slp_parameters."
        )
    if path.suffix.lower() == ".json":
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 1:
            raise ValueError("SLP JSON requires schema_version 1")
        source = document.get("source")
        if not isinstance(source, dict) or not all(
            isinstance(source.get(key), str) and source[key].strip()
            for key in ("title", "url", "license")
        ):
            raise ValueError("SLP JSON requires source title, url and license")
        parameters = pd.DataFrame(document.get("parameters", []))
        factors = pd.DataFrame(document.get("weekday_factors", []))
        factors.rename(columns={str(day): day for day in WEEKDAYS}, inplace=True)
    else:
        with pd.ExcelFile(path) as workbook:
            for sheet in ("Parameter", "Tagesfaktoren"):
                if sheet not in workbook.sheet_names:
                    raise ValueError(f"missing required sheet: {sheet}")
            parameters = pd.read_excel(workbook, sheet_name="Parameter", keep_default_na=False,
                                       dtype={"Sigmoid_SigLinDe": str, "ausprägung": str})
            factors = pd.read_excel(workbook, sheet_name="Tagesfaktoren")
        for column in ("Sigmoid_SigLinDe", "ausprägung"):
            if column not in parameters:
                raise ValueError(f"Parameter: missing required columns: {column}")
        parameters["characteristics"] = (
            parameters["Sigmoid_SigLinDe"].astype(str) + parameters["ausprägung"].astype(str)
        )
    if profiles:
        if not {"category", "characteristics"}.issubset(parameters.columns) or "category" not in factors:
            raise ValueError("SLP input requires category and characteristics identifiers")
        parameters = parameters.loc[
            [(str(row.category).strip(), str(row.characteristics).strip()) in profiles
             for row in parameters.itertuples()]
        ].copy()
        categories = {category for category, _ in profiles}
        factors = factors.loc[factors["category"].astype(str).str.strip().isin(categories)].copy()
    for label, table, columns in (
        ("Parameter", parameters, ("category", "characteristics", *COEFFICIENTS)),
        ("Tagesfaktoren", factors, ("category", *WEEKDAYS)),
    ):
        missing = set(columns) - set(table.columns)
        if missing:
            raise ValueError(f"{label}: missing required columns: {', '.join(sorted(map(str, missing)))}")
        if table.empty:
            raise ValueError(f"{label}: no profile rows")
        identifiers = ("category", "characteristics") if label == "Parameter" else ("category",)
        for column in identifiers:
            if table[column].isna().any() or table[column].astype(str).str.strip().eq("").any():
                raise ValueError(f"{label}: empty {column}")
            table[column] = table[column].astype(str).str.strip()
        if path.suffix.lower() != ".json":
            # Historical workbook repeats identical GHD rows. Collapse only
            # identical model inputs; conflicting duplicates remain errors.
            table.drop_duplicates(subset=list(columns), inplace=True)
        if table.duplicated(list(identifiers)).any():
            raise ValueError(f"{label}: duplicate profile rows")
        numeric = COEFFICIENTS if label == "Parameter" else WEEKDAYS
        for column in numeric:
            table[column] = pd.to_numeric(table[column], errors="raise")
            if not np.isfinite(table[column].to_numpy(dtype=float)).all():
                raise ValueError(f"{label}: non-finite values in {column}")
        if label == "Tagesfaktoren" and (table[list(WEEKDAYS)] <= 0).any().any():
            raise ValueError("Tagesfaktoren: weekday factors must be positive")
    if not set(parameters["category"]).issubset(set(factors["category"])):
        raise ValueError("Tagesfaktoren: missing categories used by Parameter")
    if profiles and not set(profiles).issubset(set(zip(parameters["category"], parameters["characteristics"]))):
        raise ValueError("Parameter: missing configured profiles")
    return parameters, factors
