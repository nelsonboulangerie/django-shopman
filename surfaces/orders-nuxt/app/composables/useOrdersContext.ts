import type { FulfillmentFilter, SortKey, ViewMode } from "~/presentation/board";

type BoardContext = {
  owner: number | null; query: string; channel: string; fulfillment: FulfillmentFilter;
  sort: SortKey; viewMode: ViewMode; selected: string[]; scrollTop: number; windowY: number; focusLabel: string;
};
const emptyContext = (owner: number | null): BoardContext => ({ owner, query: "", channel: "all", fulfillment: "all", sort: "arrival", viewMode: "board", selected: [], scrollTop: 0, windowY: 0, focusLabel: "" });

/** Contexto somente na sessão atual. Trocar pessoa descarta inclusive a seleção. */
export function useOrdersContext() {
  const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  const state = useState<BoardContext>("orders-board-context", () => emptyContext(session.value?.operator?.id ?? null));
  watch(() => session.value?.operator?.id, (owner) => {
    if (owner && owner !== state.value.owner) state.value = emptyContext(owner);
  }, { immediate: true, flush: "sync" });

  const query = computed({ get: () => state.value.query, set: (v: string) => { state.value.query = v; } });
  const channel = computed({ get: () => state.value.channel, set: (v: string) => { state.value.channel = v; } });
  const fulfillment = computed({ get: () => state.value.fulfillment, set: (v: FulfillmentFilter) => { state.value.fulfillment = v; } });
  const sort = computed({ get: () => state.value.sort, set: (v: SortKey) => { state.value.sort = v; } });
  const viewMode = computed({ get: () => state.value.viewMode, set: (v: ViewMode) => { state.value.viewMode = v; } });
  const selected = computed({ get: () => new Set(state.value.selected), set: (v: Set<string>) => { state.value.selected = [...v]; } });
  const location = computed(() => ({ path: "/", query: {
    ...(state.value.owner ? { person: String(state.value.owner) } : {}),
    ...(query.value ? { q: query.value } : {}), ...(channel.value !== "all" ? { channel: channel.value } : {}),
    ...(fulfillment.value !== "all" ? { fulfillment: fulfillment.value } : {}),
    ...(sort.value !== "arrival" ? { sort: sort.value } : {}), ...(viewMode.value !== "board" ? { view: viewMode.value } : {}),
  } }));
  function readLocation(params: Record<string, unknown>) {
    if (!state.value.owner) return;
    if (params.person && params.person !== String(state.value.owner)) {
      state.value = emptyContext(state.value.owner);
      return;
    }
    const text = (key: string) => typeof params[key] === "string" ? (params[key] as string) : "";
    query.value = text("q"); channel.value = text("channel") || "all";
    fulfillment.value = ["delivery", "pickup"].includes(text("fulfillment")) ? text("fulfillment") as FulfillmentFilter : "all";
    sort.value = ["urgency", "recent"].includes(text("sort")) ? text("sort") as SortKey : "arrival";
    viewMode.value = text("view") === "table" ? "table" : "board";
  }
  return { state, query, channel, fulfillment, sort, viewMode, selected, location, readLocation };
}
