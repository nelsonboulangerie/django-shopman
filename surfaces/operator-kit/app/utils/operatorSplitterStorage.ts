export interface OperatorSplitterStorage {
  getItem: (name: string) => string | null;
  setItem: (name: string, value: string) => void;
  removeItem?: (name: string) => void;
}

interface SplitterStateEntry {
  layout?: unknown;
  expandToSizes?: unknown;
  sizeUnits?: unknown;
}

function validLayout(value: unknown, panelCount: number): value is number[] {
  if (!Array.isArray(value) || value.length !== panelCount) return false;
  if (!value.every((size) => typeof size === "number" && Number.isFinite(size) && size >= 0)) return false;
  const total = value.reduce((sum, size) => sum + size, 0);
  return total > 0 && total <= 100.5;
}

export function validOperatorSplitterState(serialized: string, panelCount: number): boolean {
  try {
    const state = JSON.parse(serialized) as Record<string, SplitterStateEntry>;
    if (!state || typeof state !== "object" || Array.isArray(state)) return false;
    const entries = Object.values(state);
    return entries.length > 0 && entries.every((entry) => entry && validLayout(entry.layout, panelCount));
  } catch {
    return false;
  }
}

export function createOperatorSplitterStorage(
  panelCount: number,
  storage: OperatorSplitterStorage | undefined = typeof window === "undefined" ? undefined : window.localStorage,
): OperatorSplitterStorage {
  return {
    getItem(name) {
      const value = storage?.getItem(name) ?? null;
      if (!value) return null;
      if (validOperatorSplitterState(value, panelCount)) return value;
      storage?.removeItem?.(name);
      return null;
    },
    setItem(name, value) {
      if (validOperatorSplitterState(value, panelCount)) storage?.setItem(name, value);
    },
    removeItem(name) {
      storage?.removeItem?.(name);
    },
  };
}
