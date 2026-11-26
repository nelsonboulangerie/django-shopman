import { config } from "@vue/test-utils";

// Todo teste de componente do PDV desmonta o que montou (#3645).
//
// Medido em 26/11/2026: quase nenhum arquivo desmontava (`PosPaymentWorkspace.test.ts`
// montava 126 vezes e desmontava 9; `pages/preorders.test.ts`, 109 e 1). Os
// componentes antigos ficavam vivos até o fim do arquivo, com os observadores de
// estado compartilhado reagindo em todos eles, e cada teste custava mais que o
// anterior. Sozinho, `PosPaymentWorkspace.test.ts` levava 182 s (mediana de 703 ms por
// teste); numa máquina carregada (preflight completo, carga 14) oito testes dele
// passavam dos 5 s, um deles o "Pix sozinho" da issue. Desmontando, 7,5 s (mediana de
// 50 ms, pior teste 252 ms, com carga 17). Não era relógio nem animação.
//
// O `mountSuspended` do `@nuxt/test-utils` monta pelo Vue Test Utils, então o plugin
// de `VueWrapper` vê todo wrapper criado. O desmonte tolera nó já removido: arquivo
// que limpa o `body` no próprio `afterEach` roda ANTES deste (o do setup é o de fora),
// e aí o Vue não acha mais os nós teleportados. Quem limpa o `body` chama
// `unmountMounted()` antes, para o desmonte acontecer inteiro.
const mounted = new Set<{ unmount: () => void }>();

config.plugins.VueWrapper.install((wrapper) => {
  mounted.add(wrapper);
  return {};
});

export function unmountMounted(): void {
  for (const wrapper of mounted) {
    try {
      wrapper.unmount();
    } catch {
      // Já desmontado pelo próprio teste, ou o `body` já foi limpo.
    }
  }
  mounted.clear();
}
