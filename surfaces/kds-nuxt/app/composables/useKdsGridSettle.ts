// A grade da estação se reorganiza quando a fila muda: chega um pedido mais urgente e
// vai para a esquerda, um Pronto sai e o próximo assume o foco. A reorganização é
// animada (FLIP do `TransitionGroup`), e durante ela os tickets passam uns por cima dos
// outros. Provado na UI em 06/11/2026 (Encomendas, 800×600): o operador tocou em
// "Iniciar preparo" do P30 enquanto o P30 deslizava sobre o T69, e o toque caiu no T69,
// abrindo o detalhe do pedido errado.
//
// A regra: enquanto a grade está se acomodando, nenhum toque age. O ticket que o
// operador vê embaixo do dedo pode não ser o que o navegador acha que está ali, e não
// há como saber qual dos dois ele quis. Passada a acomodação, o toque volta a agir, e
// sempre pelo pedido (pk) do ticket tocado, nunca pela posição.

import { onScopeDispose, readonly, ref, watch, type WatchSource } from "vue";

/** O que a grade leva para se acomodar: a maior transição dela (o deslize de 0,35 s)
 *  com folga para o último quadro. Acompanha o CSS da página `[ref].vue`. */
export const KDS_GRID_SETTLE_MS = 420;

/** A posição de cada ticket visível, na ordem da fila: muda quando um ticket entra, sai
 *  ou troca de célula, que são os momentos em que a grade anima. */
export function placementSignature(
  visible: ReadonlyArray<{ pk: number }>,
  placements: ReadonlyMap<number, { column: number; row: number }>,
): string {
  return visible
    .map((card) => {
      const place = placements.get(card.pk);
      return place ? `${card.pk}@${place.row}.${place.column}` : `${card.pk}@-`;
    })
    .join("|");
}

function prefersReducedMotion(): boolean {
  if (typeof globalThis.matchMedia !== "function") return false;
  return globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Num tablet carregado o quadro atrasa e a animação dura mais que o CSS diz: passado o
 *  prazo, a trava confere se algum ticket ainda se move e, se sim, espera mais um
 *  pouco. Nunca além deste teto, para a grade não ficar surda se a animação travar. */
export const KDS_GRID_SETTLE_RECHECK_MS = 100;
export const KDS_GRID_SETTLE_MAX_MS = 3000;

/** As classes que o `TransitionGroup` põe no ticket enquanto ele entra, sai ou desliza. */
export const KDS_GRID_MOVING_SELECTOR =
  ".kds-card-move, .kds-card-enter-active, .kds-card-leave-active";

/** `settling` fica verdadeiro do instante em que a grade muda até ela se acomodar;
 *  `guard(fn)` só deixa o ato passar com a grade parada. `stillMoving` diz se algum
 *  ticket ainda está em movimento na tela. Sem animação (movimento reduzido) não há o
 *  que esperar. */
export function useKdsGridSettle(
  signature: WatchSource<string>,
  options: { settleMs?: number; stillMoving?: () => boolean } = {},
) {
  const settleMs = options.settleMs ?? KDS_GRID_SETTLE_MS;
  const settling = ref(false);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let startedAt = 0;

  function release() {
    timer = null;
    const waited = Date.now() - startedAt;
    if (options.stillMoving?.() && waited < KDS_GRID_SETTLE_MAX_MS) {
      timer = setTimeout(release, KDS_GRID_SETTLE_RECHECK_MS);
      return;
    }
    settling.value = false;
  }

  function settle() {
    if (prefersReducedMotion() || settleMs <= 0) return;
    settling.value = true;
    startedAt = Date.now();
    if (timer) clearTimeout(timer);
    timer = setTimeout(release, settleMs);
  }

  // `sync`: a trava liga no mesmo instante em que a fila muda, antes do DOM se mexer,
  // para nenhum toque daquele quadro passar.
  watch(
    signature,
    (next, previous) => {
      if (previous !== undefined && next !== previous) settle();
    },
    { flush: "sync" },
  );

  onScopeDispose(() => {
    if (timer) clearTimeout(timer);
  });

  function guard(act: () => unknown) {
    if (settling.value) return;
    act();
  }

  return { settling: readonly(settling), guard };
}
