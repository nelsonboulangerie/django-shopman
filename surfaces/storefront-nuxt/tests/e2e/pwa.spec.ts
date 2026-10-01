import { readFile, rename, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

test('manifesto, service worker e metadados iOS são servidos pelo build', async ({ page, request }) => {
  const manifestResponse = await request.get('/manifest.webmanifest?v=7')
  expect(manifestResponse.ok()).toBe(true)
  expect(manifestResponse.headers()['content-type']).toContain('application/manifest+json')
  expect(manifestResponse.headers()['cache-control']).toBe('private, no-store')

  const manifest = await manifestResponse.json()
  expect(manifest.icons).toEqual(expect.arrayContaining([
    expect.objectContaining({ sizes: '512x512', purpose: 'maskable' }),
    expect.objectContaining({ sizes: '512x512', purpose: 'monochrome' })
  ]))
  expect(manifest.screenshots).toHaveLength(3)

  const workerResponse = await request.head('/sw.js')
  expect(workerResponse.ok()).toBe(true)
  expect(workerResponse.headers()['cache-control']).toBe('no-cache, no-store, must-revalidate')

  await page.goto('/')
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', '/manifest.webmanifest?v=7')
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute('href', '/pwa/apple-touch-icon-180x180.png?v=7')
  await expect(page.locator('link[rel="apple-touch-startup-image"]')).toHaveCount(40)
})

test('service worker registra e entrega o casco quando uma navegação perde a rede', async ({ page, context }) => {
  await page.goto('/')
  await page.evaluate(async () => navigator.serviceWorker.ready)

  await context.setOffline(true)
  await page.goto('/menu')

  await expect(page.getByRole('heading', { name: 'A loja ficou sem conexão' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Tentar de novo' })).toBeVisible()
})

// O fluxo que travava o app instalado: existe versão nova, e o cliente consegue
// atualizar. O build é um só, então a "versão nova" é o mesmo `sw.js` com um byte
// trocado no disco depois que o primeiro worker já assumiu.
//
// Por que no disco, e não por `context.route`: a sonda (`registration.update()`) é
// uma busca do próprio navegador, que a interceptação do Playwright não vê. Por que
// com o MESMO tamanho: o Nitro serve `public/` com `Content-Length` pré-calculado no
// build. O `sw.js` sai com `no-store`, então o navegador não manda `If-None-Match` e
// o ETag pré-calculado não responde 304 por engano. E por que NESTE arquivo: os
// testes de um arquivo rodam em série (`fullyParallel: false`), e o `sw.js` trocado
// não pode vazar para outro teste do PWA.
const swPath = fileURLToPath(new URL('../../.output/public/sw.js', import.meta.url))
const SW_ORIGINAL = '"storefront-fonts"'
const SW_NEXT = '"storefront-f0nts"'

// Troca ATÔMICA (arquivo ao lado + rename): o Nitro manda o `Content-Length` do build,
// e um `sw.js` lido pela metade no meio da escrita deixaria a busca do navegador
// esperando bytes que nunca chegam.
async function replaceServiceWorker (content: string) {
  await writeFile(`${swPath}.next`, content)
  await rename(`${swPath}.next`, swPath)
}

test('versão nova aparece num aviso persistente e só entra pelo toque', async ({ page }) => {
  // Duas instalações completas do worker (o precache inteiro, duas vezes) não cabem
  // no teto padrão de 30 s num runner lento da CI.
  test.setTimeout(90_000)
  const original = await readFile(swPath, 'utf8')
  expect(original).toContain(SW_ORIGINAL)

  // Ícone buscado na rede durante a troca é a causa provada do aviso que girava sem
  // fim: ver o comentário do toque, abaixo.
  const iconFetches: string[] = []
  page.on('request', request => { if (request.url().includes('/api/_nuxt_icon/')) iconFetches.push(request.url()) })

  try {
    await page.goto('/menu')
    // Primeira instalação: o worker ativa direto (não há outro em uso) e não há aviso.
    await page.evaluate(async () => { await navigator.serviceWorker.ready })
    const prompt = page.getByTestId('pwa-update-prompt')
    await expect(prompt).toBeHidden()

    await replaceServiceWorker(original.replace(SW_ORIGINAL, SW_NEXT))
    // A página recarregada já é controlada pelo worker antigo; a sonda de boot do
    // app pergunta ao servidor, o worker novo instala e fica em espera.
    await page.reload()
    await expect(prompt).toBeVisible()
    await expect(prompt).toContainText('A loja tem uma versão nova')

    // No checkout o aviso cala (o toque recarregaria a página no meio do pedido)...
    await page.goto('/finalizar')
    await expect(prompt).toBeHidden()
    // ...e volta na tela seguinte: não é tiro único.
    await page.goto('/menu')
    await expect(prompt).toBeVisible()

    // Só o toque aplica: o worker novo assume e a página recarrega sem aviso.
    //
    // O toque NÃO pode buscar nada na rede. O Chromium ativa o worker em espera
    // desligando o antigo; requisição da página que chega ao antigo ENQUANTO ele
    // desliga o religa, e a ativação fica para quando ele ficar ocioso de novo (30 s
    // sem requisição). Era o spinner do botão, buscado em `/api/_nuxt_icon` no
    // instante do toque: a trilha da CI mostrava o worker antigo `stopping → stopped →
    // starting` e o novo parado em "installed" até o fim. Por isso a trilha registra
    // as versões do worker (CDP) e as requisições depois do toque.
    expect(await page.evaluate(async () => Boolean((await navigator.serviceWorker.getRegistration())?.waiting))).toBe(true)
    const trail: string[] = []
    page.on('console', message => trail.push(`console ${message.type()}: ${message.text()}`))
    page.on('framenavigated', frame => { if (frame === page.mainFrame()) trail.push(`nav ${frame.url()}`) })
    page.on('request', request => trail.push(`req ${request.method()} ${request.url()}`))
    const cdp = await page.context().newCDPSession(page)
    cdp.on('ServiceWorker.workerVersionUpdated', ({ versions }) => {
      for (const version of versions) trail.push(`worker ${version.versionId} ${version.status}/${version.runningStatus}`)
    })
    await cdp.send('ServiceWorker.enable')
    const snapshot = () => page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration()
      return {
        active: registration?.active?.state || null,
        waiting: registration?.waiting?.state || null,
        installing: registration?.installing?.state || null,
        controller: navigator.serviceWorker.controller?.state || null
      }
    }).catch(error => ({ error: String(error).slice(0, 120) }))
    // O toque vem com a página assentada, como o de uma pessoa: a mesma janela de
    // corrida existe para QUALQUER requisição da página (aqui, o prefetch de rotas do
    // Nuxt, que corre logo depois da carga), e esta prova é sobre o que o TOQUE faz.
    await page.waitForLoadState('networkidle')
    trail.push(`antes do toque ${JSON.stringify(await snapshot())}`)
    await prompt.getByRole('button', { name: 'Atualizar' }).click()
    // A página recarrega no meio da sonda: avaliação perdida na troca conta como "ainda não".
    try {
      await expect.poll(async () => {
        const state = await snapshot()
        trail.push(JSON.stringify(state))
        return 'active' in state && state.active === 'activated' && !state.waiting
      }, { timeout: 30_000 }).toBe(true)
    } catch (error) {
      // Sem as linhas repetidas da sonda, a trilha cabe inteira: o começo é o que conta.
      console.log(`trilha da troca de versão:\n${trail.filter((line, index) => line !== trail[index - 1]).join('\n')}`)
      throw error
    }
    // Recarregada com o worker novo no comando, não há mais versão em espera.
    await expect(prompt).toBeHidden({ timeout: 15_000 })
    expect(iconFetches).toEqual([])
  } finally {
    await replaceServiceWorker(original)
  }
})

test('convite de instalação não aparece no checkout', async ({ page }) => {
  await page.goto('/finalizar')
  await page.evaluate(() => {
    const event = new Event('beforeinstallprompt', { cancelable: true })
    Object.defineProperties(event, {
      prompt: { value: async () => undefined },
      userChoice: { value: Promise.resolve({ outcome: 'dismissed', platform: 'web' }) }
    })
    window.dispatchEvent(event)
  })

  await expect(page.getByTestId('pwa-install-invite')).toBeHidden()
})

test('overlays travam e restauram o body no navegador comum', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/menu')

  const body = page.locator('body')
  const viewport = page.locator('[data-shop-scroll-viewport]')
  await page.getByRole('button', { name: 'Abrir menu' }).click()

  await expect.poll(() => body.evaluate(element => element.style.overflow)).toBe('hidden')
  expect(await viewport.evaluate(element => element.style.overflow)).not.toBe('hidden')

  await page.getByRole('button', { name: 'Fechar menu' }).click()
  await expect.poll(() => body.evaluate(element => element.style.overflow)).toBe('')
})

test('barra inferior permanece ancorada fora da rolagem no PWA instalado', async ({ page }) => {
  await page.addInitScript(() => {
    const nativeMatchMedia = window.matchMedia.bind(window)
    Object.defineProperty(navigator, 'platform', { configurable: true, get: () => 'MacIntel' })
    Object.defineProperty(navigator, 'maxTouchPoints', { configurable: true, get: () => 5 })
    window.matchMedia = query => query === '(display-mode: standalone)'
      ? {
          matches: true,
          media: query,
          onchange: null,
          addListener: () => undefined,
          removeListener: () => undefined,
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
          dispatchEvent: () => true
        }
      : nativeMatchMedia(query)
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/menu')

  await expect(page.locator('html')).toHaveClass(/shop-ios-standalone/)
  await page.locator('#main-content').evaluate(element => {
    const filler = document.createElement('div')
    filler.style.height = '3000px'
    filler.dataset.testScrollFiller = ''
    element.appendChild(filler)
  })

  const viewport = page.locator('[data-shop-scroll-viewport]')
  const bottomNav = page.locator('.shop-bottomnav-bar')
  await expect(viewport).toHaveCSS('overflow-y', 'auto')
  await expect(bottomNav).toHaveCSS('position', 'relative')

  const shellColors = await page.evaluate(() => {
    const viewport = document.querySelector<HTMLElement>('[data-shop-scroll-viewport]')!
    const main = document.querySelector<HTMLElement>('#main-content')!
    const probe = document.createElement('div')
    probe.style.backgroundColor = 'var(--shop-ink)'
    document.body.appendChild(probe)
    const ink = getComputedStyle(probe).backgroundColor
    probe.style.backgroundColor = 'var(--background)'
    const canvas = getComputedStyle(probe).backgroundColor
    probe.remove()
    return {
      canvas,
      ink,
      main: getComputedStyle(main).backgroundColor,
      shell: getComputedStyle(document.querySelector<HTMLElement>('.shop-shell')!).backgroundColor,
      viewport: getComputedStyle(viewport).backgroundColor
    }
  })
  expect(shellColors.ink).not.toBe(shellColors.canvas)
  expect(shellColors.shell).toBe(shellColors.ink)
  expect(shellColors.viewport).toBe(shellColors.ink)
  expect(shellColors.main).toBe(shellColors.canvas)

  const contentFlow = await page.evaluate(() => {
    const main = document.querySelector<HTMLElement>('#main-content')!
    const filler = document.querySelector<HTMLElement>('[data-test-scroll-filler]')!
    const footer = document.querySelector<HTMLElement>('.shop-footer')!
    return {
      mainClientHeight: main.clientHeight,
      mainScrollHeight: main.scrollHeight,
      fillerBottom: filler.getBoundingClientRect().bottom,
      footerTop: footer.getBoundingClientRect().top
    }
  })
  expect(contentFlow.mainClientHeight).toBe(contentFlow.mainScrollHeight)
  expect(contentFlow.footerTop).toBeGreaterThanOrEqual(contentFlow.fillerBottom)

  const before = await bottomNav.boundingBox()
  await viewport.evaluate(element => element.scrollTo({ top: 900, behavior: 'instant' }))
  await expect.poll(() => viewport.evaluate(element => element.scrollTop)).toBe(900)
  const after = await bottomNav.boundingBox()

  expect(before).not.toBeNull()
  expect(after).not.toBeNull()
  expect(after?.y).toBeCloseTo(before?.y || 0, 0)
  expect((after?.y || 0) + (after?.height || 0)).toBeCloseTo(844, 0)
  expect(await page.evaluate(() => window.scrollY)).toBe(0)

  await bottomNav.getByRole('link', { name: 'Início' }).click()
  await expect(page).toHaveURL('/')
  await expect.poll(() => viewport.evaluate(element => element.scrollTop)).toBe(0)

  const body = page.locator('body')
  await page.getByRole('button', { name: 'Abrir menu' }).click()
  await expect.poll(() => viewport.evaluate(element => element.style.overflow)).toBe('hidden')
  expect(await body.evaluate(element => element.style.overflow)).not.toBe('hidden')

  await page.getByRole('button', { name: 'Fechar menu' }).click()
  await expect.poll(() => viewport.evaluate(element => element.style.overflow)).toBe('')
})
