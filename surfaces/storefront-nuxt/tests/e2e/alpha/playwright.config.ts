import { defineConfig, devices } from '@playwright/test'

// Suíte alpha do storefront — roda contra o ambiente online de staging.
//
//   npx playwright test --config=tests/e2e/alpha/playwright.config.ts
//
// Notas:
// - O alpha expõe o código OTP de teste na própria UI ("AMBIENTE DE TESTE" /
//   "Usar código de teste"), então o login é dirigido por UI sem interceptar rede.
// - O request-code é limitado a 5/min por IP: helpers.ts já faz pacing de 75s
//   entre logins e retry de 60s quando limitado; não rode em paralelo (workers: 1).
// - Fora do horário de funcionamento o checkout agenda para o dia seguinte
//   ("encomendar para o próximo dia") — a suíte cobre esse fluxo; o pedido do
//   mesmo dia + bloco de pagamento só é exercitável com a loja aberta.
export default defineConfig({
  testDir: './specs',
  testMatch: '**/*.spec.ts',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  outputDir: './test-results',
  use: {
    // ⚠️ Uma variável, não uma constante: trocar o domínio da loja (alpha.* →
    // menu.*) não pode exigir edição de código no momento do corte. Defina
    // STOREFRONT_URL no ambiente para apontar a suíte para outro host.
    baseURL: process.env.STOREFRONT_URL || 'https://alpha.nelsonboulangerie.com.br',
    viewport: { width: 390, height: 844 },
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  projects: [
    { name: 'chromium-mobile', use: { ...devices['Pixel 7'] } }
  ]
})
