import { randomInt } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { expect, type Page, type TestInfo } from '@playwright/test'

// A pilha que as jornadas usam: URLs vindas do ambiente (playwright.journeys.config.ts
// recusa rodar sem elas) e os papéis do elenco de dev
// (shopman/shop/management/commands/setup_operators.py, que o `seed` roda). Nada aqui cria
// estado: os apoios só fazem o que a pessoa faz na tela.
export const stack = {
  store: process.env.JOURNEY_STORE_URL!.replace(/\/$/, ''),
  gestor: process.env.JOURNEY_GESTOR_URL!.replace(/\/$/, ''),
  otpFile: process.env.JOURNEY_OTP_FILE!
}

// O elenco de setup_operators.py. A Gerente tem senha porque é ela quem abre os
// dispositivos; o superusuário (`admin`) nunca entra numa jornada.
export const cast = {
  manager: { username: 'joyce', name: 'Joyce', password: 'admin', pin: '1234' }
} as const

export const gestorViewport = { width: 1366, height: 768 } as const

/** Espera o Nuxt hidratar: digitar antes disso perde o texto. */
export async function settled (page: Page): Promise<void> {
  await page.waitForLoadState('domcontentloaded')
  await page.waitForFunction(() => {
    const root = document.querySelector('#__nuxt') as (Element & { __vue_app__?: unknown }) | null
    return Boolean(root?.__vue_app__)
  })
  // A loja e o Gestor mantêm SSE aberto: "networkidle" pode nunca chegar.
  await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => undefined)
}

const captureCount = new Map<string, number>()

/** Captura de um passo, anexada ao relatório e gravada em test-results/journeys. */
export async function capture (page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const step = (captureCount.get(testInfo.testId) ?? 0) + 1
  captureCount.set(testInfo.testId, step)
  const path = testInfo.outputPath(`${String(step).padStart(2, '0')}-${name}.png`)
  await page.screenshot({ path, fullPage: false })
  await testInfo.attach(name, { path, contentType: 'image/png' })
}

/** O que o arquivo do sender tinha antes de a cliente pedir o código. */
export interface InboxMark { mtimeMs: number, code: string }

function readInbox (): InboxMark {
  if (!existsSync(stack.otpFile)) return { mtimeMs: 0, code: '' }
  return { mtimeMs: statSync(stack.otpFile).mtimeMs, code: readFileSync(stack.otpFile, 'utf8').trim() }
}

/** A caixa de entrada é UM arquivo para a pilha inteira: com dois workers (a J5 roda a 375 e
 *  a 1366 juntas, esperando o mesmo fechamento), dois pedidos de código ao mesmo tempo
 *  fariam um apagar o do outro. Quem pede o código segura a caixa até lê-lo. A trava é uma
 *  pasta (mkdir é atômico); uma trava de mais de 2 min é de um processo que morreu. */
export async function withInbox<T> (fn: () => Promise<T>): Promise<T> {
  const lock = `${stack.otpFile}.lock`
  const deadline = Date.now() + 120_000
  for (;;) {
    try {
      mkdirSync(lock)
      break
    } catch {
      const stale = existsSync(lock) && Date.now() - statSync(lock).mtimeMs > 120_000
      if (stale) rmSync(lock, { recursive: true, force: true })
      else if (Date.now() > deadline) throw new Error(`a caixa de entrada da pilha ficou presa (${lock})`)
      else await new Promise(resolve => setTimeout(resolve, 250))
    }
  }
  try {
    return await fn()
  } finally {
    rmSync(lock, { recursive: true, force: true })
  }
}

/** Marca a caixa de entrada antes de tocar em "Receber por SMS". */
export function inboxMark (): InboxMark {
  return readInbox()
}

/** O código que chegou depois da marca, lido do arquivo do sender (E2EFileSender), como a
 *  cliente leria o SMS. O sender troca o arquivo inteiro a cada envio. */
export async function readLoginCode (mark: InboxMark): Promise<string> {
  let code = ''
  await expect
    .poll(
      () => {
        const now = readInbox()
        const arrived = now.mtimeMs > mark.mtimeMs || (now.code !== mark.code && now.code !== '')
        code = arrived ? now.code : ''
        return code
      },
      { message: `código de entrada no arquivo do sender (${stack.otpFile})`, timeout: 60_000 }
    )
    .toMatch(/^\d{6}$/)
  return code
}

/** Um celular que nunca comprou na loja: DDD 43, nono dígito, sorteado por execução. */
export function newCustomerPhone (): string {
  // Sorteio, não relógio: dois workers que começam no mesmo milissegundo (a J5 roda a 375
  // e a 1366 juntas) geravam o MESMO número, e o segundo caía na espera do reenvio.
  const tail = String(randomInt(100_000_000)).padStart(8, '0')
  return `439${tail}`
}
