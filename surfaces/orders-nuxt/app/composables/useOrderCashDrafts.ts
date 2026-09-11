export type SettlementDraft = { amount: string; changeBack: string; equipmentBack: boolean; revision: string; custody: string };
export type DispatchDraft = { amount: string; equipment: string[] };

/** Valores físicos digitados ficam só nesta sessão/pessoa/pedido, nunca em storage. */
export function useOrderCashDrafts() {
  const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  const drafts = useState<{ owner: number | null; baseline: Record<string, string>; settlement: Record<string, SettlementDraft>; dispatch: Record<string, DispatchDraft> }>("orders-cash-drafts", () => ({ owner: session.value?.operator?.id ?? null, baseline: {}, settlement: {}, dispatch: {} }));
  watch(() => session.value?.operator?.id, (owner) => {
    if (owner && owner !== drafts.value.owner) drafts.value = { owner, baseline: {}, settlement: {}, dispatch: {} };
  }, { immediate: true, flush: "sync" });
  function settlement(ref_: string, initial: SettlementDraft) {
    if (!drafts.value.settlement[ref_]) {
      drafts.value.baseline[`settlement:${ref_}`] = settlementInputs(initial);
      drafts.value.settlement[ref_] = { ...initial };
    }
    return drafts.value.settlement[ref_]!;
  }
  function dispatch(ref_: string, initial: DispatchDraft) {
    if (!drafts.value.dispatch[ref_]) {
      drafts.value.baseline[`dispatch:${ref_}`] = JSON.stringify(initial);
      drafts.value.dispatch[ref_] = { ...initial, equipment: [...initial.equipment] };
    }
    return drafts.value.dispatch[ref_]!;
  }
  const settlementInputs = (value: SettlementDraft) => JSON.stringify({ amount: value.amount, changeBack: value.changeBack, equipmentBack: value.equipmentBack });
  const hasDirty = computed(() => Object.entries(drafts.value.settlement).some(([ref_, value]) => settlementInputs(value) !== drafts.value.baseline[`settlement:${ref_}`])
    || Object.entries(drafts.value.dispatch).some(([ref_, value]) => JSON.stringify(value) !== drafts.value.baseline[`dispatch:${ref_}`]));
  function clear(kind: "settlement" | "dispatch", ref_: string) {
    delete drafts.value[kind][ref_];
    delete drafts.value.baseline[`${kind}:${ref_}`];
  }
  return { settlement, dispatch, clear, hasDirty, settlements: computed(() => drafts.value.settlement), dispatches: computed(() => drafts.value.dispatch) };
}
