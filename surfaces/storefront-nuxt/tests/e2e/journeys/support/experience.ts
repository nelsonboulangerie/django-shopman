import { resolve } from 'node:path'
import { expect, type Page } from '@playwright/test'
import { variantFromShell } from '../../../../scripts/experience-compare.mjs'

// A rodada da comparação A/B: qual versão o servidor deve ter decidido, para qual
// experimento e para qual cliente. Tudo vem do ambiente que scripts/run_experience_compare.sh
// monta; nada daqui escolhe a versão (decisão D1: só o servidor decide, nunca a URL).

export const experience = {
  /** O que esta rodada espera do servidor: a cliente fora (a) ou dentro (b) da coorte. */
  variant: process.env.EXPERIENCE_VARIANT as 'a' | 'b',
  /** Os experimentos ligados pelo seed (shopman/shop/tests/e2e/seed_experience.py): o de
   *  prova do harness e os que a loja anota no código como experimento (o marcador que
   *  scripts/check_experiments.py lê); a cliente está na mesma coorte em todos, então a
   *  versão esperada é a mesma em todos. */
  refs: (process.env.EXPERIENCE_REFS || 'prova-e2e').split(',').map(r => r.trim()).filter(Boolean),
  /** A cliente da jornada, a mesma nas duas rodadas (CLI-003 do seed `qa`). */
  customer: process.env.EXPERIENCE_CUSTOMER_REF || 'CLI-003',
  phone: process.env.EXPERIENCE_CUSTOMER_PHONE || '43993333333',
  out: resolve(process.env.EXPERIENCE_OUT || 'test-results/experience-compare', process.env.EXPERIENCE_VARIANT || 'a')
}

/** O shell que a loja lê (pelo BFF, com o cookie da cliente), como contrato cru. */
export async function readShell (page: Page): Promise<unknown> {
  return await page.evaluate(async () => {
    const response = await fetch('/api/v1/storefront/shell/', { credentials: 'include', headers: { Accept: 'application/json' } })
    return await response.json()
  })
}

/** A versão que o servidor decidiu, por experimento, para quem está nesta página. */
export async function serverVariants (page: Page): Promise<Record<string, string>> {
  const shell = await readShell(page)
  return Object.fromEntries(experience.refs.map(ref => [ref, variantFromShell(shell, ref)]))
}

/** Reprova se o servidor não decidiu, em cada experimento, a versão que a rodada espera. */
export async function expectServerVariant (page: Page): Promise<void> {
  expect(
    await serverVariants(page),
    `o servidor deveria ter decidido "${experience.variant}" para ${experience.customer} em ${experience.refs.join(', ')}`
  ).toEqual(Object.fromEntries(experience.refs.map(ref => [ref, experience.variant])))
}

/** Espera o Nuxt hidratar. Sem "networkidle": a loja mantém SSE aberto, e numa máquina
 *  carregada o idle não chega (o harness do OC-21 mediu 30 s estourados por isso). */
export async function hydrated (page: Page): Promise<void> {
  await page.waitForLoadState('domcontentloaded')
  await page.waitForFunction(() => {
    const root = document.querySelector('#__nuxt') as (Element & { __vue_app__?: unknown }) | null
    return Boolean(root?.__vue_app__)
  })
}

/** Começa a jornada com a sacola vazia: as jornadas dividem a mesma sessão da cliente
 *  (um login só por rodada; o código por SMS tem limite por telefone). */
export async function startsWithEmptyBag (page: Page): Promise<void> {
  await page.goto('/sacola')
  await hydrated(page)
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()
  const main = page.locator('main')
  for (let i = 0; i < 20; i += 1) {
    const remove = main.getByRole('button', { name: /^(Remover|Diminuir) / }).first()
    if (!(await remove.isVisible().catch(() => false))) break
    await remove.click()
    await page.waitForTimeout(400)
  }
  await expect(main.getByRole('group', { name: /^Quantidade de / })).toHaveCount(0, { timeout: 30_000 })
}
