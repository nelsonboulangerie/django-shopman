// Presentation — o bloqueio à vista no cartão do pedido (WP-G06). Puro.
//
// Dois defeitos do laudo do Gestor moravam aqui:
//   - o botão travado só dizia o porquê no `title`, que não existe no toque (P1-12);
//   - a pílula "Por que espera" guardava o fato ("Cobrança recusada") atrás do toque
//     (P2-16).
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

/** O que a pílula do bloqueio diz quando o servidor não nomeou o bloqueio. */
const UNNAMED_BLOCK_PILL = "Por que espera";

/**
 * O rótulo da pílula do bloqueio no cartão (laudo do Gestor, P2-16).
 *
 * A pílula diz o FATO, pelo nome que o servidor deu ao bloqueio ("Pix expirado",
 * "Cobrança recusada"); o porquê continua a um toque, no Popover. Só quando o
 * servidor não nomeou o bloqueio fica a pergunta "Por que espera". As reticências
 * do rótulo de espera ("Aguardando Pix…") não vão para a pílula.
 */
export function blockPillLabel(blockLabel: string | null | undefined): string {
  return String(blockLabel ?? "").replace(/…$/, "").trim() || UNNAMED_BLOCK_PILL;
}
