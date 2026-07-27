type StatusBadgeProps = {
  status: string;
  errorMessage?: string | null;
};

export function StatusBadge({ status, errorMessage }: StatusBadgeProps) {
  const title = status === "failed" && errorMessage ? errorMessage : undefined;
  return (
    <span className={`status-badge status-${status}`} title={title}>
      {status}
    </span>
  );
}
