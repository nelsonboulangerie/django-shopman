import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import sharp from 'sharp'
import { describe, expect, it } from 'vitest'

// A marca do Storefront é o selo: monograma marrom `#aa6a2b` sobre disco amarelo
// `#ffcd40`. Ele entra em duas versões, e o formato do ícone decide qual:
// `brand/nelson-mark.svg` (fundo transparente fora do círculo) onde há alfa, e
// `brand/nelson-mark-bg.svg` (quadrado amarelo em degradê, de ponta a ponta) onde
// o formato exige opacidade.
const DISC_YELLOW = [255, 205, 64]
const MONOGRAM_BROWN = [170, 106, 43]

const raw = async (file: string) => {
  const { data, info } = await sharp(resolve(file)).ensureAlpha().raw().toBuffer({ resolveWithObject: true })
  return { data, info, at: (x: number, y: number) => Array.from(data.subarray((y * info.width + x) * 4, (y * info.width + x) * 4 + 4)) }
}

describe('storefront PWA assets', () => {
  it('keeps the approved yellow seal: brown monogram on the #ffcd40 disc', async () => {
    const regular = await raw('public/pwa/pwa-512x512.png')
    const maskable = await raw('public/pwa/maskable-512x512.png')
    const apple = await raw('public/pwa/apple-touch-icon-180x180.png')

    for (const [name, image] of [['pwa-512', regular], ['maskable', maskable], ['apple', apple]] as const) {
      const middle = Math.floor(image.info.width / 2)
      expect(image.at(middle, middle), `${name}: monograma no centro`).toEqual([...MONOGRAM_BROWN, 255])
    }

    // No `any` o disco encosta na borda: a 30% do centro já é o amarelo do selo.
    expect(regular.at(Math.floor(regular.info.width * 0.8), Math.floor(regular.info.width / 2))).toEqual([...DISC_YELLOW, 255])
  })

  it('paints the opaque formats with the gradient field, not a flat yellow', async () => {
    // `maskable` (launcher Android) e `apple-touch-icon` (iOS pinta de preto o que
    // for transparente) usam `nelson-mark-bg.svg`: quadrado cheio, amarelo em
    // degradê `#cca135` → `#ffcd40` → `#e6b93a`. Se o degradê virar cor chapada, o
    // canto e o meio da borda passam a ser o mesmo pixel — é isso que se mede.
    for (const name of ['maskable-512x512.png', 'apple-touch-icon-180x180.png']) {
      const image = await raw(`public/pwa/${name}`)
      const corner = image.at(0, 0)
      const topEdgeMiddle = image.at(Math.floor(image.info.width / 2), 0)

      expect(corner[3], `${name}: canto opaco`).toBe(255)
      expect(corner, `${name}: canto é campo amarelo`).toEqual([230, 185, 58, 255])
      expect(topEdgeMiddle, `${name}: degradê clareia da quina para o meio`).toEqual([243, 195, 61, 255])
    }
  })

  it('leaves the any-purpose icons as a free-standing disc: desktop shows them unmasked', async () => {
    // Windows, macOS e Linux mostram o `any` COMO ESTÁ, sem máscara. O selo é
    // redondo por desenho, então o canto fica transparente e o disco preenche o
    // quadro. `maskable` e `apple-touch-icon` seguem cheios: o SO recorta sozinho.
    for (const size of [64, 192, 512]) {
      const image = await raw(`public/pwa/pwa-${size}x${size}.png`)
      expect(image.at(0, 0)[3], `pwa-${size}x${size} canto`).toBe(0)
      // O disco não encosta na borda: sobra folga. Em 64 px essa folga é menor que
      // um pixel e o meio da borda sai antisserrilhado (alfa 75), não opaco — por
      // isso a medida é "não preenchido", e não "zero".
      expect(image.at(Math.floor(size / 2), 0)[3], `pwa-${size}x${size} meio da borda de cima`).toBeLessThan(255)
      const transparent = Array.from({ length: size * size }, (_, pixel) => image.data[pixel * 4 + 3]).filter(value => value === 0).length
      expect(transparent / (size * size), `pwa-${size}x${size}: fração transparente de um disco`).toBeGreaterThan(0.2)
      expect(transparent / (size * size), `pwa-${size}x${size}: fração transparente de um disco`).toBeLessThan(0.28)
    }
    for (const name of ['maskable-512x512.png', 'apple-touch-icon-180x180.png']) {
      const image = await raw(`public/pwa/${name}`)
      expect(image.at(0, 0)[3], `${name} canto`).toBe(255)
    }

    // Nada opaco passa do círculo inscrito, e o disco não encolheu dentro do quadro.
    const { data, info } = await raw('public/pwa/pwa-512x512.png')
    const center = info.width / 2
    let farthest = 0
    for (let pixel = 0; pixel < info.width * info.height; pixel += 1) {
      if (data[pixel * 4 + 3] < 200) continue
      const x = (pixel % info.width) + 0.5 - center
      const y = Math.floor(pixel / info.width) + 0.5 - center
      farthest = Math.max(farthest, Math.hypot(x, y) / info.width)
    }
    expect(farthest).toBeGreaterThan(0.45)
    expect(farthest).toBeLessThanOrEqual(0.5)
  })

  it('keeps the installed-icon geometry of the operator family, so the Dock shows both at one size', async () => {
    // O Chrome no macOS gera o ícone do app a partir do `maskable` (recorte na grade
    // do macOS, forma em 412/512) e só cai no `any` de ponta a ponta quando não há
    // `maskable`. A loja estava 512/512 contra 412/512 do PDV no Dock (17/09/2026).
    // A paridade que resolveu aquilo é a do `maskable` e a do `apple-touch-icon`:
    // os dois são quadrados opacos, como na família de operador. O `any` NÃO entra
    // aqui — a loja é superfície de cliente e a marca dela é um selo redondo, não o
    // retângulo arredondado dos apps de operador.
    const alpha = async (file: string) => {
      const { data, info } = await sharp(resolve(file)).ensureAlpha().raw().toBuffer({ resolveWithObject: true })
      return { alpha: Array.from({ length: info.width * info.height }, (_, pixel) => data[pixel * 4 + 3]), info, data }
    }
    const operatorReference = '../pos-nuxt/public/pwa'
    for (const name of ['maskable-512x512.png', 'apple-touch-icon-180x180.png']) {
      const store = await alpha(`public/pwa/${name}`)
      const operator = await alpha(`${operatorReference}/${name}`)
      expect(store.info.width, name).toBe(operator.info.width)
      const divergent = store.alpha.filter((value, pixel) => Math.abs(value - operator.alpha[pixel]) > 8).length
      expect(divergent, `${name}: pixels de forma diferentes da família de operador`).toBe(0)
    }

    // Onde o traço marrom do `maskable` chega, medido em fração do lado. A arte de
    // fundo oficial leva o ANEL do selo a 0,452 — fora do círculo de 40% que o
    // launcher Android pode recortar. É propriedade da arte entregue pelo dono, não
    // do gerador: o corte possível é a borda fina do anel, nunca o monograma. Se um
    // dia o selo tiver de caber no círculo de 40%, a arte é que encolhe.
    const { data, info } = await alpha('public/pwa/maskable-512x512.png')
    const center = info.width / 2
    let farthest = 0
    for (let pixel = 0; pixel < info.width * info.height; pixel += 1) {
      const offset = pixel * 4
      const [red, green, blue] = [data[offset], data[offset + 1], data[offset + 2]]
      if (red > 120 && red < 210 && green > 70 && green < 150 && blue < 90) {
        const x = (pixel % info.width) + 0.5 - center
        const y = Math.floor(pixel / info.width) + 0.5 - center
        farthest = Math.max(farthest, Math.hypot(x, y) / info.width)
      }
    }
    expect(farthest).toBeGreaterThan(0.2)
    expect(farthest).toBeLessThanOrEqual(0.46)
  })

})
