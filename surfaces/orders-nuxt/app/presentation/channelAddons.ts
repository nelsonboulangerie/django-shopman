/**
 * Complementos do iFood no Gestor: leitura pura da tela (preço digitado, regra de
 * escolhas e o rótulo do estado), testada sem montar componente.
 */

/** "12,50" | "12.5" | "R$ 3" → centavos; null quando não é um preço. */
export function parsePriceQ(text: string): number | null {
  const clean = String(text ?? "")
    .replace(/R\$\s?/i, "")
    .replace(/\s/g, "")
    .trim();
  if (!clean) return null;
  // Vírgula é o decimal da casa; ponto só é decimal quando não há vírgula.
  const normalized = clean.includes(",")
    ? clean.replace(/\./g, "").replace(",", ".")
    : clean;
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return null;
  return Math.round(Number(normalized) * 100);
}

/** "Opcional, até 2" | "Obrigatório, 1" | "Obrigatório, de 1 a 3". */
export function choiceRule(min: number, max: number): string {
  if (min === 0)
    return max === 1 ? "Opcional, escolhe 1" : `Opcional, até ${max}`;
  if (min === max) return `Obrigatório, escolhe ${min}`;
  return `Obrigatório, de ${min} a ${max}`;
}

export function addonStatusLabel(active: boolean): string {
  return active ? "Ativo" : "Pausado";
}

/** Separador que o servidor põe entre a frase do operador e o texto original do iFood. */
export const IFOOD_ORIGINAL_MARK = " | iFood: ";

/** "A foto não foi aceita… | iFood: image could not…" → frase e original (letra pequena). */
export function splitIfoodReason(message: string): {
  text: string;
  original: string;
} {
  const at = message.indexOf(IFOOD_ORIGINAL_MARK);
  if (at < 0) return { text: message, original: "" };
  return {
    text: message.slice(0, at),
    original: message.slice(at + IFOOD_ORIGINAL_MARK.length),
  };
}
