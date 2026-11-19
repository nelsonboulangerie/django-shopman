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

type Action = AlertProjection["actions"][number];

export function verificationActions(alert: AlertProjection): { answer: Action | null; takeOver: Action | null } {
  const find = (kind: string) => alert.actions?.find((action) => action.kind === kind && action.enabled) ?? null;
  return { answer: find(ANSWER_KIND), takeOver: find(TAKE_OVER_KIND) };
}

/**
 * O que o cartão de verificação acrescenta ao aviso da caixa: o campo de resposta e o
 * "Assumir a conversa", no lugar do gesto direto. Aviso de outro tipo: nada.
 */
export function verificationInbox(alert: AlertProjection): { answer?: OperatorInboxAnswerSpec; actLabel?: undefined } {
  const { answer, takeOver } = verificationActions(alert);
  if (!answer) return {};
  return {
    actLabel: undefined,
    answer: {
      label: answer.label,
      placeholder: ANSWER_PLACEHOLDER,
      maxLength: ANSWER_MAX_LENGTH,
      hint: ANSWER_HINT,
      ...(takeOver ? { altLabel: takeOver.label } : {}),
    },
  };
}
