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
