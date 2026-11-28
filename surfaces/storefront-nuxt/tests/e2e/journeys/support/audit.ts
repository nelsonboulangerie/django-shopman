import { createRequire } from 'node:module'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { basename, join, relative } from 'node:path'
import type { Page, TestInfo } from '@playwright/test'
import { AXE_TAGS, VIEWPORTS, summarizeX11, summarizeX9 } from '../../../../scripts/experience-compare.mjs'
import { auditTypographyInPage } from '../../../journeys/support/typographyAudit.mjs'
import { experience, readShell } from './experience'

// Cada passo de uma jornada é auditado do mesmo jeito nas duas versões: captura, axe
// (X10), X9 nos `data-decisive` e X11 com a fonte raiz a 200 %, em 320/375/390 px e no
// computador. X9 e X11 são a MESMA medida da varredura da fila (OC-30,
// tests/journeys/support/typographyAudit.mjs); aqui ela roda também com `obscured`, que
// acusa o que fica embaixo de barra ou cartão fixo. O resumo é de
// scripts/experience-compare.mjs.
// A auditoria não reprova a jornada: ela é a medida que o relatório compara. O que reprova
// é a jornada não chegar ao fim, ou a versão do servidor não ser a esperada.

const require = createRequire(import.meta.url)
const AXE_SOURCE = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8')
const steps = new Map<string, number>()

/** Onde o passo grava: <saída>/<versão>/<jornada>/<NN-passo>/. */
function stepDir (testInfo: TestInfo, name: string): { dir: string, step: string, journey: string } {
  const journey = basename(testInfo.file).replace(/\.spec\.ts$/, '')
  const n = (steps.get(testInfo.testId) ?? 0) + 1
  steps.set(testInfo.testId, n)
  const step = `${String(n).padStart(2, '0')}-${name}`
  const dir = join(experience.out, journey, step)
  mkdirSync(dir, { recursive: true })
  return { dir, step, journey }
}

/** Espera o layout assentar depois de mudar largura ou fonte: dois quadros e as fontes. */
async function settleLayout (page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  })
  // As fotos à vista carregam antes da captura: a loja usa `loading="lazy"`, e trocar de
  // largura traz fotos novas para a tela. Captura com o quadro vazio não serve para pôr A e
  // B lado a lado.
  await page.waitForFunction(() => [...document.images]
    .filter((img) => {
      const r = img.getBoundingClientRect()
      return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight
    })
    .every(img => img.complete), undefined, { timeout: 8_000 }).catch(() => undefined)
  // Transições curtas (folhas, carrosséis) terminam antes da captura.
  await page.waitForFunction(() => document.getAnimations()
    .filter(a => a.effect?.getTiming().iterations !== Infinity)
    .every(a => a.playState !== 'running'), undefined, { timeout: 3_000 }).catch(() => undefined)
}

async function runAxe (page: Page) {
  const loaded = await page.evaluate(() => typeof (window as Window & { axe?: unknown }).axe !== 'undefined')
  if (!loaded) await page.evaluate(AXE_SOURCE)
  return await page.evaluate(async (tags) => {
    const axe = (window as unknown as { axe: { run: (ctx: object, opts: object) => Promise<{ violations: Array<{ id: string, impact: string | null, help: string, nodes: Array<{ target: unknown[] }> }> }> } }).axe
    // Fora da medida: a fita "Ambiente de desenvolvimento" (EnvironmentRibbon.vue), fixa,
    // `aria-hidden` e sem toque. Só existe fora de produção; medida, ela punha um
    // color-contrast em toda tela das duas versões e escondia o que é da loja.
    const context = { exclude: [['.fixed.pointer-events-none[aria-hidden="true"]']] }
    const result = await axe.run(context, { runOnly: { type: 'tag', values: tags }, resultTypes: ['violations'] })
    return result.violations.map(v => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      nodes: v.nodes.length,
      targets: v.nodes.slice(0, 5).map(n => n.target.map(String).join(' '))
    }))
  }, AXE_TAGS)
}

/** A fonte raiz a 200 % (X11), como a cliente que aumenta a letra no sistema. */
async function setRootFont (page: Page, size: '200%' | ''): Promise<void> {
  await page.evaluate((value) => { document.documentElement.style.fontSize = value }, size)
}

export interface AuditOptions {
  /** Larguras a auditar (padrão: as quatro). Um diálogo que fecha ao trocar de largura
   *  pede só a da jornada. */
  widths?: string[]
}

/**
 * Audita o passo em todas as larguras e volta a página como estava (375 px, fonte do
 * navegador). Grava `audit.json` e as capturas no diretório do passo.
 */
export async function auditStep (page: Page, testInfo: TestInfo, name: string, options: AuditOptions = {}): Promise<void> {
  const { dir, step } = stepDir(testInfo, name)
  const original = page.viewportSize()!
  const wanted = VIEWPORTS.filter(v => !options.widths || options.widths.includes(v.name))
  // A largura da jornada primeiro: o estado da tela é o dela.
  const ordered = [...wanted.filter(v => v.width === original.width), ...wanted.filter(v => v.width !== original.width)]
  const record: Record<string, unknown> & { viewports: Record<string, unknown> } = {
    step,
    url: new URL(page.url()).pathname,
    variant: experience.variant,
    at: new Date().toISOString(),
    viewports: {}
  }
  for (const vp of ordered) {
    await page.setViewportSize({ width: vp.width, height: vp.height })
    await settleLayout(page)
    const capture = join(dir, `${vp.name}.png`)
    await page.screenshot({ path: capture })
    const axe = await runAxe(page)
    const x9 = summarizeX9(await page.evaluate(auditTypographyInPage, {}))
    await setRootFont(page, '200%')
    await settleLayout(page)
    const captureFont200 = join(dir, `${vp.name}-fonte200.png`)
    await page.screenshot({ path: captureFont200 })
    const x11 = summarizeX11(await page.evaluate(auditTypographyInPage, { zoomed: true, obscured: true }))
    await setRootFont(page, '')
    await settleLayout(page)
    record.viewports[vp.name] = {
      capture: relative(experience.out, capture),
      captureFont200: relative(experience.out, captureFont200),
      axe,
      x9,
      x11
    }
  }
  await page.setViewportSize(original)
  await settleLayout(page)
  record.shell = await readShell(page)
  writeFileSync(join(dir, 'audit.json'), JSON.stringify(record, null, 2))
  await testInfo.attach(step, { path: join(dir, `${ordered[0]!.name}.png`), contentType: 'image/png' })
}
