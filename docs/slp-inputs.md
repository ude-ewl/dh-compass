# Supplying heat SLP coefficients

DH-COMPASS defaults to the bundled `data/reference/slp_parameters.json`.
It contains the HEF03 and HMF03 coefficients and weekday factors used by the
default building and subgraph profiles. No separate workbook is needed for
these profiles.

The following reference is directly accessible:

BDEW/VKU/GEODE, *Leitfaden Abwicklung von Standardlastprofilen Gas*,
Kooperationsvereinbarung Gas, Annex XV, 27 March 2026, Appendix 6.
[Official PDF](https://www.bdew.de/media/documents/260327_LF_SLP_Gas_KoV_XV_CO4f7Rb.pdf),
[archived PDF](https://web.archive.org/web/20260619125016/https://www.bdew.de/media/documents/260327_LF_SLP_Gas_KoV_XV_CO4f7Rb.pdf).

The bundled values match the seven decimal places and weekday factors printed
in this edition. The JSON records its source and transcription credit. The cited
guide does not state an open-data license, so attribution must not be interpreted
as permission to redistribute additional BDEW tables or publications.

The [BDEW SLP page](https://www.bdew.de/energie/standardlastprofile-gas/) discusses
the procedure. Operators such as [EAM Netz](https://www.eam-netz.de/fuer-partner/marktpartner/erdgas/standardlastprofilverfahren/)
publish their own procedure-specific workbooks. These are potential sources of
authorized coefficients, not drop-in replacements for the DH-COMPASS schema.
Check the operator's profile variants, terms and values before adapting them.
Ask the original supplier/BDEW for an authorized copy when reproducing historical
results. Do not assume that a public workbook or an open-source wrapper grants
redistribution rights for the underlying coefficient database.

## Custom workbook

For profiles beyond HEF03/HMF03, supply your own JSON or authorized workbook
and set an override. For example:

```toml
[paths]
slp_parameters = "data/reference/SLP-Gas_Pramter_Tagesfaktoren.xlsx"
```

The `Parameter` sheet needs `category`, `Sigmoid_SigLinDe`, `ausprägung`,
`A`, `B`, `C`, `D`, `m_H`, `b_H`, `m_w`, `b_w`. The characteristic identifier
is the exact concatenation of the two characteristic columns; retain leading
zeroes as text. `Tagesfaktoren` needs `category` and numeric column headings
`1` through `7` (Monday through Sunday). Holidays use Sunday's factor.
Coefficients must be finite; weekday factors must be positive. Each profile key
and weekday category must be unique. Identifiers are trimmed; identical workbook
rows are collapsed (the historical workbook repeats two GHD rows), while
conflicting duplicates are rejected. Defaults select HEF/HMF with characteristic
`03`; your table must contain the profiles actually selected in configuration.

## Portable local JSON

The bundled input is already JSON. Additional inputs can use the same schema. Set
`paths.slp_parameters = "data/reference/my-authorized-slp.json"`.
The schema is:

```text
{
  "schema_version": 1,
  "source": {"title": "source and version", "url": "source URL", "license": "actual terms"},
  "parameters": [
    {"category": "profile ID", "characteristics": "variant ID",
     "A": number, "B": number, "C": number, "D": number,
     "m_H": number, "b_H": number, "m_w": number, "b_w": number}
  ],
  "weekday_factors": [
    {"category": "profile ID", "1": number, "2": number, "3": number,
     "4": number, "5": number, "6": number, "7": number}
  ]
}
```

This is a schema illustration, not a production dataset. Populate it only with
coefficients you may use. To convert the existing authorized local workbook:

```bash
uv run python scripts/convert_slp.py data/reference/SLP-Gas_Pramter_Tagesfaktoren.xlsx data/reference/my-authorized-slp.json --profile HEF:03 --profile HMF:03 --source-title "My authorized SLP source/version" --source-url "https://www.bdew.de/energie/standardlastprofile-gas/" --source-license "local-use-only; redistribution not established"
```

Conversion preserves numbers and does not grant new rights. Keep local source
workbooks out of Git. Validate any replacement against annual energy, peak load
and seasonal shape before relying on planning results. The program normalizes
annual demand; normalization alone cannot establish that a profile is correct.
Conversion without `--profile` validates every row; use explicit profile
selection to convert only the profiles needed.
