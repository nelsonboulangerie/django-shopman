import type { Action } from "~/generated/ordersContract";

type Intention = { key: string; owner: number; body: Record<string, unknown> };
type Result = { outcome?: string; detail?: string };

/** Session-only, person-bound intentions. Unknown results never create a new key. */
export function useOrderIntention() {
  const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  const pending = useState<Record<string, Intention>>("orders-local-intentions", () => ({}));
  watch(() => session.value?.operator?.id, (next) => {
    if (next) pending.value = Object.fromEntries(Object.entries(pending.value).filter(([, intent]) => intent.owner === next));
  });

  async function execute(ref_: string, operation: string, action: Action | undefined, inputs: Record<string, unknown>) {
    const owner = session.value?.operator?.id;
    if (!owner) throw new Error("Identifique-se antes de continuar.");
    const resource = `${ref_}:${operation}`;
    let intent = pending.value[resource];
    if (!intent) {
      if (!action?.enabled || !action.payload_schema.base_revision || (operation === "advance" && !action.payload_schema.target_status)) {
        throw new Error(action?.reason || "Atualize o pedido antes de continuar.");
      }
      intent = { owner, key: crypto.randomUUID(), body: JSON.parse(JSON.stringify({ ...action.payload_schema, ...inputs })) };
      pending.value[resource] = intent;
    }
    const current = intent;
    const path = `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/${encodeURIComponent(operation)}/`;
    const samePerson = () => session.value?.operator?.id === current.owner;
    if (Object.entries(inputs).some(([key, value]) => JSON.stringify(value) !== JSON.stringify(current.body[key]))) {
      const result = await $fetch<Result>(path, { query: { idempotency_key: current.key } });
      if (!samePerson()) throw new Error("A identificação mudou. Confira o pedido.");
      if (result.outcome === "applied") {
        delete pending.value[resource];
        throw new Error("A gravação anterior foi confirmada. Seu novo rascunho ainda não foi salvo.");
      }
      throw new Error("Há uma gravação anterior sem resultado confirmado. Seu novo rascunho foi preservado.");
    }
    const finish = (result: Result) => {
      if (!samePerson()) throw new Error("A identificação mudou. Confira o pedido antes de continuar.");
      if (result.outcome === "applied") {
        delete pending.value[resource];
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
        if (status !== 401 && status !== 403 && httpErrorCode(error) !== "intention_conflict") delete pending.value[resource];
        throw error;
      }
      // A resposta pode ter se perdido depois do commit. Consultar não executa efeitos.
      const result = await $fetch<Result>(path, { query: { idempotency_key: current.key } });
      return finish(result);
    }
  }
  return { execute };
}
