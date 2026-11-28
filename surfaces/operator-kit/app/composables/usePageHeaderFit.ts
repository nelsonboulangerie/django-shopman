// A barra do topo que cabe (dono, 07/11/2026: "parece coisa de amador; não pode
// acontecer, nem nessa tela nem em nenhuma"). No cabeçalho do pedido do Gestor, a
// 1360 px, a seta "Pedido anterior" se desenhava por cima da hora e a busca por cima do
// "Próximo pedido": a coluna da esquerda do `DashboardNavbar` é `min-w-0` (encolhe
// abaixo do conteúdo) e nada nela encolhia junto, então o conteúdo vazava por baixo da
// busca. A largura que sobra depende do que cada tela põe na barra (título, selo,
// anterior/próximo, ações), e nenhum degrau fixo de largura acerta todas.
//
// Aqui a barra mede a si mesma e cede em degraus, nesta ordem:
//   1. `full`    tudo na linha, a busca inteira (o selo de atualização já encolhe sozinho
//                até o ícone, `OperatorLiveStatus`);
//   2. `compact` a busca vira a lupa (a mesma do celular), e a linha devolve a largura;
//   3. `wrap`    ainda não cabe: as ações descem para uma segunda linha, à direita.
// Nunca sobrepõe. O CSS de cada degrau mora no `OperatorPageHeader.vue`.
//
// A medida roda no `ResizeObserver` (entregue depois do layout e antes da pintura: sem
// piscar) e quando o conteúdo da barra muda (o rótulo do primário, o status do pedido).
import { onBeforeUnmount, onMounted, type Ref } from "vue";

export type PageHeaderFit = "full" | "compact" | "wrap";
export const PAGE_HEADER_FIT_STEPS: readonly PageHeaderFit[] = ["full", "compact", "wrap"];

/** O título quebrou em mais de uma linha (ele pode, `app.config`: "cópia não se corta";
 *  mas espremido ao lado de uma busca inteira é a busca que cede, não o título). */
export function pageHeaderTitleWraps(root: HTMLElement): boolean {
  const title = root.querySelector<HTMLElement>('[data-slot="title"]');
  if (!title || title.clientWidth === 0) return false;
  // Só as caixas do TEXTO, linha a linha: a caixa de um elemento em bloco cobre as duas
  // linhas e as esconderia. Duas caixas com topos 2 px diferentes (o texto e o selo ao
  // lado) são a mesma linha: é linha nova só a que tem o meio fora das que já vieram.
  const lines: { top: number; bottom: number }[] = [];
  const range = document.createRange();
  const walker = document.createTreeWalker(title, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.textContent?.trim()) continue;
    range.selectNodeContents(node);
    for (const box of range.getClientRects()) {
      if (box.width <= 0 || box.height <= 0) continue;
      const middle = box.top + box.height / 2;
      if (!lines.some((line) => middle >= line.top && middle <= line.bottom)) {
        lines.push({ top: box.top, bottom: box.top + box.height });
      }
    }
  }
  return lines.length > 1;
}

/** Algum filho direto da barra (esquerda, centro, direita), ou ela mesma, desenha
 *  além da própria caixa. Meio pixel de folga para o layout fracionário. */
export function pageHeaderOverflows(root: HTMLElement): boolean {
  if (root.scrollWidth > root.clientWidth + 1) return true;
  return [...root.children].some(
    (child) => child instanceof HTMLElement && child.clientWidth > 0 && child.scrollWidth > child.clientWidth + 1,
  );
}

/** Põe a barra no primeiro degrau em que ela cabe e devolve o degrau. Síncrono: cada
 *  troca de atributo força o layout na leitura seguinte. */
export function fitPageHeader(root: HTMLElement): PageHeaderFit {
  for (const step of PAGE_HEADER_FIT_STEPS) {
    root.dataset.pageHeaderFit = step;
    if (step === "wrap") return step;
    if (!pageHeaderOverflows(root) && !pageHeaderTitleWraps(root)) return step;
  }
  return "wrap";
}

/** `target` é a barra (`[data-operator-page-header]`) ou um ancestral dela. */
export function usePageHeaderFit(target: Readonly<Ref<HTMLElement | null>>) {
  let resize: ResizeObserver | null = null;
  let mutation: MutationObserver | null = null;
  let frame = 0;

  function element(): HTMLElement | null {
    const value = target.value;
    if (!value) return null;
    return value.matches("[data-operator-page-header]")
      ? value
      : value.querySelector<HTMLElement>("[data-operator-page-header]");
  }
  function run() {
    const root = element();
    if (root) fitPageHeader(root);
  }
  function schedule() {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      run();
    });
  }

  onMounted(() => {
    const root = element();
    if (!root) return;
    run();
    if (typeof ResizeObserver !== "undefined") {
      resize = new ResizeObserver(run);
      resize.observe(root);
    }
    if (typeof MutationObserver !== "undefined") {
      // Só conteúdo (texto e nós): o atributo do degrau, que esta função escreve, fica
      // de fora, senão ela se chamaria a si mesma.
      mutation = new MutationObserver(schedule);
      mutation.observe(root, { childList: true, characterData: true, subtree: true });
    }
    // A fonte da casa chega depois do primeiro desenho e muda a largura dos rótulos.
    void document.fonts?.ready.then(run);
  });
  onBeforeUnmount(() => {
    resize?.disconnect();
    mutation?.disconnect();
    if (frame) cancelAnimationFrame(frame);
  });

  return { refit: run };
}
