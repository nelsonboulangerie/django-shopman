// Timers da bancada — a regra PURA da página /timers. Aqui mora o que o toque
// no card faz (e o que a tela DIZ que ele faz) e a comparação de nome de tag;
// a página e o card só desenham. Mesma divisão do KDS (presentation/board.ts),
// e pelo mesmo motivo: o gesto de toda hora precisa ser testável sem DOM.
//
// O tipo do modo vem do composable porque o modo é dele (o relógio é que vira
// running → ringing → seen). A importação é só de TIPO: este módulo não carrega
// Vue nem localStorage e roda no projeto `unit` (node).
import type { FloorTimerMode } from "~/composables/useFloorTimers";

/** O que um toque no CORPO do card faz. ``none`` = o corpo não é botão. */
export type FloorTimerTap = "seen" | "clear" | "none";

/** Janela em que o card recém-tocado ignora o toque seguinte.
 *
 *  ``Visto`` transforma o card de ``ringing`` em ``seen``, e em ``seen`` o
 *  toque encerra: sem esta janela, um toque que quicasse silenciaria e apagaria
 *  o timer no mesmo gesto. Mesma trava do card do KDS (``KDS_ARM_DELAY_MS``),
 *  pela mesma razão — dedo molhado, tablet no fournil. */
export const FLOOR_TIMER_ARM_MS = 800;

/** O gesto de toda hora, por estado — e é só UM por estado:
 *
 *  - ``ringing``: está gritando; a única coisa que importa é calar. O corpo
 *    inteiro é o alvo, porque ninguém mira num botão com a mão na fornada.
 *  - ``seen``: já cumpriu o que prometeu; o que resta é tirar da tela.
 *  - ``running``: nada. O card que corre não tem gesto de toda hora, e um
 *    toque acidental nele não pode mexer no tempo de ninguém.
 *
 *  ``+5 min`` e ``Encerrar`` continuam existindo como botões explícitos: o
 *  corpo cobre o caso comum, os botões cobrem o resto sem esconder nada. */
export function floorTimerTap(
  mode: FloorTimerMode,
  state: { armed: boolean },
): FloorTimerTap {
  if (mode === "ringing") return "seen";
  if (mode === "seen") return state.armed ? "clear" : "none";
  return "none";
}

/** O que a tela escreve no card sobre o próprio toque. Vazio quando o corpo
 *  não é botão — dica de gesto que não existe é ruído. */
export function floorTimerTapHint(mode: FloorTimerMode): string {
  if (mode === "ringing") return "Toque no card para marcar Visto";
  if (mode === "seen") return "Toque no card para encerrar";
  return "";
}

/** Rótulo do estado, na linha do contador. ``running`` devolve "" porque ali
 *  quem fala é o relógio (``remainingLabel``), não uma palavra. */
export function floorTimerModeLabel(mode: FloorTimerMode): string {
  if (mode === "ringing") return "Tempo esgotado";
  if (mode === "seen") return "Visto";
  return "";
}

/** Duração em português de padaria: minutos até 1 h, depois "1 h 30 min". */
export function minutesLabel(minutes: number): string {
  const total = Math.max(0, Math.round(minutes));
  if (total < 60) return `${total} min`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

/** Nome comparável de tag: sem acento, sem espaço sobrando, caixa única.
 *
 *  É o espelho do normalizador do servidor
 *  (``shopman.backstage.models.timer_tag.normalize_tag_label``). Serve para a
 *  tela reconhecer que "Pausa-café" e "pausa cafe" são a mesma coisa ANTES de
 *  gravar; quem decide continua sendo o servidor, que deduplica na criação. */
export function normalizeTagLabel(label: string): string {
  return label
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^0-9a-zA-Z]+/g, " ")
    .trim()
    .toLowerCase();
}

export interface TimerTagLike {
  ref: string;
  label: string;
  minutes: number;
}

/** A tag já existente equivalente a este nome, ou ``null``. */
export function findTagByLabel<T extends TimerTagLike>(
  tags: readonly T[],
  label: string,
): T | null {
  const normalized = normalizeTagLabel(label);
  if (!normalized) return null;
  return tags.find((tag) => normalizeTagLabel(tag.label) === normalized) ?? null;
}

/** As tags que a busca do cabeçalho deixa na tela. Busca vazia = todas. */
export function filterTags<T extends TimerTagLike>(
  tags: readonly T[],
  query: string,
): T[] {
  const needle = normalizeTagLabel(query);
  if (!needle) return [...tags];
  return tags.filter((tag) => normalizeTagLabel(tag.label).includes(needle));
}
