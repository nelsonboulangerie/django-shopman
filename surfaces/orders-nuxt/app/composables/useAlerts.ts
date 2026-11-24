import { useOperatorResourceKey } from "./useOperatorResourceKey";
// Operator alerts read-side. SSE-first (ADR-016): o push do canal de alertas
// (`/sse/alerts` no BFF → backstage-alerts-main no Django) só avisa "chegou
// algo" e dispara o refetch; o fetch REST segue sendo a fonte da verdade e o
// poll de 60s vira rede de segurança em cadência calma.
//
// `scope=orders`: o sino do Gestor mostra só o que é de pedido. Infraestrutura,
// marketing e B.I. ficam no Admin, onde alguém pode agir.
import type { AlertProjection, AlertsResponse, OrderDetailResponse } from "~/types/orders";
import { useOrderIntention } from "./useOrderIntention";
import { alertMessageWithSchedule, splitRef } from "~/presentation/board";
import {
  ANSWER_FAILED,
  ANSWER_SENT,
  PROMOTE_FAILED,
  PROMOTE_LABEL,
  promotionToast,
  type PromotionResult,
  GIVE_BACK_CONFIRM,
  GIVE_BACK_FAILED,
  GIVEN_BACK,
  giveBackAction,
  TAKE_OVER_FAILED,
  TAKEN_OVER,
  TAKEN_OVER_NOTICE_NOT_SENT,
  isFinalAnswerError,
  verificationActions,
} from "~/presentation/conciergeVerification";
import { useConfirm } from "../../../operator-kit/app/composables/useConfirm";
import {
  openResilientEventSource,
  type ResilientEventSource,
} from "../../../operator-kit/app/utils/resilientEventSource";

function newAckKey(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  return (
    uuid ||
    `ack-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  );
}

export function useAlerts() {
  const config = useRuntimeConfig();
  const { data, refresh } = useFetch<AlertsResponse>(
    "/api/v1/backstage/alerts/",
    {
      key: useOperatorResourceKey("operator-alerts"),
      query: { scope: "orders" },
      server: true,
    },
  );

  const alerts = computed<AlertProjection[]>(() => data.value?.alerts ?? []);
  // Os avisos como o sino os diz: o pedido com data ou hora combinada leva a frase do
  // cartão à frente ("Encomenda · Amanhã · A partir das 15h."), para quem toca
  // "Aceitar" ler para quando está prometendo (WP-G01).
  const readableAlerts = computed<AlertProjection[]>(() =>
    alerts.value.map((alert) => ({ ...alert, message: alertMessageWithSchedule(alert) })),
  );
  const activeCount = computed(() => data.value?.counts?.active ?? 0);
  const criticalCount = computed(() => data.value?.counts?.critical ?? 0);

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: ResilientEventSource | null = null;

  function connectSse() {
    if (source) return;
    // O stream se recria sozinho, com backoff, depois do 502 de deploy (o
    // EventSource cru ficava CLOSED e o sino, só no poll de 60 s). O corpo é
    // sinal mínimo (id/tipo/severidade); quem recebe refaz o fetch. Ao reabrir,
    // refaz também: o alerta que nasceu com o push fora não veio por ele.
    source = openResilientEventSource({
      url: ssePath("/sse/alerts", config.app.baseURL),
      events: ["backstage-alerts-update"],
      onEvent: () => refresh(),
      onOpen: (reconnected) => {
        if (reconnected) refresh();
      },
    });
  }

  // Aba ou rede de volta: tenta o stream já, sem esperar o backoff.
  const onVisible = () => {
    if (document.visibilityState === "visible") source?.reconnectNow();
  };

  onMounted(() => {
    pollTimer = setInterval(() => refresh(), 60_000);
    connectSse();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    source?.close();
    source = null;
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  /** O alerta ainda não foi marcado como visto (o servidor oferece o gesto). */
  function ackAction(alert: AlertProjection) {
    return (
      alert.actions?.find(
        (action) => action.kind === "acknowledge_alert" && action.enabled,
      ) ?? null
    );
  }

  // Uma chave por alerta, mantida entre tentativas: o servidor deduplica.
  const attempts = new Map<number, string>();

  /**
   * "Visto": registra que alguém leu. O alerta continua no sino até a causa
   * acabar, porque é o sistema que confirma que ela acabou.
   *
   * O servidor só aceita o gesto que ele mesmo ofereceu na leitura atual
   * (ação, revisão e prova da projeção). Antes o corpo ia vazio e todo toque
   * caía em 400.
   */
  async function ack(alert: AlertProjection): Promise<void> {
    const action = ackAction(alert);
    const read = data.value;
    if (!action || !read?.source_revision) return;
    const key = attempts.get(alert.pk) ?? newAckKey();
    attempts.set(alert.pk, key);
    try {
      await $fetch(`/api/v1/backstage/alerts/${alert.pk}/ack/`, {
        method: "POST",
        body: {
          idempotency_key: key,
          expected_rev: action.expected_rev ?? 0,
          projection_generated_at: read.generated_at,
          source_revision: read.source_revision,
          fresh_until: read.fresh_until,
          contract_version: read.contract_version,
          action_ref: action.ref,
          action_proof: action.proof,
        },
      });
      attempts.delete(alert.pk);
      await refresh();
    } catch (error) {
      if (httpError(error).status === 409) {
        // A leitura venceu ou o alerta mudou: relê e deixa o operador tocar de novo.
        attempts.delete(alert.pk);
        await refresh();
        useSonner.error(
          "Os alertas mudaram. Confira e toque em Visto de novo.",
        );
        return;
      }
      useSonner.error(
        httpErrorMessage(
          error,
          "Não deu para marcar o alerta como visto. Tente de novo.",
        ),
      );
    }
  }

  /** O gesto que resolve ali mesmo, quando o servidor o oferece (P2-19: "Aceitar"). */
  function acceptAction(alert: AlertProjection) {
    return (
      alert.actions?.find(
        (action) => action.kind === "confirm_order" && action.enabled,
      ) ?? null
    );
  }

  const intentions = useOrderIntention();
  // Por aviso, não global: aceitar um pedido não trava o aviso de outro.
  const accepting = ref<Set<number>>(new Set());
  const confirm = useConfirm();
  const isAccepting = (pk: number) => accepting.value.has(pk);

  /**
   * "Aceitar" no aviso do pedido parado: o MESMO aceite do cartão. Relê o pedido e
   * manda a intenção canônica dele (`base_revision`, `expected_actor_id`) pela
   * rota que o aviso trouxe; o servidor revalida tudo sob trava. O aviso fecha
   * sozinho quando o pedido sai de "novo", e o painel se atualiza pelo SSE.
   */
  async function accept(alert: AlertProjection): Promise<boolean> {
    const action = acceptAction(alert);
    const ref_ = alert.order_ref;
    if (!action || !ref_ || accepting.value.has(alert.pk)) return false;
    accepting.value = new Set(accepting.value).add(alert.pk);
    try {
      const detail = await $fetch<OrderDetailResponse>(
        `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/`,
      );
      const confirm = detail.order.actions?.find((item) => item.ref === "confirm");
      if (!confirm) {
        useSonner.error(`O pedido ${splitRef(ref_).code} não espera mais aceite. Abra o pedido para conferir.`);
        return false;
      }
      await intentions.executePath(`${ref_}:confirm`, action.href, confirm, {});
      useSonner.success(`Pedido ${splitRef(ref_).code} aceito.`);
      return true;
    } catch (error) {
      const fallback = `${splitRef(ref_).code} continua novo: o Aceitar não chegou. Tente de novo.`;
      // Recusa do servidor fala pelo `detail`; a da intenção local (identificação
      // trocada, gravação anterior sem resultado) fala pela própria mensagem.
      useSonner.error(
        !httpError(error).status && error instanceof Error && error.message
          ? error.message
          : httpErrorMessage(error, fallback),
      );
      return false;
    } finally {
      const next = new Set(accepting.value);
      next.delete(alert.pk);
      accepting.value = next;
      await refresh();
    }
  }

  // "Vou verificar" da Concierge (WP-07): responder a pergunta do cliente, ou assumir a
  // conversa, no próprio cartão. Devolve a frase de erro para o cartão mostrar (o texto
  // digitado fica lá), ou `null` quando saiu; o cartão some no refresh.
  const answering = ref<Set<number>>(new Set());
  function mark(pk: number, on: boolean) {
    const next = new Set(answering.value);
    if (on) next.add(pk);
    else next.delete(pk);
    answering.value = next;
  }

  async function verificationPost(
    alert: AlertProjection,
    kind: "answer" | "takeOver",
    body: Record<string, unknown> | undefined,
    fallback: string,
  ): Promise<{ error: string | null; final: boolean; data: { warning?: string; promote_href?: string } | null }> {
    const action = verificationActions(alert)[kind];
    if (!action || answering.value.has(alert.pk)) return { error: null, final: false, data: null };
    mark(alert.pk, true);
    try {
      const data = await $fetch<{ ok: boolean; warning?: string; promote_href?: string }>(action.href, {
        method: "POST",
        body: body ?? {},
      });
      return { error: null, final: false, data };
    } catch (error) {
      // A janela de 24 horas fechou: tentar de novo não adianta, só assumir a conversa.
      const code = (httpError(error).data as { error?: { code?: string } } | null)?.error?.code;
      return { error: httpErrorMessage(error, fallback), final: isFinalAnswerError(code), data: null };
    } finally {
      mark(alert.pk, false);
      await refresh();
    }
  }

  async function answerVerification(
    alert: AlertProjection,
    text: string,
  ): Promise<{ message: string; final: boolean } | null> {
    const { error, final, data } = await verificationPost(alert, "answer", { text }, ANSWER_FAILED);
    if (!error) {
      const href = data?.promote_href;
      // A resposta enviada pode virar pergunta frequente (WP-15): o gesto vem no aviso,
      // porque o cartão fecha com a resposta.
      if (href) {
        useSonner.withAction("success", ANSWER_SENT, {
          action: { label: PROMOTE_LABEL, onClick: () => void promoteToFaq(href) },
        });
      } else {
        useSonner.success(ANSWER_SENT);
      }
      return null;
    }
    return { message: error, final };
  }

  async function promoteToFaq(href: string): Promise<PromotionResult | null> {
    try {
      const result = await $fetch<PromotionResult>(href, { method: "POST" });
      const toast = promotionToast(result);
      useSonner.withAction(toast.color, toast.title, {
        ...(toast.description ? { description: toast.description } : {}),
        ...(toast.action ? { action: toast.action } : {}),
      });
      return result;
    } catch (error) {
      useSonner.error(httpErrorMessage(error, PROMOTE_FAILED));
      return null;
    }
  }

  /** "Devolver à Concierge" (#3578): a conversa parada com a equipe volta à Concierge, e o cartão fecha. Pede
   *  confirmação antes (dono, 24/11): sem o "Devolver" do diálogo, nada é devolvido. */
  async function giveBack(alert: AlertProjection): Promise<boolean> {
    const action = giveBackAction(alert);
    if (!action?.href || accepting.value.has(alert.pk)) return false;
    if (!(await confirm({ tone: "primary", ...GIVE_BACK_CONFIRM }))) return false;
    accepting.value = new Set(accepting.value).add(alert.pk);
    try {
      await $fetch(action.href, { method: "POST", body: {} });
      useSonner.success(GIVEN_BACK);
      return true;
    } catch (error) {
      useSonner.error(httpErrorMessage(error, GIVE_BACK_FAILED));
      return false;
    } finally {
      const next = new Set(accepting.value);
      next.delete(alert.pk);
      accepting.value = next;
      await refresh();
    }
  }

  async function takeOverVerification(alert: AlertProjection): Promise<string | null> {
    const { error, data } = await verificationPost(alert, "takeOver", undefined, TAKE_OVER_FAILED);
    if (!error) useSonner.success(data?.warning ? TAKEN_OVER_NOTICE_NOT_SENT : TAKEN_OVER);
    return error;
  }

  return {
    alerts,
    readableAlerts,
    activeCount,
    criticalCount,
    refresh,
    ack,
    ackAction,
    accept,
    acceptAction,
    giveBack,
    isAccepting,
    answerVerification,
    promoteToFaq,
    takeOverVerification,
    isAnswering: (pk: number) => answering.value.has(pk),
  };
}
