// Escolhas no produto (Fase 1): sabor obrigatório, adicionais com preço.
//
// Contrato: o produto traz `option_groups` (grupo com `min`/`max`, opções com
// `price_q` e `available`); a linha da comanda guarda as escolhas em `options`
// e manda ao servidor só `{group, ref}`. O servidor relê tudo do catálogo e
// reprecifica; aqui mora só o que a TELA decide: a regra legível de cada
// grupo, a validade da seleção, o total ao vivo, o nome da linha e a
// assinatura que diz se duas linhas são "a mesma".

import { formatBRL } from "../../../operator-kit/app/utils/money";
import type { POSCartItemOption, POSProductOptionGroup, POSProductProjection } from "~/types/pos";

/** O que está escolhido: por grupo, os refs das opções na ordem do toque. */
export type OptionSelection = Record<string, string[]>;

/** O produto abre a escolha? (Com grupo só opcional também: é para oferecer.) */
export function hasOptionGroups(product: Pick<POSProductProjection, "option_groups">): boolean {
  return Array.isArray(product.option_groups) && product.option_groups.length > 0;
}

/**
 * A identidade das escolhas de uma linha: `group:ref` ordenados. Duas linhas do
 * mesmo SKU só somam quantidade com a MESMA assinatura; sem escolha nenhuma a
 * assinatura é "" (e `undefined` vale o mesmo que `[]`).
 */
export function optionsSignature(options: { group: string; ref: string }[] | null | undefined): string {
  return (options || [])
    .map((option) => `${option.group}:${option.ref}`)
    .sort()
    .join("|");
}

/** A regra do grupo, em português de balcão: "Escolha 1", "Opcional, até 2". */
export function groupRuleLabel(group: Pick<POSProductOptionGroup, "min" | "max">): string {
  const min = Math.max(0, group.min || 0);
  const max = Math.max(min, group.max || 1);
  if (min === 0) return max === 1 ? "Opcional" : `Opcional, até ${max}`;
  if (min === max) return `Escolha ${min}`;
  return `Escolha de ${min} a ${max}`;
}

/** Escolha única: o toque troca a opção, em vez de somar. */
export function isSingleChoice(group: Pick<POSProductOptionGroup, "max">): boolean {
  return (group.max || 1) <= 1;
}

/** "+ R$ 4,00" na opção com acréscimo; "" na que não muda o preço. */
export function optionPriceLabel(priceQ: number): string {
  return priceQ > 0 ? `+ ${formatBRL(priceQ)}` : "";
}

/**
 * O toque numa opção. Indisponível não entra. Na escolha única, troca (e tocar
 * na escolhida desmarca só quando o grupo é opcional). Na múltipla, marca até o
 * `max` e desmarca no segundo toque; acima do teto, o toque não faz nada.
 */
export function toggleOption(
  group: POSProductOptionGroup,
  selection: OptionSelection,
  optionRef: string,
): OptionSelection {
  const option = group.options.find((entry) => entry.ref === optionRef);
  if (!option || !option.available) return selection;
  const current = selection[group.ref] || [];
  const chosen = current.includes(optionRef);
  let next: string[];
  if (isSingleChoice(group)) {
    if (chosen) next = (group.min || 0) > 0 ? current : [];
    else next = [optionRef];
  } else if (chosen) {
    next = current.filter((ref) => ref !== optionRef);
  } else if (current.length >= (group.max || 1)) {
    return selection;
  } else {
    next = [...current, optionRef];
  }
  return { ...selection, [group.ref]: next };
}

/** Quantas faltam para cumprir o mínimo do grupo (0 = cumprido). */
export function groupMissing(group: POSProductOptionGroup, selection: OptionSelection): number {
  return Math.max(0, (group.min || 0) - (selection[group.ref] || []).length);
}

/** Todos os mínimos cumpridos: o "Lançar" pode agir. */
export function selectionValid(groups: POSProductOptionGroup[], selection: OptionSelection): boolean {
  return groups.every((group) => groupMissing(group, selection) === 0);
}

/**
 * As escolhas no formato da linha da comanda, na ordem do CATÁLOGO (grupo,
 * depois opção), não na do toque: é essa ordem que o nome da linha repete.
 */
export function selectedCartOptions(groups: POSProductOptionGroup[], selection: OptionSelection): POSCartItemOption[] {
  const out: POSCartItemOption[] = [];
  for (const group of groups) {
    const chosen = new Set(selection[group.ref] || []);
    for (const option of group.options) {
      if (!chosen.has(option.ref)) continue;
      out.push({
        group: group.ref,
        ref: option.ref,
        group_label: group.label,
        name: option.label,
        unit_price_q: Math.max(0, option.price_q || 0),
      });
    }
  }
  return out;
}

/** Soma dos acréscimos de uma unidade. */
export function optionsTotalQ(options: POSCartItemOption[] | null | undefined): number {
  return (options || []).reduce((sum, option) => sum + Math.max(0, option.unit_price_q || 0), 0);
}

/** O preço de uma unidade da linha: produto + opções. */
export function lineUnitPriceQ(productPriceQ: number, options: POSCartItemOption[] | null | undefined): number {
  return productPriceQ + optionsTotalQ(options);
}

/** "+ Ovo frito · Salada" — com preço leva o "+", sem preço só o rótulo. */
export function optionsSummary(options: POSCartItemOption[] | null | undefined): string {
  return (options || [])
    .map((option) => (option.unit_price_q > 0 ? `+ ${option.name}` : option.name))
    .join(" · ");
}

/** O nome da linha, igual ao que o servidor devolve: "Croque Monsieur (+ Ovo frito)". */
export function optionLineName(productName: string, options: POSCartItemOption[] | null | undefined): string {
  const summary = optionsSummary(options);
  return summary ? `${productName} (${summary})` : productName;
}

/** O que sobe ao servidor: só `{group, ref}`. Nunca preço, nunca nome. */
export function optionsIntent(options: { group: string; ref: string }[] | null | undefined): { group: string; ref: string }[] {
  return (options || [])
    .filter((option) => option && option.group && option.ref)
    .map((option) => ({ group: String(option.group), ref: String(option.ref) }));
}
