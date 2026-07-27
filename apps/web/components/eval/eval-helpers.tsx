import type { EvalRunCompareCell } from "@/lib/eval-run-compare";

export function formatRate(value: number | undefined) {
  if (typeof value !== "number") {
    return "0%";
  }
  return `${Math.round(value * 100)}%`;
}

export function formatLatency(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "0 ms";
  }
  return `${Math.round(value)} ms`;
}

export function formatDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatCellOutcome(cell: EvalRunCompareCell) {
  if (!cell.resultId) {
    return "Missing";
  }
  if (cell.refused) {
    return "Refused";
  }
  return cell.answerMatched ? "Pass" : "Fail";
}

export function getCellClassName(cell: EvalRunCompareCell) {
  if (!cell.resultId) {
    return "eval-compare-cell missing";
  }
  if (cell.refused) {
    return "eval-compare-cell refused";
  }
  return cell.answerMatched ? "eval-compare-cell pass" : "eval-compare-cell fail";
}

export function downloadTextFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
