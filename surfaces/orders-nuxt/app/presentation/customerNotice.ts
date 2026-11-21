// Presentation — "Avisar o cliente" com um toque (WP-G07; decisão 4 do dono, 17/11/2026:
// "pela API"). Puro.
//
// Quem decide quando cada aviso cabe, o que ele pede e a mensagem pronta é o servidor
// (`GET/POST orders/<ref>/customer-notice/preview/`). Aqui só se traduz a leitura em
// desenho: as linhas do rádio, as horas prontas, os itens a marcar, o que falta escolher
// e as frases de tela. Nenhuma frase da mensagem é escrita neste arquivo.

/** Uma hora pronta do "Vai atrasar": `value` volta ao servidor como veio. */
export interface CustomerNoticeDelayChoice {
  value: string;
  label: string;
}

/** Uma linha do pedido que pode faltar. */
export interface CustomerNoticeLine {
  line_id: string;
  name: string;
  qty: string;
  qty_display: string;
}

export type CustomerNoticeKind = "delayed" | "item_missing" | "reschedule";

/** Um dos três avisos, com o motivo quando não cabe. */
export interface CustomerNoticeOption {
  kind: CustomerNoticeKind;
  label: string;
  enabled: boolean;
  reason: string;
  delay_choices: CustomerNoticeDelayChoice[];
  lines: CustomerNoticeLine[];
}

/** A resposta de `GET /api/v1/backstage/orders/<ref>/customer-notice/preview/`. */
export interface CustomerNoticeOptions {
  ref: string;
  notices: CustomerNoticeOption[];
  payload_schema: Record<string, unknown>;
}

/** A resposta de `POST …/customer-notice/preview/`: a mensagem como o cliente a lê. */
export interface CustomerNoticePreview {
  kind: CustomerNoticeKind;
  status_note: string;
  message: string;
}

/** O que a tela escolheu: o aviso, a hora nova (atrasar) e os itens (faltou). */
export interface CustomerNoticePick {
  kind: CustomerNoticeKind | "";
  eta: string;
  lines: string[];
}

export const NOTICE_LEGEND = "Qual aviso";
export const DELAY_LEGEND = "Nova previsão";
export const MISSING_LEGEND = "O que vai faltar";
export const SEND_LABEL = "Enviar aviso";
/** A tela nunca diz "enviado": a fila e o recibo do pedido dizem o que houve. */
export const SENT_SENTENCE =
  "Aviso na fila de envio. O recibo aparece em Avisos ao cliente, neste pedido.";
/** O caminho do envio, dito antes do botão: um toque, pela casa. */
export const SEND_ROUTE =
  "Sai pelo WhatsApp da casa; sem WhatsApp, por SMS ou e-mail.";

const ICONS: Record<CustomerNoticeKind, string> = {
  delayed: "i-lucide-clock-alert",
  item_missing: "i-lucide-package-x",
  reschedule: "i-lucide-calendar-x",
};

export function noticeTitle(code: string): string {
  return code ? `Avisar o cliente do pedido ${code}` : "Avisar o cliente";
}

export function messageHeading(customerName: string): string {
  const name = customerName.trim();
  return name ? `Mensagem para ${name}` : "Mensagem para o cliente";
}

export interface NoticeItem {
  value: string;
  label: string;
  description?: string;
  icon: string;
  disabled: boolean;
  "data-notice-kind": string;
}

/** As linhas do rádio, na ordem do servidor; a travada escreve o motivo. */
export function noticeItems(notices: readonly CustomerNoticeOption[]): NoticeItem[] {
  return notices.map((notice) => ({
    value: notice.kind,
    label: notice.label,
    description: notice.enabled ? undefined : notice.reason || undefined,
    icon: ICONS[notice.kind],
    disabled: !notice.enabled,
    "data-notice-kind": notice.kind,
  }));
}

/** As horas prontas, como linhas do rádio. */
export function delayItems(notice: CustomerNoticeOption | null) {
  return (notice?.delay_choices ?? []).map((choice) => ({
    value: choice.value,
    label: choice.label,
    "data-notice-eta": choice.value,
  }));
}

/** Os itens do pedido, como caixas de marcar: "Focaccia · 2 unidades". */
export function lineItems(notice: CustomerNoticeOption | null) {
  return (notice?.lines ?? []).map((line) => ({
    value: line.line_id,
    label: line.name,
    description: line.qty_display,
    "data-notice-line": line.line_id,
  }));
}

/** O aviso marcado. Aviso travado nunca conta como marcado. */
export function pickedNotice(
  options: CustomerNoticeOptions | null,
  kind: string,
): CustomerNoticeOption | null {
  if (!kind) return null;
  return options?.notices.find((notice) => notice.kind === kind && notice.enabled) ?? null;
}

/**
 * O que ainda falta escolher, numa frase; vazio quando a escolha está completa e a
 * mensagem pode ser lida. Nada vem marcado sozinho: quem decide é a pessoa.
 */
export function missingStep(notice: CustomerNoticeOption | null, pick: CustomerNoticePick): string {
  if (!notice) return "Escolha o aviso para ver a mensagem.";
  if (notice.kind === "delayed" && !pick.eta) return "Escolha a nova previsão para ver a mensagem.";
  if (notice.kind === "item_missing" && pick.lines.length === 0)
    return "Marque o que vai faltar para ver a mensagem.";
  return "";
}

/** O corpo da prévia e do envio: só o que o aviso marcado pede. */
export function noticeInputs(
  notice: CustomerNoticeOption,
  pick: CustomerNoticePick,
): Record<string, unknown> {
  if (notice.kind === "delayed") return { kind: notice.kind, eta: pick.eta };
  if (notice.kind === "item_missing") {
    // Na ordem do pedido, não na ordem dos toques: a mensagem lê como o pedido.
    const marked = new Set(pick.lines);
    return {
      kind: notice.kind,
      lines: notice.lines.filter((line) => marked.has(line.line_id)).map((line) => ({ line_id: line.line_id })),
    };
  }
  return { kind: notice.kind };
}
