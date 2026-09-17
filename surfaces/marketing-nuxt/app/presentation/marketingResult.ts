import type {
  AnnouncementProjectionV2,
  DeliveryAggregateProjectionV2,
  DeliveryCountsProjectionV2,
  MarketingActionProjectionV2,
  MarketingCommandReceipt,
  PlatformDeliveryProjectionV2,
} from "~/types/campaign";
import { formatCount } from "~/presentation/campaign";

export type ResultTone = "ok" | "attention" | "danger" | "quiet";

const PLATFORM_LABELS: Record<string, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  google_business: "Google",
  whatsapp: "WhatsApp",
};

const COUNT_LABELS: ReadonlyArray<
  readonly [keyof DeliveryCountsProjectionV2, string, ResultTone]
> = [
  ["confirmed", "entrega confirmada", "ok"],
  [
    "accepted",
    "aceito pelo provedor; entrega ainda não confirmada",
    "attention",
  ],
  ["sending", "em envio", "quiet"],
  ["queued", "na fila", "quiet"],
  ["planned", "planejado", "quiet"],
  ["failed_retryable", "falha que pode ser tentada novamente", "danger"],
  ["failed_final", "falha final", "danger"],
  ["unknown", "resultado incerto", "attention"],
  ["suppressed", "não enviado por uma regra de proteção", "quiet"],
  ["cancelled", "cancelado antes do envio", "quiet"],
  ["expired", "expirado antes do envio", "quiet"],
];

export function platformResultLabel(platformRef: string): string {
  return PLATFORM_LABELS[platformRef] ?? platformRef;
}

export function deliveryStatePresentation(
  state: DeliveryAggregateProjectionV2["state"],
  announcementState?: AnnouncementProjectionV2["state"],
): { label: string; detail: string; tone: ResultTone; icon: string } {
  if (announcementState === "rejected") {
    return {
      label: "Anúncio recusado",
      detail:
        "A decisão foi encerrada sem criar entregas para nenhuma plataforma.",
      tone: "quiet",
      icon: "lucide:circle-x",
    };
  }
  if (announcementState === "expired" && state === "not_started") {
    return {
      label: "Prazo de revisão encerrado",
      detail: "O anúncio expirou sem aprovação e não foi enviado.",
      tone: "attention",
      icon: "lucide:timer-off",
    };
  }
  const values: Record<
    DeliveryAggregateProjectionV2["state"],
    {
      label: string;
      detail: string;
      tone: ResultTone;
      icon: string;
    }
  > = {
    not_started: {
      label: "A entrega ainda não começou",
      detail:
        "Enquanto nenhuma faixa iniciar, o cancelamento ainda pode ser possível.",
      tone: "quiet",
      icon: "lucide:clock-3",
    },
    fanout_pending: {
      label: "Preparando os destinos",
      detail: "O público está sendo transformado em entregas rastreáveis.",
      tone: "quiet",
      icon: "lucide:loader-circle",
    },
    delivering: {
      label: "Entrega em andamento",
      detail:
        "Os números abaixo se atualizam conforme cada plataforma responde.",
      tone: "quiet",
      icon: "lucide:send",
    },
    succeeded: {
      label: "Entrega concluída",
      detail:
        "Confira abaixo o que foi confirmado e o que só foi aceito pela plataforma.",
      tone: "ok",
      icon: "lucide:check-circle-2",
    },
    completed_with_failures: {
      label: "Entrega parcial — precisa de atenção",
      detail:
        "Parte saiu e parte falhou. O sucesso de uma plataforma não esconde as outras.",
      tone: "danger",
      icon: "lucide:triangle-alert",
    },
    unknown: {
      label: "Há resultados incertos — não reenvie",
      detail:
        "A plataforma pode ter produzido efeito sem devolver resposta. Consultar só verifica o resultado; não envia outra vez.",
      tone: "attention",
      icon: "lucide:circle-help",
    },
    cancelled: {
      label: "Entrega cancelada",
      detail:
        "As faixas que ainda não tinham começado foram preservadas sem envio.",
      tone: "quiet",
      icon: "lucide:circle-slash",
    },
    expired: {
      label: "Entrega expirada",
      detail: "O prazo venceu antes de todos os destinos iniciarem.",
      tone: "attention",
      icon: "lucide:timer-off",
    },
    legacy_untracked: {
      label: "Resultado antigo sem rastreamento completo",
      detail:
        "Este anúncio é anterior ao ledger por destino; não inferimos sucesso sem prova.",
      tone: "attention",
      icon: "lucide:archive",
    },
  };
  return values[state];
}

/**
 * A plataforma está desligada pela flag do ambiente (`platform_switched_off` na
 * prontidão). O adapter existe; quem opera escolheu não ligar. Os destinos dela
 * não somem nem falham: ficam na fila, sem envio, até alguém ligar.
 */
export function platformSwitchedOff(
  announcement: Pick<AnnouncementProjectionV2, "readiness">,
  platformRef: string,
): boolean {
  return (announcement.readiness?.platforms ?? []).some(
    (item) =>
      item.platform_ref === platformRef &&
      item.reason_code === "platform_switched_off",
  );
}

export function deliveryCountItems(
  counts: DeliveryCountsProjectionV2,
  options: { platformSwitchedOff?: boolean } = {},
) {
  return COUNT_LABELS.flatMap(([key, singular, tone]) => {
    const count = Number(counts[key] || 0);
    if (count <= 0) return [];
    if (key === "queued" && options.platformSwitchedOff) {
      // "na fila" sozinho sugere que a vez vai chegar; com a plataforma
      // desligada, não chega enquanto ninguém ligar.
      return [
        {
          key,
          count,
          label: "aguardando a plataforma ligar",
          tone: "attention" as ResultTone,
        },
      ];
    }
    const label = count === 1 ? singular : pluralizeCountLabel(singular);
    return [{ key, count, label, tone }];
  });
}

/** Rótulo do estado de uma plataforma no resultado, ciente da plataforma desligada. */
export function platformDeliveryLabel(
  platform: Pick<PlatformDeliveryProjectionV2, "state" | "counts">,
  switchedOff: boolean,
): string {
  if (switchedOff && Number(platform.counts.queued || 0) > 0) {
    return "Aguardando a plataforma ligar";
  }
  return deliveryStatePresentation(platform.state).label;
}

export function platformSwitchedOffNote(platformRef: string): string {
  return `${platformResultLabel(platformRef)} está desligado neste ambiente: os destinos na fila só podem sair depois que a operação ligar a plataforma.`;
}

function pluralizeCountLabel(label: string): string {
  const exact: Record<string, string> = {
    "entrega confirmada": "entregas confirmadas",
    "aceito pelo provedor; entrega ainda não confirmada":
      "aceitos pelo provedor; entregas ainda não confirmadas",
    "em envio": "em envio",
    "na fila": "na fila",
    planejado: "planejados",
    "falha que pode ser tentada novamente":
      "falhas que podem ser tentadas novamente",
    "falha final": "falhas finais",
    "resultado incerto": "resultados incertos",
    "não enviado por uma regra de proteção":
      "não enviados por uma regra de proteção",
    "cancelado antes do envio": "cancelados antes do envio",
    "expirado antes do envio": "expirados antes do envio",
  };
  return exact[label] ?? label;
}

export function recoveryActionLabel(
  action: MarketingActionProjectionV2,
): string {
  const count = action.eligible_count;
  if (action.kind === "retry_failed_delivery") {
    return `Tentar novamente ${formatCount(count)} ${count === 1 ? "falha" : "falhas"}`;
  }
  if (action.kind === "reconcile_unknown_delivery") {
    return `Consultar ${formatCount(count)} ${count === 1 ? "resultado incerto" : "resultados incertos"}`;
  }
  if (action.kind === "cancel_announcement") {
    return "Cancelar o que ainda não começou";
  }
  return action.label;
}

export function recoveryActionExplanation(
  action: MarketingActionProjectionV2,
): string {
  if (action.kind === "retry_failed_delivery") {
    return "Só as falhas marcadas como recuperáveis entram de novo. Aceitos, confirmados e incertos não são reenviados.";
  }
  if (action.kind === "reconcile_unknown_delivery") {
    return "Consulta o provedor para esclarecer o resultado. Esta ação não reenvia mensagem nem publicação.";
  }
  if (action.kind === "cancel_announcement") {
    return "Cancela somente faixas que ainda não começaram. Uma entrega iniciada nunca é apresentada como desfeita.";
  }
  return "A consequência será revalidada pelo servidor antes de confirmar.";
}

export function recoveryDisabledReason(reason: string): string {
  const reasons: Record<string, string> = {
    missing_capability:
      "Seu perfil pode ver o resultado, mas não autoriza esta recuperação.",
    marketing_frozen:
      "Marketing está congelado; nenhum novo efeito externo pode começar.",
    dispatch_already_started:
      "A entrega já começou; cancelá-la agora poderia prometer um efeito que não existe.",
    reconciliation_pending: "A consulta ao provedor já está em andamento.",
    unknown_not_reconcilable:
      "Este provedor não oferece consulta segura para esse resultado.",
    command_not_available:
      "Esta recuperação não está disponível no estado atual.",
  };
  return (
    reasons[reason] ??
    "O estado ou sua autorização mudou. Atualize o resultado."
  );
}

/**
 * Aprovação feita no ensaio do WhatsApp. Fora do ensaio, campanha geral por WhatsApp
 * exige o mínimo de pessoas elegíveis configurado no Admin (impede mirar uma pessoa);
 * no ensaio quem recebe já é só a lista de canário da operação, e o comprovante
 * registra `canary=true` com o `minimum_count` que não valeu. O número vem do
 * comprovante — a tela não carrega um mínimo próprio para não mentir quando a loja o
 * muda. Comprovante antigo, sem o número, recebe a frase sem número.
 */
export function approvalCanaryNote(receipt: MarketingCommandReceipt): string {
  if (receipt.kind !== "approve" || receipt.outcome.canary !== true) return "";
  const minimum = receipt.outcome.minimum_count;
  const skipped =
    typeof minimum === "number" && Number.isInteger(minimum) && minimum > 0
      ? `o mínimo de ${minimum} não vale`
      : "o mínimo de público não vale";
  return `Ensaio: ${skipped}; só a lista de canário recebe.`;
}

export function commandReceiptPresentation(receipt: MarketingCommandReceipt): {
  title: string;
  detail: string;
} {
  const count = receiptOutcomeCount(receipt);
  if (receipt.kind === "retry_delivery") {
    return {
      title: "Nova tentativa registrada",
      detail: `${formatCount(count)} ${count === 1 ? "falha voltou" : "falhas voltaram"} para a fila; nenhum destino aceito, confirmado ou incerto foi repetido.`,
    };
  }
  if (receipt.kind === "reconcile_delivery") {
    return {
      title: "Consulta registrada",
      detail: `${formatCount(count)} ${count === 1 ? "consulta foi aberta" : "consultas foram abertas"}; nenhuma mensagem foi reenviada.`,
    };
  }
  if (receipt.kind === "cancel") {
    return {
      title: "Cancelamento registrado",
      detail: `${formatCount(count)} ${count === 1 ? "faixa que não tinha começado foi cancelada" : "faixas que não tinham começado foram canceladas"}.`,
    };
  }
  if (receipt.kind === "approve") {
    return {
      title: "Decisão registrada",
      detail:
        "A versão aprovada, o público selado, as plataformas e o horário podem ser conferidos abaixo.",
    };
  }
  if (receipt.kind === "reject") {
    return {
      title: "Recusa registrada",
      detail: "O anúncio não foi enviado a nenhuma plataforma.",
    };
  }
  if (receipt.kind === "reschedule") {
    return {
      title: "Novo horário registrado",
      detail:
        "As faixas ainda não iniciadas usam o instante guardado neste comprovante.",
    };
  }
  return {
    title: "Comando registrado",
    detail: "O comprovante abaixo é a prova persistida desta operação.",
  };
}

export function receiptStateLabel(state: string): string {
  const labels: Record<string, string> = {
    accepted: "aceito",
    cancelled: "cancelado",
    completed: "concluído",
    conflict: "conflito",
    expired: "expirado",
    failed: "falhou",
    pending: "pendente",
    rejected: "recusado",
    succeeded: "concluído",
    unknown: "resultado incerto",
  };
  return labels[state] ?? "registrado";
}

function receiptOutcomeCount(receipt: MarketingCommandReceipt): number {
  const keys = [
    "queued_count",
    "lookup_count",
    "outbox_cancelled",
    "cancelled_count",
  ];
  for (const key of keys) {
    const value = receipt.outcome[key];
    if (typeof value === "number" && Number.isFinite(value) && value >= 0)
      return value;
  }
  return 0;
}

export function marketingLoadError(error: unknown): {
  title: string;
  detail: string;
  canRetry: boolean;
} {
  const status = errorStatus(error);
  if (status === 401) {
    return {
      title: "Sua sessão terminou",
      detail:
        "Entre novamente; o rascunho e o comprovante desta rota continuam preservados.",
      canRetry: false,
    };
  }
  if (status === 403) {
    return {
      title: "Você não tem acesso a este resultado",
      detail:
        "Entrar novamente não amplia sua autorização. Peça acesso ao responsável pelo Marketing.",
      canRetry: false,
    };
  }
  if (status === 404) {
    return {
      title: "Este anúncio não existe",
      detail:
        "O endereço pode estar incorreto ou o registro pode ter sido removido conforme a política de retenção.",
      canRetry: false,
    };
  }
  if (status === 429) {
    return {
      title: "Muitas consultas em pouco tempo",
      detail:
        "Aguarde o prazo indicado pelo servidor e tente novamente; nenhuma ação foi repetida.",
      canRetry: true,
    };
  }
  return {
    title: "Não foi possível carregar o resultado",
    detail:
      "Pode ser uma interrupção de rede ou do serviço. O app não transforma essa falha em lista vazia.",
    canRetry: true,
  };
}

function errorStatus(error: unknown): number {
  if (typeof error !== "object" || error === null) return 0;
  const value = error as {
    status?: number;
    statusCode?: number;
    response?: { status?: number };
  };
  return Number(
    value.statusCode || value.status || value.response?.status || 0,
  );
}

/** WhatsApp é mensagem direta; o resto do catálogo é publicação pública. */
const DIRECT_MESSAGE_PLATFORM = "whatsapp";

/**
 * A linha que explica por que o gestor caiu direto na revisão.
 *
 * O disparo leva a tela até aqui sem escala. Quem chega precisa saber, numa frase, que
 * este anúncio nasceu do toque que ele acabou de dar e que NADA saiu ainda — a mesma
 * promessa que antes vivia no painel de sucesso do disparo.
 *
 * Publicação pública conta destinos por plataforma; mensagem direta conta pessoas.
 * Misturar os dois números diria ao gestor que o mural tem público de gente.
 */
export function announcementDispatchNotice(input: {
  platforms: string[];
  audienceCount: number;
  replayed: boolean;
}): { title: string; detail: string; replayNote: string } {
  const platforms = (input.platforms ?? []).filter(Boolean);
  const publicPlatforms = platforms.filter(
    (platform) => platform !== DIRECT_MESSAGE_PLATFORM,
  );
  const publicOnly =
    platforms.length > 0 && publicPlatforms.length === platforms.length;
  const audienceCount = Math.max(0, Math.trunc(input.audienceCount || 0));
  const detail = publicOnly
    ? `${formatCount(publicPlatforms.length)} ${
        publicPlatforms.length === 1
          ? "postagem pública preparada"
          : "postagens públicas preparadas"
      }. Nada foi publicado ainda.`
    : `${formatCount(audienceCount)} ${
        audienceCount === 1 ? "pessoa elegível" : "pessoas elegíveis"
      }. Nenhuma publicação ou mensagem foi enviada.`;
  return {
    title: "Este anúncio acabou de ser criado pelo seu disparo",
    detail,
    replayNote: input.replayed
      ? "Este é o mesmo resultado do toque anterior; nenhum anúncio foi duplicado."
      : "",
  };
}

/**
 * O que acabou de acontecer, dito em estado — não em toast que some.
 *
 * A entrega é assíncrona: no instante da decisão nada foi entregue, e prometer entrega
 * seria inventar. Verdade é que a decisão foi registrada e a entrega entrou na fila; a
 * confirmação vem depois, no quadro de resultado.
 */
export function decisionOutcomeNotice(input: {
  action: "approve" | "reject";
  publishMode?: "now" | "scheduled";
  includesDirectMessage: boolean;
  includesPublicPublication: boolean;
  scheduledSummary?: string;
}): { title: string; detail: string; tone: ResultTone; icon: string } {
  if (input.action === "reject") {
    return {
      title: "Anúncio recusado",
      detail:
        "Nada foi enviado a nenhuma plataforma e ele não volta para a fila de revisão.",
      tone: "quiet",
      icon: "lucide:circle-slash",
    };
  }
  if (input.publishMode === "scheduled") {
    const when = (input.scheduledSummary || "").trim();
    return {
      title: when ? `Agendado para ${when}` : "Agendado",
      detail:
        "Nada sai antes desse horário. O resultado por plataforma aparece abaixo quando a entrega começar.",
      tone: "quiet",
      icon: "lucide:calendar-clock",
    };
  }
  if (input.includesDirectMessage && input.includesPublicPublication) {
    return {
      title: "Entrega autorizada agora",
      detail:
        "As mensagens e a publicação entraram na fila de entrega. Cada confirmação chega depois e aparece em “Resultado da entrega”, abaixo.",
      tone: "ok",
      icon: "lucide:send",
    };
  }
  if (input.includesDirectMessage) {
    return {
      title: "Envio autorizado agora",
      detail:
        "As mensagens entraram na fila de entrega. A confirmação de cada uma chega depois e aparece em “Resultado da entrega”, abaixo.",
      tone: "ok",
      icon: "lucide:send",
    };
  }
  return {
    title: "Publicação autorizada agora",
    detail:
      "A publicação entrou na fila. A confirmação da plataforma chega depois e aparece em “Resultado da entrega”, abaixo.",
    tone: "ok",
    icon: "lucide:megaphone",
  };
}

/**
 * Enquanto a entrega está nestes estados, o quadro de resultado ainda não responde
 * nada sobre o que saiu: perguntar de novo, daqui a pouco, é o único caminho honesto.
 */
const UNSETTLED_DELIVERY_STATES: ReadonlySet<string> = new Set([
  "not_started",
  "fanout_pending",
  "delivering",
]);

/**
 * O teto do acompanhamento, declarado num lugar só.
 *
 * Sem SSE de marketing, a tela pergunta de novo — mas com fim. Seis perguntas, espera
 * dobrando até o teto de 8s: cerca de meio minuto de paciência, e depois a tela admite
 * que não sabe em vez de ficar batendo no servidor para sempre.
 */
export const DELIVERY_TRACKING_POLICY = {
  attempts: 6,
  baseDelayMs: 1_500,
  capMs: 8_000,
} as const;

/** Quanto tempo de espera o acompanhamento consome, no pior caso (sem contar a rede). */
export function deliveryTrackingCeilingMs(
  policy: {
    attempts: number;
    baseDelayMs: number;
    capMs: number;
  } = DELIVERY_TRACKING_POLICY,
): number {
  let total = 0;
  for (let attempt = 1; attempt < policy.attempts; attempt++) {
    total += Math.min(policy.capMs, policy.baseDelayMs * 2 ** (attempt - 1));
  }
  return total;
}

/** O resultado já assentou? Envelope ausente NUNCA conta como assentado. */
export function deliverySettled(
  delivery: Pick<DeliveryAggregateProjectionV2, "state"> | null | undefined,
): boolean {
  if (!delivery) return false;
  return !UNSETTLED_DELIVERY_STATES.has(delivery.state);
}

/**
 * "aceito pelo provedor; entrega ainda não confirmada" é correto e inútil sozinho: o
 * gestor lê e não sabe o que fazer com isso. A frase abaixo diz o que o estado
 * significa na prática, de onde vem a confirmação e por que reenviar seria pior que
 * esperar.
 */
export function acceptedAwaitingConfirmationNote(count: number): string {
  const total = Math.max(0, Math.trunc(count || 0));
  if (total <= 0) return "";
  const subject =
    total === 1
      ? "Uma entrega foi aceita pelo provedor"
      : `${formatCount(total)} entregas foram aceitas pelo provedor`;
  return `${subject}: ele recebeu e assumiu a entrega, e a confirmação de que chegou à pessoa vem depois, dele mesmo — quando chegar, aparece neste mesmo quadro, sem você fazer nada. Até lá não reenvie: o reenvio duplicaria a mensagem em vez de apressá-la.`;
}
