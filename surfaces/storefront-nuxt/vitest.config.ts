import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'
import { defineVitestProject } from '@nuxt/test-utils/config'

const appAlias = {
  '~': fileURLToPath(new URL('./app', import.meta.url)),
  '@': fileURLToPath(new URL('./app', import.meta.url))
}

export default defineConfig({
  test: {
    projects: [
      // Unit: presentation pura, composables (com $fetch mockado) e BFF Nitro.
      // Env `node` — rápido, sem DOM, sem custo de Nuxt.
      {
        resolve: { alias: appAlias },
        test: {
          name: 'unit',
          environment: 'node',
          globals: true,
          include: ['tests/**/*.test.ts'],
          exclude: ['tests/components/**', 'tests/composables/**', 'tests/pages/**', 'tests/e2e/**', 'node_modules/**']
        }
      },
      // Component: monta componentes Vue reais com auto-imports/composables do
      // Nuxt (mountSuspended). Env `nuxt` (happy-dom) — mais pesado, isolado aqui.
      //
      // `tests/pages/**` entra aqui porque há regra que só a PÁGINA decide. O
      // checkout é o caso: o campo Nome desmontava sozinho na primeira tecla
      // porque a condição de exibição lia o conteúdo do próprio campo. Nenhum
      // teste de projection ou de utilitário puro alcança isso — é preciso
      // montar a tela e digitar nela.
      await defineVitestProject({
        test: {
          name: 'component',
          environment: 'nuxt',
          globals: true,
          include: [
            'tests/components/**/*.test.ts',
            'tests/composables/**/*.test.ts',
            'tests/pages/**/*.test.ts'
          ]
        }
      })
    ]
  }
})
