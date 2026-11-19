// Aquecimento da montagem, fora do primeiro teste (#2762).
//
// O PRIMEIRO `mountSuspended` de um arquivo paga o que os seguintes não pagam:
// importa a raiz do app (`#build/root-component.mjs`, que traz o `app.vue` e a
// casca do operador inteira), resolve a rota e faz a primeira renderização a
// frio. Nos arquivos que o Vitest roda primeiro, o servidor do Vite ainda não
// transformou nada disso, e a conta caía inteira no primeiro teste do arquivo,
// fosse ele qual fosse. Medido em 19/11/2026, para um teste que sem essa conta
// leva 0,5 s ou menos: 1,3 a 2,5 s no `ubuntu-latest` (7 execuções) e 1,3 a
// 5,4 s no `macos-15` em que a fila rodava (25 execuções, quatro delas
// reprovadas pelo teto de 5 s).
//
// Sem cache, o Vitest ordena os arquivos do maior para o menor e sobe um worker
// a menos que os núcleos da máquina. O primeiro lote são os dois maiores
// arquivos de teste no `macos-15` (3 núcleos) e os três maiores no
// `ubuntu-latest` (4 núcleos). Os dois maiores montam componente e chamam
// `warmUpMount()`: `PosPaymentWorkspace.test.ts` e `pages/preorders.test.ts`. O
// terceiro, `usePosSale.sale.test.ts`, testa composable e não monta nada.
// Arquivo que monta componente e crescer até entrar nesse lote chama também.
//
// Por que por arquivo, e não no setup do projeto (a tentativa de pôr no setup
// reprovou a suíte inteira, run 44525588946):
// - o `@nuxt/test-utils` põe o setup do app NA FRENTE do entry dele, então um
//   `beforeAll` de `componentSetup.ts` roda antes do boot do Nuxt e não tem app
//   onde montar;
// - 34 dos 103 arquivos nunca montam componente, e 27 deles simulam
//   `vue-sonner` sem `Toaster`: obrigá-los a importar a raiz do app quebra o
//   arquivo.
//
// O hook registrado dentro do arquivo de teste roda depois dos hooks de setup,
// isto é, com o Nuxt já de pé. O teto dele é o `hookTimeout` do projeto de
// componente (`vitest.config.ts`), que tem a conta ao lado.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { beforeAll } from "vitest";
import { defineComponent, h } from "vue";

const Blank = defineComponent({ name: "MountWarmup", render: () => h("div") });

export function warmUpMount(): void {
  beforeAll(async () => {
    const startedAt = performance.now();
    const wrapper = await mountSuspended(Blank);
    wrapper.unmount();
    // Fica no log da CI de propósito: é a medida, a cada execução, de quanto o
    // primeiro mount custa naquele runner (e de quão perto do teto ele chega).
    console.info(`[aquecimento da montagem] ${Math.round(performance.now() - startedAt)} ms`);
  });
}
