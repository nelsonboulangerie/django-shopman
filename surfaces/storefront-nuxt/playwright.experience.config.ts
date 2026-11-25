import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

// Comparação A/B supervisionada (OC-23, plano da Etapa II omnicanal §9.6): as jornadas
// essenciais do §5.1, escritas uma vez em tests/e2e/journeys/, rodadas contra uma pilha
// de pé (a mesma das jornadas da cliente, scripts/run_storefront_journeys.sh) para UMA
// versão por vez. Quem roda as duas e monta o relatório é scripts/run_experience_compare.sh
// (`make experience-compare`).
//
// A versão NÃO é escolhida aqui: o servidor decide (RuleConfig de ExperienceRule com a
// cliente da jornada dentro ou fora da coorte, gravada antes de o Django subir).
// EXPERIENCE_VARIANT só diz o que a rodada ESPERA ver; a primeira coisa que a suíte faz
// depois de entrar é conferir que o shell trouxe essa versão, e reprova se não trouxe.
const required = {
  JOURNEY_STORE_URL: 'a loja compilada da pilha (ex.: http://loja.jornadas.localhost:3190)',
  JOURNEY_OTP_FILE: 'o arquivo onde o Django da pilha entrega o código de entrada (SHOPMAN_E2E_OTP_FILE)',
  EXPERIENCE_VARIANT: 'a versão que o servidor deve ter decidido para a cliente da jornada (a ou b)'
} as const
const missing = Object.entries(required).filter(([name]) => !process.env[name])
if (missing.length) {
  throw new Error(
    'A comparação A/B roda pela pilha (scripts/run_experience_compare.sh). Faltam:\n' +
      missing.map(([name, what]) => `  ${name}: ${what}`).join('\n')
  )
}
if (!['a', 'b'].includes(process.env.EXPERIENCE_VARIANT!)) {
  throw new Error(`EXPERIENCE_VARIANT precisa ser a ou b (veio ${process.env.EXPERIENCE_VARIANT}).`)
}
if (!existsSync(dirname(process.env.JOURNEY_OTP_FILE!))) {
  throw new Error(`A pasta de JOURNEY_OTP_FILE não existe (${dirname(process.env.JOURNEY_OTP_FILE!)}).`)
}

const out = resolve(process.env.EXPERIENCE_OUT || 'test-results/experience-compare', process.env.EXPERIENCE_VARIANT!)
// A sessão da cliente, gravada pelo passo de entrada e usada pelas jornadas.
export const storageState = resolve(out, 'sessao.json')

// A cliente dirige a jornada a 375 px (o celular do §5.1); cada passo é auditado também
// a 320 e 390 px e no computador, pelo próprio passo (support/audit.ts).
export default defineConfig({
  testDir: './tests/e2e/journeys',
  // Uma rodada inteira numa pilha local carregada: o tempo aqui é de jornada.
  timeout: 600_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: resolve(out, 'playwright.json') }]],
  outputDir: resolve(out, 'playwright'),
  use: {
    baseURL: process.env.JOURNEY_STORE_URL!.replace(/\/$/, ''),
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
    trace: 'on',
    screenshot: 'only-on-failure',
    actionTimeout: 20_000,
    navigationTimeout: 60_000
  },
  projects: [
    {
      name: 'entrar',
      testMatch: /00-entrar\.setup\.ts$/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true }
    },
    {
      name: 'jornadas',
      testMatch: /\d\d-[a-z-]+\.spec\.ts$/,
      dependencies: ['entrar'],
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 375, height: 812 },
        isMobile: true,
        hasTouch: true,
        storageState
      }
    }
  ]
})
