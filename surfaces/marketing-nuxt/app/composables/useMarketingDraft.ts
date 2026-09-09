import { computed, nextTick, onBeforeUnmount, onMounted, ref, toValue, watch } from "vue";
import type { MaybeRefOrGetter } from "vue";
import {
  browserDraftStorage,
  clearMarketingDraft,
  marketingDraftEqual,
  mergeMarketingDraft,
  readMarketingDraft,
  writeMarketingDraft,
} from "~/utils/marketingDraft";
import type {
  DraftStorage,
  MarketingDraftConflict,
  MarketingDraftIdentity,
  MarketingDraftPayload,
} from "~/utils/marketingDraft";

export type MarketingDraftState = "" | "saved" | "restored" | "rebased" | "conflict";

export interface UseMarketingDraftOptions {
  owner: MaybeRefOrGetter<string>;
  resource: MaybeRefOrGetter<string>;
  version: MaybeRefOrGetter<string | number>;
  base: MaybeRefOrGetter<MarketingDraftPayload>;
  current: MaybeRefOrGetter<MarketingDraftPayload>;
  apply: (payload: MarketingDraftPayload) => void;
  storage?: DraftStorage | null;
  debounceMs?: number;
}

interface PendingConflict {
  currentBase: MarketingDraftPayload;
  localWins: MarketingDraftPayload;
  serverWins: MarketingDraftPayload;
}

function copy(value: MarketingDraftPayload): MarketingDraftPayload {
  return JSON.parse(JSON.stringify(value)) as MarketingDraftPayload;
}

export function useMarketingDraft(options: UseMarketingDraftOptions) {
  const state = ref<MarketingDraftState>("");
  const savedAt = ref(0);
  const conflicts = ref<MarketingDraftConflict[]>([]);
  const storage = options.storage === undefined ? browserDraftStorage() : options.storage;
  const debounceMs = options.debounceMs ?? 400;
  let ready = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pendingConflict: PendingConflict | null = null;

  const identity = computed<MarketingDraftIdentity>(() => ({
    owner: String(toValue(options.owner) || ""),
    resource: String(toValue(options.resource) || ""),
  }));
  const enabled = computed(() => Boolean(storage && identity.value.owner && identity.value.resource));

  function cancelTimer() {
    if (timer) clearTimeout(timer);
    timer = null;
  }

  function persist(payload = copy(toValue(options.current))) {
    cancelTimer();
    if (!enabled.value || !storage || state.value === "conflict") return;
    const base = copy(toValue(options.base));
    if (marketingDraftEqual(payload, base)) {
      clearMarketingDraft(storage, identity.value);
      state.value = "";
      savedAt.value = 0;
      return;
    }
    const record = writeMarketingDraft(
      storage,
      identity.value,
      toValue(options.version),
      base,
      payload,
    );
    if (record) {
      savedAt.value = record.savedAt;
      state.value = "saved";
    }
  }

  function schedulePersist() {
    cancelTimer();
    timer = setTimeout(() => persist(), debounceMs);
  }

  async function applyWithoutSaving(payload: MarketingDraftPayload) {
    ready = false;
    options.apply(copy(payload));
    await nextTick();
    ready = true;
  }

  async function restore() {
    cancelTimer();
    ready = false;
    pendingConflict = null;
    conflicts.value = [];
    state.value = "";
    savedAt.value = 0;
    if (!enabled.value || !storage) {
      ready = true;
      return;
    }

    const record = readMarketingDraft(storage, identity.value);
    const currentBase = copy(toValue(options.base));
    if (!record) {
      ready = true;
      return;
    }
    savedAt.value = record.savedAt;

    const sameBase = record.baseVersion === String(toValue(options.version))
      && marketingDraftEqual(record.base, currentBase);
    if (sameBase) {
      options.apply(copy(record.payload));
      state.value = "restored";
      await nextTick();
      ready = true;
      return;
    }

    const merged = mergeMarketingDraft(record.base, currentBase, record.payload);
    if (merged.localChanged.length === 0) {
      clearMarketingDraft(storage, identity.value);
      ready = true;
      return;
    }
    if (merged.conflicts.length === 0) {
      options.apply(copy(merged.localWins));
      const rebased = writeMarketingDraft(
        storage,
        identity.value,
        toValue(options.version),
        currentBase,
        merged.localWins,
      );
      savedAt.value = rebased?.savedAt ?? record.savedAt;
      state.value = "rebased";
      await nextTick();
      ready = true;
      return;
    }

    conflicts.value = merged.conflicts;
    pendingConflict = {
      currentBase,
      localWins: merged.localWins,
      serverWins: merged.serverWins,
    };
    state.value = "conflict";
    await nextTick();
    ready = true;
  }

  async function resolveConflict(preference: "local" | "server") {
    if (!pendingConflict || !storage) return;
    const payload = preference === "local"
      ? pendingConflict.localWins
      : pendingConflict.serverWins;
    ready = false;
    options.apply(copy(payload));
    const hasLocalChanges = !marketingDraftEqual(payload, pendingConflict.currentBase);
    const record = hasLocalChanges
      ? writeMarketingDraft(
          storage,
          identity.value,
          toValue(options.version),
          pendingConflict.currentBase,
          payload,
        )
      : null;
    if (!hasLocalChanges) clearMarketingDraft(storage, identity.value);
    pendingConflict = null;
    conflicts.value = [];
    savedAt.value = record?.savedAt ?? 0;
    state.value = hasLocalChanges ? "rebased" : "";
    await nextTick();
    ready = true;
  }

  async function discard() {
    cancelTimer();
    if (storage && enabled.value) clearMarketingDraft(storage, identity.value);
    pendingConflict = null;
    conflicts.value = [];
    state.value = "";
    savedAt.value = 0;
    await applyWithoutSaving(copy(toValue(options.base)));
  }

  function flushBeforePageLeaves() {
    if (ready && timer) persist();
  }

  watch(
    () => toValue(options.current),
    () => {
      if (ready && enabled.value && state.value !== "conflict") schedulePersist();
    },
    { deep: true },
  );

  watch(
    () => [
      identity.value.owner,
      identity.value.resource,
      String(toValue(options.version)),
      JSON.stringify(toValue(options.base)),
    ],
    () => { void restore(); },
    { flush: "post" },
  );

  onMounted(() => {
    if (typeof window !== "undefined") window.addEventListener("pagehide", flushBeforePageLeaves);
    void restore();
  });
  onBeforeUnmount(() => {
    if (typeof window !== "undefined") window.removeEventListener("pagehide", flushBeforePageLeaves);
    if (ready && timer) persist();
    else cancelTimer();
  });

  return {
    state,
    savedAt,
    conflicts,
    enabled,
    flush: persist,
    restore,
    discard,
    keepLocal: () => resolveConflict("local"),
    keepServer: () => resolveConflict("server"),
  };
}

/** Read the already-loaded session without creating another protected request. */
export function useMarketingDraftOwner() {
  const { data } = useNuxtData<{
    operator: { id: number } | null;
  }>("operator-session");
  return computed(() => data.value?.operator?.id ? `operator:${data.value.operator.id}` : "");
}

export function clearBrowserMarketingDraft(identity: MarketingDraftIdentity): void {
  const storage = browserDraftStorage();
  if (storage && identity.owner && identity.resource) clearMarketingDraft(storage, identity);
}
