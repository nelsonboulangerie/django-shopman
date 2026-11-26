import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import { defineVitestProject } from "@nuxt/test-utils/config";

const appAlias = {
  "~": fileURLToPath(new URL("./app", import.meta.url)),
  "@": fileURLToPath(new URL("./app", import.meta.url)),
};

export default defineConfig({
  test: {
    projects: [
      // Unit: presentation pura, composables (com $fetch mockado) e BFF. Env `node`.
      {
        resolve: { alias: appAlias },
        test: {
          name: "unit",
          environment: "node",
          globals: true,
          include: ["tests/**/*.test.ts"],
          exclude: ["tests/components/**", "tests/composables/**", "tests/pages/**", "tests/e2e/**", "node_modules/**"],
        },
      },
      // Component: monta componentes Vue reais com auto-imports/composables do Nuxt
      // (mountSuspended). Env `nuxt` (happy-dom) — mais pesado, isolado aqui.
      //
      // `tests/pages/**` entra aqui porque uma PÁGINA também se monta, e há
      // regra que só a página decide: o fechamento do dia recebe da projection
      // os números da produção (precisa deles depois do registro) e escolhe não
      // mostrá-los antes, para a contagem ser cega. Testar isso pela projection
      // provaria o contrário do que interessa.
      await defineVitestProject({
        test: {
          name: "component",
          environment: "nuxt",
          globals: true,
          setupFiles: ["./tests/support/componentSetup.ts"],
          // O teto dos HOOKS é declarado, com a conta (#2762, medido em 19/11/2026
          // nos runners gratuitos do GitHub). O teto de cada TESTE fica no padrão
          // do Vitest (5 s) de propósito NA CI: teste não espera ambiente, e lá ele
          // continua pegando o teste que ficou lento.
          //
          // NA MÁQUINA LOCAL (`make preflight`), 15 s (#3645, 26/11/2026). Medido:
          // primeiro o vazamento (os testes não desmontavam; `tests/support/
          // mountedWrappers.ts`), que levava o arquivo do pagamento de 182 s para
          // 7,5 s. O que sobrou é falta de CPU, não relógio: no preflight a máquina de
          // 8 núcleos/8 GB divide as vagas com outras worktrees (uma delas com
          // `pytest -n auto` ao lado, carga 12 a 14), a etapa do PDV vai de 65 s a
          // 194 s, e 9 testes diferentes por rodada, espalhados por 7 arquivos,
          // passam de 5 s; um teste que monta e clica em 100 ms sozinho chegou a
          // 28 s com carga 24. Teto maior só aqui, onde a carga é dos outros.
          //
          // O `beforeAll` do `@nuxt/test-utils` sobe o app Nuxt em cada arquivo e
          // não aceita teto próprio: vale o `hookTimeout` do projeto, 10 s no
          // padrão. Com o Vite já quente ele leva em torno de 0,6 s (p90 de 1,5 s).
          // No primeiro arquivo que chega a ele, com o Vite frio, levou 6,0 s,
          // 9,4 s e 9,5 s em três execuções no `ubuntu-latest`, e passou de 10 s em
          // quatro execuções da CI, que caíram com "Hook timed out in 10000ms"
          // (uma no `ubuntu-latest` e duas no `macos-15` em 19/11, uma no
          // `macos-15` em 16/11).
          //
          // A conta: o arranque a frio fica em 5,5% da duração do passo. São 9,5 s
          // no passo de 168 s do `ubuntu-latest`, onde a fila roda desde o #2651, e
          // 17 s projetados para o passo mais lento já medido (314 s, no `macos-15`
          // em que a fila rodava até então). 60 s é seis vezes o maior valor medido
          // e três vezes e meia o projetado. O mesmo teto cobre o aquecimento da
          // montagem (`tests/support/mountWarmup.ts`), que mediu 1,2 a 1,9 s.
          hookTimeout: 60_000,
          testTimeout: process.env.CI ? 5_000 : 15_000,
          include: [
            "tests/components/**/*.test.ts",
            "tests/composables/**/*.test.ts",
            "tests/pages/**/*.test.ts",
          ],
        },
      }),
    ],
  },
});
