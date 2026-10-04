// A fila de decisões do Marketing, em pt-BR. Funções puras sobre a projeção
// `marketing_decisions` (backstage): o servidor diz o quê e quando, aqui se
// decide como a frase fica.
//
// Duas regras do contrato do Marketing atravessam o arquivo inteiro:
// - **grandezas não se somam**: postagem pública e pessoa com mensagem direta são
//   números separados, sempre com a palavra ao lado;
// - **o incerto nunca se repete às cegas**: a linha automática diz que o sistema
//   consultou SEM reenviar, porque é exatamente isso que ele fez.
import type {
  AutomaticCheck,
  DecisionFailure,
  DecisionItem,
  DecisionReach,
  ScheduledItem,
} from "~/types/decisions";

const PLATFORM_LABELS: Record<string, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  google_business: "Google",
  whatsapp: "WhatsApp",
};

// Título curto do cartão, pela ocasião. "Lote" é a palavra da Produção para o que
// sai do forno (vocabulário da suíte, 22/09); "fornada" fica no texto do cliente.
const TRIGGER_TITLES: Record<string, string> = {
  production_finished: "Lote pronto",
  low_stock: "Estoque baixo",
  stock_back: "De volta ao estoque",
  product_created: "Produto novo",
  manual: "Disparo manual",
  schedule: "Campanha agendada",
};

export type DeadlineTone = "urgent" | "soon" | "calm" | "none";

export interface DeadlinePresentation {
  /** A linha forte: "Decide até 10:15", "Publica hoje às 17:30", "Repetir até 11:40". */
  label: string;
  /** A linha de baixo: "faltam 12 min", "decide até 17:00". Vazia quando não há. */
  detail: string;
  tone: DeadlineTone;
}

/** Abaixo disto o cartão fica em tom urgente; abaixo de uma hora, em aviso. */
export const URGENT_MINUTES = 15;
export const SOON_MINUTES = 60;

export function platformLabel(ref: string): string {
  return PLATFORM_LABELS[ref] ?? ref;
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}

export function peopleCount(value: number): string {
  return `${formatCount(value)} ${value === 1 ? "pessoa" : "pessoas"}`;
}

export function postCount(value: number): string {
  return `${formatCount(value)} ${value === 1 ? "postagem" : "postagens"}`;
}

/** "Instagram, Facebook e WhatsApp". */
export function joinPlatforms(refs: readonly string[]): string {
  const labels = refs.map(platformLabel);
  if (labels.length <= 1) return labels[0] ?? "";
  return `${labels.slice(0, -1).join(", ")} e ${labels.at(-1)}`;
}

/**
 * Para onde vai, na grandeza certa: "Instagram, Facebook e WhatsApp (86 pessoas)".
 * O número entre parênteses só aparece quando há mensagem direta, e só fala de
 * pessoas: as postagens já estão contadas pelos nomes das plataformas (uma cada).
 */
export function destinationsLine(
  refs: readonly string[],
  reach: DecisionReach,
): string {
  const platforms = joinPlatforms(refs);
  if (!platforms) return "Sem plataforma escolhida";
  return reach.people > 0
    ? `${platforms} (${peopleCount(reach.people)})`
    : platforms;
}

/** "2 postagens · 86 pessoas": as duas grandezas lado a lado, nunca somadas. */
export function reachLine(reach: DecisionReach): string {
  const parts: string[] = [];
  if (reach.posts > 0) parts.push(postCount(reach.posts));
  if (reach.people > 0) parts.push(peopleCount(reach.people));
  return parts.join(" · ");
}

export function decisionTitle(item: DecisionItem | ScheduledItem): string {
  const occasion = TRIGGER_TITLES[item.trigger] ?? "";
  if (occasion && item.product_name) return `${occasion}: ${item.product_name}`;
  return item.campaign_name || occasion || "Anúncio avulso";
}

/** O que o cartão de falha diz no título: onde falhou e quanto, na grandeza dela. */
export function failureHeadline(item: DecisionItem): string {
  const where = joinPlatforms(item.failures.map((failure) => failure.platform_ref));
  const amount = reachLine(item.reach);
  const head =
    item.kind === "reconcile_unknown"
      ? `Resultado incerto no ${where}`
      : `Falhou no ${where}`;
  return amount ? `${head} · ${amount}` : head;
}

// O motivo, escrito para quem decide se repete. Os códigos vêm do provedor de
// cada plataforma e são muitos; o que muda a decisão é a FAMÍLIA do motivo, e é
// por ela que a frase se escolhe. Código desconhecido não vira texto inventado:
// cai na frase geral, que diz o que é certo sobre toda falha repetível.
const REASON_RULES: ReadonlyArray<readonly [RegExp, string]> = [
  [/subscriber_busy/, "O contato estava recebendo outra mensagem. Repetir é seguro."],
  [/consent_unavailable/, "O consentimento não pôde ser conferido na hora do envio."],
  [/rate_limit|throttl|quota/, "A plataforma pediu para esperar antes de mais envios."],
  [/oauth|token|auth/, "A plataforma recusou o acesso. Confira a conexão em Plataformas antes de repetir."],
  [/transport|timeout|network|unavailable/, "A conexão com a plataforma caiu antes do envio. Nada foi disparado."],
  [/response_invalid|invalid_response/, "A plataforma respondeu algo que não deu para ler. Nada foi disparado."],
];

export function failureReason(failure: DecisionFailure, kind: DecisionItem["kind"]): string {
  if (kind === "reconcile_unknown") {
    return "O sistema já consultou sem reenviar e a plataforma não soube dizer se o disparo chegou. Consultar de novo também não reenvia.";
  }
  const code = failure.reason_code;
  for (const [pattern, text] of REASON_RULES) {
    if (pattern.test(code)) return text;
  }
  return "A plataforma não aceitou agora, por um motivo que permite repetir só para quem não recebeu.";
}

function zonedParts(ms: number, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(ms));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return {
    day: `${get("year")}-${get("month")}-${get("day")}`,
    dayMonth: `${get("day")}/${get("month")}`,
    time: `${get("hour")}:${get("minute")}`,
  };
}

/** "10:15" se for hoje; "amanhã, 08:00"; "05/10, 08:00" depois disso. */
export function clockLabel(instant: string, timeZone: string, nowMs = Date.now()): string {
  const ms = Date.parse(instant);
  if (!Number.isFinite(ms)) return "";
  const at = zonedParts(ms, timeZone);
  const today = zonedParts(nowMs, timeZone);
  if (at.day === today.day) return at.time;
  if (at.day === zonedParts(nowMs + 86_400_000, timeZone).day) return `amanhã, ${at.time}`;
  return `${at.dayMonth}, ${at.time}`;
}

/** Quando algo JÁ aconteceu: "às 09:58", "ontem às 18:10", "em 01/10 às 08:00". */
export function pastAtLabel(instant: string, timeZone: string, nowMs = Date.now()): string {
  const ms = Date.parse(instant);
  if (!Number.isFinite(ms)) return "";
  const at = zonedParts(ms, timeZone);
  if (at.day === zonedParts(nowMs, timeZone).day) return `às ${at.time}`;
  if (at.day === zonedParts(nowMs - 86_400_000, timeZone).day) return `ontem às ${at.time}`;
  return `em ${at.dayMonth} às ${at.time}`;
}

const MESSAGE_PLATFORMS = new Set(["whatsapp"]);

/**
 * O verbo do que acontece na hora marcada, pelo vocabulário fechado da casa:
 * mensagem se ENVIA, postagem se PUBLICA, e as duas juntas se DISPARAM. "Sair"
 * não é ato do sistema (trava em `tests/operatorLanguage.test.ts`).
 */
export function departureVerb(refs: readonly string[]): "Envia" | "Publica" | "Dispara" {
  const messages = refs.some((ref) => MESSAGE_PLATFORMS.has(ref));
  const posts = refs.some((ref) => !MESSAGE_PLATFORMS.has(ref));
  if (messages && posts) return "Dispara";
  return messages ? "Envia" : "Publica";
}

/** "Publica hoje às 17:30", "Envia amanhã às 08:00", "Dispara 05/10 às 08:00". */
export function departureLabel(
  instant: string,
  refs: readonly string[],
  timeZone: string,
  nowMs = Date.now(),
): string {
  const ms = Date.parse(instant);
  if (!Number.isFinite(ms)) return "";
  const verb = departureVerb(refs);
  const at = zonedParts(ms, timeZone);
  const today = zonedParts(nowMs, timeZone);
  if (at.day === today.day) return `${verb} hoje às ${at.time}`;
  if (at.day === zonedParts(nowMs + 86_400_000, timeZone).day) return `${verb} amanhã às ${at.time}`;
  return `${verb} ${at.dayMonth} às ${at.time}`;
}

export function remainingLabel(instant: string, nowMs = Date.now()): string {
  const remaining = Date.parse(instant) - nowMs;
  if (!Number.isFinite(remaining)) return "";
  if (remaining <= 0) return "o prazo acabou";
  const minutes = Math.ceil(remaining / 60_000);
  if (minutes < 60) return `faltam ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `faltam ${hours} h ${rest} min` : `faltam ${hours} h`;
}

export function deadlineTone(instant: string | null, nowMs = Date.now()): DeadlineTone {
  if (!instant) return "none";
  const minutes = (Date.parse(instant) - nowMs) / 60_000;
  if (!Number.isFinite(minutes)) return "none";
  if (minutes <= URGENT_MINUTES) return "urgent";
  if (minutes <= SOON_MINUTES) return "soon";
  return "calm";
}

export function deadlinePresentation(
  item: DecisionItem,
  timeZone: string,
  nowMs = Date.now(),
): DeadlinePresentation {
  const tone = deadlineTone(item.deadline_at, nowMs);
  if (item.kind === "review") {
    if (item.scheduled_for) {
      return {
        label: departureLabel(item.scheduled_for, item.platform_refs, timeZone, nowMs),
        detail: item.deadline_at
          ? `decide até ${clockLabel(item.deadline_at, timeZone, nowMs)}`
          : "sem prazo para decidir",
        tone,
      };
    }
    if (item.deadline_at) {
      return {
        label: `Decide até ${clockLabel(item.deadline_at, timeZone, nowMs)}`,
        detail: remainingLabel(item.deadline_at, nowMs),
        tone,
      };
    }
    return { label: "Sem prazo para decidir", detail: "", tone };
  }
  if (item.kind === "retry_failed") {
    if (item.deadline_at) {
      return {
        label: `Repetir até ${clockLabel(item.deadline_at, timeZone, nowMs)}`,
        detail: "depois disso o anúncio vence",
        tone,
      };
    }
    return { label: "Repetir quando quiser", detail: "o anúncio não tem prazo", tone };
  }
  return { label: "Sem prazo", detail: "nada é reenviado sem você", tone };
}

/** O cabeçalho da fila: quantas decisões, e em que ordem estão. */
export function queueHeadline(count: number): { strong: string; rest: string } {
  if (count === 0) return { strong: "Nada pede você agora", rest: "" };
  return {
    strong: count === 1 ? "1 pede você" : `${formatCount(count)} pedem você`,
    rest: count === 1 ? "" : "o prazo mais curto primeiro",
  };
}

/** O cabeçalho dos Agendados. */
export function scheduledHeadline(count: number): string {
  if (count === 0) return "Nada aprovado esperando a hora marcada.";
  if (count === 1) return "1 anúncio aprovado espera a hora marcada.";
  return `${formatCount(count)} anúncios aprovados esperam a hora marcada, o mais próximo primeiro.`;
}

/**
 * A mesma linha em duas partes, para o desenho da v4 (`marketing-decisoes4.html`): o
 * número forte ("+2") e o resto em tom calmo. Sem agendado hoje não há número forte.
 */
export function scheduledSummaryParts(
  scheduledToday: number,
  activeCampaigns: number,
): { lead: string; rest: string } {
  const full = scheduledSummary(scheduledToday, activeCampaigns);
  if (scheduledToday === 0) return { lead: "", rest: full };
  const lead = `+${formatCount(scheduledToday)}`;
  return { lead, rest: full.slice(lead.length + 1) };
}

/** A linha do rodapé da fila: "+2 agendados hoje · 3 campanhas ligadas". */
export function scheduledSummary(scheduledToday: number, activeCampaigns: number): string {
  const scheduled =
    scheduledToday === 0
      ? "Nenhum agendado hoje"
      : `+${formatCount(scheduledToday)} ${scheduledToday === 1 ? "agendado" : "agendados"} hoje`;
  const campaigns =
    activeCampaigns === 0
      ? "nenhuma campanha ligada"
      : `${formatCount(activeCampaigns)} ${activeCampaigns === 1 ? "campanha ligada" : "campanhas ligadas"}`;
  return `${scheduled} · ${campaigns}`;
}

/**
 * A linha do resultado incerto que o sistema confere sozinho (decisão do dono,
 * 03/10/2026). O fim "automático" diz quem fez; "sem reenviar" diz o que NÃO fez.
 */
export function automaticCheckLine(
  check: AutomaticCheck,
  timeZone: string,
  nowMs = Date.now(),
): { title: string; detail: string } {
  const title = `${platformLabel(check.platform_ref)}: resultado incerto.`;
  const at = check.checked_at ? ` ${pastAtLabel(check.checked_at, timeZone, nowMs)}` : "";
  const isMessage = check.delivery_kind === "direct_message";
  const amount =
    check.target_count > 1
      ? ` (${isMessage ? peopleCount(check.target_count) : postCount(check.target_count)})`
      : "";
  switch (check.state) {
    case "checking":
      return {
        title,
        detail: `O sistema está consultando sem reenviar${amount} · automático`,
      };
    case "confirmed":
      return {
        title,
        detail: `O sistema consultou sem reenviar: ${isMessage ? "entregue" : "publicado"}${at}${amount} · automático`,
      };
    case "accepted":
      return {
        title,
        detail: `O sistema consultou sem reenviar: a plataforma aceitou, ainda sem confirmar${amount} · automático`,
      };
    case "failed":
      return {
        title,
        detail: `O sistema consultou sem reenviar: ${isMessage ? "não foi entregue" : "não foi publicado"}${amount} · automático`,
      };
    default:
      return {
        title,
        detail: `O sistema consultou sem reenviar e a plataforma não soube dizer${amount} · automático`,
      };
  }
}
