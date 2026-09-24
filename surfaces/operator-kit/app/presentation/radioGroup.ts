// Contrato entre `UiRadioGroup` (o dono da escolha) e `UiRadio` (cada opção).
//
// O grupo mantém o registro dos filhos em ordem de montagem — que é a ordem do
// `v-for`, e portanto a da tela. É o registro, e não uma varredura de DOM, que
// responde "qual é o próximo": consulta ao DOM por seletor teria que adivinhar a
// fronteira do grupo em telas aninhadas, e não seria testável sem navegador.
import type { InjectionKey } from "vue";

import type { ChoiceValue } from "../types/choice";

export interface RadioItem {
  readonly value: ChoiceValue;
  readonly disabled: boolean;
  focus: () => void;
}

export interface RadioGroupContext {
  /** Valor escolhido no grupo. */
  readonly selected: ChoiceValue;
  /** Grupo inteiro desabilitado. */
  readonly disabled: boolean;
  select: (value: ChoiceValue) => void;
  register: (item: RadioItem) => void;
  unregister: (item: RadioItem) => void;
  /** Seta/Home/End: anda `delta` casas a partir de `item` (0 = ir para a ponta). */
  move: (item: RadioItem, delta: number) => void;
  moveToEdge: (edge: "first" | "last") => void;
  /**
   * Este item é a parada de tabulação do grupo? Um grupo de rádio tem UMA: a
   * escolhida, ou — quando nada foi escolhido ainda — a primeira utilizável.
   * Sem isso o Tab passearia por cada opção, que é o erro clássico.
   */
  isTabStop: (item: RadioItem) => boolean;
}

export const radioGroupKey: InjectionKey<RadioGroupContext> = Symbol("operator-kit:radio-group");
