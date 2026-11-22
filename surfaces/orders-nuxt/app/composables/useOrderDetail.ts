import { useReadMetadata } from "./useReadMetadata";
import { coalesceRefresh } from "../utils/coalesceRefresh";
import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { useOrderIntention } from "./useOrderIntention";
import { useDanfePrint } from "./useDanfePrint";
import { SENT_SENTENCE } from "~/presentation/customerNotice";
import {
  httpError,
  isForbiddenError,
} from "../../../operator-kit/app/utils/httpError";
// Order detail read-side. Reads the expanded operator projection (items, timeline,
// notes, fiscal links) and exposes the full action set. Writes go through the django
// proxy and reconcile via refresh. Mirrors useOrdersBoard's in-flight guard.
import type {
  CourierBlock,
  OperatorOrderProjection,
  OrderDetailResponse,
} from "~/types/orders";
import type { Action } from "~/generated/ordersContract";
import { deliveryServiceName } from "../../../operator-kit/app/presentation/deliveryService";

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

  // A impressora desta estação, a mesma que o painel recebe (a Via Pedido sai por ela).
  const deviceAgent = computed(() => data.value?.device_agent ?? null);

  // ── Por que a leitura falhou ───────────────────────────────────────────────
  //
  // Três recusas liam a mesma frase ("Pedido não encontrado ou falha ao carregar"):
  // a conta que não abre o detalhe (403 de permissão: quem só expede chega aqui pelo
  // sino), o pedido que não existe (404) e a rede. A tela diz qual foi (P1-20).
  const forbidden = computed(
    () => Boolean(error.value) && isForbiddenError(error.value),
  );
  const notFound = computed(
    () => Boolean(error.value) && httpError(error.value).status === 404,
  );

  // A DANFE no detalhe (P1-14): o MESMO gesto do cartão do painel, que pede ao
  // servidor a impressão (ou reimpressão) pela impressora do despacho.
  const danfe = useDanfePrint(deviceAgent, () => refresh());
  const printDanfe = () => danfe.printDanfe(orderRef);
  const danfePrinting = computed(() => danfe.isPrinting(orderRef));

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
  const managerChallenge = ref<{
    code: string;
    message: string;
    /** O ato que pediu a assinatura: o diálogo do PIN nomeia o que o gerente assina. */
    action: string;
  } | null>(null);
  let lastAttempt: {
    action: string;
    body?: Record<string, unknown>;
    contract?: Action;
  } | null = null;

  async function act(
    action: string,
    body?: Record<string, unknown>,
    approval?: Record<string, string>,
    /** A ação que vem da prévia do gesto, não do detalhe (a devolução, o não retirado). */
    contract?: Action,
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
          "courier-back",
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
          "return",
          "no-show",
          "refund-retry",
          "customer-notice",
        ].includes(action)
      ) {
        await intentions.execute(
          orderRef,
          action,
          contract ?? order.value?.actions?.find((item) => item.ref === action),
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
        lastAttempt = { action, body, contract };
        managerChallenge.value = {
          action,
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
    return act(lastAttempt.action, lastAttempt.body, approval, lastAttempt.contract);
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
  // "Entregador voltou": o MESMO gesto do cartão, que fecha a saída inteira
  // (entrega, dinheiro, troco e maquininha).
  const courierBack = () => act("courier-back");
  // Desfazer o que ainda está na janela (a saída tocada; o pronto da Cozinha).
  const undoHandoff = () => act("undo-handoff");
  const undoReady = () => act("undo-ready");
  // Recusar e cancelar: a chave da lista única de motivos (`reason_key`, em qualquer
  // canal; no iFood o código dele sai da chave, no servidor) e a observação interna.
  const reject = (choice: { reasonKey: string; internalNote: string }) =>
    act("reject", { reason_key: choice.reasonKey, internal_note: choice.internalNote });
  const cancel = (choice: { reasonKey: string; internalNote: string }) =>
    act("cancel", { reason_key: choice.reasonKey, internal_note: choice.internalNote });
  // Devolução depois da venda (WP-G12): itens, quantidade e motivo, com a ação
  // da prévia (`return/preview/`). O PIN do gerente vem pelo desafio de sempre.
  const returnOrder = (
    choice: { items: { line_id: string; qty: string }[]; reason: string },
    contract: Action,
  ) => act("return", { items: choice.items, reason: choice.reason }, undefined, contract);
  // Não retirado (WP-G11): não há o que escolher, o destino de cada linha é do
  // servidor. A ação é a da prévia (`no-show/preview/`), com a base que o comando
  // confere; a do detalhe só diz se a porta existe. O PIN vem pelo desafio de sempre.
  const markNotPickedUp = (contract: Action) =>
    act("no-show", undefined, undefined, contract);
  // Tentar o estorno de novo (WP-G13): não há o que escolher, o valor e as cobranças
  // são do servidor. A ação é a do detalhe (`refund-retry`), com a base que o comando
  // confere; o PIN vem pelo desafio de sempre. `true` diz que a TENTATIVA foi gravada:
  // se o dinheiro voltou, quem diz é o pedido relido (`cancelled_money`), e a recusa
  // do meio de pagamento chega escrita na linha da faixa.
  const retryRefund = () => act("refund-retry");
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
  // Avisar o cliente (WP-G07): o corpo vem do diálogo (o aviso, a hora nova ou os
  // itens), a base é a do detalhe. A tela diz "na fila", nunca "enviado": o recibo do
  // pedido, relido aqui, diz o que o provedor respondeu.
  async function notifyCustomer(inputs: Record<string, unknown>): Promise<boolean> {
    const ok = await act("customer-notice", inputs);
    if (ok) useSonner.success(SENT_SENTENCE);
    return ok;
  }

  async function resendPaymentLink(): Promise<boolean> {
    const ok = await act("resend-payment-link");
    if (ok) useSonner.success("Reenvio do link solicitado.");
    return ok;
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

  // Courier ride (external delivery): re-dispatch, cancel the active ride, and
  // "just quote" (stores the estimate; refresh shows it in the panel). Chamar a
  // primeira vez é o sheet único das Entregas (#2876), fora daqui.

  // O nome do serviço da corrida, como o cadastro diz ("TaOn"): as frases o usam.
  const courierService = () => deliveryServiceName((order.value?.courier as CourierBlock | null)?.service_name);

  // "Chamar de novo": a última chamada ficou sem resposta do serviço. Libera a
  // chamada pendente e chama outra (a confirmação é da página).
  async function courierDispatchAgain(): Promise<boolean> {
    const service = courierService();
    const ok = await act("courier-dispatch-again");
    if (ok) useSonner.success(`Pedido de entregador enviado à ${service}.`);
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

  /** `reasonId`: o motivo escolhido na confirmação (só depois do aceite). */
  async function courierCancel(reasonId?: number): Promise<boolean> {
    const service = courierService();
    const ok = await act(
      "courier-cancel",
      reasonId ? { reason_id: reasonId } : undefined,
    );
    if (ok) useSonner.success(`Pedido de cancelamento enviado à ${service}.`);
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
    forbidden,
    notFound,
    refresh,
    printDanfe,
    danfePrinting,
    busy,
    mutationError,
    confirm,
    advance,
    reject,
    cancel,
    returnOrder,
    markNotPickedUp,
    retryRefund,
    settleCash,
    equipmentBack,
    courierBack,
    undoHandoff,
    undoReady,
    requeueFiscal,
    retryIFoodAccept,
    resendPaymentLink,
    notifyCustomer,
    saveNotes,
    addComment,
    courierDispatchAgain,
    courierReminderDismiss,
    resolveContactRequest,
    courierCancel,
    courierQuote,
    managerChallenge,
    authorize,
    dismissManagerChallenge,
  };
}
