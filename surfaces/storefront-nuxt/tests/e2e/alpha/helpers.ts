import { expect, type Page } from '@playwright/test'

export const TEST_PHONE = '11999999999'
export const TEST_NAME = 'QA Alpha Tester'

// Pacing entre logins: o alpha limita request-code a 5/min por IP; a suíte roda
// seriada com vários logins, então espaça 75s entre um login e o próximo.
let lastLoginAt = 0

/** Login via UI (WhatsApp alternativo → SMS → código de teste do alpha). Resiliente a rate-limit. */
export async function login (page: Page, phone = TEST_PHONE): Promise<void> {
  const since = Date.now() - lastLoginAt
  if (lastLoginAt && since < 75_000) {
    const wait = 75_000 - since
    console.log(`[login] aguardando pacing de ${Math.round(wait / 1000)}s`)
    await page.waitForTimeout(wait)
  }
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) {
      console.log(`[login] tentativa ${attempt + 1} — aguardando 60s p/ rate-limit`)
      await page.waitForTimeout(60_000)
    }
    const ok = await tryLoginOnce(page, phone)
    if (ok) {
      lastLoginAt = Date.now()
      return
    }
  }
  throw new Error('login falhou após 3 tentativas (rate-limit ou fluxo inesperado)')
}

/** Coleta erros de console/request da página. */
export function collectConsoleErrors (page: Page): string[] {
  const errors: string[] = []
  page.on('console', m => { if (m.type() === 'error') errors.push(`[console] ${m.text()}`) })
  page.on('pageerror', e => errors.push(`[pageerror] ${e.message}`))
  page.on('requestfailed', r => errors.push(`[requestfailed] ${r.url()} :: ${r.failure()?.errorText || ''}`))
  page.on('response', r => { if (r.status() >= 400) errors.push(`[http${r.status()}] ${r.url()}`) })
  return errors
}

async function tryLoginOnce (page: Page, phone: string): Promise<boolean> {
  await page.goto('/entrar', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2200)
  const semWA = page.getByText(/Não consigo usar WhatsApp/i).first()
  if (await semWA.count()) await semWA.click()
  await page.waitForTimeout(1400)
  const phoneInput = page.locator('input[inputmode="tel"], input[type="tel"]').filter({ visible: true }).first()
  if (!(await phoneInput.count())) return false
  await phoneInput.fill(phone)
  await page.waitForTimeout(400)
  const sms = page.locator('button').filter({ hasText: /Receber por SMS/i }).first()
  if (!(await sms.count())) return false
  await sms.click()
  await page.waitForTimeout(4500)

  // erro de rate-limit visível?
  const erro = await page.getByText(/Muitas tentativas/i).count()
  if (erro) return false

  const testBtn = page.locator('button').filter({ hasText: /Usar código de teste/i }).first()
  if (await testBtn.count()) {
    await testBtn.click()
  } else {
    const banner = await page.locator('text=/Código para entrar/').first().locator('..').innerText().catch(() => '')
    const digits = (banner.match(/\d/g) || []).slice(0, 6)
    if (digits.length !== 6) return false
    const boxes = page.locator('input[type="text"]').filter({ visible: true })
    for (let i = 0; i < 6; i++) await boxes.nth(i).fill(digits[i] || '')
  }
  await page.waitForTimeout(700)
  const entrar = page.locator('button').filter({ hasText: /^Entrar$/i }).first()
  if (await entrar.count()) await entrar.click()
  // o redirect pós-login pode ser lento; espera ativa até sair de /entrar
  await page.waitForTimeout(2500)
  try {
    await page.waitForURL(u => !u.pathname.includes('/entrar'), { timeout: 20_000 })
  } catch { /* segue */ }
  await page.waitForTimeout(1500)
  const authed = !page.url().includes('/entrar')
  if (authed) return true
  await page.goto('/conta', { waitUntil: 'domcontentloaded' }).catch(() => {})
  await page.waitForTimeout(2000)
  return !page.url().includes('/entrar')
}

/** Adiciona produto pelo menu usando o aria-label. */
export async function addToCart (page: Page, productName: string): Promise<void> {
  await page.goto('/menu', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  const btn = page.getByRole('button', { name: `Adicionar ${productName}` }).first()
  await expect(btn).toBeVisible()
  await btn.click()
  await page.waitForTimeout(1200)
}

/** Vai para a sacola e clica em Finalizar (CTA visível). */
export async function goToCheckout (page: Page): Promise<void> {
  await page.goto('/sacola', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  const fin = page.locator('a[href="/finalizar"], button').filter({ hasText: /Finalizar/i }).filter({ visible: true }).last()
  await expect(fin).toBeVisible()
  await fin.click()
  await page.waitForTimeout(4500)
}

/** Texto do body limpo. */
export async function bodyText (page: Page): Promise<string> {
  return (await page.locator('body').innerText()).replace(/\n{2,}/g, '\n')
}

/** Botão "Continuar" visível do wizard de checkout (role-based: nome acessível é trimado,
 *  ao contrário do textContent bruto usado por filter({hasText})). */
export function continueBtn (page: Page) {
  return page.getByRole('button', { name: /^Continuar$/i }).filter({ visible: true }).last()
}

/** Garante o passo Contato do checkout: se o input de nome aparecer, preenche e salva;
 *  se já estiver salvo (autofill do perfil), segue direto. */
export async function ensureContactSaved (page: Page, name = TEST_NAME): Promise<void> {
  const nameInput = page.locator('input[type="text"]').filter({ visible: true }).first()
  const hasInput = await nameInput.count()
  if (hasInput) {
    await nameInput.fill(name)
    const salvar = page.getByRole('button', { name: /Salvar contato/i }).first()
    if (await salvar.count()) { await salvar.click(); await page.waitForTimeout(3000) }
  } else {
    // já salvo: espera o resumo "Editar" aparecer
    const edit = page.getByRole('button', { name: /Editar/i }).first()
    if (await edit.count()) await page.waitForTimeout(500)
  }
  await page.waitForLoadState('domcontentloaded').catch(() => {})
}

/** Espera o tempo de pacing restante (compartilhado com login). */
export async function pace (): Promise<void> {
  const since = Date.now() - lastLoginAt
  if (lastLoginAt && since < 75_000) {
    const wait = 75_000 - since
    console.log(`[pace] aguardando ${Math.round(wait / 1000)}s`)
    await new Promise(r => setTimeout(r, wait))
  }
  lastLoginAt = Date.now()
}

/** Filtra erros de console irrelevantes (favicon, aborts de navegação, 400 de request-code
 *  por rate-limit da própria suíte; o console "Failed to load resource 400" é duplicado do
 *  [http400] com URL, que continua como fonte da verdade). */
export function realErrors (errors: string[]): string[] {
  return errors.filter(e => !e.includes('favicon')
    && !e.includes('net::ERR_ABORTED')
    && !e.includes('net::ERR_FAILED')
    && !e.includes('/api/auth/request-code/')
    && !e.includes('/api/auth/verify-code/')
    && !e.includes('/api/auth/device-check/')
    && !e.includes('/api/v1/cart/coupon/')
    && !/\[console\] Failed to load resource: the server responded with a status of 400/.test(e))
}
