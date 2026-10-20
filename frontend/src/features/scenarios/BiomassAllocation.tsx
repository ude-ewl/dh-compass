import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Checkbox, FormControlLabel, Link, Paper, Stack, Typography } from "@mui/material";
import { updateScenarioConfig } from "../../api/client";
import { useScenarioConfigQuery } from "../../api/queries";
import { ApiErrorAlert } from "../../components/feedback/ApiErrorAlert";
import { useLocale } from "../../i18n/locale";
import { tr } from "../../i18n/translate";
import { formatMwh, formatNumber } from "../results/format";

interface Municipality {
  ags: string;
  name: string;
  population: number;
  region_population?: number;
  population_share?: number;
  allocated_fuel_mwh?: number;
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>) : null;
}

function municipalities(value: unknown): Municipality[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Municipality => {
    const row = record(item);
    return Boolean(row && typeof row.ags === "string" && typeof row.name === "string"
      && typeof row.population === "number" && Number.isFinite(row.population));
  });
}

export function BiomassAllocationDetails({ value }: { value: unknown }) {
  useLocale();
  const allocation = record(value);
  if (!allocation || typeof allocation.fuel_budget_mwh !== "number") return null;
  const rows = municipalities(allocation.municipalities);
  const population = record(allocation.population_data);
  return (
    <Stack spacing={0.5}>
      <Typography variant="subtitle2">{tr("Biomass fuel budget")}</Typography>
      <Typography variant="body2">
        {tr(allocation.method === "municipality_population"
          ? "Whole-municipality population share" : "Selected-area weighting (legacy)")}
        {" · "}{formatMwh(allocation.fuel_budget_mwh)}/a
      </Typography>
      {rows.map((row) => (
        <Typography key={row.ags} variant="body2">
          {row.name} ({row.ags}) · {formatNumber(row.population)} / {formatNumber(row.region_population)}
          {" · "}{formatNumber((row.population_share ?? 0) * 100, 4)}%
          {" · "}{formatMwh(row.allocated_fuel_mwh)}/a
        </Typography>
      ))}
      <Typography variant="caption">
        {tr("Project budget fraction")}: {formatNumber(Number(allocation.budget_fraction) * 100, 1)}%
        {typeof allocation.population_date === "string" && <>{" · "}{tr("Population date")}: {allocation.population_date}</>}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {tr("Fuel energy, not useful heat. The source already includes the district-heating availability share.")}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {tr("Independent studies do not reserve biomass. Concurrent projects must share the municipal budget.")}
      </Typography>
      {population && (
        <Typography variant="caption" color="text.secondary">
          {typeof population.attribution === "string" && population.attribution}{" · "}
          <Link href="https://www.bkg.bund.de">BKG</Link>{" · "}
          <Link href="https://www.govdata.de/dl-de/by-2-0">dl-de/by-2-0</Link>{" · "}
          <Link href="https://sgx.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_vg_nuts.pdf">{tr("Data sources")}</Link>
        </Typography>
      )}
    </Stack>
  );
}

export function BiomassMunicipalitySelection({ scenarioId, value }: { scenarioId: string; value: unknown }) {
  useLocale();
  const choices = municipalities(value);
  const config = useScenarioConfigQuery(scenarioId);
  const client = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const choiceKey = choices.map((choice) => choice.ags).join(",");
  useEffect(() => {
    const resources = record(config.data?.effective_document.resources);
    const current = resources?.biomass_municipality_ags;
    setSelected(Array.isArray(current)
      ? current.filter((ags): ags is string => typeof ags === "string" && choiceKey.split(",").includes(ags)) : []);
  }, [config.data, choiceKey]);
  const save = useMutation({
    mutationFn: () => {
      if (!config.data) throw new Error("Scenario configuration is unavailable.");
      return updateScenarioConfig(scenarioId, {
        expected_revision_id: config.data.revision_id,
        document: { resources: { biomass_municipality_ags: selected } },
        replace: false,
      });
    },
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["scenario", scenarioId] }),
        client.invalidateQueries({ queryKey: ["configuration-schema", scenarioId] }),
      ]);
    },
  });
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Typography variant="subtitle2">{tr("Confirm biomass municipalities")}</Typography>
        <Typography variant="body2">{tr("Choose the municipalities whose full population shares are available to this study. Neighbouring municipalities are not included automatically.")}</Typography>
        {choices.map((choice) => (
          <FormControlLabel key={choice.ags}
            label={`${choice.name} (${choice.ags}) · ${formatNumber(choice.population)}`}
            control={<Checkbox checked={selected.includes(choice.ags)} disabled={save.isPending}
              onChange={(event) => setSelected((previous) => event.target.checked
                ? [...previous, choice.ags] : previous.filter((ags) => ags !== choice.ags))} />}
          />
        ))}
        {config.isError && <ApiErrorAlert error={config.error} />}
        {save.isError && <ApiErrorAlert error={save.error} />}
        <Button disabled={!config.data || selected.length === 0 || save.isPending}
          onClick={() => save.mutate()} variant="outlined">
          {tr(save.isPending ? "Saving…" : "Apply municipality selection")}
        </Button>
      </Stack>
    </Paper>
  );
}
