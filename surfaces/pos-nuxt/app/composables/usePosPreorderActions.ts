import type { ComputedRef, Ref } from "vue";
import { toast } from "vue-sonner";

import type { ManagerApproval } from "~/composables/usePosCashSession";
import { handOverDoneMessage, type HandOverBody } from "~/presentation/preorderActions";
import type { PreorderDetailResponse, PreorderHandOverResponse } from "~/types/preorders";
import type { POSProjection } from "~/types/pos";

export interface ManagerChallenge {
  code: string;
  message: string;
}

/**
 * Os gestos do detalhe de uma encomenda (ENCOMENDAS-PDV-PLAN, WP-E3/E4).
 *
 * - **Receber e entregar**: a rota do PDV (`/pos/preorders/<ref>/hand-over/`),
 *   que faz o acerto no turno DESTA estação e conclui, numa transação. Mesma
 *   idempotência das mutações de caixa: uma chave por gesto (`client_request_id`),
 *   reaproveitada quando o mesmo gesto é repetido depois de uma falha de rede.
 * - **Cancelar**: a MESMA rota do Gestor (`/orders/<ref>/cancel/`) — régua,
 *   política, permissão e PIN de gerente num lugar só. Pedido pago volta com
 *   `manager_approval_required`; a página abre o `OperatorManagerAuth` e repete o
 *   gesto com a assinatura.
 *
 * Depois de qualquer gesto, a leitura canônica é refeita (`refresh`).
 */
export function usePosPreorderActions(options: {
  detail: Ref<PreorderDetailResponse | null | undefined>;
  pos: ComputedRef<POSProjection | null>;
  refresh: () => Promise<unknown>;
}) {
  const action = usePosAction();
  const drawer = useCounterAgent(options.pos);
  const busy = ref(false);
  const managerChallenge = ref<ManagerChallenge | null>(null);

  let lastAttempt: { signature: string; key: string } | null = null;
  function gestureKey(signature: string): string {
    if (lastAttempt?.signature === signature) return lastAttempt.key;
    const key = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    lastAttempt = { signature, key };
    return key;
  }

  async function handOver(body: HandOverBody): Promise<boolean> {
    const detail = options.detail.value;
    if (!detail || busy.value) return false;
    busy.value = true;
    const path = `/api/v1/backstage/pos/preorders/${encodeURIComponent(detail.card.ref)}/hand-over/`;
    const payload = {
      base_revision: detail.revision,
      terminal_ref: options.pos.value?.terminal_ref || "",
      ...body,
    };
    try {
      const response = await action.call<PreorderHandOverResponse>(path, {
        body: { ...payload, client_request_id: gestureKey(`${path}:${JSON.stringify(payload)}`) },
      });
      lastAttempt = null;
      if (body.tenders?.some((tender) => tender.method === "cash")) void drawer.kick("preorder_cash");
      toast.success(handOverDoneMessage(response?.received_q ?? 0));
      await options.refresh();
      return true;
    } catch (error) {
      toast.error(`${httpErrorMessage(error, "Não deu para entregar a encomenda.")} Confira a encomenda e tente de novo.`);
      await options.refresh();
      return false;
    } finally {
      busy.value = false;
    }
  }

  async function cancel(reason: string, managerApproval: ManagerApproval | null = null): Promise<boolean> {
    const detail = options.detail.value;
    if (!detail || busy.value) return false;
    busy.value = true;
    const path = `/api/v1/backstage/orders/${encodeURIComponent(detail.card.ref)}/cancel/`;
    const payload = { reason: reason.trim(), base_revision: detail.revision, expected_actor_id: detail.actor_id };
    try {
      await action.call(path, {
        body: {
          ...payload,
          idempotency_key: gestureKey(`${path}:${JSON.stringify(payload)}`),
          ...(managerApproval ? { manager_approval: managerApproval } : {}),
        },
      });
      lastAttempt = null;
      managerChallenge.value = null;
      toast.success("Encomenda cancelada.");
      await options.refresh();
      return true;
    } catch (error) {
      const code = httpErrorCode(error);
      if (code === "manager_approval_required" || code === "manager_approval_invalid") {
        managerChallenge.value = { code, message: httpErrorMessage(error, "Peça a um gerente para autorizar.") };
        return false;
      }
      managerChallenge.value = null;
      toast.error(`${httpErrorMessage(error, "Não deu para cancelar a encomenda.")} Confira a encomenda e tente de novo.`);
      await options.refresh();
      return false;
    } finally {
      busy.value = false;
    }
  }

  function dismissManagerChallenge() {
    managerChallenge.value = null;
  }

  return { busy, managerChallenge, handOver, cancel, dismissManagerChallenge };
}
