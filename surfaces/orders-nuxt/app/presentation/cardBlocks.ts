// Presentation — o bloqueio à vista no cartão do pedido (WP-G06). Puro.
//
// Dois defeitos do laudo do Gestor moravam aqui:
//   - o botão travado só dizia o porquê no `title`, que não existe no toque (P1-12);
//   - a pílula "Por que espera" guardava o fato ("Cobrança recusada") atrás do toque
//     (P2-16), e o aviso da NFC-e prometia "Abrir e reprocessar" num botão que só
//     abre o pedido (P2-13).
// Quem decide o que trava, e por quê, é o servidor: aqui só se escolhe o que vai
// escrito, e onde.
import type { Affordance } from "./board";

/** Um gesto travado do cartão, com o rótulo que o botão mostra. */
export interface BlockedGesture {
  ref: string;
  label: string;
  reason: string;
}

/**
 * As linhas de "por que não pode", escritas sob os botões do cartão.
 *
 * Um motivo por linha. Quando o motivo vale para todos os botões do cartão, a frase
 * vai sozinha; quando vale só para alguns, o nome do botão vem na frente ("Receber na
 * retirada: Abra um turno de caixa para registrar o acerto."), para ninguém ter de
 * adivinhar de qual botão a frase fala.
 *
 * O avanço e o aceite travados por um bloqueio que o cartão já anuncia
 * (`advance_block_reason`: o aviso "Aguardando Pix", "Pix expirado") não repetem a
 * frase aqui: o fato já está escrito na pílula, com o motivo a um toque.
 */
export function blockedReasonLines(input: {
  primary: Affordance | null;
  primaryLabel: string;
  secondary: readonly Affordance[];
  /** O cartão já diz por que o avanço espera (`card.advance_block_reason`). */
  blockAnnounced: boolean;
}): string[] {
  const buttons: Array<{ aff: Affordance; label: string }> = [
    ...input.secondary.map((aff) => ({ aff, label: aff.label })),
    ...(input.primary
      ? [{ aff: input.primary, label: input.primaryLabel || input.primary.label }]
      : []),
  ];
  const blocked: BlockedGesture[] = buttons
    .filter(({ aff }) => aff.disabled && String(aff.reason ?? "").trim())
    .filter(
      ({ aff }) =>
        !(input.blockAnnounced && (aff.ref === "advance" || aff.ref === "confirm")),
    )
    .map(({ aff, label }) => ({
      ref: aff.ref,
      label,
      reason: String(aff.reason).trim(),
    }));
  const byReason = new Map<string, string[]>();
  for (const gesture of blocked) {
    const labels = byReason.get(gesture.reason) ?? [];
    labels.push(gesture.label);
    byReason.set(gesture.reason, labels);
  }
  return [...byReason.entries()].map(([reason, labels]) =>
    labels.length === buttons.length
      ? reason
      : `${listed(labels)}: ${reason}`,
  );
}

function listed(labels: string[]): string {
  if (labels.length <= 1) return labels[0] ?? "";
  return `${labels.slice(0, -1).join(", ")} e ${labels.at(-1)}`;
}

/** O aviso do cartão, como o `OrderCard` o monta (pílula + Popover). */
export interface CardNoticeLike {
  key: string;
  label: string;
  title: string;
  /** As ações do aviso (`ButtonProps` do Nuxt UI): aqui só importam o rótulo e o destino. */
  actions?: Array<{ label?: string; to?: unknown }>;
}

/** O título que o cartão põe quando o servidor não nomeou o bloqueio. */
const UNNAMED_BLOCK = "Bloqueado";
/** O gesto que existe na tela: o botão do aviso da NFC-e só abre o pedido. */
export const OPEN_ORDER_LABEL = "Abrir o pedido";

/**
 * O aviso como a pílula o mostra.
 *
 * - **Bloqueio**: a pílula diz o FATO ("Pix expirado", "Cobrança recusada"), não a
 *   pergunta "Por que espera". O porquê continua a um toque. Sem nome de bloqueio do
 *   servidor, fica a pergunta: "Bloqueado" repetiria o selo do cartão sem dizer nada.
 * - **NFC-e não autorizada**: o botão só abre o pedido, então diz "Abrir o pedido". O
 *   reprocessar é gesto do detalhe, e só lá o botão leva esse verbo.
 */
export function cardNoticeView<T extends CardNoticeLike>(notice: T): T {
  if (notice.key === "block") {
    const fact = String(notice.title ?? "").trim();
    return fact && fact !== UNNAMED_BLOCK ? { ...notice, label: fact } : notice;
  }
  if (notice.key === "fiscal" && notice.actions?.length) {
    return {
      ...notice,
      actions: notice.actions.map((action) =>
        action.to ? { ...action, label: OPEN_ORDER_LABEL } : action,
      ),
    } as T;
  }
  return notice;
}
