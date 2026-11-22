import { expect, test, type Locator, type Page } from '@playwright/test'
import { capture, settled } from './support/stack'

// J12 · Busca e coleção (#2569, item 8): a cliente acha o que procura sem saber o nome
// exato, chega a uma coleção pela busca, e a busca que não acha nada mostra a saída.
//
// Papel: a cliente sem conta, na loja aberta. Ela só olha: nada entra na sacola, nada
// nasce por API, Admin ou banco, e as duas larguras podem rodar juntas.
//
// O caminho é o da tela: o atalho "Buscar no cardápio" do início abre a busca por cima
// da página (o teclado do iOS só abre quando o foco nasce dentro do toque).

/** A busca aberta por cima da página. Fechada, ela continua no DOM, escondida. */
function searchOverlay (page: Page): Locator {
  return page.locator('[data-search-overlay][data-state="open"]')
}

/** A busca abre e fecha por opacidade (200 ms): a captura espera a transição acabar,
 *  senão a foto mostra a busca pela metade, por cima da página. */
async function searchShown (page: Page): Promise<void> {
  await expect(searchOverlay(page)).toBeVisible()
  await expect(searchOverlay(page)).toHaveCSS('opacity', '1')
}

async function searchGone (page: Page): Promise<void> {
  await expect(searchOverlay(page)).toHaveCount(0)
  await expect(page.locator('[data-search-overlay]')).toHaveCSS('opacity', '0')
}

/** Do início, a cliente toca "Buscar no cardápio" e a busca abre com o campo pronto. */
async function opensSearchFromHome (page: Page): Promise<Locator> {
  await page.goto('/')
  await settled(page)
  await page.getByRole('button', { name: 'Buscar no cardápio' }).first().click()
  await searchShown(page)
  const overlay = searchOverlay(page)
  const field = overlay.getByRole('searchbox', { name: 'Buscar no cardápio' })
  await expect(field).toBeFocused()
  return field
}

test('J12: a cliente acha pelo pedaço do nome, sem acento, e chega à coleção pela busca', async ({ page }, testInfo) => {
  await test.step('o pedaço do nome acha o produto', async () => {
    const field = await opensSearchFromHome(page)
    await field.pressSequentially('croiss')
    const results = searchOverlay(page).locator('[data-search-results]')
    await expect(results.getByRole('link', { name: /Croissant/ }).first()).toBeVisible()
    await capture(page, testInfo, 'busca-pedaco-do-nome')
  })

  await test.step('sem acento, a busca acha o nome com acento', async () => {
    const overlay = searchOverlay(page)
    await overlay.getByRole('button', { name: 'Limpar busca' }).click()
    await overlay.getByRole('searchbox', { name: 'Buscar no cardápio' }).pressSequentially('frappe')
    await expect(overlay.locator('[data-search-results]').getByRole('link', { name: /Frappé/ }).first()).toBeVisible()
    await capture(page, testInfo, 'busca-sem-acento')
  })

  await test.step('a busca vazia lista as coleções', async () => {
    const overlay = searchOverlay(page)
    await overlay.getByRole('button', { name: 'Limpar busca' }).click()
    const collections = overlay.locator('[data-search-collections]')
    await expect(collections.getByRole('link', { name: /Folhados/ })).toBeVisible()
    await capture(page, testInfo, 'busca-colecoes')
  })

  await test.step('com um termo, a coleção vira um filtro, e o toque leva até ela', async () => {
    const overlay = searchOverlay(page)
    await overlay.getByRole('searchbox', { name: 'Buscar no cardápio' }).pressSequentially('folha')
    const chips = overlay.locator('[data-search-filter-chips]')
    const collectionChip = chips.getByRole('button', { name: /^Folhados/ })
    await expect(collectionChip).toBeVisible()
    await capture(page, testInfo, 'busca-colecao')

    await collectionChip.click()
    await expect(page).toHaveURL(/\/colecao\/folhados$/)
    await settled(page)
    // Navegar fecha a busca: a coleção fica à vista, sem a busca por cima.
    await searchGone(page)
    await expect(page.getByRole('heading', { name: 'Folhados', level: 1 })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Trilha de navegação' }).getByRole('link', { name: 'Cardápio' })).toBeVisible()
    await expect(page.getByRole('main').getByRole('link', { name: /Croissant/ }).first()).toBeVisible()
    await capture(page, testInfo, 'colecao')
  })

  await test.step('da coleção, o produto abre', async () => {
    await page.getByRole('main').getByRole('link', { name: /Croissant/ }).first().click()
    await expect(page).toHaveURL(/\/produto\//)
    await settled(page)
    await expect(page.getByRole('heading', { name: /Croissant/, level: 1 })).toBeVisible()
    await capture(page, testInfo, 'produto')
  })
})

test('J12: a busca que não acha nada diz isso e leva ao cardápio', async ({ page }, testInfo) => {
  await test.step('no fim da coleção, a cliente volta a buscar', async () => {
    await page.goto('/colecao/folhados')
    await settled(page)
    const endActions = page.locator('[data-collection-end-actions]')
    await expect(endActions.getByText('Ainda procurando algo?')).toBeVisible()
    await endActions.getByRole('button', { name: 'Buscar no cardápio' }).click()
    await searchShown(page)
    await expect(searchOverlay(page).getByRole('searchbox', { name: 'Buscar no cardápio' })).toBeFocused()
  })

  await test.step('o termo sem resultado mostra o vazio com a saída para o cardápio', async () => {
    const overlay = searchOverlay(page)
    await overlay.getByRole('searchbox', { name: 'Buscar no cardápio' }).pressSequentially('xyzqw')
    await expect(overlay.locator('[data-search-results]')).toHaveCount(0)
    const exit = overlay.locator('[data-search-empty-menu]')
    await expect(exit).toBeVisible()
    await capture(page, testInfo, 'busca-vazia')

    await exit.click()
    await expect(page).toHaveURL(/\/menu/)
    await settled(page)
    await searchGone(page)
    await capture(page, testInfo, 'cardapio')
  })
})
