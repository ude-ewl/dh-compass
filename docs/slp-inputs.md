# Supplying heat SLP coefficients

The maintainer confirmed on 5 October 2026 that
`SLP-Gas_Pramter_Tagesfaktoren.xlsx` was created by the Chair of Energy Economics
from BDEW PDF publications. It is a chair-authored transcription, not a missing
BDEW Excel download. The workbook remains excluded from the current source ZIP.

The code now defaults to the bundled `data/reference/slp_parameters.json`.
It contains only HEF03 and HMF03 coefficients and their weekday factors, which
are used by the default building and subgraph profiles. No separate workbook
is needed for these defaults. Original full-precision values are preserved.

The following reference is directly accessible:

BDEW/VKU/GEODE, *Leitfaden Abwicklung von Standardlastprofilen Gas*,
Kooperationsvereinbarung Gas, Annex XV, 27 March 2026, Appendix 6.
[Official PDF](https://www.bdew.de/media/documents/260327_LF_SLP_Gas_KoV_XV_CO4f7Rb.pdf),
[archived reference supplied by the maintainer](https://web.archive.org/web/20260619125016/https://www.bdew.de/media/documents/260327_LF_SLP_Gas_KoV_XV_CO4f7Rb.pdf).

The local HEF03/HMF03 coefficients match the seven decimal places printed in
this edition, and their weekday factors match. The local workbook has additional
decimal precision; this edition therefore corroborates the values but is not
established as the source of their full precision or the original transcription.
Do not relabel the workbook as an exact extraction from the 2026 edition.

The bundled input includes only the required HEF03/HMF03 numbers in JSON,
with a precise source/version citation and separate credit for the chair's
transcription. It includes no PDF prose, graphics or complete table layout.
Attribution is not itself a redistribution grant. No explicit open-data license
was identified in the cited guide. Individual factual numbers and a protected
compilation are different questions: [UrhG § 2](https://www.gesetze-im-internet.de/urhg/__2.html)
requires a personal intellectual creation, while
[UrhG § 87b](https://www.gesetze-im-internet.de/urhg/__87b.html) addresses substantial
database extraction and certain repeated systematic extractions. Whether those
rights apply to this extraction has not been legally established. Another
package's citation does not resolve that question or license the source data.

The maintainer requested adoption of this slim attributed JSON as the bundled
default. This records the release decision; it does not assert that the BDEW
publication grants an open-data license or that the chair owns rights in the
underlying compilation. Source metadata retains that distinction and the
unresolved origin of the additional decimal precision.

The [BDEW SLP page](https://www.bdew.de/energie/standardlastprofile-gas/) discusses
the procedure. Operators such as [EAM Netz](https://www.eam-netz.de/fuer-partner/marktpartner/erdgas/standardlastprofilverfahren/)
publish their own procedure-specific workbooks. These are potential sources of
authorized coefficients, not drop-in replacements for the DH-COMPASS schema.
Check the operator's profile variants, terms and values before adapting them.
Ask the original supplier/BDEW for an authorized copy when reproducing historical
results. Do not assume that a public workbook or an open-source wrapper grants
redistribution rights for the underlying coefficient database.

## Existing workbook

For profiles beyond HEF03/HMF03, supply your own JSON or authorized workbook
and set an override. To use the original local workbook:

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

Conversion preserves numbers and does not grant new rights. Both files stay
ignored. Validate any replacement against annual energy, peak load and seasonal
shape before relying on planning results. The program normalizes annual demand;
normalization alone cannot establish that a profile is the correct one.

The local historical workbook also contains malformed numeric entries in an
unused GHD variant. Runtime and readiness validate the configured profiles only,
so this does not block the default HEF/HMF calculation. Conversion without
`--profile` validates every row and rejects malformed data. Use explicit profile
selection to export exactly the profiles needed, or obtain corrected values from
the authorized source; do not guess a repair for combined/text coefficient cells.
