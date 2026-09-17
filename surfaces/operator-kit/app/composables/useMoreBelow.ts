import { measureBottomObstruction } from "./useNextFocus"
import { hintOffset, shouldHint } from "../presentation/moreBelow"

/**
 * Tem mais abaixo — observa o fim do conteúdo e diz se a dica deve aparecer.
 *
 * O sentinela é um elemento de 1px no fim do conteúdo rolável. Enquanto ele
 * não entra na área visível, há coisa abaixo. IntersectionObserver em vez de
 * contas de rolagem: reage de graça a redimensionamento, a teclado virtual e a
 * conteúdo que cresce (um toggle que abre), sem ouvinte de scroll.
 *
 * `offset` põe a dica logo acima do que flutua na base, lendo o mesmo fato que
 * o próximo foco usa (`data-focus-obstruction`).
 */
export function useMoreBelow() {
  const sentinel = ref<HTMLElement | null>(null);
  const endReached = ref(true);
  const obstruction = ref(0);
  const offset = computed(() => hintOffset(obstruction.value));
  let observer: IntersectionObserver | null = null;

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
    observer = new IntersectionObserver(entries => {
      const entry = entries[entries.length - 1];
      if (entry) endReached.value = entry.isIntersecting;
    }, { rootMargin: `0px 0px -${Math.round(Math.max(0, obstaculo))}px 0px` });
    observer.observe(el);
  }

  function measure() {
    if (!import.meta.client) return;
    const medido = measureBottomObstruction();
    if (Math.abs(medido - obstruction.value) < 1) return;
    obstruction.value = medido;
    observe(sentinel.value, medido);
  }

  watch(sentinel, el => observe(el, obstruction.value), { immediate: true });
  // O que flutua na base muda de altura (o botão vira "Autorizar e validar", o
  // aviso do mínimo aparece): a folga e a área de observação acompanham.
  useEventListener(() => (import.meta.client ? window : null), 'resize', measure);
  onMounted(measure);
  onBeforeUnmount(() => {
    observer?.disconnect();
    observer = null;
  });

  return { sentinel, visible, offset, measure };
}
