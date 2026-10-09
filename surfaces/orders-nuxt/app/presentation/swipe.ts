// Puxar para atualizar no celular (G16, prévia v4 `cozinha-celular`). Puro: testado em
// `tests/gestorV6Gestures.test.ts`. O deslizar da linha é do kit
// (`operator-kit/app/presentation/swipe.ts`, peça `OperatorSwipeRow`).

/** Puxar para atualizar: o quanto puxar no topo da lista. */
export const PULL_COMMIT_PX = 72;

/** A frase do puxar para atualizar, pelo quanto já se puxou. */
export function pullLabel(dy: number, refreshing: boolean): string {
  if (refreshing) return "Atualizando…";
  return dy >= PULL_COMMIT_PX ? "Solte para atualizar" : "Puxe para atualizar";
}
