import type { UUID } from "@/lib/types";

export function openOnlyProject(projectId: UUID) {
  return new Set<UUID>([projectId]);
}

export function getNextExpandedProjectIds(current: Set<UUID>, projectId: UUID) {
  if (current.has(projectId)) {
    return new Set<UUID>();
  }

  return openOnlyProject(projectId);
}
