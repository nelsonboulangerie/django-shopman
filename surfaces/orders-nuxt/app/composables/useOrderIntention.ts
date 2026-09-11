import type { Action } from "~/generated/ordersContract";

type Intention = { key: string; owner: number; body: Record<string, unknown>; method: "POST" | "PATCH" };
type Result = { outcome?: string; detail?: string; count?: number };

/** Session-only, person-bound intentions. Unknown results never create a new key. */
export function useOrderIntention() {
  const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  const pending = useState<Record<string, Intention>>("orders-local-intentions", () => ({}));
  watch(() => session.value?.operator?.id, (next) => {
    if (next) pending.value = Object.fromEntries(Object.entries(pending.value).filter(([, intent]) => intent.owner === next));
  });

  async function executePath(resource: string, path: string, action: (Pick<Action, "enabled" | "reason" | "payload_schema"> & Partial<Pick<Action, "method">>) | undefined, inputs: Record<string, unknown>, approval?: Record<string, string>) {
    const owner = session.value?.operator?.id;
    if (!owner) throw new Error("Identifique-se antes de continuar.");
    let intent = pending.value[resource];
    if (!intent) {
      if (!action?.enabled || !action.payload_schema.base_revision) {
        throw new Error(action?.reason || "Atualize os dados antes de continuar.");
      }
      intent = { owner, key: crypto.randomUUID(), method: action.method === "PATCH" ? "PATCH" : "POST", body: JSON.parse(JSON.stringify({ ...action.payload_schema, ...inputs })) };
      pending.value[resource] = intent;
    }
    const current = intent;
    const samePerson = () => session.value?.operator?.id === current.owner;
    if (Object.entries(inputs).some(([key, value]) => JSON.stringify(value) !== JSON.stringify(current.body[key]))) {
      const result = await $fetch<Result>(path, { query: { idempotency_key: current.key, ...(typeof current.body.ref === "string" ? { ref: current.body.ref } : {}) } });
      if (!samePerson()) throw new Error("A identificação mudou. Confira os dados.");
      if (result.outcome === "applied") {
        delete pending.value[resource];
        throw new Error("A gravação anterior foi confirmada. Seu novo rascunho ainda não foi salvo.");
      }
      throw new Error("Há uma gravação anterior sem resultado confirmado. Seu novo rascunho foi preservado.");
    }
    const finish = (result: Result) => {
      if (!samePerson()) throw new Error("A identificação mudou. Confira os dados antes de continuar.");
      if (result.outcome === "applied") {
        delete pending.value[resource];
        return result;
      }
      throw new Error(result.detail || "Resultado ainda desconhecido. Verifique esta intenção antes de uma nova ação.");
    };
    try {
      const result = await $fetch<Result>(path, {
        method: current.method, headers: { "Idempotency-Key": current.key }, body: { ...current.body, ...(approval ? { manager_approval: approval } : {}) },
      });
      return finish(result);
    } catch (error) {
      if (!samePerson()) throw error;
      const status = httpError(error).status;
      if (status && status >= 400 && status < 500) {
        const directCode = (httpError(error).data as { code?: unknown } | null)?.code;
        const code = httpErrorCode(error) || (typeof directCode === "string" ? directCode : "");
        if (status !== 401 && status !== 403 && !["intention_conflict", "manager_approval_required", "manager_approval_invalid"].includes(code)) delete pending.value[resource];
        throw error;
      }
      // A resposta pode ter se perdido depois do commit. Consultar não executa efeitos.
      const result = await $fetch<Result>(path, { query: { idempotency_key: current.key, ...(typeof current.body.ref === "string" ? { ref: current.body.ref } : {}) } });
      return finish(result);
    }
  }
  async function checkPath(resource: string, path: string) {
    const intent = pending.value[resource];
    if (!intent || intent.owner !== session.value?.operator?.id) throw new Error("Não há gravação pendente para consultar. Confira a ordem atual.");
    const result = await $fetch<Result>(path, { query: { idempotency_key: intent.key, ...(typeof intent.body.ref === "string" ? { ref: intent.body.ref } : {}) } });
    if (intent.owner !== session.value?.operator?.id) throw new Error("A identificação mudou. Confira os dados.");
    if (result.outcome === "applied") delete pending.value[resource];
    return result;
  }
  async function execute(ref_: string, operation: string, action: Action | undefined, inputs: Record<string, unknown>, approval?: Record<string, string>) {
    await executePath(`${ref_}:${operation}`, `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/${encodeURIComponent(operation)}/`, action, inputs, approval);
    return true;
  }
  return { execute, executePath, checkPath };
}
