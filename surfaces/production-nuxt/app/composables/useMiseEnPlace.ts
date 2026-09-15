// Mise en place read-side. Single source for the day's aggregated ingredient
// list (GET /api/v1/backstage/production/mise-en-place/):
//   - expand=false (default): immediate ingredients with per-recipe breakdown;
//   - expand=true: sub-recipes exploded down to raw materials.
// The "separado" checkmark is shift-local state (localStorage), never persisted
// server-side. It is scoped to station + date + projection digest so a changed
// plan cannot inherit marks from the list the operator actually checked.
import type { Ref } from "vue";
import type { MiseEnPlaceLineProjection, MiseEnPlaceResponse } from "~/types/production";

interface ChecklistStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

interface ChecklistScope {
  stationRef: string;
  selectedDate: string;
  sourceRevision: string;
}

interface LoadedChecklist {
  checked: Set<string>;
  revisionChanged: boolean;
}

function revisionDigest(sourceRevision: string): string {
  const match = /^sha256:([0-9a-f]{16,64}):/.exec(sourceRevision);
  return match?.[1] ?? "";
}

export function checklistStorageKeys(scope: ChecklistScope) {
  const digest = revisionDigest(scope.sourceRevision);
  if (!scope.selectedDate || !digest) return null;
  const station = encodeURIComponent(scope.stationRef.trim() || "unprovisioned-device");
  const base = `preparacao:v2:${station}:${scope.selectedDate}`;
  return {
    activeRevision: `${base}:active-revision`,
    items: `${base}:items:${digest}`,
    digest,
    base,
  };
}

export function loadChecklist(storage: ChecklistStorage, scope: ChecklistScope): LoadedChecklist {
  const keys = checklistStorageKeys(scope);
  if (!keys) return { checked: new Set(), revisionChanged: false };

  const previousDigest = storage.getItem(keys.activeRevision);
  const revisionChanged = Boolean(previousDigest && previousDigest !== keys.digest);
  if (revisionChanged) storage.removeItem(`${keys.base}:items:${previousDigest}`);
  storage.setItem(keys.activeRevision, keys.digest);

  try {
    const parsed = JSON.parse(storage.getItem(keys.items) ?? "[]");
    return {
      checked: new Set(
        Array.isArray(parsed)
          ? parsed.filter((value): value is string => typeof value === "string")
          : [],
      ),
      revisionChanged,
    };
  } catch {
    return { checked: new Set(), revisionChanged };
  }
}

export function useMiseEnPlace(selectedDate: Ref<string>, stationRef: Ref<string>) {
  const expand = ref(false);

  const { data, pending, error, refresh } = useFetch<MiseEnPlaceResponse>(
    "/api/v1/backstage/production/mise-en-place/",
    {
      key: "production-mise-en-place",
      server: true,
      query: computed(() => ({ expand: expand.value ? "1" : "", date: selectedDate.value })),
    },
  );

  const projection = computed(() => data.value?.mise_en_place ?? null);
  const lines = computed<MiseEnPlaceLineProjection[]>(() => projection.value?.lines ?? []);

  useAdaptivePoll(refresh, () => 60_000);

  const checklistScope = computed<ChecklistScope>(() => ({
    stationRef: stationRef.value,
    selectedDate: projection.value?.selected_date ?? "",
    sourceRevision: projection.value?.source_revision ?? "",
  }));
  const checkedKey = computed(() => checklistStorageKeys(checklistScope.value)?.items ?? "");
  const checked = ref<Set<string>>(new Set());
  const checklistRevisionChanged = ref(false);

  function loadChecked() {
    checklistRevisionChanged.value = false;
    if (!import.meta.client || !projection.value || !checkedKey.value) {
      checked.value = new Set();
      return;
    }
    try {
      const loaded = loadChecklist(localStorage, checklistScope.value);
      checked.value = loaded.checked;
      checklistRevisionChanged.value = loaded.revisionChanged;
    } catch {
      checked.value = new Set();
    }
  }
  watch(checkedKey, loadChecked, { immediate: true });

  function toggleChecked(sku: string) {
    const next = new Set(checked.value);
    if (next.has(sku)) next.delete(sku);
    else next.add(sku);
    checked.value = next;
    if (import.meta.client && checkedKey.value) {
      try {
        localStorage.setItem(checkedKey.value, JSON.stringify([...next]));
      } catch {
        // storage cheio/indisponível: o check vive só na sessão.
      }
    }
  }
  const isChecked = (sku: string) => checked.value.has(sku);
  const checkedCount = computed(
    () => lines.value.filter((line) => checked.value.has(line.sku)).length,
  );

  return {
    projection,
    lines,
    expand,
    pending,
    error,
    refresh,
    isChecked,
    toggleChecked,
    checkedCount,
    checklistRevisionChanged,
  };
}
