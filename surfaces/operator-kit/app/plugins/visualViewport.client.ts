// Publica no `:root` o tamanho do que a pessoa REALMENTE vê — para que caixa e folha
// não fiquem atrás do teclado virtual.
//
// Plugin da layer: vale para os oito apps de operador sem nenhum deles montar nada. A
// conta mora em `utils/visualViewport.ts` e é testada lá; aqui só escutamos o navegador
// e escrevemos as variáveis. Quem as consome é `operator-base.css`, e só as caixas e
// folhas — nenhuma outra tela muda de posição por causa disto.
//
// ⚠️ Com o teclado fechado o atributo `data-keyboard` some do `<html>` e NENHUMA regra
// nova entra em vigor. Isto é de propósito: nada na tela se mexe enquanto ninguém está
// digitando, e a matriz visual das nove superfícies não vê diferença nenhuma.
//
// ⚠️ `visualViewport` pode não existir (navegador antigo, ambiente de teste). Sem ela o
// plugin não faz nada e o sistema continua como está — degradação, nunca erro.
import { viewportState } from "../utils/visualViewport";

export default defineNuxtPlugin(() => {
  const viewport = window.visualViewport;
  if (!viewport) return;

  let frame = 0;
  const apply = () => {
    frame = 0;
    const state = viewportState({
      layoutHeight: window.innerHeight,
      visualHeight: viewport.height,
      offsetTop: viewport.offsetTop,
    });
    const root = document.documentElement;
    for (const [name, value] of Object.entries(state.variables)) {
      root.style.setProperty(name, value);
    }
    // ⚠️ É o ATRIBUTO que liga o CSS. Com o teclado fechado nenhuma regra nova entra
    // em vigor — `top: 50%` continua sendo `top: 50%`, e não uma conta equivalente
    // escrita de outro jeito. Nove superfícies montam esta folha; mudança inerte
    // precisa ser inerte de verdade.
    if (state.covered) root.dataset.keyboard = "open";
    else delete root.dataset.keyboard;
  };
  // O iOS dispara `resize`/`scroll` do viewport visual em rajada enquanto o teclado
  // sobe. Um quadro por rajada basta, e evita escrever no `style` dezenas de vezes.
  const schedule = () => {
    if (frame) return;
    frame = requestAnimationFrame(apply);
  };

  apply();
  viewport.addEventListener("resize", schedule, { passive: true });
  viewport.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("orientationchange", schedule, { passive: true });
});
