import pandas as pd

from dh_compass.economics.cost_curves import read_ts_data


def test_csv_preserves_full_precision_ratios_and_excel_timestamp_noise(tmp_path):
    path = tmp_path / "factors.csv"
    path.write_text(
        "Datum,sh_to_wh_ratio\n"
        "2012-01-01T00:59:59.997000,0.23839409509808987\n"
        "2012-01-01T02:00:00,0.0\n",
        encoding="utf-8",
    )

    data, hours, days = read_ts_data(path)

    assert data["sh_to_wh_ratio"].tolist() == [0.23839409509808987, 0.0]
    assert data["Datum"].tolist() == [
        pd.Timestamp("2012-01-01T00:59:59.997000"),
        pd.Timestamp("2012-01-01T02:00:00"),
    ]
    assert hours == 2
    assert days == 2 / 24


def test_existing_excel_override_remains_supported(tmp_path, monkeypatch):
    expected = pd.DataFrame({"Datum": [pd.Timestamp("2012-01-01")], "sh_to_wh_ratio": [0.25]})
    path = tmp_path / "custom.xlsx"
    calls = []

    def read_excel(filepath):
        calls.append(filepath)
        return expected

    monkeypatch.setattr(pd, "read_excel", read_excel)
    data, hours, days = read_ts_data(path)

    pd.testing.assert_frame_equal(data, expected)
    assert calls == [path]
    assert (hours, days) == (1, 1 / 24)
