import { existsSync } from 'node:fs'
import { dirname } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

// Jornadas da cliente de verdade (WP-L00): a loja COMPILADA e o Gestor contra o Django de
// uma pilha já de pé, com a cliente fazendo o que ela faz (cardápio, sacola, código que
// chegou, Pix) e a operadora aceitando pela tela do Gestor. Nenhum estado nasce por API,
// Admin ou banco. Como subir a pilha: tests/e2e/README.md, seção 3.
//
// Esta suíte não sobe servidor nenhum. Sem a pilha declarada, ela recusa rodar: uma
// jornada que "passa" contra o Django errado (ou contra nenhum) não prova nada.
const required = {
  JOURNEY_STORE_URL: 'a loja compilada da pilha (ex.: http://loja.l00.localhost:3190)',
  JOURNEY_GESTOR_URL: 'o Gestor compilado da pilha (ex.: http://gestor.l00.localhost:3194)',
  JOURNEY_OTP_FILE: 'o arquivo onde o Django da pilha entrega o código de entrada (SHOPMAN_E2E_OTP_FILE)'
} as const
const missing = Object.entries(required).filter(([name]) => !process.env[name])
if (missing.length) {
  throw new Error(
    'Suba a pilha antes das jornadas (tests/e2e/README.md, seção 3). Faltam:\n' +
      missing.map(([name, what]) => `  ${name}: ${what}`).join('\n')
  )
}
if (!existsSync(dirname(process.env.JOURNEY_OTP_FILE!))) {
  throw new Error(
    `A pasta de JOURNEY_OTP_FILE não existe (${dirname(process.env.JOURNEY_OTP_FILE!)}): ` +
      'o Django da pilha escreve o código ali, com o mesmo caminho em SHOPMAN_E2E_OTP_FILE.'
  )
}

// A cliente percorre a jornada no celular e no computador; a operadora usa o Gestor em
// 1366 px nas duas. Cada projeto é uma cliente nova (telefone sorteado por execução).
export default defineConfig({
  testDir: './tests/journeys',
  testMatch: '**/*.spec.ts',
  // Uma jornada inteira (loja e Gestor) numa pilha local: a máquina de quem roda costuma
  // estar carregada, e o tempo aqui é de jornada, não de clique.
  timeout: 300_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  outputDir: './test-results/journeys',
  use: {
    baseURL: process.env.JOURNEY_STORE_URL!.replace(/\/$/, ''),
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 20_000,
    navigationTimeout: 60_000
  },
  projects: [
    {
      name: 'cliente-375',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 375, height: 812 },
        deviceScaleFactor: 2,
        isMobile: true,
        hasTouch: true
      }
    },
    {
      name: 'cliente-1366',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 768 } }
    }
  ]
})
