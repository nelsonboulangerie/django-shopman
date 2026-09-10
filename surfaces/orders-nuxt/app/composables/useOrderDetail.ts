// Order detail read-side. Reads the expanded operator projection (items, timeline,
// notes, fiscal links) and exposes the full action set. Writes go through the django
// proxy and reconcile via refresh. Mirrors useOrdersBoard's in-flight guard.
import type { CancellationReason, OperatorOrderProjection, OrderDetailResponse } from "~/types/orders";

export function useOrderDetail(orderRef: string) {
  const path = `/api/v1/backstage/orders/${encodeURIComponent(orderRef)}/`;
  // Estação travada: a leitura volta 403 `station_locked` e a tela dizia "Pedido
  // não encontrado ou falha ao carregar" — o pedido existe, quem não se
  // identificou é o operador. Erguer a bandeira aqui é o que permite à tela
  // calar o aviso de erro (mesmo gesto do `usePosTerminal`).
  const { flagIfStationLocked } = useStationLock();

  const { data, pending, error, refresh } = useFetch<OrderDetailResponse>(path, {
    key: `order-detail-${orderRef}`,
    server: true,
  });

  watch(error, (value) => { if (value) flagIfStationLocked(value); }, { immediate: true });

  const order = computed<OperatorOrderProjection | null>(() => data.value?.order ?? null);

  const busy = ref(false);

  // ── Desafio de gerente ─────────────────────────────────────────────────────
  //
  // ⚠️ Cancelar pedido PAGO exige segunda assinatura, e o servidor pede isso com
  // um erro TIPADO (`manager_approval_required`, de `validate_manager_override`).
  // O `act` engolia qualquer erro num toast: o gerente lia "Falha na ação",
  // sem nenhum lugar onde assinar. O pedido pago simplesmente não cancelava pelo
  // Gestor — e nenhuma outra superfície cancela pedido da loja.
  //
  // Guardamos a tentativa para REENVIAR o mesmo ato com a autorização, em vez de
  // pedir ao gerente que refaça o gesto (e escolha o motivo de novo).
  const managerChallenge = ref<{ code: string; message: string } | null>(null);
  let lastAttempt: { action: string; body?: Record<string, unknown> } | null = null;

  async function act(
    action: string,
    body?: Record<string, unknown>,
    approval?: Record<string, string>,
  ): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    try {
      await $fetch(`/api/v1/backstage/orders/${encodeURIComponent(orderRef)}/${action}/`, {
        method: "POST",
        body: { ...(body ?? {}), ...(approval ? { manager_approval: approval } : {}) },
      });
      managerChallenge.value = null;
      lastAttempt = null;
      await refresh();
      return true;
    } catch (error) {
      const code = httpErrorCode(error);
      if (code === "manager_approval_required" || code === "manager_approval_invalid") {
        // Sem toast: o desafio NÃO é falha, é um passo do fluxo. Um toast
        // vermelho aqui ensina o gerente que o sistema quebrou.
        lastAttempt = { action, body };
        managerChallenge.value = {
          code,
          message: httpErrorMessage(error, "Esta ação precisa da autorização de um gerente."),
        };
        return false;
      }
      useSonner.error(httpErrorMessage(error, "Falha na ação. Tente de novo."));
      return false;
    } finally {
      busy.value = false;
    }
  }

  /** Reenvia o ato que pediu assinatura, agora com ela. PIN ou crachá. */
  async function authorize(approval: Record<string, string>): Promise<boolean> {
    if (!lastAttempt) return false;
    return act(lastAttempt.action, lastAttempt.body, approval);
  }

  function dismissManagerChallenge() {
    managerChallenge.value = null;
    lastAttempt = null;
  }

  const confirm = () => act("confirm");
  const advance = (changeOut?: string, equipment?: string[]) => {
    const body: Record<string, unknown> = {};
    if (changeOut !== undefined) body.change_out = changeOut;
    if (equipment && equipment.length) body.equipment = equipment;
    return act("advance", Object.keys(body).length ? body : undefined);
  };
  const equipmentBack = () => act("equipment-back");
  // Marketplace (iFood) reject/cancel carry the operator-picked code so the backend
  // relays a valid reason to the provider; empty string for other channels.
  const reject = (reason: string, cancellation_code = "") => act("reject", { reason, cancellation_code });
  const cancel = (reason: string, cancellation_code = "") => act("cancel", { reason, cancellation_code });
  const settleCash = (amount: string, changeBack?: string, equipmentBack?: boolean) =>
    act("settle-delivery-cash", {
      amount,
      ...(changeBack === undefined ? {} : { change_back: changeBack }),
      ...(equipmentBack ? { equipment_back: true } : {}),
    });
  const requeueFiscal = () => act("requeue-fiscal");

  // Reenvio do link de pagamento ("não chegou"): o servidor enfileira o aviso
  // de novo com a MESMA URL, e recusa com motivo (vencido, pago, cancelado,
  // cedo demais) — o motivo chega como `detail` e vira o toast do `act`.
  async function resendPaymentLink(): Promise<boolean> {
    const ok = await act("resend-payment-link");
    if (ok) useSonner.success("Link reenviado ao cliente.");
    return ok;
  }

  // Valid cancellation reasons for this order: for iFood, the live per-order coded
  // list ({code, description}); empty for channels without reason codes.
  async function fetchCancellationReasons(): Promise<CancellationReason[]> {
    try {
      const res = await $fetch<{ reasons: CancellationReason[] }>(
        `/api/v1/backstage/orders/${encodeURIComponent(orderRef)}/cancellation-reasons/`,
      );
      return res?.reasons ?? [];
    } catch {
      return [];
    }
  }

  async function saveNotes(notes: string): Promise<boolean> {
    const ok = await act("notes", { notes });
    if (ok) useSonner.success("Notas salvas.");
    return ok;
  }

  async function addComment(note: string): Promise<boolean> {
    const ok = await act("comment", { note });
    if (ok) useSonner.success("Comentário adicionado.");
    return ok;
  }

  // Courier ride (external delivery): dispatch/re-dispatch, cancel the active
  // ride, and "just quote" (stores the estimate; refresh shows it in the panel).
  async function courierDispatch(): Promise<boolean> {
    const ok = await act("courier-dispatch");
    if (ok) useSonner.success("Corrida solicitada.");
    return ok;
  }

  async function courierCancel(): Promise<boolean> {
    const ok = await act("courier-cancel");
    if (ok) useSonner.success("Corrida cancelada.");
    return ok;
  }

  async function courierQuote(): Promise<boolean> {
    const ok = await act("courier-quote");
    if (ok) useSonner.success("Cotação atualizada.");
    return ok;
  }

  return { order, pending, error, refresh, busy, confirm, advance, reject, cancel, fetchCancellationReasons, settleCash, equipmentBack, requeueFiscal, resendPaymentLink, saveNotes, addComment, courierDispatch, courierCancel, courierQuote, managerChallenge, authorize, dismissManagerChallenge };
}
