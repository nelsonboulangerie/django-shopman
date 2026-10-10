// Vocação do produto (etiqueta de consumo do SKU) — puro e determinístico.
//
// Serve só ao B.I. (lotação, consumo local × levar); não muda a venda. Por isso
// pesa pouco na tela: uma linha no painel e um aviso `info` na lista.
// As escolhas vêm do servidor (papéis de consumo editáveis no Admin): o Nuxt
// não tem lista própria, só o rótulo do estado vazio.
import type { VocationChoice, VocationPending } from "~/types/catalog";

export interface VocationOption {
  value: string;
  label: string;
  hint: string;
}

/** As escolhas do controle segmentado, na ordem do catálogo de papéis. */
export function vocationOptions(
  choices: readonly VocationChoice[] | undefined,
): VocationOption[] {
  return (choices ?? []).map((choice) => ({
    value: choice.ref,
    label: choice.label,
    hint: choice.hint,
  }));
}

/** O rótulo do valor gravado, para o conflito e para leitores de tela. */
export function vocationLabel(
  value: string,
  choices: readonly VocationChoice[] | undefined,
): string {
  if (!value) return "Sem vocação";
  return choices?.find((choice) => choice.ref === value)?.label ?? value;
}

export interface VocationNotice {
  count: number;
  // "3 produtos à venda sem vocação"
  headline: string;
  // "Bolo, Pão e Torta" ou "Bolo, Pão, Torta e mais 2"
  names: string;
  firstSku: string;
}

const NAMES_SHOWN = 3;

function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

/**
 * O aviso da lista: quantos produtos à venda ainda não têm vocação, e
 * quais. Nenhum pendente = sem aviso (null), nunca "0 produtos".
 */
export function vocationNotice(
  pending: readonly VocationPending[] | undefined,
): VocationNotice | null {
  const items = pending ?? [];
  if (!items.length) return null;
  const count = items.length;
  const shown = items
    .slice(0, NAMES_SHOWN)
    .map((item) => item.name || item.sku);
  const rest = count - shown.length;
  return {
    count,
    headline: `${count} ${count === 1 ? "produto à venda" : "produtos à venda"} sem vocação`,
    names: rest > 0 ? `${shown.join(", ")} e mais ${rest}` : joinNames(shown),
    firstSku: items[0]!.sku,
  };
}
