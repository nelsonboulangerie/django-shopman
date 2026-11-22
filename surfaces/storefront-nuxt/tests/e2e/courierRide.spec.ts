import { test, expect, type Page } from '@playwright/test'

// A página do entregador da casa (`/rota/<token>`, DEV-2026-030, M2), tela por tela, com a
// API respondida aqui (sem Django). Cada tela passa pela auditoria do critério de pronto do
// plano (DELIVERY-MULTI-SERVICE-PLAN §4.5.2): só os 3 tamanhos de texto, só as cores da
// paleta, o código nunca na linha de um título, nada centralizado fora de botão, nada
// transbordando, e o contraste WCAG de todo texto. Com `COURIER_SHOTS_DIR`, grava a prova.

const TOKEN = 'tok-e2e-rota'
const SHOTS = process.env.COURIER_SHOTS_DIR || ''

const marina = {
  ref: 'ORD-A47',
  code: 'A47',
  name: 'Marina',
  street: 'Rua Caracas 420',
  complement: 'Torre 2 · Apto 41',
  neighborhood: 'Gleba Palhano',
  instructions: 'O interfone não funciona, me ligue que eu desço.',
  bags: 2,
  ready: true,
  state: 'open',
  receive: { cash_q: 5800, card_q: 0, pays_with_q: 10000, change_back_q: 4200, paid_other: '' },
  lat: -23.33,
  lng: -51.18,
  phone: '+5543999990000'
}
const paulo = {
  ...marina,
  ref: 'ORD-C03',
  code: 'C03',
  name: 'Paulo',
  street: 'Rua Bélgica 155',
  complement: 'Casa de portão verde',
  instructions: 'Toque a campainha.',
  bags: 1,
  receive: { cash_q: 0, card_q: 4200, pays_with_q: 0, change_back_q: 0, paid_other: '' }
}
const base = { courier: 'Diego', ride_ref: 'R1', label: 'Rota A', letter: 'A', value_q: 1500, machine: 'Azul' }
const settle = { cash_q: 10000, cash: 'R$ 100,00', machine: 'Azul', bags_back: [] }

const VIEWS: Record<string, unknown> = {
  confirm: { moment: 'confirm', courier: 'Diego' },
  pickup: { ...base, moment: 'pickup', stops: [marina, paulo], settle },
  pickup_wait: { ...base, moment: 'pickup_wait', stops: [marina, { ...paulo, ready: false, ready_at: '12:48' }], settle },
  route: { ...base, moment: 'route', stops: [marina, paulo], settle },
  route_card: { ...base, moment: 'route', stops: [{ ...marina, state: 'done' }, paulo], settle },
  route_cancel: { ...base, moment: 'route', stops: [marina, { ...paulo, state: 'cancelled' }], settle },
  back: { ...base, moment: 'back', stops: [{ ...marina, state: 'done' }, { ...paulo, state: 'done' }], settle },
  closed: { ...base, moment: 'closed', today_q: 2700 },
  cancelled: { courier: 'Diego', ride_ref: 'R1', moment: 'cancelled' },
  other_device: { moment: 'other_device', detail: 'Esta rota está aberta em outro celular.' }
}

async function openRide (page: Page, view: string, theme: 'light' | 'dark', local: Record<string, unknown> = {}) {
  await page.addInitScript(({ theme, token, local }) => {
    localStorage.setItem('shopman-courier-theme', theme)
    localStorage.setItem('shopman-courier-device', 'e2e-device-key-0123456789abcdefghijklmnopq')
    localStorage.setItem(`shopman-courier-local:${token}`, JSON.stringify(local))
  }, { theme, token: TOKEN, local })
  await page.route('**/api/v1/courier/rides/**', async (route) => {
    const status = view === 'other_device' ? 403 : 200
    const body = route.request().method() === 'POST' && view === 'route' ? VIEWS.route : VIEWS[view]
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto(`/rota/${TOKEN}`)
  await page.locator('.cr').waitFor()
  await page.waitForFunction(() => document.querySelector('.cr')?.getAttribute('data-screen') !== 'loading')
}

interface Audit {
  sizes: number[]
  offSizes: string[]
  offColors: string[]
  badgeOnTitleLine: string[]
  centered: string[]
  overflow: string[]
  minContrast: number
  minContrastText: string
}

async function audit (page: Page): Promise<Audit> {
  return page.evaluate(() => {
    const PALETTE = new Set(['255,255,255', '0,0,0', '245,245,245', '212,212,212', '38,38,38', '82,82,82'])
    const SIZES = [28, 18, 15]
    const root = document.querySelector('.cr') as HTMLElement
    const rgb = (value: string) => (value.match(/[\d.]+/g) || []).map(Number)
    const lum = ([r, g, b]: number[]) => {
      const ch = (v: number) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 }
      return 0.2126 * ch(r!) + 0.7152 * ch(g!) + 0.0722 * ch(b!)
    }
    const background = (el: Element | null): string => {
      for (let node = el; node; node = node.parentElement) {
        const bg = getComputedStyle(node).backgroundColor
        const parts = rgb(bg)
        if (parts.length >= 3 && (parts.length === 3 || parts[3]! > 0)) return parts.slice(0, 3).join(',')
      }
      return '255,255,255'
    }
    const isLetter = (el: Element) => Boolean(el.closest('.cr-letter, .cr-letter-sm, .cr-letter-lg'))
    const visible = (el: Element) => {
      const rect = el.getBoundingClientRect()
      return rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== 'hidden'
    }
    const texts = [...root.querySelectorAll('*')].filter(el => visible(el)
      && !el.closest('.is-behind')
      && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent!.trim()))
    const result = {
      sizes: [] as number[],
      offSizes: [] as string[],
      offColors: [] as string[],
      badgeOnTitleLine: [] as string[],
      centered: [] as string[],
      overflow: [] as string[],
      minContrast: 99,
      minContrastText: ''
    }
    const sizes = new Set<number>()
    for (const el of texts) {
      const style = getComputedStyle(el)
      const label = (el.textContent || '').trim().slice(0, 40)
      const size = Math.round(Number.parseFloat(style.fontSize))
      sizes.add(size)
      if (!SIZES.includes(size)) result.offSizes.push(`${size}px: ${label}`)
      const fg = rgb(style.color).slice(0, 3).join(',')
      const bg = background(el)
      if (!isLetter(el)) {
        if (!PALETTE.has(fg)) result.offColors.push(`texto ${fg}: ${label}`)
        if (!PALETTE.has(bg)) result.offColors.push(`fundo ${bg}: ${label}`)
      }
      const a = lum(fg.split(',').map(Number))
      const b = lum(bg.split(',').map(Number))
      const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
      if (ratio < result.minContrast) { result.minContrast = ratio; result.minContrastText = label }
      const inControl = el.closest('button, a')
      if (!inControl && style.textAlign === 'center') result.centered.push(label)
      if (el.scrollWidth > el.clientWidth + 1 && style.overflow !== 'visible') result.overflow.push(label)
      const rect = el.getBoundingClientRect()
      if (rect.right > window.innerWidth + 0.5 || rect.left < -0.5) result.overflow.push(`fora da tela: ${label}`)
    }
    // Contêiner fora de botão não centraliza nada.
    for (const el of root.querySelectorAll('*')) {
      if (!visible(el) || el.closest('button, a')) continue
      const style = getComputedStyle(el)
      if (style.display.includes('flex') && style.justifyContent === 'center' && style.flexDirection === 'row') {
        result.centered.push(`flex centralizado: ${el.className}`)
      }
    }
    if (document.documentElement.scrollWidth > window.innerWidth) result.overflow.push('a página rola na horizontal')
    // O código do pedido nunca na mesma linha de um título.
    const bigs = [...root.querySelectorAll('.cr-big')].filter(el => visible(el) && !el.closest('.is-behind')).map(el => el.getBoundingClientRect())
    for (const badge of [...root.querySelectorAll('.cr-badge')].filter(el => visible(el) && !el.closest('.is-behind'))) {
      const r = badge.getBoundingClientRect()
      if (bigs.some(t => r.top < t.bottom - 1 && r.bottom > t.top + 1)) result.badgeOnTitleLine.push(badge.textContent || '')
    }
    result.sizes = [...sizes].sort((x, y) => y - x)
    result.minContrast = Math.round(result.minContrast * 10) / 10
    return result
  })
}

const report: Record<string, Audit> = {}

async function check (page: Page, name: string) {
  const result = await audit(page)
  report[name] = result
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` })
  expect(result.offSizes, name).toEqual([])
  expect(result.offColors, name).toEqual([])
  expect(result.badgeOnTitleLine, name).toEqual([])
  expect(result.centered, name).toEqual([])
  expect(result.overflow, name).toEqual([])
  expect(result.minContrast, name).toBeGreaterThanOrEqual(4.5)
}

const PORTRAIT = { width: 375, height: 812 }
const SMALL = { width: 340, height: 700 }
const LANDSCAPE = { width: 812, height: 375 }

for (const theme of ['light', 'dark'] as const) {
  for (const [size, viewport] of [['375', PORTRAIT], ['340', SMALL]] as const) {
    test.describe(`rota do entregador · ${theme} · ${size}`, () => {
      test.use({ viewport, isMobile: true, hasTouch: true })
      const tag = (screen: string) => `${screen}-${theme}${size === '340' ? '-340' : ''}`

      test('tela inicial', async ({ page }) => {
        await page.addInitScript(theme => localStorage.setItem('shopman-courier-theme', theme), theme)
        await page.goto('/rota/')
        await page.locator('.cr[data-screen="home"]').waitFor()
        await expect(page.getByText('Nenhuma corrida agora.', { exact: false })).toBeVisible()
        await check(page, tag('00-inicio'))
      })

      test('confirmar o link: nada da rota antes do toque', async ({ page }) => {
        await openRide(page, 'confirm', theme)
        await expect(page.getByRole('button', { name: 'Sou o Diego, abrir' })).toBeVisible()
        await expect(page.getByText('Rua Caracas')).toHaveCount(0)
        await check(page, tag('01-confirmar'))
      })

      test('no balcão e esperando', async ({ page }) => {
        await openRide(page, 'pickup', theme)
        await expect(page.getByRole('button', { name: 'Saí da loja' })).toBeVisible()
        await expect(page.getByText('Dica: C03 no fundo, A47 por cima.', { exact: false })).toBeVisible()
        await check(page, tag('02-balcao'))
      })

      test('esperando um pedido: sem botão', async ({ page }) => {
        await openRide(page, 'pickup_wait', theme)
        await expect(page.getByText('Fica pronto às 12h48')).toBeVisible()
        await expect(page.getByText('Espere C03 ficar pronto')).toBeVisible()
        await expect(page.getByRole('button', { name: 'Saí da loja' })).toHaveCount(0)
        await check(page, tag('03-esperando'))
      })

      test('dirigindo, na porta, desfazer e as folhas', async ({ page }) => {
        await openRide(page, 'route', theme)
        await expect(page.getByRole('link', { name: 'Abrir no Waze' })).toHaveAttribute('href', /waze\.com/)
        await check(page, tag('04-dirigindo'))

        await page.getByRole('button', { name: 'Cheguei' }).click()
        await expect(page.getByRole('button', { name: 'Entreguei A47' })).toBeVisible()
        await expect(page.getByText('Marina paga com R$ 100,00. Devolva R$ 42,00.')).toBeVisible()
        await expect(page.getByRole('link', { name: 'Ligar' })).toHaveAttribute('href', 'tel:+5543999990000')
        await check(page, tag('05-porta'))

        await page.getByRole('button', { name: 'Problema' }).click()
        await expect(page.getByText('Qual o problema?')).toBeVisible()
        await check(page, tag('07-problema'))
        await page.getByRole('button', { name: 'Pagou de outro jeito' }).click()
        await expect(page.getByRole('button', { name: 'No Pix, na maquininha Azul' })).toBeVisible()
        await check(page, tag('08-como-pagou'))
        await page.getByRole('button', { name: 'Fechar' }).click()

        await page.getByRole('button', { name: 'Entreguei A47' }).click()
        await expect(page.getByText('A47 entregue.')).toBeVisible()
        await expect(page.getByRole('button', { name: 'Desfazer' })).toBeVisible()
        await check(page, tag('06-desfazer'))
        await page.getByRole('button', { name: 'Desfazer' }).click()
        await expect(page.getByRole('button', { name: 'Entreguei A47' })).toBeVisible()
      })

      test('ninguém atendeu: a espera curta', async ({ page }) => {
        await openRide(page, 'route', theme, { arrivedRef: 'ORD-A47', noAnswerRef: 'ORD-A47' })
        await expect(page.getByText('Espere 2 minutos')).toBeVisible()
        await check(page, tag('09-ninguem-atendeu'))
      })

      test('na porta, no cartão', async ({ page }) => {
        await openRide(page, 'route_card', theme, { arrivedRef: 'ORD-C03' })
        await expect(page.getByText('Na maquininha Azul.')).toBeVisible()
        await check(page, tag('10-porta-cartao'))
      })

      test('pedido cancelado com ele na rua', async ({ page }) => {
        await openRide(page, 'route_cancel', theme, { wasOnRoute: true })
        await expect(page.getByText('Foi cancelado.')).toBeVisible()
        await check(page, tag('11-cancelado-pedido'))
        await page.getByRole('button', { name: 'Entendi' }).click()
        await expect(page.getByText('Rua Caracas 420')).toBeVisible()
      })

      test('rota inteira cancelada', async ({ page }) => {
        await openRide(page, 'cancelled', theme, { wasOnRoute: true })
        await expect(page.getByText('Não entregue. Traga a sacola de volta.')).toBeVisible()
        await check(page, tag('12-cancelada'))
      })

      test('voltando: só o acerto', async ({ page }) => {
        await openRide(page, 'back', theme)
        await expect(page.getByText('Entregue no caixa')).toBeVisible()
        await expect(page.getByText('R$ 100,00')).toBeVisible()
        await check(page, tag('13-voltando'))
      })

      test('fechada', async ({ page }) => {
        await openRide(page, 'closed', theme)
        await expect(page.getByText('Rota A fechada')).toBeVisible()
        await check(page, tag('14-fechada'))
      })

      test('aberta em outro celular', async ({ page }) => {
        await openRide(page, 'other_device', theme)
        await expect(page.getByText('Esta rota está aberta em outro celular.')).toBeVisible()
        await check(page, tag('15-outro-celular'))
      })
    })
  }

  test.describe(`rota do entregador · ${theme} · deitado`, () => {
    test.use({ viewport: LANDSCAPE, isMobile: true, hasTouch: true })

    test('dirigindo e na porta, deitado', async ({ page }) => {
      await openRide(page, 'route', theme)
      const button = page.getByRole('button', { name: 'Cheguei' })
      await expect(button).toBeInViewport()
      await check(page, `04-dirigindo-${theme}-deitado`)
      await button.click()
      await expect(page.getByRole('button', { name: 'Entreguei A47' })).toBeInViewport()
      await check(page, `05-porta-${theme}-deitado`)
    })
  })
}

// A posição para a loja (#2509): com a rota na rua e a localização permitida, a página
// diz que a loja vê e manda a posição a cada 15 s, em pé e deitado.
for (const [size, viewport] of [['em-pe', PORTRAIT], ['deitado', LANDSCAPE]] as const) {
  test.describe(`rota do entregador · posição · ${size}`, () => {
    test.use({
      viewport, isMobile: true, hasTouch: true,
      permissions: ['geolocation'], geolocation: { latitude: -23.32, longitude: -51.17, accuracy: 10 }
    })

    test('a loja vê onde ele está, e a posição sai a cada 15 s', async ({ page }) => {
      test.setTimeout(45_000)
      const sent: Record<string, unknown>[] = []
      page.on('request', (request) => {
        if (request.method() === 'POST' && request.url().includes('/events/')) sent.push(request.postDataJSON())
      })
      await openRide(page, 'route', 'light')
      await expect(page.getByText('A loja vê onde você está enquanto esta tela estiver aberta.')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Cheguei' })).toBeInViewport()
      await check(page, `04b-posicao-light-${size}`)
      await expect.poll(() => sent.filter(body => body.action === 'position').length, { timeout: 20_000 }).toBeGreaterThan(0)
      expect(sent.find(body => body.action === 'position')).toMatchObject({ lat: -23.32, lng: -51.17, accuracy: 10 })
    })
  })
}

test.describe('rota do entregador · posição bloqueada', () => {
  test.use({ viewport: PORTRAIT, isMobile: true, hasTouch: true, permissions: [] })

  test('sem permissão, a tela diz que a loja não vê e como liberar', async ({ page, context }) => {
    await context.clearPermissions()
    await openRide(page, 'route', 'light')
    await expect(page.locator('[data-tracking="denied"]')).toHaveText(
      'Localização bloqueada: a loja não vê onde você está. Libere nas configurações do navegador.')
    await check(page, '04c-posicao-bloqueada-light')
  })
})

test('o link manda o manifesto das rotas e não se indexa', async ({ page, request }) => {
  await openRide(page, 'confirm', 'light')
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', '/rota/manifest.webmanifest')
  await expect(page.locator('link[rel="manifest"]')).toHaveCount(1)
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/)
  const manifest = await request.get('/rota/manifest.webmanifest')
  expect(await manifest.json()).toMatchObject({ id: '/rota/', scope: '/rota/', name: 'Rotas · Nelson' })
  const html = await request.get(`/rota/${TOKEN}`)
  expect(html.headers()['x-robots-tag']).toBe('noindex')
})

test.afterAll(() => {
  if (!SHOTS) return
  // eslint-disable-next-line no-console
  console.log(`[courier-audit] ${JSON.stringify(Object.fromEntries(Object.entries(report).map(([k, v]) => [k, { sizes: v.sizes, minContrast: v.minContrast, minContrastText: v.minContrastText }])))}`)
})
