# Biomass energy semantics and local population-data verification

Research checked on 12 October 2026. This is the source-verification record;
[setup and implemented behavior](biomass-allocation.md) are documented separately.

## Conclusion

**`Bio_TWh` in the repository's `biomass_nuts2(1).gpkg` is annual biomass fuel energy available to district heating, not useful heat after a boiler/CHP. The source has already applied a 50% allocation to district heating.**

This conclusion is based on reconstructing every non-null value from the underlying ENSPRESO energy workbook, rather than relying solely on ambiguous descriptions of “heat potential.”

Consequently:

- Continue constraining the sum of biomass boiler and biomass CHP **fuel inputs**.
- Convert TWh to MWh with `× 1,000,000`.
- Do not halve the potential again.
- Do not multiply the fuel budget by a boiler or CHP efficiency before passing it to the solver.
- The model's technology efficiencies convert fuel input into heat/electricity. Report the fuel allowance separately from actual useful heat.
- Population allocation changes the geographical allocation, not these energy semantics.

## 1. Paper and metadata: why the wording alone is insufficient

[Manz et al., Renewable Energy 224 (2024), 120111](https://repositum.tuwien.at/bitstream/20.500.12708/195104/1/Manz-2024-Renewable%20Energy-vor.pdf), sections 2.3 and 2.3.1:

- The paper generally describes quantified heat as heat delivered to district-heating areas.
- Table 1 mentions biomass-CHP efficiency assumptions of 53% and 55% for its temperature scenarios.
- The biomass subsection selects ENSPRESO `ENS_Med`, year 2050, eight commodity codes, and assumes that 50% is available to DH.
- It reports approximately 734 TWh and allocates regional biomass to DH areas relative to DH demand.

The [Fordatis metadata workbook](https://fordatis.fraunhofer.de/bitstream/fordatis/341.5/11/Results_DH_Matching_Cluster.xlsx), sheet `Metadata`, describes `Bio_TWh` only as:

> Biomass for NUTS2 (2013) areas with available potential for DH in 2050 in TWh ("Bio_TWh").

Neither that field description nor the paper's general wording conclusively identifies the serialized layer as fuel or heat. The paper's matched supply/utilization results and temperature assumptions must not automatically be assigned to the NUTS2 input layer. The reconstruction below identifies the transformation actually present in that layer; it does not attempt to audit every heat-output calculation in the paper.

## 2. Numerical reconstruction from the primary ENSPRESO workbook

Sources:

- [JRC ENSPRESO Biomass dataset](https://data.jrc.ec.europa.eu/dataset/74ed5a04-7d74-4807-9eab-b94774309d9f).
- [Primary energy workbook](https://cidportal.jrc.ec.europa.eu/ftp/jrc-opendata/ENSPRESO/ENSPRESO_BIOMASS.xlsx).
- [Underlying JRC bioenergy-potential report](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC98626/biomass%20potentials%20in%20europe_web%20rev.pdf), explaining biomass feedstock potentials and mass/energy conversions, rather than heat output from one specified DH technology.

Workbook sheet: `ENER - NUTS2 BioCom E`.

Actual relevant columns: `Year`, `Scenario`, `NUTS0`, `NUST2` (source spelling), `E-Comm`, `B-Com`, `NUTS2 Potential available by Bio Commodity`, `Unit`.

Filter:

```text
Year = 2050
Scenario = ENS_Med
E-Comm in:
    MINBIOAGRW1
    MINBIOCRP31
    MINBIOCRP41
    MINBIOCRP41a
    MINBIOFRSR1
    MINBIOFRSR1a
    MINBIOWOOW1
    MINBIOWOOW1a
```

Sum biomass energy by NUTS2, with units PJ. The reconstruction is:

```text
Bio_TWh(region) = selected_ENSPRESO_fuel_PJ(region) / 3.6 × 0.5
```

The `0.5` is the paper's share made available to DH. **There is no additional boiler/CHP heat-conversion factor in the stored values.** The source workbook treats these as biomass energy commodities/feedstocks, including agricultural waste, miscanthus/switchgrass, willow/poplar, forestry residues, woodchips and sawdust.

Results against the existing checksum-pinned local biomass layer:

- 236 region records: 226 numeric potentials and 10 null potentials.
- **226 out of 226 numeric values reproduce within absolute tolerance `1e-7` TWh.**
- Maximum absolute discrepancy: approximately `3.33e-9` TWh, consistent with stored rounding.
- Stored total: **733.74524709 TWh**.
- Reconstructed total: **733.7452470833 TWh**, explaining the paper's rounded 734 TWh.
- Raw selected ENSPRESO energy for those regions is twice this total. Applying another 50% share or a conversion efficiency would no longer reproduce the file.

### NRW checks

| NUTS2 | Selected ENSPRESO fuel energy, PJ | After `/ 3.6 × 0.5`, TWh | Stored `Bio_TWh` |
| --- | ---: | ---: | ---: |
| `DEA1` | 8.29323 | 1.1518375 | 1.1518375 |
| `DEA2` | 13.26421 | 1.8422513889 | 1.842251389 |
| `DEA3` | 14.15334 | 1.9657416667 | 1.965741667 |
| `DEA4` | 13.22544 | 1.8368666667 | 1.836866667 |
| `DEA5` | 14.76531 | 2.0507375 | 2.0507375 |

For Arnsberg (`DEA5`), in particular:

```text
14.76531 PJ fuel / 3.6 × 50% = 2.0507375 TWh fuel available to DH
```

ENSPRESO workbook SHA256 at verification:

```text
5f9e2579fabb561b966b5c1840f2ba40f227d4ad9a4b9545db94e71b5c389d98
```

It was downloaded to temporary research storage, not added to the repository or application inputs. The existing local biomass hash is recorded in `docs/licenses/data-manifest.json`.

## 3. Local VG250-EW file

The supplied file is:

```text
data/external/vg250-ew_ebenen_1231/DE_VG250.gpkg
```

Verified:

- `gpkg_contents` describes `vg250_gem` with reference date **2024-12-31** and CRS **EPSG:25832**.
- It contains `vg250_gem`, `vg250_rbz` and `vgtb_vz_gem`.
- Municipal columns include `AGS`, `ARS`, `GEN`, `NUTS`, `EWZ`, `GF`.
- The assignment table includes `ARS_G`, `AGS_G`, `NUTS2_CODE` and `NUTS2_NAME`; an explicit NUTS2 join is available, so a code-prefix fallback is unnecessary for this input.
- Municipal `GF = 4` records for NRW total 396. Their five regional population sums exactly match the five regional `GF = 4` EWZ values.
- Brilon: AGS `05958012`, population **25,424**, parent region `DEA5` with population **3,571,898**.

Local file size: **117,809,152 bytes**.

SHA256:

```text
2c880a1d9b8c338e71248dbac05d9b060510314041231d5c64dc8c54a9e198e8
```

Preparation reads this existing file offline; no additional VG250 download is needed. Retain its source and license notes with the companion manifest. NUTS-2013 compatibility is verified below. The municipality with the largest study-area overlap is selected automatically, with optional explicit AGS overrides. VG250 is not parcel-accurate.

## 4. What repeated studies in one municipality mean

A study is a calculation, not a resource reservation. Running it must not consume biomass or reduce what the next calculation sees.

For Brilon, the population method gives approximately **14,597 MWh/year of fuel energy** at project fraction 1.

- **Alternative studies:** a study of neighbourhood A and another of neighbourhood B each see 14,597 MWh/year if they independently test access to the whole municipal share. Re-running, deleting or comparing either study does not change the other. Their budgets must not be added as if they were separate resources.
- **Projects operating simultaneously:** the projects share one 14,597 MWh/year municipal envelope. For example, a manually coordinated 60%/40% split gives about 8,758 and 5,839 MWh/year. Alternatively, optimize both areas together with one shared cap. Other existing users may require reducing the allocatable envelope further.
- **Within one combined study:** the current cumulative central optimization shares the budget across the entire connected system. It must not grant a fresh municipal quota to each candidate area.

The implementation remains stateless across independent runs. `biomass_budget_fraction` is an explicit scenario assumption, not a reservation ledger and not an automatically enforced cross-project allocation. Checking that fractions or actual fuel uses across concurrent projects fit the municipal envelope is a separate portfolio-planning responsibility; automatic reservation/coordination would be a distinct feature.

## 5. NUTS 2013 to 2024 compatibility

The classification check used the three primary amendment workbooks linked by
[Eurostat's NUTS history](https://ec.europa.eu/eurostat/web/nuts/history), not merely
an assertion that the five regional codes still exist.

| Transition | Official workbook / checked sheet | SHA256 |
| --- | --- | --- |
| 2013 → 2016 | [NUTS2013-NUTS2016.xlsx](https://ec.europa.eu/eurostat/documents/345175/629341/NUTS2013-NUTS2016.xlsx), `NUTS2013-NUTS2016` | `1f1d7044cbbb41de54ad50414a60971e8c241a4239a5bc10e29eb7ea8a15f639` |
| 2016 → 2021 | [NUTS2021.xlsx](https://ec.europa.eu/eurostat/documents/345175/629341/NUTS2021.xlsx), `Changes detailed NUTS 2016-2021` | `b17dcc379bb3586550ec3b16f3f474dd2a8a55b4cfdcdc1e1575097f1c2d4761` |
| 2021 → 2024 | [NUTS2021-NUTS2024.xlsx](https://ec.europa.eu/eurostat/documents/345175/629341/NUTS2021-NUTS2024.xlsx/2b35915f-9c14-6841-8197-353408c4522d?t=1717505289640), `NUTS2021- NUTS2024` | `893731f6ae1383ed3a6541ab84ec342865377c36c7544b01f0da1d9bed86e17e` |

For **every transition**, all **59 NRW records** (`DEA` NUTS1, five NUTS2 and
53 NUTS3) map to themselves, with empty change indicators. There is no NRW
boundary/classification change recorded in these amendments. This establishes
the supported regional classification correspondence; it does not claim that
every generalized polygon vertex is identical.

As a separate local consistency check, all **396** municipal representative
points are covered by their explicitly assigned NUTS2 polygon in the existing
biomass layer. Runtime/preparation repeat that check and validate all five
regional potentials. Municipality populations are never interpolated using
polygon overlaps. The original workbooks were used only in temporary research
storage, not added to runtime dependencies or redistributed.
