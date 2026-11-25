// O "vou verificar" da Concierge no sino do Gestor (WP-07): a pergunta que ela levou à
// equipe, respondida ali mesmo, ou a conversa assumida. Puro: o que o cartão mostra e
// o que cada desfecho diz. A chamada mora em `useAlerts`.
import type { OperatorInboxAnswerSpec } from "../../../operator-kit/app/composables/useSuiteChrome";
import type { AlertProjection } from "~/types/orders";

export const ANSWER_KIND = "answer_concierge_verification";
export const TAKE_OVER_KIND = "take_over_conversation";
/** O mesmo teto do servidor (``verification.MAX_ANSWER_CHARS``). */
export const ANSWER_MAX_LENGTH = 300;

export const ANSWER_PLACEHOLDER = "Escreva a resposta para o cliente";
export const ANSWER_HINT = "Sai pela Concierge como “A equipe confirmou: …”.";
export const ANSWER_SENT = "Resposta enviada ao cliente.";
export const TAKEN_OVER = "A conversa é sua. Continue pelo Live Chat do ManyChat.";
export const TAKEN_OVER_NOTICE_NOT_SENT =
  "A conversa é sua, mas o aviso ao cliente não saiu. Continue pelo Live Chat do ManyChat.";
export const ANSWER_FAILED = "A resposta não saiu. O texto continua aqui: tente de novo.";
export const TAKE_OVER_FAILED = "Não deu para assumir a conversa. Tente de novo.";

// Promover a pergunta frequente (WP-15): a resposta enviada pode virar rascunho de
// pergunta frequente. O gesto mora no aviso de "Resposta enviada", porque o cartão fecha
// com a resposta; o rascunho só vale para os próximos clientes depois de publicado.
export const PROMOTE_LABEL = "Promover a pergunta frequente";
export const PROMOTED = "Virou rascunho em Perguntas frequentes. A Concierge só usa depois de publicado.";
export const ALREADY_PROMOTED = "Esta pergunta já é um rascunho em Perguntas frequentes.";
export const PROMOTE_FAILED = "Não deu para criar o rascunho. Tente de novo.";
export const OPEN_IN_ADMIN = "Abrir no Admin";

export interface PromotionResult {
  already?: boolean;
  admin_url?: string;
  warning?: string;
}

export interface PromotionToast {
  color: "success" | "warning" | "info";
  title: string;
  description?: string;
  /** O rascunho no Admin, onde se lê, ajusta e publica. Sem o endereço, sem botão. */
  action?: { label: string; to: string };
}

/** O aviso depois de promover: criado, já existia, e o alerta de data quando há. */
export function promotionToast(result: PromotionResult): PromotionToast {
  return {
    color: result.warning ? "warning" : result.already ? "info" : "success",
    title: result.already ? ALREADY_PROMOTED : PROMOTED,
    ...(result.warning ? { description: result.warning } : {}),
    ...(result.admin_url ? { action: { label: OPEN_IN_ADMIN, to: result.admin_url } } : {}),
  };
}

/** Os desfechos em que tentar de novo não adianta: só resta assumir a conversa. */
const FINAL_ANSWER_ERRORS = new Set(["window_closed"]);
export function isFinalAnswerError(code: string | undefined | null): boolean {
  return Boolean(code && FINAL_ANSWER_ERRORS.has(code));
}

type Action = AlertProjection["actions"][number];

// A conversa parada com a equipe (#3578): o cartão do handoff a devolve à Concierge ali mesmo.
export const GIVE_BACK_KIND = "give_back_to_concierge";
export const GIVEN_BACK = "A Concierge voltou a responder nesta conversa.";
export const GIVE_BACK_FAILED = "Não deu para devolver a conversa. Tente de novo.";
// Com confirmação (dono, 24/11): o gesto não é o principal, e pergunta antes de devolver.
export const GIVE_BACK_CONFIRM = {
  title: "A equipe terminou com este cliente?",
  description: "A Concierge volta a responder.",
  confirmLabel: "Devolver",
  cancelLabel: "Cancelar",
} as const;

/** O cartão do handoff: "Responder no Live Chat" é o principal, e "Devolver à Concierge" vem em contorno. */
export function handoffInbox(alert: AlertProjection): { actSecondary?: true } {
  return giveBackAction(alert) ? { actSecondary: true } : {};
}

/** O "Devolver à Concierge" do cartão do handoff, quando o servidor o oferece. */
export function giveBackAction(alert: AlertProjection): Action | null {
  return alert.actions?.find((action) => action.kind === GIVE_BACK_KIND && action.enabled) ?? null;
}

export const LIVE_CHAT_KIND = "open_live_chat";
export const CONFIGURE_LIVE_CHAT_KIND = "configure_live_chat";

export function verificationActions(alert: AlertProjection): {
  answer: Action | null;
  takeOver: Action | null;
  liveChat: Action | null;
  configureLiveChat: Action | null;
} {
  const find = (kind: string) => alert.actions?.find((action) => action.kind === kind && action.enabled) ?? null;
  return {
    answer: find(ANSWER_KIND),
    takeOver: find(TAKE_OVER_KIND),
    liveChat: find(LIVE_CHAT_KIND),
    configureLiveChat: find(CONFIGURE_LIVE_CHAT_KIND),
  };
}

/**
 * O que o cartão de verificação acrescenta ao aviso da caixa: o campo de resposta e o
 * "Assumir" (que abre o Live Chat), no lugar do gesto direto. Aviso de outro tipo: nada.
 */
/** A linha do prazo prometido ("Prometemos responder até 16h12."). */
const PROMISE_LINE = /^Prometemos responder até .+$/;

/** A mensagem sem a linha do prazo: na janela, o relógio já diz a hora. */
export function withoutPromiseLine(message: string): string {
  return message
    .split("\n")
    .filter((line) => !PROMISE_LINE.test(line.trim()))
    .join("\n")
    .trim();
}

export function verificationInbox(alert: AlertProjection): {
  answer?: OperatorInboxAnswerSpec;
  actLabel?: undefined;
  urgentMessage?: string;
} {
  const { answer, takeOver, liveChat, configureLiveChat } = verificationActions(alert);
  if (!answer) return {};
  // Assumir leva ao Live Chat daquela conversa, no mesmo gesto (dono, 21/11/2026); sem a
  // conta no Admin, o cartão diz por que não leva, com o botão que configura.
  const destination = takeOver && liveChat?.href ? { altHref: liveChat.href } : {};
  // A linha sob os botões: o que assumir faz, e (sem a conta) por que não abre o Live Chat.
  const missing = takeOver && !liveChat ? configureLiveChat : null;
  const lines = [takeOver?.reason, missing?.reason].filter((line): line is string => Boolean(line));
  const note = lines.length
    ? {
        altNote: lines.join(" "),
        ...(missing?.href ? { altNoteHref: missing.href, altNoteLabel: missing.label } : {}),
      }
    : {};
  return {
    actLabel: undefined,
    ...(alert.respond_by_iso ? { urgentMessage: withoutPromiseLine(alert.message) } : {}),
    answer: {
      label: answer.label,
      placeholder: ANSWER_PLACEHOLDER,
      maxLength: ANSWER_MAX_LENGTH,
      hint: ANSWER_HINT,
      ...(takeOver ? { altLabel: takeOver.label } : {}),
      ...destination,
      ...note,
    },
  };
}
