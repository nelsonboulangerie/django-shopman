import { useReadMetadata } from "./useReadMetadata";
import { coalesceRefresh } from "../utils/coalesceRefresh";
import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { useOrderIntention } from "./useOrderIntention";
// Order detail read-side. Reads the expanded operator projection (items, timeline,
// notes, fiscal links) and exposes the full action set. Writes go through the django
// proxy and reconcile via refresh. Mirrors useOrdersBoard's in-flight guard.
import type {
  CancellationReason,
  OperatorOrderProjection,
  OrderDetailResponse,
} from "~/types/orders";

export function useOrderDetail(orderRef: string) {
  const intentions = useOrderIntention();
  const path = `/api/v1/backstage/orders/${encodeURIComponent(orderRef)}/`;
  // Estação travada: a leitura volta 403 `station_locked` e a tela dizia "Pedido
  // não encontrado ou falha ao carregar" — o pedido existe, quem não se
  // identificou é o operador. Erguer a bandeira aqui é o que permite à tela
  // calar o aviso de erro (mesmo gesto do `usePosTerminal`).
  const { flagIfStationLocked } = useStationLock();

  const {
    data,
    pending,
    error,
    refresh: fetchOrder,
  } = useFetch<OrderDetailResponse>(path, {
    key: useOperatorResourceKey(`order-detail-${orderRef}`),
    server: true,
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });

  const refresh = coalesceRefresh(() => fetchOrder());

  // ── Conferência do cartão com o gateway ────────────────────────────────────
  //
  // A leitura do detalhe não pergunta ao gateway (A8-1): o servidor diz
  // `payment_check_due` quando o pedido deve cartão, e a tela pede o comando ao
  // abrir o pedido e quando ele volta a dever. O intervalo mínimo entre
  // perguntas é do servidor. Pagou (o webhook se perdeu): relê o pedido.
  async function checkPayment() {
    try {
      const result = await $fetch<{ changed: boolean }>(
        `/api/v1/backstage/orders/${encodeURIComponent(orderRef)}/payment/check/`,
        { method: "POST" },
      );
      if (result.changed) await refresh();
    } catch {
      // Melhor esforço, como era no GET: o `reconcile_payments` do worker é a
      // rede, e a tela segue com o que leu.
    }
  }
  if (!import.meta.server) {
    watch(
      () => data.value?.payment_check_due === true,
      (due) => {
        if (due) void checkPayment();
      },
      { immediate: true },
    );
  }

  watch(
    error,
    (value) => {
      if (value) flagIfStationLocked(value);
    },
    { immediate: true },
  );

  const readMetadata = useReadMetadata(data, error);
  const lastConfirmed = shallowRef<OperatorOrderProjection | null>(
    data.value?.order ?? null,
  );
  watch(
    [data, error],
    ([value, failure]) => {
      if (value?.order && !failure) lastConfirmed.value = value.order;
    },
    { flush: "sync" },
  );
  const order = computed<OperatorOrderProjection | null>(
    () => data.value?.order ?? (error.value ? lastConfirmed.value : null),
  );

  // A impressora desta estação, a mesma que o quadro recebe (a Via Pedido sai por ela).
  const deviceAgent = computed(() => data.value?.device_agent ?? null);

  const busy = ref(false);
  const mutationError = ref("");

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
  let lastAttempt: { action: string; body?: Record<string, unknown> } | null =
    null;

  async function act(
    action: string,
    body?: Record<string, unknown>,
    approval?: Record<string, string>,
  ): Promise<boolean> {
    if (busy.value) return false;
    if (error.value) {
      mutationError.value =
        "A leitura está desatualizada. Atualize o pedido antes de confirmar; seu rascunho foi mantido.";
      return false;
    }
    busy.value = true;
    mutationError.value = "";
    try {
      if (
        [
          "confirm",
          "advance",
          "reject",
          "cancel",
          "notes",
          "assign",
          "unassign",
          "equipment-back",
          "comment",
          "settle-delivery-cash",
          "requeue-fiscal",
          "resend-payment-link",
          "courier-dispatch",
          "courier-dispatch-again",
          "courier-cancel",
          "courier-quote",
          "undo-handoff",
          "undo-ready",
          "ifood-accept-retry",
        ].includes(action)
      ) {
        await intentions.execute(
          orderRef,
          action,
          order.value?.actions?.find((item) => item.ref === action),
          body ?? {},
          approval,
        );
      } else {
        await $fetch(
          `/api/v1/backstage/orders/${encodeURIComponent(orderRef)}/${action}/`,
          {
            method: "POST",
            body: {
              ...(body ?? {}),
              ...(approval ? { manager_approval: approval } : {}),
            },
          },
        );
      }
      managerChallenge.value = null;
      lastAttempt = null;
      try {
        await refresh();
      } catch {
        mutationError.value =
          "Ação confirmada. A leitura atualizada falhou; atualize antes da próxima ação.";
      }
      if (error.value)
        mutationError.value =
          "Ação confirmada. A leitura atualizada falhou; atualize antes da próxima ação.";
      return true;
    } catch (error) {
      const code = httpErrorCode(error);
      if (
        code === "manager_approval_required" ||
        code === "manager_approval_invalid"
      ) {
        // Sem toast: o desafio NÃO é falha, é um passo do fluxo. Um toast
        // vermelho aqui ensina o gerente que o sistema quebrou.
        lastAttempt = { action, body };
        managerChallenge.value = {
          code,
          message: httpErrorMessage(
            error,
            "Esta ação precisa da autorização de um gerente.",
          ),
        };
        return false;
      }
      mutationError.value = httpErrorMessage(
        error,
        error instanceof Error
          ? error.message
          : "Não foi possível confirmar o resultado da ação.",
      );
      useSonner.error(mutationError.value);
      try {
        await refresh();
      } catch {
        mutationError.value +=
          " A leitura atualizada também falhou. Preserve o rascunho e tente atualizar.";
      }
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
  // Desfazer o que ainda está na janela (a saída tocada; o pronto da Cozinha).
  const undoHandoff = () => act("undo-handoff");
  const undoReady = () => act("undo-ready");
  // Marketplace (iFood) reject/cancel carry the operator-picked code so the backend
  // relays a valid reason to the provider; empty string for other channels.
  const reject = (reason: string, cancellation_code = "") =>
    act("reject", { reason, cancellation_code });
  // Cancelar: o motivo é a chave da lista única (`reason_key`, obrigatória fora do
  // iFood); o texto é a observação interna. No iFood, `reason` + código do iFood.
  const cancel = (choice: {
    reasonKey: string;
    internalNote: string;
    reason: string;
    cancellationCode: string;
  }) =>
    act("cancel", {
      reason_key: choice.reasonKey,
      internal_note: choice.internalNote,
      reason: choice.reason,
      cancellation_code: choice.cancellationCode,
    });
  const settleCash = (
    amount: string,
    changeBack?: string,
    equipmentBack?: boolean,
    baseRevision?: string,
  ) =>
    act("settle-delivery-cash", {
      amount,
      ...(changeBack === undefined ? {} : { change_back: changeBack }),
      ...(equipmentBack ? { equipment_back: true } : {}),
      ...(baseRevision ? { base_revision: baseRevision } : {}),
    });
  // A nota volta para a emissão; o alerta de NFC-e não autorizada fecha no
  // servidor. O resultado chega pelo SSE do pedido (autorizada ou recusada).
  async function requeueFiscal(): Promise<boolean> {
    const ok = await act("requeue-fiscal");
    if (ok)
      useSonner.success(
        "NFC-e enviada de novo. O pedido mostra quando ela for autorizada.",
      );
    return ok;
  }

  // O aceite que não chegou ao iFood: o servidor põe o ``confirm`` para sair agora.
  // O resultado chega pelo SSE do pedido (o aviso some quando o iFood recebe).
  async function retryIFoodAccept(): Promise<boolean> {
    const ok = await act("ifood-accept-retry");
    if (ok) useSonner.success("Aceite enviado de novo ao iFood.");
    return ok;
  }

  // Reenvio do link de pagamento ("não chegou"): o servidor enfileira o aviso
  // de novo com a MESMA URL, e recusa com motivo (vencido, pago, cancelado,
  // cedo demais) — o motivo chega como `detail` e vira o toast do `act`.
  async function resendPaymentLink(): Promise<boolean> {
    const ok = await act("resend-payment-link");
    if (ok) useSonner.success("Reenvio do link solicitado.");
    return ok;
  }

  // Valid cancellation reasons for this order: for iFood, the live per-order coded
  // list ({code, description}); empty for channels without reason codes.
  async function fetchCancellationReasons(): Promise<CancellationReason[]> {
    const res = await $fetch<{ reasons: CancellationReason[] }>(
      `/api/v1/backstage/orders/${encodeURIComponent(orderRef)}/cancellation-reasons/`,
    );
    return res.reasons;
  }

  async function saveNotes(
    notes: string,
    baseRevision?: string,
  ): Promise<boolean> {
    const ok = await act("notes", {
      notes,
      ...(baseRevision ? { base_revision: baseRevision } : {}),
    });
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
  // A custódia que sai com o entregador da TaOn (troco da gaveta, maquininha)
  // vai no mesmo corpo do despacho do Gestor: `change_out` e `equipment`.
  async function courierDispatch(
    custody: { change_out?: string; equipment?: string[] } = {},
  ): Promise<boolean> {
    const ok = await act("courier-dispatch", custody);
    if (ok) useSonner.success("Pedido de entregador enviado à central.");
    return ok;
  }

  // Uma corrida para este pedido e os que vão junto (o "Vai junto?" da chamada):
  // a mesma rota do "Juntar entregas" do quadro, com a custódia de cada um.
  async function courierRide(body: {
    refs: string[];
    change_out: Record<string, string>;
    machine: string;
  }): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    mutationError.value = "";
    try {
      await $fetch("/api/v1/backstage/orders/courier-ride/", {
        method: "POST",
        body,
      });
    } catch (error) {
      mutationError.value = httpErrorMessage(
        error,
        "Não foi possível chamar a corrida. Atualize o pedido.",
      );
      useSonner.error(mutationError.value);
      return false;
    } finally {
      busy.value = false;
    }
    useSonner.success(
      `Uma corrida para ${body.refs.length} pedidos enviada à central.`,
    );
    try {
      await refresh();
    } catch {
      mutationError.value =
        "Corrida pedida. A leitura atualizada falhou; atualize antes da próxima ação.";
    }
    return true;
  }

  // "Chamar de novo": a última chamada ficou sem resposta da TaOn. Libera a
  // chamada pendente e chama outra (a confirmação é da página).
  async function courierDispatchAgain(): Promise<boolean> {
    const ok = await act("courier-dispatch-again");
    if (ok) useSonner.success("Pedido de entregador enviado à TaOn.");
    return ok;
  }

  // O "Dispensar" do lembrete de chamar o entregador (todos os dispositivos).
  async function courierReminderDismiss(): Promise<boolean> {
    return act("courier-reminder-dismiss");
  }

  // Ouvidoria: o "Resolvido" fecha o pedido de contato com a nota do que foi feito.
  async function resolveContactRequest(note: string): Promise<boolean> {
    const ok = await act("customer-contact/resolve", { note });
    if (ok) useSonner.success("Atendimento registrado.");
    return ok;
  }

  async function courierCancel(): Promise<boolean> {
    const ok = await act("courier-cancel");
    if (ok)
      useSonner.success(
        "Cancelamento da corrida pedido. Falta a central confirmar.",
      );
    return ok;
  }

  async function courierQuote(): Promise<boolean> {
    const ok = await act("courier-quote");
    if (ok) useSonner.success("Cotação atualizada.");
    return ok;
  }

  return {
    readMetadata,
    order,
    deviceAgent,
    pending,
    error,
    refresh,
    busy,
    mutationError,
    confirm,
    advance,
    reject,
    cancel,
    fetchCancellationReasons,
    settleCash,
    equipmentBack,
    undoHandoff,
    undoReady,
    requeueFiscal,
    retryIFoodAccept,
    resendPaymentLink,
    saveNotes,
    addComment,
    courierDispatch,
    courierDispatchAgain,
    courierRide,
    courierReminderDismiss,
    resolveContactRequest,
    courierCancel,
    courierQuote,
    managerChallenge,
    authorize,
    dismissManagerChallenge,
  };
}
