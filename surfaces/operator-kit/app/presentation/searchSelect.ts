// SearchSelect — transformações puras da busca. O componente só renderiza o que
// sai daqui, então "o que casa com o que foi digitado", "para onde a seta anda" e
// "onde o destaque nasce" são testáveis sem montar Vue.
import type { SearchSelectOption } from "../types/searchSelect";

/**
 * Dobra acento e caixa. No balcão ninguém digita "Açúcar" com cedilha: digita
 * "acucar" e espera achar. NFD separa a letra do acento e a faixa de combining
 * marks apaga só o acento, preservando a letra.
 */
export function normalizeSearchText(value: string): string {
  return (value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

/**
 * Termos soltos, em qualquer ordem: "farinha tri" e "tri farinha" acham os dois
 * "Farinha de Trigo". Cada termo precisa bater em ALGUM campo (E entre termos, OU
 * entre campos) — é o que faz a lista estreitar conforme se digita, em vez de
 * zerar na primeira palavra fora de ordem.
 */
export function searchTerms(query: string): string[] {
  return normalizeSearchText(query).split(/\s+/).filter(Boolean);
}

export function matchesQuery(option: SearchSelectOption, query: string): boolean {
  const terms = searchTerms(query);
  if (!terms.length) return true;
  const haystack = normalizeSearchText(`${option.label} ${option.hint ?? ""}`);
  return terms.every((term) => haystack.includes(term));
}

export function filterOptions(options: SearchSelectOption[], query: string): SearchSelectOption[] {
  const terms = searchTerms(query);
  if (!terms.length) return options;
  return options.filter((option) => matchesQuery(option, query));
}

/** Navegação ↑/↓ com volta pelas pontas — mesmo padrão da busca de cliente do PDV. */
export function moveHighlight(current: number, delta: 1 | -1, count: number): number {
  if (count <= 0) return -1;
  const base = current < 0 ? (delta === 1 ? -1 : 0) : current;
  return (base + delta + count) % count;
}

/**
 * Onde o destaque nasce quando a lista abre: em cima do que já está escolhido, e
 * não no primeiro item. Abrir um campo já preenchido e apertar Enter sem querer
 * tem de ser inócuo — reconfirma o que estava lá, não troca pelo primeiro da
 * lista.
 */
export function highlightForValue(options: SearchSelectOption[], value: string): number {
  if (!options.length) return -1;
  if (!value) return 0;
  const index = options.findIndex((option) => option.value === value);
  return index >= 0 ? index : 0;
}

/** Rótulo do que está escolhido — o que o campo mostra fechado. */
export function selectedLabel(options: SearchSelectOption[], value: string): string {
  if (!value) return "";
  return options.find((option) => option.value === value)?.label ?? value;
}
