import type { ManagerApproval } from "~/composables/usePosCashSession";
import type { DeliveryPaymentMethod } from "~/presentation/orderEdit";
import { needsDeliveryPaymentMethod, orderEditBody } from "~/presentation/orderEdit";
import type {
  OrderEditContext,
  OrderEditPreview,
  OrderEditPreviewResponse,
  OrderEditResponse,
  OrderEditSessionResponse,
} from "~/types/preorders";
import type { POSTabPayload } from "~/types/pos";

/**
 * A tela de venda em MODO EDIÇÃO de uma encomenda (ENCOMENDAS-PDV-PLAN, WP-E6).
 *
 * Decisão do dono (28/09): o editor é a própria venda — carrinho, grade, F7, F8,
 * cliente. Quem monta o carrinho é o servidor: `start` abre (ou retoma) a
 * comanda virtual da encomenda (`pos/preorders/<ref>/edit-session/`), que a
 * venda carrega como qualquer comanda. O que muda é o fim: em vez do
 * pagamento, "Salvar alterações" — prévia (`orders/<ref>/edit/preview/`: novo
 * total, diferença e o que acontece com ela) e confirmação
 * (`orders/<ref>/edit/`, com o PIN do gerente quando a encomenda paga fica mais
 * barata). Preço, total e devolução são do servidor; a tela só mostra.
 */
export function usePosOrderEdit() {
  const action = usePosAction();
  const context = ref<OrderEditContext | null>(null);
  const preview = ref<OrderEditPreview | null>(null);
  const reviewOpen = ref(false);
  const busy = ref(false);
  /** A frase da última recusa (prévia ou gravação), para a caixa de revisão. */
  const error = ref("");
  /** O servidor pediu como o entregador recebe o que falta (retirada → entrega). */
  const needsPaymentMethod = ref(false);
  const deliveryPaymentMethod = ref<DeliveryPaymentMethod | "">("");
  const managerChallenge = ref<{ code: string; message: string } | null>(null);

  const editing = computed(() => Boolean(context.value));
  const orderRef = computed(() => context.value?.order_ref ?? "");

  let lastAttempt: { signature: string; key: string } | null = null;
  function gestureKey(signature: string): string {
    if (lastAttempt?.signature === signature) return lastAttempt.key;
    const key = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    lastAttempt = { signature, key };
    return key;
  }

  /** Abre a comanda virtual da encomenda. Devolve a comanda para a venda carregar. */
  async function start(ref: string): Promise<POSTabPayload | null> {
    busy.value = true;
    try {
      const response = await action.call<OrderEditSessionResponse>(
        `/api/v1/backstage/pos/preorders/${encodeURIComponent(ref)}/edit-session/`,
        { body: {} },
      );
      context.value = response.edit;
      preview.value = null;
      error.value = "";
      return response.tab;
    } catch (err) {
      error.value = `${httpErrorMessage(err, "Não deu para abrir a edição da encomenda.")} A encomenda não mudou; confira o detalhe e tente de novo.`;
      return null;
    } finally {
      busy.value = false;
    }
  }

  function body(intent: Record<string, unknown>) {
    return orderEditBody(intent, context.value!.original, { deliveryPaymentMethod: deliveryPaymentMethod.value });
  }

  /** A prévia: o que muda, o total novo e o destino da diferença. Nada é gravado. */
  async function review(intent: Record<string, unknown>): Promise<boolean> {
    if (!context.value || busy.value) return false;
    busy.value = true;
    reviewOpen.value = true;
    error.value = "";
    try {
      const response = await action.call<OrderEditPreviewResponse>(
        `/api/v1/backstage/orders/${encodeURIComponent(context.value.order_ref)}/edit/preview/`,
        { body: body(intent) as unknown as Record<string, unknown> },
      );
      preview.value = response.preview;
      needsPaymentMethod.value = false;
      return true;
    } catch (err) {
      preview.value = null;
      const code = httpErrorCode(err);
      if (needsDeliveryPaymentMethod(code)) needsPaymentMethod.value = true;
      error.value = `${httpErrorMessage(err, "Não deu para calcular as alterações.")} Nada foi gravado: corrija na venda e tente de novo.`;
      return false;
    } finally {
      busy.value = false;
    }
  }

  /** Grava a edição. `true` quando aplicou; o PIN do gerente sobe como `managerChallenge`. */
  async function confirm(intent: Record<string, unknown>, managerApproval: ManagerApproval | null = null): Promise<OrderEditResponse | null> {
    if (!context.value || busy.value) return null;
    busy.value = true;
    error.value = "";
    const path = `/api/v1/backstage/orders/${encodeURIComponent(context.value.order_ref)}/edit/`;
    const payload = {
      ...body(intent),
      base_revision: context.value.base_revision,
      expected_actor_id: context.value.actor_id,
    };
    try {
      const response = await action.call<OrderEditResponse>(path, {
        body: {
          ...payload,
          idempotency_key: gestureKey(`${path}:${JSON.stringify(payload)}`),
          ...(managerApproval ? { manager_approval: managerApproval } : {}),
        },
      });
      lastAttempt = null;
      managerChallenge.value = null;
      reviewOpen.value = false;
      return response;
    } catch (err) {
      const code = httpErrorCode(err);
      if (code === "manager_approval_required" || code === "manager_approval_invalid") {
        managerChallenge.value = { code, message: httpErrorMessage(err, "Peça a um gerente para autorizar.") };
        return null;
      }
      managerChallenge.value = null;
      if (needsDeliveryPaymentMethod(code)) needsPaymentMethod.value = true;
      error.value = `${httpErrorMessage(err, "Não deu para salvar as alterações.")} Nada foi gravado: confira a encomenda e tente de novo.`;
      return null;
    } finally {
      busy.value = false;
    }
  }

  function closeReview() {
    reviewOpen.value = false;
    managerChallenge.value = null;
  }

  function reset() {
    context.value = null;
    preview.value = null;
    reviewOpen.value = false;
    error.value = "";
    needsPaymentMethod.value = false;
    deliveryPaymentMethod.value = "";
    managerChallenge.value = null;
    lastAttempt = null;
  }

  return {
    context, preview, reviewOpen, busy, error, needsPaymentMethod, deliveryPaymentMethod, managerChallenge,
    editing, orderRef, start, review, confirm, closeReview, reset,
  };
}
