// Escolha — transformações puras por trás de `UiRadioGroup` e `UiSelect`.
//
// Mesmo arranjo do `columnPicker` ao lado: o que a lista mostra, o que a busca
// acha e para onde a seta anda é testável sem montar Vue. O componente renderiza
// o que sai daqui.
import type { ChoiceOption, ChoiceValue } from "../types/choice";

/**
 * Limiar em que a lista passa a ter campo de busca.
 *
 * O número saiu de uma MEDIÇÃO das listas que existem, não do olho. De um lado, o
 * maior vocabulário FIXO das nove superfícies tem 10 itens (`ROLE_OPTIONS` do
 * Produção e o filtro de desfecho do Histórico); pôr campo de busca em cima de dez
 * opções escritas no código seria obstáculo, não ajuda. Do outro lado estão as
 * listas que a casa já reclamou: os modelos aprovados da Meta em Plataformas (a
 * queixa que abriu esta frente), os 41 exemplos do Explorar no B.I. e os 56 insumos
 * que fizeram o Compras abandonar o `<select>` nativo e escrever o
 * `MaterialPicker` à mão (ver o cabeçalho dele).
 *
 * 12 é a fronteira entre os dois grupos, com duas casas de folga para os
 * vocabulários fixos crescerem sem virar busca sem querer.
 */
export const SEARCH_THRESHOLD = 12;

/** A lista merece campo de busca? */
export function isSearchable(count: number, threshold: number = SEARCH_THRESHOLD): boolean {
  return count > threshold;
}

/**
 * Texto comparável: minúsculo e SEM acento. O operador digita "padrao" com o
 * teclado de celular e espera achar "Padrão"; exigir o acento seria a tela
 * cobrando uma precisão que ninguém tem com uma mão só.
 */
export function normalizeText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

/**
 * Filtra por TODOS os termos digitados, em qualquer ordem, contra rótulo, detalhe
 * e palavras-chave. "story insta" acha "Instagram — Story": busca por termo solto
 * é o que as pessoas fazem quando não lembram o nome exato.
 */
export function filterOptions<T extends ChoiceOption>(options: T[], query: string): T[] {
  const terms = normalizeText(query).split(/\s+/).filter(Boolean);
  if (terms.length === 0) return options;

  return options.filter((option) => {
    const haystack = normalizeText([option.label, option.hint, option.keywords].filter(Boolean).join(" "));
    return terms.every((term) => haystack.includes(term));
  });
}

/** O que o leitor de tela ouve quando a lista muda de tamanho. */
export function resultsAnnouncement(count: number): string {
  if (count === 0) return "Nenhum resultado";
  if (count === 1) return "1 resultado";
  return `${count} resultados`;
}

/**
 * O mínimo que a navegação por seta precisa saber de um item: se ele está
 * desabilitado. Pedir a `ChoiceOption` inteira deixaria de fora o `RadioItem` do
 * grupo de rádio, que é a MESMA lista vista pelo outro lado.
 */
interface Steppable {
  readonly disabled?: boolean;
}

function enabledAt(options: readonly Steppable[], index: number): boolean {
  const option = options[index];
  return option != null && !option.disabled;
}

/** Primeiro índice utilizável, ou -1 quando a lista está vazia/toda desabilitada. */
export function firstEnabledIndex(options: readonly Steppable[]): number {
  return options.findIndex((option) => !option.disabled);
}

/** Último índice utilizável, ou -1. */
export function lastEnabledIndex(options: readonly Steppable[]): number {
  for (let index = options.length - 1; index >= 0; index -= 1) {
    if (enabledAt(options, index)) return index;
  }
  return -1;
}

/**
 * Próximo índice na direção pedida, pulando desabilitado e dando a volta.
 *
 * Dar a volta é escolha: a seta para baixo no último item volta ao primeiro. Numa
 * lista curta de rádio isso é o comportamento nativo, e numa lista longa de select
 * é o que evita a sensação de controle travado. Devolve -1 quando não há para onde
 * ir (nenhuma opção utilizável), e nunca entra em laço infinito.
 */
export function stepIndex(options: readonly Steppable[], from: number, delta: number): number {
  const total = options.length;
  if (total === 0) return -1;

  const start = from < 0 || from >= total ? (delta > 0 ? -1 : total) : from;
  for (let step = 1; step <= total; step += 1) {
    const index = (((start + delta * step) % total) + total) % total;
    if (enabledAt(options, index)) return index;
  }
  return -1;
}

/** Índice da opção escolhida na lista dada, ou -1 quando ela não está ali. */
export function indexOfValue(options: ChoiceOption[], value: ChoiceValue | undefined): number {
  return options.findIndex((option) => option.value === value);
}

/** A opção escolhida, ou `null` — o que o gatilho do select mostra. */
export function selectedOption<T extends ChoiceOption>(options: T[], value: ChoiceValue | undefined): T | null {
  return options.find((option) => option.value === value) ?? null;
}
