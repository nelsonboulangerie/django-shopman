import type { Action } from "~/generated/ordersContract";

type Intention = { key: string; owner: number; body: Record<string, unknown> };
type Result = { outcome?: string; detail?: string };

/** Session-only, person-bound intentions. Unknown results never create a new key. */
export function useOrderAdvanceIntention() {
  const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  const pending = useState<Record<string, Intention>>("orders-advance-intentions", () => ({}));
  watch(() => session.value?.operator?.id, (next) => {
    if (next) pending.value = Object.fromEntries(Object.entries(pending.value).filter(([, intent]) => intent.owner === next));
  });

  async function advance(ref_: string, action: Action | undefined, inputs: Record<string, unknown>) {
    const owner = session.value?.operator?.id;
    if (!owner) throw new Error("Identifique-se antes de continuar.");
    let intent = pending.value[ref_];
    if (!intent) {
      if (!action?.enabled || !action.payload_schema.base_revision || !action.payload_schema.target_status) {
        throw new Error(action?.reason || "Atualize o pedido antes de continuar.");
      }
      intent = { owner, key: crypto.randomUUID(), body: { ...inputs, ...action.payload_schema } };
      pending.value[ref_] = intent;
    }
    const current = intent;
    const path = `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/advance/`;
    const samePerson = () => session.value?.operator?.id === current.owner;
    const finish = (result: Result) => {
      if (!samePerson()) throw new Error("A identificação mudou. Confira o pedido antes de continuar.");
      if (result.outcome === "applied") {
        delete pending.value[ref_];
        return true;
      }
      throw new Error(result.detail || "Resultado ainda desconhecido. Verifique esta intenção antes de uma nova ação.");
    };
    try {
      const result = await $fetch<Result>(path, {
        method: "POST", headers: { "Idempotency-Key": current.key }, body: current.body,
      });
      return finish(result);
    } catch (error) {
      if (!samePerson()) throw error;
      const status = httpError(error).status;
      if (status && status >= 400 && status < 500) {
        if (status !== 401 && status !== 403 && httpErrorCode(error) !== "intention_conflict") delete pending.value[ref_];
        throw error;
      }
      // A resposta pode ter se perdido depois do commit. Consultar não executa efeitos.
      const result = await $fetch<Result>(path, { query: { idempotency_key: current.key } });
      return finish(result);
    }
  }
  return { advance };
}
