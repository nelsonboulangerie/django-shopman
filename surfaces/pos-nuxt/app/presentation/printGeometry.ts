// Geometria de impressão (spec §D3) — traduz o que o TERMINAL declarou para as
// custom properties que o print CSS lê (`--pos-roll-*` em assets/css/tailwind.css).
//
// A regra que dá sentido ao arquivo: o default do rolo tem UM dono, o CSS. Se o
// terminal não declara nada, esta função devolve string vazia e a superfície não
// encosta no `documentElement` — o `@page` fica com o literal de 80mm. Só quando
// a loja declara outra coisa é que a var é escrita, e aí página e recibo se movem
// juntos, porque `--pos-receipt-width` deriva da mesma var.
//
// Formatação pura, sem política: quem valida a declaração (rolo fora do padrão,
// largura absurda) é o servidor, em `services/pos_terminal.printer_geometry` —
// declaração inválida chega aqui como 0 e vira warning na saúde do terminal.
import type { POSProjection } from "~/types/pos";

/** O que a superfície precisa da Projection para montar a geometria. */
export type PrintGeometrySource = Pick<
  POSProjection,
  "terminal_roll_width_mm" | "terminal_roll_margin_mm"
>;

/** Largura de rolo aceita — o servidor já limita, isto é a rede da superfície. */
const ROLL_WIDTH_BOUNDS = [40, 120] as const;

function usableMm(source: PrintGeometrySource | null | undefined) {
  const roll = Number(source?.terminal_roll_width_mm ?? 0);
  const margin = Number(source?.terminal_roll_margin_mm ?? 0);
  const [low, high] = ROLL_WIDTH_BOUNDS;
  if (!Number.isFinite(roll) || !Number.isFinite(margin)) return null;
  if (roll < low || roll > high) return null;
  // Margem tem que sobrar largura: `2 * margem >= rolo` imprimiria em nada.
  if (margin <= 0 || margin * 2 >= roll) return null;
  return { roll, margin };
}

/**
 * As custom properties do rolo, prontas para o atributo `style` do `<html>`.
 *
 * Devolve `""` quando o terminal não declarou (ou declarou algo que não fecha):
 * string vazia é o sinal de "não escreva nada e deixe o CSS mandar".
 */
export function rollStyle(source: PrintGeometrySource | null | undefined): string {
  const geometry = usableMm(source);
  if (!geometry) return "";
  return `--pos-roll-width:${geometry.roll}mm;--pos-roll-margin-x:${geometry.margin}mm`;
}
