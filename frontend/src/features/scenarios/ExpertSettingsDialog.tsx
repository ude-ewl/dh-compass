import { tr } from "../../i18n/translate";

import { useLocale } from "../../i18n/locale";

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";

import { useEffect, useMemo, useRef, useState } from "react";

import { useBlocker } from "react-router-dom";

import { updateScenarioConfig, validateScenarioConfig } from "../../api/client";

import type {
  ConfigurationField,
  ConfigurationValidationResponse,
  ScenarioConfigMutationResponse,
} from "../../api/projects";

import { ApiClientError } from "../../api/client";

import { ApiErrorAlert } from "../../components/feedback/ApiErrorAlert";

import { useConfigurationSchemaQuery } from "../../api/queries";

import {
  cloneConfiguration,
  coerceFieldInput,
  configurationValuesEqual,
  costCurveKey,
  displayValue,
  fieldErrorFor,
  fieldMatchesSearch,
  fieldValue,
  getConfigurationValue,
  impactLabel,
  resetConfigurationValue,
  isCostCurveField,
  isTechnologyMapField,
  sectionFields,
  serializeConfigurationToml,
  setConfigurationValue,
  technologyMapKey,
  type ConfigurationDocument,
} from "./configuration";

const RESOURCE_OPTIONS = [
  ["industrial_excess_heat", "Industrial excess heat"],

  ["biomass", "Biomass"],

  ["waste_to_energy", "Waste-to-energy"],

  ["geothermal", "Geothermal"],

  ["river_heat_pump", "River heat pump"],

  ["wwtp_heat_pump", "Wastewater heat pump"],
] as const;

type EditorMode = "form" | "toml";

type ConfigurationError = { path: string; message: string };

interface ExpertSettingsDialogProps {
  open: boolean;

  scenarioId: string;

  revisionId: string;

  document: ConfigurationDocument;

  mergedToml?: string | null;

  onClose: () => void;

  onApplied: (result: ScenarioConfigMutationResponse) => void;
}

function groupLabel(fields: ConfigurationField[]): string {
  return fields[0]?.group_label ?? fields[0]?.section_label ?? "Settings";
}

function inputText(value: unknown): string | number {
  if (typeof value === "number" || typeof value === "string") return value;

  return displayValue(value);
}

function impactChip(field: ConfigurationField) {
  return (
    <Chip
      color={field.impact === "preview" ? "warning" : "default"}

      label={tr(impactLabel(field))}

      size="small"

      variant="outlined"
    />
  );
}

export function ResourceEditor({
  field,

  value,

  disabled,

  error,

  onChange,
}: {
  field: ConfigurationField;

  value: unknown;

  disabled: boolean;

  error?: string;

  onChange: (value: unknown) => void;
}) {
  useLocale();

  const selected = Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];

  return (
    <Paper
      component="fieldset"

      disabled={disabled}

      sx={{ p: 2 }}

      variant="outlined"
    >
      <Typography component="legend" sx={{ px: 0.5 }} variant="subtitle2">
        {tr(field.label)}
      </Typography>

      <Typography color="text.secondary" variant="body2">
        {field.description}
      </Typography>

      <Stack
        direction={{ sm: "row", xs: "column" }}

        flexWrap="wrap"

        gap={1}

        sx={{ mt: 1 }}
      >
        {RESOURCE_OPTIONS.map(([resource, label]) => (
          <FormControlLabel
            control={
              <Checkbox
                checked={selected.includes(resource)}

                onChange={(event) => {
                  const next = event.target.checked
                    ? [...selected, resource]
                    : selected.filter((item) => item !== resource);

                  onChange(next);
                }}
              />
            }

            key={resource}

            label={tr(label)}
          />
        ))}
      </Stack>

      {error && (
        <Typography color="error" variant="caption">
          {tr(error)}
        </Typography>
      )}
    </Paper>
  );
}

function FieldEditor({
  field,

  document,

  errors,

  onChange,

  onReset,
}: {
  field: ConfigurationField;

  document: ConfigurationDocument;

  errors: ConfigurationError[];

  onChange: (path: string, value: unknown) => void;

  onReset: (path: string) => void;
}) {
  useLocale();

  const value = fieldValue(field, document);

  const error = fieldErrorFor(errors, field.key);

  const disabled = !field.editable;

  const allowedValues = Array.isArray(field.constraints.allowed_values)
    ? field.constraints.allowed_values
    : [];

  if (field.key === "scenario.enabled_resources") {
    return (
      <ResourceEditor
        disabled={disabled}

        error={error}

        field={field}

        onChange={(next) => onChange(field.key, next)}

        value={value}
      />
    );
  }

  if (field.data_type === "boolean") {
    return (
      <Paper sx={{ p: 1.5 }} variant="outlined">
        <FormControlLabel
          control={
            <Checkbox
              checked={Boolean(value)}

              disabled={disabled}

              onChange={(event) => onChange(field.key, event.target.checked)}
            />
          }

          label={tr(field.label)}
        />

        <FieldMeta field={field} error={error} onReset={onReset} />
      </Paper>
    );
  }

  return (
    <Stack spacing={0.75}>
      <TextField
        disabled={disabled}

        error={Boolean(error)}

        fullWidth

        helperText={tr(error ?? field.description)}

        inputProps={{
          min: field.constraints.minimum as number | undefined,

          max: field.constraints.maximum as number | undefined,

          step: field.data_type === "integer" ? 1 : "any",
        }}

        label={tr(field.label)}

        multiline={field.data_type === "array" || field.data_type === "object"}

        onChange={(event) =>
          onChange(field.key, coerceFieldInput(field, event.target.value))
        }

        select={allowedValues.length > 0}

        type={
          field.data_type === "number" || field.data_type === "integer"
            ? "number"
            : "text"
        }

        value={allowedValues.length > 0 ? String(value) : inputText(value)}
      >
        {allowedValues.map((option) => (
          <MenuItem key={String(option)} value={String(option)}>
            {tr(String(option))}
          </MenuItem>
        ))}
      </TextField>

      <FieldMeta field={field} error={error} onReset={onReset} />
    </Stack>
  );
}

function FieldMeta({
  field,

  error,

  onReset,
}: {
  field: ConfigurationField;

  error?: string;

  onReset: (path: string) => void;
}) {
  useLocale();

  return (
    <Stack
      alignItems={{ sm: "center" }}

      direction={{ sm: "row", xs: "column" }}

      spacing={1}
    >
      <Typography color="text.secondary" sx={{ flex: 1 }} variant="caption">
        <code>{tr(field.key)}</code>
        {tr(field.unit ? ` · ${field.unit}` : "")} {tr(" · default:")}
        {tr(" ")}
        {tr(displayValue(field.default))}
        {tr(field.path_policy === "managed" ? " · deployment-managed" : "")}
      </Typography>

      {field.changed_from_default && (
        <Chip
          label={tr("Changed from default")}

          size="small"

          variant="outlined"
        />
      )}

      {field.changed_from_parent && (
        <Chip
          label={tr("Changed from parent")}

          size="small"

          variant="outlined"
        />
      )}

      {tr(impactChip(field))}

      {field.editable && (
        <Button onClick={() => onReset(field.key)} size="small" variant="text">
          {tr("Reset")}
        </Button>
      )}

      {error && (
        <Typography color="error" variant="caption">
          {tr(error)}
        </Typography>
      )}
    </Stack>
  );
}

export function CostCurveEditor({
  fields,

  document,

  errors,

  onChange,

  onReset,

  onResetCurve,
}: {
  fields: ConfigurationField[];

  document: ConfigurationDocument;

  errors: ConfigurationError[];

  onChange: (path: string, value: unknown) => void;

  onReset: (path: string) => void;

  onResetCurve: (path: string) => void;
}) {
  useLocale();

  const groups = useMemo(() => {
    const result = new Map<string, ConfigurationField[]>();

    fields.forEach((field) => {
      const values = result.get(costCurveKey(field)) ?? [];

      values.push(field);

      result.set(costCurveKey(field), values);
    });

    return result;
  }, [fields]);

  return (
    <Stack spacing={2}>
      {[...groups.entries()].map(([curvePath, curveFields]) => {
        const curve = getConfigurationValue(document, curvePath);

        const curveValues =
          curve && typeof curve === "object" && !Array.isArray(curve)
            ? (curve as Record<string, unknown>)
            : {};

        return (
          <Paper
            key={curvePath}

            sx={{ p: 2, overflowX: "auto" }}

            variant="outlined"
          >
            <Stack
              alignItems="center"

              direction="row"

              justifyContent="space-between"

              spacing={1}
            >
              <Box>
                <Typography variant="subtitle1">
                  {tr(curvePath.split(".").slice(-1)[0].replaceAll("_", " "))}
                </Typography>

                <Typography color="text.secondary" variant="caption">
                  <code>{tr(curvePath)}</code>{" "}
                  {tr(" · threshold to specific cost/value")}
                </Typography>
              </Box>

              {tr(impactChip(curveFields[0]))}
            </Stack>

            <Table aria-label={tr(`${curvePath} cost curve`)} size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{tr("Threshold")}</TableCell>

                  <TableCell>{tr("Value")}</TableCell>

                  <TableCell>{tr("Inherited default")}</TableCell>

                  <TableCell />
                </TableRow>
              </TableHead>

              <TableBody>
                {(Object.keys(curveValues).length > 0
                  ? Object.keys(curveValues)
                  : curveFields.map(
                      (field) => field.key.split(".").at(-1) ?? "",
                    )
                ).map((threshold) => {
                  const field = curveFields.find(
                    (candidate) =>
                      candidate.key.split(".").at(-1) === threshold,
                  );

                  const valueField = field ?? curveFields[0];

                  const currentValue = curveValues[threshold] ?? field?.value;

                  const rowPath = field?.key ?? `${curvePath}.${threshold}`;

                  const error = fieldErrorFor(errors, rowPath);

                  const editable = field?.editable ?? true;

                  return (
                    <TableRow key={`${curvePath}.${threshold}`}>
                      <TableCell>
                        <TextField
                          aria-label={tr(`${curvePath} threshold ${threshold}`)}

                          disabled={!editable}

                          error={Boolean(error)}

                          onChange={(event) => {
                            const nextThreshold = event.target.value;

                            if (!nextThreshold || nextThreshold === threshold)
                              return;

                            const nextCurve = { ...curveValues };

                            delete nextCurve[threshold];

                            nextCurve[nextThreshold] = currentValue;

                            onChange(curvePath, nextCurve);
                          }}

                          size="small"

                          type="number"

                          value={threshold}
                        />
                      </TableCell>

                      <TableCell>
                        <TextField
                          aria-label={tr(`${curvePath} value ${threshold}`)}

                          disabled={!editable}

                          error={Boolean(error)}

                          helperText={tr(error)}

                          onChange={(event) => {
                            if (!field) {
                              onChange(curvePath, {
                                ...curveValues,

                                [threshold]: coerceFieldInput(
                                  valueField,

                                  event.target.value,
                                ),
                              });

                              return;
                            }

                            onChange(
                              field.key,

                              coerceFieldInput(field, event.target.value),
                            );
                          }}

                          size="small"

                          type="number"

                          value={inputText(currentValue)}
                        />
                      </TableCell>

                      <TableCell>
                        {tr(displayValue(field?.default))}

                        {field?.changed_from_default && (
                          <Chip
                            label={tr("Changed")}

                            size="small"

                            sx={{ ml: 1 }}

                            variant="outlined"
                          />
                        )}
                      </TableCell>

                      <TableCell>
                        {editable && (
                          <Button
                            onClick={() =>
                              field
                                ? onReset(field.key)
                                : onResetCurve(curvePath)
                            }

                            size="small"
                          >
                            {tr("Reset")}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Paper>
        );
      })}
    </Stack>
  );
}

export function TechnologyMapEditor({
  fields,

  document,

  errors,

  onChange,

  onReset,
}: {
  fields: ConfigurationField[];

  document: ConfigurationDocument;

  errors: ConfigurationError[];

  onChange: (path: string, value: unknown) => void;

  onReset: (path: string) => void;
}) {
  useLocale();

  const maps = useMemo(() => {
    const result = new Map<string, ConfigurationField[]>();

    fields.forEach((field) => {
      const values = result.get(technologyMapKey(field)) ?? [];

      values.push(field);

      result.set(technologyMapKey(field), values);
    });

    return result;
  }, [fields]);

  return (
    <Stack spacing={2}>
      {[...maps.entries()].map(([mapName, mapFields]) => {
        const parameterNames = [
          ...new Set(
            mapFields.map((field) => field.key.split(".").at(-1) ?? ""),
          ),
        ];

        const ids = [
          ...new Set(mapFields.map((field) => field.key.split(".")[2])),
        ];

        return (
          <Paper
            key={mapName}

            sx={{ p: 2, overflowX: "auto" }}

            variant="outlined"
          >
            <Typography variant="subtitle1">
              {tr(mapName.replaceAll("_", " "))}
            </Typography>

            <Typography color="text.secondary" variant="caption">
              {tr("Technology map ")}

              <code>
                {tr("technologies.")}

                {tr(mapName)}
              </code>
            </Typography>

            <Table aria-label={tr(`${mapName} technology map`)} size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{tr("Technology ID")}</TableCell>

                  {parameterNames.map((parameter) => (
                    <TableCell key={parameter}>
                      {tr(parameter.replaceAll("_", " "))}
                    </TableCell>
                  ))}

                  <TableCell>{tr("Defaults and reset")}</TableCell>
                </TableRow>
              </TableHead>

              <TableBody>
                {ids.map((id) => (
                  <TableRow key={id}>
                    <TableCell>{tr(id)}</TableCell>

                    {parameterNames.map((parameter) => {
                      const field = mapFields.find(
                        (candidate) =>
                          candidate.key ===
                          `technologies.${mapName}.${id}.${parameter}`,
                      );

                      if (!field)
                        return <TableCell key={parameter}>—</TableCell>;

                      const value = fieldValue(field, document);

                      const error = fieldErrorFor(errors, field.key);

                      return (
                        <TableCell key={parameter}>
                          <TextField
                            aria-label={tr(`${mapName} ${id} ${parameter}`)}

                            disabled={!field.editable}

                            error={Boolean(error)}

                            helperText={tr(error)}

                            onChange={(event) =>
                              onChange(
                                field.key,

                                coerceFieldInput(field, event.target.value),
                              )
                            }

                            size="small"

                            type={
                              field.data_type === "string" ? "text" : "number"
                            }

                            value={inputText(value)}
                          />
                        </TableCell>
                      );
                    })}

                    <TableCell>
                      <Stack spacing={0.25}>
                        {parameterNames.map((parameter) => {
                          const field = mapFields.find(
                            (candidate) =>
                              candidate.key ===
                              `technologies.${mapName}.${id}.${parameter}`,
                          );

                          return field ? (
                            <Button
                              key={field.key}

                              onClick={() => onReset(field.key)}

                              size="small"
                            >
                              {tr("Reset ")}

                              {tr(parameter)}
                            </Button>
                          ) : null;
                        })}
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        );
      })}
    </Stack>
  );
}

export function ExpertSettingsDialog({
  open,

  scenarioId,

  revisionId,

  document,

  mergedToml,

  onClose,

  onApplied,
}: ExpertSettingsDialogProps) {
  useLocale();

  const schema = useConfigurationSchemaQuery(scenarioId);

  const [draft, setDraft] = useState<ConfigurationDocument>(() =>
    cloneConfiguration(document),
  );

  const [original, setOriginal] = useState<ConfigurationDocument>(() =>
    cloneConfiguration(document),
  );

  const [rawToml, setRawToml] = useState(
    mergedToml ?? serializeConfigurationToml(document),
  );

  const [originalToml, setOriginalToml] = useState(rawToml);

  const [mode, setMode] = useState<EditorMode>("form");

  const [search, setSearch] = useState("");

  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);

  const [errors, setErrors] = useState<ConfigurationError[]>([]);

  const [validation, setValidation] =
    useState<ConfigurationValidationResponse | null>(null);

  const [requestError, setRequestError] = useState<unknown>(null);

  const [isValidating, setIsValidating] = useState(false);

  const [isApplying, setIsApplying] = useState(false);

  const [previewConfirmationRequired, setPreviewConfirmationRequired] =
    useState(false);

  const bypassNavigationGuard = useRef(false);

  useEffect(() => {
    if (!open) return;

    const nextDocument = cloneConfiguration(document);

    const nextToml = mergedToml ?? serializeConfigurationToml(nextDocument);

    setDraft(nextDocument);

    setOriginal(cloneConfiguration(nextDocument));

    setRawToml(nextToml);

    setOriginalToml(nextToml);

    setMode("form");

    setSearch("");

    setErrors([]);

    setValidation(null);

    setRequestError(null);

    setPreviewConfirmationRequired(false);

    bypassNavigationGuard.current = false;
  }, [document, mergedToml, open]);

  const fields = useMemo(
    () => schema.data?.fields ?? [],

    [schema.data?.fields],
  );

  const groups = useMemo(() => sectionFields(fields), [fields]);

  const groupKeys = useMemo(() => [...groups.keys()], [groups]);

  useEffect(() => {
    if (selectedGroup && groupKeys.includes(selectedGroup)) return;

    setSelectedGroup(groupKeys[0] ?? null);
  }, [groupKeys, selectedGroup]);

  const currentFields = useMemo(() => {
    return (groups.get(selectedGroup ?? "") ?? []).filter((field) =>
      fieldMatchesSearch(field, search),
    );
  }, [groups, search, selectedGroup]);

  const dirty =
    !configurationValuesEqual(draft, original) ||
    (mode === "toml" && rawToml !== originalToml);

  useEffect(() => {
    if (!open || !dirty) return;

    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();

      event.returnValue = "";
    };

    window.addEventListener("beforeunload", beforeUnload);

    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty, open]);

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      open &&
      dirty &&
      !bypassNavigationGuard.current &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  );

  useEffect(() => {
    if (blocker.state !== "blocked") return;

    if (window.confirm("Discard unapplied Expert settings changes?")) {
      bypassNavigationGuard.current = true;

      blocker.proceed();
    } else {
      blocker.reset();
    }
  }, [blocker]);

  const close = () => {
    if (dirty && !window.confirm("Discard unapplied Expert settings changes?"))
      return;

    bypassNavigationGuard.current = true;

    onClose();
  };

  const changeMode = (nextMode: EditorMode) => {
    if (
      mode === "toml" &&
      nextMode === "form" &&
      rawToml !== originalToml &&
      !window.confirm("Discard unapplied raw TOML changes?")
    ) {
      return;
    }

    if (nextMode === "toml") {
      setRawToml(serializeConfigurationToml(draft));

      setOriginalToml(serializeConfigurationToml(original));
    }

    setMode(nextMode);
  };

  const updateField = (path: string, value: unknown) => {
    setDraft((current) => setConfigurationValue(current, path, value));

    setValidation(null);

    setRequestError(null);

    setPreviewConfirmationRequired(false);
  };

  const clearDraftFeedback = () => {
    setValidation(null);

    setErrors([]);

    setRequestError(null);

    setPreviewConfirmationRequired(false);
  };

  const resetFields = (
    current: ConfigurationDocument,

    fieldsToReset: ConfigurationField[],
  ) => {
    let next = current;

    const curveFields = fieldsToReset.filter(isCostCurveField);

    fieldsToReset

      .filter((field) => field.editable && !isCostCurveField(field))

      .forEach((field) => {
        next = resetConfigurationValue(
          next,

          field.key,

          field.default,

          field.has_default,
        );
      });

    for (const curvePath of new Set(curveFields.map(costCurveKey))) {
      const defaults = Object.fromEntries(
        curveFields

          .filter(
            (field) => costCurveKey(field) === curvePath && field.has_default,
          )

          .map((field) => [field.key.split(".").at(-1) ?? "", field.default]),
      );

      next = setConfigurationValue(next, curvePath, defaults);
    }

    return next;
  };

  const resetField = (path: string) => {
    const field = fields.find((candidate) => candidate.key === path);

    if (!field || !field.editable) return;

    setDraft((current) =>
      resetConfigurationValue(current, path, field.default, field.has_default),
    );

    clearDraftFeedback();
  };

  const resetCurve = (curvePath: string) => {
    setDraft((current) =>
      resetFields(
        current,

        fields.filter((field) => costCurveKey(field) === curvePath),
      ),
    );

    clearDraftFeedback();
  };

  const resetGroup = () => {
    const section = groups.get(selectedGroup ?? "") ?? [];

    setDraft((current) => resetFields(current, section));

    clearDraftFeedback();
  };

  const resetAll = () => {
    setDraft((current) => resetFields(current, fields));

    clearDraftFeedback();
  };

  const validateDraft =
    async (): Promise<ConfigurationValidationResponse | null> => {
      setIsValidating(true);

      setErrors([]);

      setRequestError(null);

      try {
        const result = await validateScenarioConfig(
          scenarioId,

          mode === "toml" ? { toml: rawToml } : draft,

          mode === "form",
        );

        setValidation(result);

        setErrors(result.field_errors ?? []);

        if (!result.valid) setPreviewConfirmationRequired(false);

        if (result.valid && result.document) {
          setDraft(result.document);

          if (result.merged_toml) {
            setRawToml(result.merged_toml);
          }
        }

        return result;
      } catch (error) {
        setRequestError(error);

        if (error instanceof ApiClientError)
          setErrors(error.payload.field_errors ?? []);

        return null;
      } finally {
        setIsValidating(false);
      }
    };

  const apply = async () => {
    const result = await validateDraft();

    if (!result?.valid || !result.document) return;

    if (
      result.invalidation?.preview_invalidated &&
      !previewConfirmationRequired
    ) {
      setPreviewConfirmationRequired(true);

      return;
    }

    setIsApplying(true);

    setRequestError(null);

    try {
      const saved = await updateScenarioConfig(scenarioId, {
        expected_revision_id: revisionId,

        document: result.document,

        replace: true,
      });

      setPreviewConfirmationRequired(false);

      onApplied(saved);
    } catch (error) {
      setRequestError(error);

      if (error instanceof ApiClientError)
        setErrors(error.payload.field_errors ?? []);
    } finally {
      setIsApplying(false);
    }
  };

  const matchingCurrentFields = currentFields;

  const regularFields = matchingCurrentFields.filter(
    (field) => !isCostCurveField(field) && !isTechnologyMapField(field),
  );

  const costFields = matchingCurrentFields.filter(isCostCurveField);

  const technologyFields = matchingCurrentFields.filter(isTechnologyMapField);

  const hasSearchResults = matchingCurrentFields.length > 0;

  return (
    <Dialog fullWidth maxWidth="xl" onClose={close} open={open} scroll="paper">
      <DialogTitle>
        <Stack
          alignItems={{ sm: "center" }}

          direction={{ sm: "row", xs: "column" }}

          justifyContent="space-between"

          spacing={1}
        >
          <Box>
            <Typography component="h2" variant="h5">
              {tr("Expert settings")}
            </Typography>

            <Typography color="text.secondary" variant="body2">
              {tr(
                "Advanced values stay in this draft until you validate and apply them.",
              )}
            </Typography>
          </Box>

          <Stack direction="row" spacing={1}>
            <Button
              onClick={() => changeMode("form")}

              variant={mode === "form" ? "contained" : "outlined"}
            >
              {tr("Form")}
            </Button>

            <Button
              onClick={() => changeMode("toml")}

              variant={mode === "toml" ? "contained" : "outlined"}
            >
              {tr("Raw TOML")}
            </Button>
          </Stack>
        </Stack>
      </DialogTitle>

      <DialogContent dividers>
        <Stack
          direction={{ lg: "row", xs: "column" }}

          spacing={2}

          sx={{ minHeight: 560 }}
        >
          <Paper
            component="nav"

            sx={{ flex: "0 0 220px", p: 1 }}

            variant="outlined"
          >
            <Typography sx={{ p: 1 }} variant="subtitle2">
              {tr("Sections")}
            </Typography>

            <Stack spacing={0.5}>
              {groupKeys.map((key) => {
                const values = groups.get(key) ?? [];

                return (
                  <Button
                    key={key}

                    onClick={() => setSelectedGroup(key)}

                    sx={{ justifyContent: "flex-start", textAlign: "left" }}

                    variant={selectedGroup === key ? "contained" : "text"}
                  >
                    {tr(groupLabel(values))} ({tr(values.length)})
                  </Button>
                );
              })}
            </Stack>
          </Paper>

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack spacing={2}>
              <TextField
                fullWidth

                label={tr("Search parameters or configuration keys")}

                onChange={(event) => setSearch(event.target.value)}

                value={search}
              />

              <Stack
                alignItems="center"

                direction="row"

                justifyContent="space-between"

                spacing={1}
              >
                <Typography color="text.secondary" variant="body2">
                  {tr(
                    hasSearchResults
                      ? `${matchingCurrentFields.length} matching fields`
                      : "No matching fields",
                  )}
                </Typography>

                {mode === "form" && (
                  <Stack direction="row" spacing={1}>
                    <Button
                      onClick={resetGroup}

                      size="small"

                      variant="outlined"
                    >
                      {tr("Reset section")}
                    </Button>

                    <Button onClick={resetAll} size="small" variant="outlined">
                      {tr("Reset all")}
                    </Button>
                  </Stack>
                )}
              </Stack>

              {mode === "toml" ? (
                <Stack spacing={1}>
                  <Alert severity="warning">
                    {tr(
                      "Raw TOML replaces the complete draft. The server validates the merged document before anything is saved.",
                    )}
                  </Alert>

                  <TextField
                    fullWidth

                    helperText={tr(
                      "Values use TOML syntax and configuration paths are preserved in server validation errors.",
                    )}

                    label={tr("Merged configuration TOML")}

                    multiline

                    minRows={24}

                    onChange={(event) => {
                      setRawToml(event.target.value);

                      setValidation(null);

                      setErrors([]);

                      setPreviewConfirmationRequired(false);
                    }}

                    value={rawToml}
                  />
                </Stack>
              ) : (
                <Stack spacing={2}>
                  {regularFields.map((field) => (
                    <FieldEditor
                      document={draft}

                      errors={errors}

                      field={field}

                      key={field.key}

                      onChange={updateField}

                      onReset={resetField}
                    />
                  ))}

                  {costFields.length > 0 && (
                    <Box>
                      <Typography gutterBottom variant="h6">
                        {tr("Cost curves")}
                      </Typography>

                      <CostCurveEditor
                        document={draft}

                        errors={errors}

                        fields={costFields}

                        onChange={updateField}

                        onReset={resetField}

                        onResetCurve={resetCurve}
                      />
                    </Box>
                  )}

                  {technologyFields.length > 0 && (
                    <Box>
                      <Typography gutterBottom variant="h6">
                        {tr("Technology maps")}
                      </Typography>

                      <TechnologyMapEditor
                        document={draft}

                        errors={errors}

                        fields={technologyFields}

                        onChange={updateField}

                        onReset={resetField}
                      />
                    </Box>
                  )}
                </Stack>
              )}
            </Stack>
          </Box>

          <Paper
            component="aside"

            sx={{ flex: "0 0 300px", p: 2 }}

            variant="outlined"
          >
            <Typography gutterBottom variant="h6">
              {tr("Change summary")}
            </Typography>

            <Typography color="text.secondary" variant="body2">
              {tr(dirty ? "Unapplied local changes" : "No unapplied changes")}
            </Typography>

            <Divider sx={{ my: 1.5 }} />

            <Stack spacing={1} sx={{ maxHeight: 430, overflow: "auto" }}>
              {fields

                .filter((field) => {
                  const before = fieldValue(field, original);

                  const after = fieldValue(field, draft);

                  return (
                    field.editable && !configurationValuesEqual(before, after)
                  );
                })

                .map((field) => (
                  <Box key={field.key}>
                    <Typography fontWeight={600} variant="body2">
                      {tr(field.label)}
                    </Typography>

                    <Typography color="text.secondary" variant="caption">
                      <code>{tr(field.key)}</code>
                    </Typography>

                    <Typography variant="body2">
                      {tr(displayValue(fieldValue(field, original)))} →{tr(" ")}
                      {tr(displayValue(fieldValue(field, draft)))}
                    </Typography>

                    {tr(impactChip(field))}
                  </Box>
                ))}

              {fields.every((field) => {
                const before = fieldValue(field, original);

                const after = fieldValue(field, draft);

                return (
                  !field.editable || configurationValuesEqual(before, after)
                );
              }) && (
                <Typography color="text.secondary" variant="body2">
                  {tr("No changes yet.")}
                </Typography>
              )}
            </Stack>

            {previewConfirmationRequired && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                <Typography fontWeight={600}>
                  {tr("Preview invalidation requires confirmation.")}
                </Typography>

                <Typography variant="body2">
                  {tr(
                    "The preview will be invalidated. Select Apply again to confirm the change.",
                  )}
                </Typography>
              </Alert>
            )}

            {validation?.valid && (
              <Alert
                severity={
                  validation.invalidation?.preview_invalidated
                    ? "warning"
                    : "success"
                }

                sx={{ mt: 2 }}
              >
                {tr("Configuration is valid.")}

                {tr(" ")}

                {tr(
                  validation.invalidation?.preview_invalidated
                    ? "Applying it will require a new candidate preview."
                    : validation.invalidation?.new_run_required
                      ? "Applying it will require a new optimization run."
                      : "No downstream work is required.",
                )}
              </Alert>
            )}
          </Paper>
        </Stack>

        {schema.isError && <ApiErrorAlert error={schema.error} />}

        {requestError !== null && <ApiErrorAlert error={requestError} />}

        {(validation?.valid === false || errors.length > 0) && (
          <Alert severity="error" sx={{ mt: 2 }}>
            <Typography fontWeight={600}>
              {tr(
                "Correct the highlighted configuration errors before applying.",
              )}
            </Typography>

            {errors.length > 0 && (
              <Box component="ul" sx={{ m: 0, pl: 2 }}>
                {errors.map((error) => (
                  <li key={`${error.path}-${error.message}`}>
                    <code>{tr(error.path)}</code>: {tr(error.message)}
                  </li>
                ))}
              </Box>
            )}
          </Alert>
        )}
      </DialogContent>

      <DialogActions>
        <Typography
          color="text.secondary"

          sx={{ mr: "auto" }}

          variant="caption"
        >
          {tr("Revision ")}
          {tr(revisionId.slice(0, 8))} ·{tr(" ")}
          {tr(dirty ? "unsaved draft" : "saved")}
        </Typography>

        <Button
          disabled={isValidating || isApplying}

          onClick={() => void validateDraft()}
        >
          {tr(isValidating ? "Validating…" : "Validate")}
        </Button>

        <Button disabled={isValidating || isApplying} onClick={close}>
          {tr("Cancel")}
        </Button>

        <Button
          disabled={isValidating || isApplying || !dirty}

          onClick={() => void apply()}

          variant="contained"
        >
          {tr(
            isApplying
              ? "Applying…"
              : previewConfirmationRequired
                ? "Apply again"
                : "Apply",
          )}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
