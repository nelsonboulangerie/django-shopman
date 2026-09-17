import type { MaybeRefOrGetter } from "vue";
import {
  FOCUS_CONTROL_ATTRIBUTE,
  FOCUS_OBSTRUCTION_ATTRIBUTE,
  focusTargetSelector,
  needsInitialReveal,
  revealPlan,
  type RevealOptions,
  type RevealPlan,
} from "../presentation/nextFocus";

// O QUE FLUTUA NA BASE DA TELA (card de ação, barra) come área utilizável.
// Vive no escopo do módulo porque dois mecanismos leem o mesmo fato: o próximo
// foco, para saber se o bloco está mesmo à vista, e a dica de "tem mais
// abaixo", para flutuar logo acima dele.
//
// Só conta o que está ancorado embaixo: um obstáculo que rolou para fora do
// caminho não obstrui nada.
export function measureBottomObstruction(): number {
  if (!import.meta.client) return 0;
  let maior = 0;
  for (const el of document.querySelectorAll<HTMLElement>(`[${FOCUS_OBSTRUCTION_ATTRIBUTE}]`)) {
    const rect = el.getBoundingClientRect();
    if (rect.height <= 0) continue;
    if (rect.bottom < window.innerHeight / 2) continue;
    maior = Math.max(maior, window.innerHeight - rect.top);
  }
  return maior;
}

export type RevealTarget = string | Element | (() => Element | null | undefined) | null | undefined;

// Quem já é focável por natureza não ganha `tabindex=-1`: em input/button isso
// tiraria o controle da ordem do Tab.
const NATIVELY_FOCUSABLE = "input, select, textarea, button, a[href], [contenteditable], [tabindex]";

// Próximo foco — a página diz QUAL é o foco; o mecanismo leva a página até ele.
//
//   const { reveal } = useNextFocus(() => currentSection.value)
//   <section data-focus-target="when">…</section>
//
// A cada mudança da chave, o bloco `[data-focus-target="<chave>"]` vai para a
// linha de foco (topo da área visível, respeitando o `scroll-margin-top` do
// bloco) e recebe o foco de teclado: o próprio bloco (focável via tabindex=-1,
// para o leitor de tela anunciar a seção) ou, se o bloco marcar um controle com
// `data-focus-control`, esse controle — o caso de "a próxima ação é digitar".
//
// `reveal(alvo, opções)` é a forma imperativa para focos fora do fluxo (um erro
// que apareceu, um item que chegou). Aceita chave, elemento ou função que
// resolve o elemento depois do DOM assentar. Tela cujo foco é todo explícito
// (o PDV, com o modelo de teclado próprio) chama `useNextFocus()` sem fonte e
// usa só o `reveal`.
//
// Regras que fazem o mecanismo ser confiável em qualquer tela:
// - nunca roda no servidor;
// - espera o DOM refletir o estado (nextTick) e tolera bloco que ainda vai
//   montar (poucos quadros de espera — nunca fica rondando);
// - o pedido mais novo sempre vence: trocas rápidas não disputam, e o reveal
//   automático (agendado na renderização) passa na frente de um `reveal`
//   explícito pedido no mesmo handler — a página se organiza em torno do
//   novo foco, não do detalhe;
// - na montagem só rola se o foco estiver fora da área visível;
// - respeita `prefers-reduced-motion`.
//
// Espelhado em `storefront-nuxt/app/composables/useNextFocus.ts`.
export function useNextFocus(source?: MaybeRefOrGetter<string | null | undefined>, options: RevealOptions = {}) {
  let ticket = 0;

  function resolveTarget(target: RevealTarget): HTMLElement | null {
    if (!target) return null;
    if (typeof target === "function") return (target() as HTMLElement | null | undefined) || null;
    if (typeof target !== "string") return target as HTMLElement;
    return document.querySelector<HTMLElement>(focusTargetSelector(target));
  }

  function focusControl(block: HTMLElement) {
    const control = block.querySelector<HTMLElement>(`[${FOCUS_CONTROL_ATTRIBUTE}]`) || block;
    if (control === block && !block.matches(NATIVELY_FOCUSABLE)) block.setAttribute("tabindex", "-1");
    control.focus({ preventScroll: true });
  }

  function scrollTo(block: HTMLElement, plan: RevealPlan) {
    if (typeof block.scrollIntoView !== "function") return;
    block.scrollIntoView({ block: plan.align, behavior: plan.behavior });
  }

  function reducedMotion(): boolean {
    return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function revealNow(block: HTMLElement, overrides: RevealOptions, initial: boolean) {
    const plan = revealPlan({ ...options, ...overrides }, reducedMotion());
    if (initial) {
      const obstacle = measureBottomObstruction();
      const rect = block.getBoundingClientRect();
      if (
        !needsInitialReveal({
          top: rect.top,
          bottom: rect.bottom,
          viewportHeight: window.innerHeight,
          obstructedBottom: obstacle,
        })
      )
        return;
      // A CHEGADA TAMBÉM VAI PARA A LINHA DE FOCO, não para o mínimo necessário.
      // Rolar é, em si, o aviso de que havia algo acima: quem quiser conferir
      // sobe com um gesto. Parar no meio do caminho custaria a promessa que
      // sustenta o mecanismo — o bloco de trabalho sempre no mesmo lugar.
      //
      // A margem embaixo continua valendo: sem ela um bloco curto encosta no
      // card flutuante.
      block.style.scrollMarginBottom = `${obstacle}px`;
    }
    if (plan.focus) focusControl(block);
    scrollTo(block, plan);
  }

  // Bloco gated por dado assíncrono pode montar um quadro depois da chave mudar.
  // Poucos quadros de tolerância; o pedido mais novo (ticket) cancela o anterior.
  function schedule(target: RevealTarget, overrides: RevealOptions, initial: boolean) {
    if (!import.meta.client) return;
    const mine = ++ticket;
    let framesLeft = 12;
    const attempt = () => {
      if (mine !== ticket) return;
      const block = resolveTarget(target);
      if (block) {
        revealNow(block, overrides, initial);
        return;
      }
      if (framesLeft-- > 0) requestAnimationFrame(attempt);
    };
    void nextTick(attempt);
  }

  function reveal(target: RevealTarget, overrides: RevealOptions = {}) {
    schedule(target, overrides, false);
  }

  if (source !== undefined) {
    watch(
      () => toValue(source),
      (key, previous) => {
        if (!key || key === previous) return;
        schedule(key, {}, false);
      },
      { flush: "post" },
    );

    onMounted(() => {
      schedule(toValue(source), {}, true);
    });
  }

  onBeforeUnmount(() => {
    ticket++;
  });

  return { reveal };
}
