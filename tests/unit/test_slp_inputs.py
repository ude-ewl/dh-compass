"""Verify input portability and the bundled defaults without provider workbooks."""

import json

import numpy as np
import pandas as pd
import pytest

from dh_compass.demand.slp_inputs import read_slp_tables


def synthetic_document():
    return {
        "schema_version": 1,
        "source": {"title": "Synthetic test", "url": "https://example.invalid", "license": "MIT"},
        "parameters": [{"category": "TEST", "characteristics": "03", "A": 1,
                        "B": -20, "C": 2, "D": 0.1, "m_H": 0, "b_H": 0,
                        "m_w": 0, "b_w": 0}],
        "weekday_factors": [{"category": "TEST", **{str(day): 1 for day in range(1, 8)}}],
    }


def test_json_and_workbook_preserve_same_coefficients(tmp_path):
    document = synthetic_document()
    json_path = tmp_path / "slp.json"
    json_path.write_text(json.dumps(document))
    parameters, factors = read_slp_tables(json_path)
    workbook_path = tmp_path / "slp.xlsx"
    workbook_parameters = parameters.drop(columns="characteristics").copy()
    workbook_parameters["Sigmoid_SigLinDe"] = "X"
    workbook_parameters["ausprägung"] = "03"
    with pd.ExcelWriter(workbook_path) as workbook:
        workbook_parameters.to_excel(workbook, sheet_name="Parameter", index=False)
        factors.to_excel(workbook, sheet_name="Tagesfaktoren", index=False)
    excel_parameters, excel_factors = read_slp_tables(workbook_path)
    assert excel_parameters.iloc[0]["A"] == parameters.iloc[0]["A"]
    assert excel_factors.to_dict("records") == factors.to_dict("records")


@pytest.mark.parametrize("problem", ["source", "day", "nonfinite", "duplicate", "category"])
def test_invalid_input_fails_with_explanation(tmp_path, problem):
    document = synthetic_document()
    if problem == "source":
        del document["source"]
    elif problem == "day":
        del document["weekday_factors"][0]["7"]
    elif problem == "nonfinite":
        document["parameters"][0]["A"] = float("nan")
    elif problem == "duplicate":
        document["parameters"] *= 2
    else:
        document["weekday_factors"][0]["category"] = "OTHER"
    path = tmp_path / "slp.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        read_slp_tables(path)


def test_weekday_order_is_explicit_even_with_extra_columns(tmp_path):
    document = synthetic_document()
    document["weekday_factors"][0] = {"category": "TEST", "notes": "ignored", **{
        str(day): day for day in reversed(range(1, 8))}}
    path = tmp_path / "slp.json"
    path.write_text(json.dumps(document))
    _, factors = read_slp_tables(path)
    assert [factors.iloc[0][day] for day in range(1, 8)] == list(range(1, 8))


def test_selected_profile_ignores_unused_bad_rows_but_requires_requested_profile(tmp_path):
    document = synthetic_document()
    document["parameters"].append({**document["parameters"][0], "category": "OTHER", "A": "malformed"})
    path = tmp_path / "slp.json"
    path.write_text(json.dumps(document))
    parameters, _ = read_slp_tables(path, (("TEST", "03"),))
    assert parameters["category"].tolist() == ["TEST"]
    with pytest.raises(ValueError):
        read_slp_tables(path)
    with pytest.raises(ValueError, match="missing configured profiles"):
        read_slp_tables(path, (("TEST", "03"), ("MISSING", "03")))


def test_bundled_defaults_match_workbook_profiles_without_external_data(tmp_path):
    from dh_compass.config import PathConfig
    from dh_compass.demand.heat_profiles import generate_slp_from_temperatures

    paths = PathConfig.from_project_root()
    assert paths.slp_parameters.name == "slp_parameters.json"
    parameters, factors = read_slp_tables(paths.slp_parameters)
    assert set(zip(parameters["category"], parameters["characteristics"])) == {
        ("HEF", "03"), ("HMF", "03"),
    }
    legacy = parameters.drop(columns="characteristics").copy()
    legacy["Sigmoid_SigLinDe"] = "0"
    legacy["ausprägung"] = "3"
    workbook_path = tmp_path / "legacy.xlsx"
    with pd.ExcelWriter(workbook_path) as workbook:
        legacy.to_excel(workbook, sheet_name="Parameter", index=False)
        factors.to_excel(workbook, sheet_name="Tagesfaktoren", index=False)
    dates = pd.date_range("2022-01-01", periods=8760, freq="h", tz="UTC")
    temperatures = pd.DataFrame({"datetime": dates,
                                 "temperature": 8 + 15 * np.sin(np.arange(8760) / 8760 * 2 * np.pi)})
    for category in ("HEF", "HMF"):
        actual = generate_slp_from_temperatures(
            2022, category, "03", 100_000, temperatures, slp_path=paths.slp_parameters,
        )
        expected = generate_slp_from_temperatures(
            2022, category, "03", 100_000, temperatures, slp_path=workbook_path,
        )
        np.testing.assert_allclose(actual["load"], expected["load"], rtol=1e-14)
        assert actual["load"].sum() == pytest.approx(100_000)
