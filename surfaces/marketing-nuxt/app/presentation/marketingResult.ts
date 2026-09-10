import type {
  AnnouncementProjectionV2,
  DeliveryAggregateProjectionV2,
  DeliveryCountsProjectionV2,
  MarketingActionProjectionV2,
  MarketingCommandReceipt,
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
  ["suppressed", "suprimido pela política", "quiet"],
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
        "A plataforma pode ter produzido efeito sem devolver resposta. Reconciliar só consulta; não envia outra vez.",
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

export function deliveryCountItems(counts: DeliveryCountsProjectionV2) {
  return COUNT_LABELS.flatMap(([key, singular, tone]) => {
    const count = Number(counts[key] || 0);
    if (count <= 0) return [];
    const label = count === 1 ? singular : pluralizeCountLabel(singular);
    return [{ key, count, label, tone }];
  });
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
    "suprimido pela política": "suprimidos pela política",
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
    return `Reconciliar ${formatCount(count)} ${count === 1 ? "resultado incerto" : "resultados incertos"}`;
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
      title: "Reconciliação registrada",
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
        "A versão aprovada e seu horário ficaram guardados neste comprovante.",
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
