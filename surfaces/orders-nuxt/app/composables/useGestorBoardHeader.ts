import type { MaybeRefOrGetter } from "vue";

/**
 * Interface do dono do header do Gestor (item 4).
 *
 * O header NÃO tem store próprio: é uma view do estado do board. O dono dos efeitos
 * (`useOrdersBoard` com SSE/som, `useBoardLayout`) continua sendo o `index.vue` — este
 * model só transporta o que a casca canônica precisa para desenhar o chrome.
 * Nunca re-instancie os controllers aqui (ligaria um segundo SSE/som).
 */
export type GestorBoardHeaderModel = {
  /** Título canônico da tela. */
  title: string;
  /** Linha fina acima do título (ex.: "Posto Saída · este dispositivo"). */
  eyebrow: MaybeRefOrGetter<string>;
};

const GESTOR_BOARD_HEADER: unique symbol = Symbol("gestor-board-header");

/** Provê o model uma única vez, no dono (`index.vue`). Devolve o próprio model. */
export function provideGestorBoardHeader(model: GestorBoardHeaderModel): GestorBoardHeaderModel {
  provide(GESTOR_BOARD_HEADER, model);
  return model;
}

/** Consome o model do dono (componente do header). */
export function useGestorBoardHeader(): GestorBoardHeaderModel {
  const model = inject<GestorBoardHeaderModel | null>(GESTOR_BOARD_HEADER, null);
  if (!model) throw new Error("useGestorBoardHeader(): falta provideGestorBoardHeader() no dono (index.vue).");
  return model;
}
