export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const size = value / 1024 ** index;
  return `${size.toFixed(size >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatLatency(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "";
  }

  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`;
}

export function shortId(value: string): string {
  return value.slice(0, 8);
}

export function metadataLabel(metadata: Record<string, unknown>): string {
  const source = metadata.source ?? metadata.filename ?? metadata.sheet_name;
  return typeof source === "string" && source.length > 0 ? source : "source";
}
