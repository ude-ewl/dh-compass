import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import type { FeatureCollection } from "../../api/results";
import { ResultMap } from "../results/ResultMap";
import { CandidateInspector } from "../results/CandidateInspector";
import { AccessibleBarChart } from "../results/AccessibleBarChart";
import { formatEuro, formatMwh, formatNumber } from "../results/format";
import { emptyNetwork, gridAtStep, type GridStep } from "./viewerState";
import { PanelErrorBoundary } from "../../components/feedback/PanelErrorBoundary";

interface GridViewerProps {
  steps: GridStep[];
  network: FeatureCollection;
  paths?: FeatureCollection | null;
  lhd?: FeatureCollection | null;
  bbox?: [number, number, number, number] | null;
  live?: boolean;
  title: string;
  subtitle?: string;
  children?: ReactNode;
  finalResultsOnly?: boolean;
}

/** The original viewer's map, timeline, statistics, and right-hand inspector. */
export function GridViewer({
  steps,
  network,
  paths,
  lhd,
  bbox,
  live = false,
  title,
  subtitle,
  children,
  finalResultsOnly = false,
}: GridViewerProps) {
  useLocale();
  const [requestedStep, setRequestedStep] = useState<number | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<number | null>(
    null,
  );
  const [playing, setPlaying] = useState(false);
  const [fitRequest, setFitRequest] = useState(0);
  const index =
    requestedStep === null
      ? steps.length - 1
      : Math.min(requestedStep, steps.length - 1);
  const state = useMemo(
    () => gridAtStep(network, steps, index, paths ?? emptyNetwork),
    [network, steps, index, paths],
  );
  const selected = selectedCandidate ?? state.current?.candidateId;
  const candidate = [...steps.slice(0, index + 1)]
    .reverse()
    .find((step) => step.candidateId === selected);
  const move = (step: number) => {
    const target = Math.max(0, Math.min(steps.length - 1, step));
    const followLatest = live && target === steps.length - 1;
    setRequestedStep(followLatest ? null : target);
    if (followLatest) setPlaying(false);
    setSelectedCandidate(null);
  };

  useEffect(() => {
    if (!playing || steps.length < 2) return;
    const timer = window.setTimeout(() => {
      if (index >= steps.length - 1) setPlaying(false);
      else {
        const followLatest = live && index + 1 === steps.length - 1;
        setRequestedStep(followLatest ? null : index + 1);
        if (followLatest) setPlaying(false);
        setSelectedCandidate(null);
      }
    }, 900);
    return () => window.clearTimeout(timer);
  }, [playing, index, steps.length, live]);

  return (
    <section className="grid-viewer" aria-label={tr("Heat grid viewer")}>
      <div
        className="viewer-timeline"
        aria-label={tr("Grid playback controls")}
      >
        <button
          disabled={!steps.length}
          onClick={() => move(0)}
          aria-label={tr("First step")}
        >
          ⏮
        </button>
        <button
          disabled={index <= 0}
          onClick={() => move(index - 1)}
          aria-label={tr("Previous step")}
        >
          ◀
        </button>
        <button
          disabled={steps.length < 2}
          onClick={() => {
            if (!playing && index === steps.length - 1) move(0);
            setPlaying((value) => !value);
          }}
        >
          {tr(playing ? "Pause" : "Play")}
        </button>
        <input
          aria-label={tr("Grid playback step")}
          type="range"
          min="0"
          max={Math.max(0, steps.length - 1)}
          value={Math.max(0, index)}
          disabled={!steps.length}
          onChange={(event) => {
            setPlaying(false);
            move(Number(event.target.value));
          }}
        />
        <button
          disabled={!steps.length || index >= steps.length - 1}
          onClick={() => move(index + 1)}
          aria-label={tr("Next step")}
        >
          ▶
        </button>
        <button
          disabled={!steps.length}
          onClick={() => move(steps.length - 1)}
          aria-label={tr("Last step")}
        >
          ⏭
        </button>
        <span className="viewer-step-label">
          {tr("Step ")}
          {formatNumber(Math.max(0, index + 1))} / {formatNumber(steps.length)}
        </span>
        <div className="viewer-layer-toggles">
          <button onClick={() => setFitRequest((value) => value + 1)}>
            {tr("Center map")}
          </button>
        </div>
      </div>
      {!finalResultsOnly && (
        <div
          className="viewer-stats"
          aria-label={tr("Grid statistics")}
          aria-live="polite"
        >
          <span>
            {tr("Connected: ")}
            <strong>{formatNumber(state.connected)}</strong>
          </span>
          <span>
            {tr("Rejected: ")}
            <strong>{formatNumber(state.rejected)}</strong>
          </span>
          <span>
            {tr("Cumulative cost: ")}
            <strong>{tr(formatEuro(state.cumulativeCost))}</strong>
          </span>
          <span>
            {tr("Connected demand:")}
            {tr(" ")}
            <strong>{tr(formatMwh(state.connectedDemand))}</strong>
          </span>
        </div>
      )}
      <div className="viewer-body">
        <div className="viewer-map">
          <PanelErrorBoundary resetKey={title} title={tr("Heat grid map")}>
            <ResultMap
              viewerMode
              candidateNetwork={state.network}
              connectionPaths={state.paths}
              lhd={lhd}
              showCandidates={true}
              showFinalNetwork={false}
              showPaths={true}
              showLhd={false}
              editableBoundingBox={bbox}
              fitRequest={fitRequest}
              selectedCandidateId={selected ?? null}
              onSelectCandidate={(id) => setSelectedCandidate(id)}
              title={tr("Heat grid map")}
            />
          </PanelErrorBoundary>
          {!steps.length && (
            <div className="viewer-map-note">
              {tr(
                "The grid will appear here as candidates are prepared and evaluated.",
              )}
            </div>
          )}
        </div>
        <aside
          className="viewer-sidebar"
          aria-label={tr(
            finalResultsOnly
              ? "Final combined grid results"
              : "Subgraph details",
          )}
        >
          <h1>{tr(title)}</h1>
          {subtitle && <p className="viewer-muted">{tr(subtitle)}</p>}
          {!finalResultsOnly &&
            (candidate?.decision === "current" ? (
              <div className="viewer-evaluating" role="status">
                {tr("Evaluating subgraph #")}
                {tr(candidate.candidateId)}…
              </div>
            ) : candidate?.candidate ? (
              <>
                <CandidateInspector candidate={candidate.candidate} />
                <AccessibleBarChart
                  title={tr(`Costs for subgraph #${candidate.candidateId}`)}
                  valueLabel="Annualized cost (€/a)"
                  formatValue={formatEuro}
                  data={[
                    { label: "Marginal central", value: candidate.centralCost },
                    { label: "Decentralized", value: candidate.decentralCost },
                  ]}
                />
                {candidate.candidate.supply && (
                  <AccessibleBarChart
                    title={tr("Heat supply")}
                    valueLabel="Annual heat production (MWh/a)"
                    formatValue={formatMwh}
                    data={Object.entries(candidate.candidate.supply).map(
                      ([name, technology]) => ({
                        label: name.replaceAll("_", " "),
                        value:
                          technology.annual_heat_energy_mwh ??
                          technology.annual_energy_mwh,
                      }),
                    )}
                  />
                )}
              </>
            ) : (
              <p className="viewer-muted">
                {tr(
                  "Select a subgraph on the map or use the timeline to inspect a decision.",
                )}
              </p>
            ))}
          {tr(children)}
        </aside>
      </div>
    </section>
  );
}
