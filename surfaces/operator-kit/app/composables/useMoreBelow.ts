import { measureBottomObstruction } from "./useNextFocus"
import { CONTAINED_HINT_REACH, HINT_REACH, endReached as fimAlcancado, hintOffset, shouldHint } from "../presentation/moreBelow"
import { FOCUS_OBSTRUCTION_ATTRIBUTE } from "../presentation/nextFocus"

/**
 * Tem mais abaixo — observa o fim do conteúdo e diz se a dica deve aparecer.
 *
 * O sentinela é um elemento de 1px no fim do conteúdo rolável. Enquanto ele
 * não entra na área visível, há coisa abaixo. IntersectionObserver em vez de
 * contas de rolagem: reage de graça a redimensionamento, a teclado virtual e a
 * conteúdo que cresce (um toggle que abre), sem ouvinte de scroll.
 *
 * `offset` apoia a base da dica no topo do que flutua na base, lendo o mesmo
 * fato que o próximo foco usa (`data-focus-obstruction`).
 *
 * `scrollToEnd` é o que o toque na dica faz: leva até o fim do conteúdo. O
 * destino é o próprio sentinela, alinhado pela borda de baixo — e como ele
 * carrega `scroll-margin-bottom` igual ao obstáculo, o fim para ACIMA do card,
 * não atrás dele.
 */
export interface UseMoreBelowOptions {
  /**
   * A dica mora DENTRO de um contêiner que rola (uma coluna lateral), não na janela.
   * A área observada é a do contêiner: o que flutua fora dele (o bloco de ação e o pé
   * da comanda) já está fora da área por construção, sem medida de obstrução.
   */
  contained?: boolean;
}

/** O ancestral que rola (o contêiner da dica contida). */
function scrollParent(el: HTMLElement | null): HTMLElement | null {
  for (let node = el?.parentElement ?? null; node; node = node.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(node).overflowY)) return node;
  }
  return null;
}

export function useMoreBelow(options: UseMoreBelowOptions = {}) {
  const contained = Boolean(options.contained);
  const reach = contained ? CONTAINED_HINT_REACH : HINT_REACH;
  const sentinel = ref<HTMLElement | null>(null);
  const endReached = ref(true);
  const obstruction = ref(0);
  const offset = computed(() => hintOffset(obstruction.value));
  let observer: IntersectionObserver | null = null;
  let obstructionSizes: ResizeObserver | null = null;

  const visible = computed(() => shouldHint(endReached.value));

  // O FIM SÓ CONTA ACIMA DO OBSTÁCULO. Entrar na tela não basta: o sentinela
  // pode estar dentro da área visível e, ainda assim, atrás do card de ação ou
  // da navegação inferior. Medido no checkout: sentinela em 626 numa tela de
  // 667, com o card cobrindo de 490 a 587 — a dica sumia com conteúdo ainda
  // escondido. `rootMargin` negativo embaixo encolhe a área de observação
  // exatamente pelo que flutua ali.
  function observe(el: HTMLElement | null, obstaculo: number) {
    observer?.disconnect();
    observer = null;
    if (!import.meta.client || !el || typeof IntersectionObserver !== "function") return;
    if (contained) {
      const root = scrollParent(el);
      observer = new IntersectionObserver(entries => {
        const entry = entries[entries.length - 1];
        if (!entry) return;
        const limite = entry.rootBounds?.bottom ?? root?.getBoundingClientRect().bottom ?? window.innerHeight;
        chegouAoFim(entry.boundingClientRect.top, limite);
      }, { root, threshold: [0, 1] });
      observer.observe(el);
      return;
    }
    const recuo = Math.round(Math.max(0, obstaculo));
    observer = new IntersectionObserver(entries => {
      const entry = entries[entries.length - 1];
      if (!entry) return;
      // ⚠️ `isIntersecting` É FALSO DOS DOIS LADOS: antes de o sentinela subir
      // para dentro da área observada E depois de ele sair por cima. Com ele, a
      // dica SUMIA no fim do conteúdo e VOLTAVA assim que a pessoa rolava para
      // dentro do rodapé do site — dizendo "tem mais abaixo" no fim da página.
      // Medido no login em 375x667: sentinela em 752 (dica certa), 37 (some,
      // certo), -11 (voltava). A pergunta certa não é "está à vista", é "o fim
      // do conteúdo já passou da linha de baixo da área observada".
      // A área observada desce `HINT_REACH` além da linha de baixo: o resto que
      // cabe sob a própria dica não ganha dica (`endReached`).
      const limite = (entry.rootBounds?.bottom ?? window.innerHeight - recuo + HINT_REACH) - HINT_REACH;
      chegouAoFim(entry.boundingClientRect.top, limite);
    }, { rootMargin: `0px 0px ${HINT_REACH - recuo}px 0px` });
    observer.observe(el);
  }

  /** O fim chegou quando o sentinela está na linha de baixo da área visível, ou a menos de uma dica dela. */
  function chegouAoFim (topoDoSentinela: number, limite: number) {
    endReached.value = fimAlcancado(topoDoSentinela, limite, reach);
  }

  // ⚠️ SALTO NÃO DISPARA OBSERVADOR. O IntersectionObserver só avisa quando o
  // elemento CRUZA a fronteira; num salto direto para o fim (âncora, tecla End,
  // restauração de rolagem ao voltar) o sentinela vai de "abaixo da tela" para
  // "acima dela" sem cruzar nada, e nenhum callback acontece — a dica ficava
  // pendurada no fim da página. `scrollend` cobre exatamente esse caso e não
  // custa nada por quadro, porque só dispara quando a rolagem para. Onde ele
  // não existir, vale o observador sozinho, que é o comportamento de antes.
  function reavaliar () {
    const el = sentinel.value;
    if (!el) return;
    if (contained) {
      const root = scrollParent(el);
      chegouAoFim(el.getBoundingClientRect().top, root?.getBoundingClientRect().bottom ?? window.innerHeight);
      return;
    }
    chegouAoFim(el.getBoundingClientRect().top, window.innerHeight - obstruction.value);
  }

  function measure() {
    if (!import.meta.client) return;
    if (contained) {
      // A coluna muda de altura sem a janela mexer (o bloco de ação abre e fecha).
      reavaliar();
      return;
    }
    const medido = measureBottomObstruction();
    if (Math.abs(medido - obstruction.value) < 1) return;
    obstruction.value = medido;
    observe(sentinel.value, medido);
  }

  // O DEGRADÊ ENCOSTA NO CARD, ENTÃO A MEDIDA NÃO PODE ENVELHECER. Enquanto a
  // dica flutuava 12px acima do obstáculo, uma medida velha só deslocava um
  // pouco a pílula. Agora que a base dela se apoia no topo do card, medida
  // velha reabre exatamente a faixa de conteúdo cru que se foi consertar. O
  // `resize` da janela não cobre o caso comum: o card cresce sozinho quando o
  // rótulo do botão muda ou o motivo aparece, sem a janela mexer.
  function watchObstructionSizes() {
    obstructionSizes?.disconnect();
    obstructionSizes = null;
    if (!import.meta.client || typeof ResizeObserver !== "function") return;
    obstructionSizes = new ResizeObserver(measure);
    for (const el of document.querySelectorAll(`[${FOCUS_OBSTRUCTION_ATTRIBUTE}]`)) {
      obstructionSizes.observe(el);
    }
  }

  // O toque na dica leva até o fim do conteúdo — o pedido é esse, e o destino é
  // o mesmo sentinela que decide se a dica existe. Alinhado pela borda de baixo
  // e com a margem de rolagem que o desenho aplica, o fim para acima do card.
  function scrollToEnd(behavior: ScrollBehavior = "smooth") {
    const el = sentinel.value;
    if (!import.meta.client || !el || typeof el.scrollIntoView !== "function") return;
    el.scrollIntoView({ block: "end", behavior });
  }

  watch(sentinel, el => observe(el, obstruction.value), { immediate: true });
  // O que flutua na base muda de altura (o botão vira "Autorizar e validar", o
  // aviso do mínimo aparece): a folga e a área de observação acompanham.
  useEventListener(() => (import.meta.client ? window : null), 'resize', measure)
  useEventListener(() => (import.meta.client ? window : null), 'scrollend', reavaliar);
  // ⚠️ DENTRO DE UM CONTÊINER ROLÁVEL O OBSERVADOR NÃO BASTA. O shell da suíte rola o
  // `<main>`, não a janela: o sentinela é recortado pelo contêiner, a área estendida
  // por `HINT_REACH` não o alcança, e o resto de 30 px que cabe sob a dica nunca
  // dispara callback (medido na Central a 390x600: a dica ficava). A rolagem de um
  // elemento não borbulha até a janela; na fase de captura do documento ela chega.
  // Um quadro por rolagem, no máximo.
  let quadro = 0;
  function reavaliarNoQuadro () {
    if (quadro) return;
    quadro = requestAnimationFrame(() => {
      quadro = 0;
      reavaliar();
    });
  }
  useEventListener(() => (import.meta.client ? document : null), 'scroll', reavaliarNoQuadro, { capture: true, passive: true });
  let containerSize: ResizeObserver | null = null;
  onMounted(() => {
    measure();
    if (contained) {
      const root = scrollParent(sentinel.value);
      if (root && typeof ResizeObserver === "function") {
        containerSize = new ResizeObserver(() => reavaliar());
        containerSize.observe(root);
      }
      return;
    }
    watchObstructionSizes();
  });
  onBeforeUnmount(() => {
    if (quadro) cancelAnimationFrame(quadro);
    observer?.disconnect();
    observer = null;
    obstructionSizes?.disconnect();
    obstructionSizes = null;
    containerSize?.disconnect();
    containerSize = null;
  });

  return { sentinel, visible, offset, measure, scrollToEnd };
}
