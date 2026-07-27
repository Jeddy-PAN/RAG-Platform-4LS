"use client";

import { useMemo, useState } from "react";
import type { EvalRun, UUID } from "@/lib/types";
import { evalApi } from "@/lib/api";
import { buildEvalCompareCsv, buildExportFilename } from "@/lib/eval-export";
import { buildEvalRunCompare, type EvalRunCompareCell } from "@/lib/eval-run-compare";
import { downloadTextFile, formatLatency, formatRate } from "./eval-helpers";

export function useEvalCompare(
  selectedProjectId: UUID | "",
  selectedDatasetId: UUID | "",
  currentRun: EvalRun | null,
  setError: (msg: string | null) => void,
) {
  const [compareRunIds, setCompareRunIds] = useState<UUID[]>([]);
  const [compareRunsById, setCompareRunsById] = useState<Record<UUID, EvalRun>>({});
  const [loadingCompareRunIds, setLoadingCompareRunIds] = useState<Set<UUID>>(new Set());

  const compareRuns = useMemo(
    () =>
      compareRunIds
        .map((runId) => (currentRun?.id === runId ? currentRun : compareRunsById[runId]))
        .filter((item): item is EvalRun => Boolean(item)),
    [compareRunIds, compareRunsById, currentRun]
  );

  const compare = useMemo(() => buildEvalRunCompare(compareRuns), [compareRuns]);

  const compareMetricRows = useMemo(
    () => [
      { label: "Hit rate", values: compare.runs.map((item) => formatRate(item.hitRate)) },
      { label: "Citation", values: compare.runs.map((item) => formatRate(item.citationCoverageRate)) },
      { label: "Answer match", values: compare.runs.map((item) => formatRate(item.answerMatchRate)) },
      { label: "Judge", values: compare.runs.map((item) => formatRate(item.judgeMatchRate)) },
      { label: "Avg retrieval", values: compare.runs.map((item) => formatLatency(item.avgRetrievalLatencyMs)) },
      { label: "Avg generation", values: compare.runs.map((item) => formatLatency(item.avgGenerationLatencyMs)) },
    ],
    [compare.runs]
  );

  function resetCompareState() {
    setCompareRunIds([]);
    setCompareRunsById({});
    setLoadingCompareRunIds(new Set());
  }

  async function ensureCompareRunDetail(runId: UUID) {
    if (!selectedProjectId || !selectedDatasetId || currentRun?.id === runId || compareRunsById[runId]) {
      return;
    }

    setLoadingCompareRunIds((current) => new Set(current).add(runId));
    setError(null);
    try {
      const result = await evalApi.getRun(selectedProjectId, selectedDatasetId, runId);
      setCompareRunsById((current) => ({ ...current, [runId]: result }));
    } catch (loadError) {
      setCompareRunIds((current) => current.filter((id) => id !== runId));
      setError(loadError instanceof Error ? loadError.message : "Unable to load compare run");
    } finally {
      setLoadingCompareRunIds((current) => {
        const next = new Set(current);
        next.delete(runId);
        return next;
      });
    }
  }

  function toggleCompareRun(runId: UUID) {
    if (compareRunIds.includes(runId)) {
      setCompareRunIds((current) => current.filter((id) => id !== runId));
      return;
    }
    if (compareRunIds.length >= 4) {
      return;
    }
    setCompareRunIds((current) => [...current, runId]);
    void ensureCompareRunDetail(runId);
  }

  function exportCompareCsv() {
    downloadTextFile(
      buildExportFilename("eval compare", compare.runs.map((item) => item.id).join("-"), "csv"),
      buildEvalCompareCsv(compare),
      "text/csv;charset=utf-8"
    );
  }

  function addRunToCompare(run: EvalRun) {
    setCompareRunsById((current) => ({ ...current, [run.id]: run }));
  }

  return {
    compareRunIds,
    loadingCompareRunIds,
    compareRuns,
    compare,
    compareMetricRows,
    resetCompareState,
    addRunToCompare,
    ensureCompareRunDetail,
    toggleCompareRun,
    exportCompareCsv,
  };
}
