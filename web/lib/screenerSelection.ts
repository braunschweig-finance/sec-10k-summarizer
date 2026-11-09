export const MAX_COMPARISON_COMPANIES = 4;
export const MIN_COMPARISON_COMPANIES = 2;

/** Undated responses can only be compared within the same response object. */
export function sameSelectionSnapshot(saved: {builtAt:string|null; source:unknown}, current: {built_at:string|null}): boolean {
  return saved.builtAt === current.built_at && (current.built_at !== null || saved.source === current);
}

const identity = (row: { ticker: string }) => row.ticker.trim().toUpperCase();

export function canCompare(selected: readonly { ticker: string }[]): boolean {
  const ids = selected.map(identity);
  return ids.length >= MIN_COMPARISON_COMPANIES && ids.length <= MAX_COMPARISON_COMPANIES
    && ids.every(Boolean) && new Set(ids).size === ids.length;
}

/** Normalize and toggle without mutating the input rows or their order. */
export function toggleSelection<T extends { ticker: string }>(selected: readonly T[], row: T): T[] {
  const seen = new Set<string>();
  const normalized = selected.filter((item) => {
    const id = identity(item);
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  }).slice(0, MAX_COMPARISON_COMPANIES);
  const id = identity(row);
  if (!id) return normalized;
  if (normalized.some((item) => identity(item) === id)) return normalized.filter((item) => identity(item) !== id);
  return normalized.length < MAX_COMPARISON_COMPANIES ? [...normalized, row] : normalized;
}
