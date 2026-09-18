// Publica no `:root` o tamanho do que a pessoa REALMENTE vê — para que caixa e folha
// não fiquem atrás do teclado virtual.
//
// Plugin da layer: vale para os oito apps de operador sem nenhum deles montar nada. A
// conta mora em `utils/visualViewport.ts` e é testada lá; aqui só escutamos o navegador
// e escrevemos as variáveis. Quem as consome é `operator-base.css`, e só as caixas e
// folhas — nenhuma outra tela muda de posição por causa disto.
//
// ⚠️ Com o teclado fechado as variáveis voltam a `100dvh` / `0px`, que é exatamente o
// que o CSS já fazia. Isto é de propósito: nada na tela se mexe enquanto ninguém está
// digitando, e a matriz visual não vê diferença nenhuma.
//
// ⚠️ `visualViewport` pode não existir (navegador antigo, ambiente de teste). Sem ela o
// plugin não faz nada e o sistema continua como está — degradação, nunca erro.
import { viewportVariables } from "../utils/visualViewport";

export default defineNuxtPlugin(() => {
  const viewport = window.visualViewport;
  if (!viewport) return;

  let frame = 0;
  const apply = () => {
    frame = 0;
    const variables = viewportVariables({
      layoutHeight: window.innerHeight,
      visualHeight: viewport.height,
      offsetTop: viewport.offsetTop,
    });
    for (const [name, value] of Object.entries(variables)) {
      document.documentElement.style.setProperty(name, value);
    }
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
