// X9 e X11 (docs/reports/2026-11-23-etapa-ii-omnicanal-espec-e-plano.md, §6): o que decide
// a compra se lê sem esforço. Esta função roda DENTRO da página (page.evaluate) e mede o que
// o navegador desenhou, não o que o código pretendia:
//
//   - todo `[data-decisive]` visível (preço, disponibilidade, total, estado, erro) tem pelo
//     menos 14 px e contraste AA contra o fundo que está de fato atrás dele (4,5:1; 3:1 se
//     for texto grande, 24 px ou 18,66 px em negrito);
//   - todo `.shop-reading` (corpo de leitura) tem pelo menos 16 px;
//   - com `zoomed`, nenhum decisivo nem CTA (botão, link com papel de botão) some ou fica
//     cortado: tamanho zero, fora da largura da tela ou com o texto maior que a própria
//     caixa sob `overflow` que esconde;
//   - com `zoomed` e `obscured` (opt-in, a comparação A/B do OC-23 liga), nenhum decisivo
//     nem CTA fica EMBAIXO de outra coisa: levado ao meio da tela, o ponto que ele ocupa
//     é dele, não de um cabeçalho grudado, de uma folha ou de uma foto por cima (WCAG
//     1.4.4, 1.4.10, 2.4.11). O cartão de ação da base (`.shop-action-dock`) fica de fora
//     desta: tem regra própria, abaixo (#3573). Opt-in porque a varredura do X9 da fila
//     (x9-tipografia-decisiva.spec.ts) ainda não tem issue para cada achado desta medida.
//
// O fundo é composto subindo pelos ancestrais até o primeiro opaco; cor em qualquer espaço
// (oklch, color-mix) é normalizada pelo canvas. Sobre foto (`background-image` ou `<img>`
// irmão por baixo) o fundo real é desconhecido: a medida usa a camada translúcida composta
// sobre branco e marca `overImage`, para quem lê saber que é aproximação.
//
// É JavaScript puro (sem TypeScript) para servir à suíte (tests/journeys) e ao script de
// prévia que mede antes e depois com o mesmo código.

/** @param {{ zoomed?: boolean, obscured?: boolean, inventory?: boolean }} [opts] */
export function auditTypographyInPage (opts = {}) {
  const zoomed = Boolean(opts.zoomed)
  const obscured = zoomed && Boolean(opts.obscured)
  const canvas = document.createElement('canvas')
  canvas.width = 1
  canvas.height = 1
  const ctx = canvas.getContext('2d', { willReadFrequently: true })

  /** @returns {[number, number, number, number]} r, g, b em 0..255 e alfa em 0..1 */
  function rgba (color) {
    if (!color || color === 'transparent') return [0, 0, 0, 0]
    ctx.clearRect(0, 0, 1, 1)
    ctx.fillStyle = '#000'
    ctx.fillStyle = color
    ctx.fillRect(0, 0, 1, 1)
    const d = ctx.getImageData(0, 0, 1, 1).data
    return [d[0], d[1], d[2], d[3] / 255]
  }
  function over (top, bottom) {
    const a = top[3] + bottom[3] * (1 - top[3])
    if (a === 0) return [0, 0, 0, 0]
    const mix = i => (top[i] * top[3] + bottom[i] * bottom[3] * (1 - top[3])) / a
    return [mix(0), mix(1), mix(2), a]
  }
  function luminance (c) {
    const lin = v => {
      const s = v / 255
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
    }
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])
  }
  function ratio (a, b) {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (hi + 0.05) / (lo + 0.05)
  }

  function backgroundOf (el) {
    const layers = []
    let overImage = false
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      const cs = getComputedStyle(node)
      if (cs.backgroundImage && cs.backgroundImage !== 'none') overImage = true
      const c = rgba(cs.backgroundColor)
      const opacity = Number(cs.opacity)
      if (c[3] > 0) layers.push([c[0], c[1], c[2], c[3] * opacity])
      if (c[3] * opacity >= 0.999) break
      // Uma foto por baixo, no mesmo bloco posicionado (o selo sobre a foto do produto).
      if (!overImage && node.parentElement && [...node.parentElement.children].some(s => s !== node && s.tagName === 'IMG')) overImage = true
    }
    let bg = [255, 255, 255, 1]
    for (let i = layers.length - 1; i >= 0; i--) bg = over(layers[i], bg)
    return { bg, overImage }
  }

  function effectiveOpacity (el) {
    let o = 1
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) o *= Number(getComputedStyle(node).opacity)
    return o
  }

  /** O que está por cima PINTA sobre o elemento? O link esticado do cartão (transparente,
   *  `absolute inset-0`) recebe o toque mas não esconde o preço: não é encobrir. Encobre o
   *  que tem fundo, imagem ou texto próprio entre o ponto e o ancestral comum. */
  function paintsOver (hit, el) {
    if (['IMG', 'SVG', 'VIDEO', 'CANVAS', 'PICTURE'].includes(hit.tagName.toUpperCase())) return true
    for (let node = hit; node && node.nodeType === 1 && !node.contains(el); node = node.parentElement) {
      const cs = getComputedStyle(node)
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return true
      if (rgba(cs.backgroundColor)[3] > 0.1) return true
      if ([...node.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return true
    }
    return false
  }

  function visible (el) {
    const cs = getComputedStyle(el)
    if (cs.visibility === 'hidden' || cs.display === 'none') return false
    if (el.closest('[aria-hidden="true"], [hidden], .sr-only')) return false
    const r = el.getBoundingClientRect()
    return r.width > 0 && r.height > 0
  }

  /** O texto próprio do elemento: o primeiro nó de texto não vazio dá o tamanho e a cor. */
  function textCarrier (el) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
      acceptNode: n => (n.textContent.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT)
    })
    const carriers = []
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const host = n.parentElement
      if (host && visible(host)) carriers.push(host)
    }
    return carriers
  }

  /** Onde está: o elemento e três ancestrais, com classe e largura, para o achado se achar. */
  function where (el) {
    const chain = []
    for (let n = el; n && chain.length < 4; n = n.parentElement) {
      chain.push(`${n.tagName.toLowerCase()}.${String(n.className).trim().split(/\s+/).slice(0, 4).join('.')}[${Math.round(n.getBoundingClientRect().width)}]`)
    }
    return chain.join(' < ')
  }

  function label (el) {
    return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60)
  }

  const findings = []
  // Contraste abaixo do AA que o dono decidiu manter por ora, com issue aberta para sair
  // (`data-contrast-exception="<nome>-<issue>"`): vai para cá, à vista, e não reprova.
  // Só contraste: o tamanho de 14 px vale sempre.
  const exceptions = []
  const measured = []

  for (const el of document.querySelectorAll('[data-decisive]')) {
    if (!visible(el)) continue
    for (const host of textCarrier(el)) {
      const cs = getComputedStyle(host)
      const size = parseFloat(cs.fontSize)
      const weight = Number(cs.fontWeight) || 400
      const { bg, overImage } = backgroundOf(host)
      const fg = rgba(cs.color)
      const alpha = fg[3] * effectiveOpacity(host)
      const text = over([fg[0], fg[1], fg[2], alpha], bg)
      const contrast = ratio(text, bg)
      const large = size >= 24 || (size >= 18.66 && weight >= 600)
      const disabled = Boolean(host.closest('[disabled], [aria-disabled="true"]'))
      const row = {
        kind: el.getAttribute('data-decisive') || 'decisive',
        text: label(host),
        size,
        contrast: Math.round(contrast * 100) / 100,
        overImage,
        disabled
      }
      measured.push(row)
      if (size < 14 - 0.01) findings.push({ ...row, rule: 'decisivo abaixo de 14 px' })
      // Controle desativado é isento de contraste pela WCAG (1.4.3); o decisivo que o
      // explica precisa estar ao lado, legível, e é medido nele.
      if (!disabled && contrast < (large ? 3 : 4.5)) {
        const exception = host.closest('[data-contrast-exception]')?.getAttribute('data-contrast-exception')
        if (exception) exceptions.push({ ...row, rule: 'decisivo sem contraste AA', exception })
        else findings.push({ ...row, rule: 'decisivo sem contraste AA' })
      }
    }
  }

  for (const el of document.querySelectorAll('.shop-reading')) {
    if (!visible(el)) continue
    const size = parseFloat(getComputedStyle(el).fontSize)
    measured.push({ kind: 'reading', text: label(el), size })
    if (size < 16 - 0.01) findings.push({ kind: 'reading', text: label(el), size, rule: 'corpo de leitura abaixo de 16 px' })
  }

  if (zoomed) {
    // O cartão de ação preso na base (`.shop-action-dock`) deixa a página à vista: entre o
    // cabeçalho fixo e ele sobra pelo menos 45 % da tela (#3573; a regra e o porquê do
    // número em app/presentation/actionDock.ts, repetidos aqui porque esta função roda
    // sozinha dentro da página). Com a fonte a 200 % o cartão da sacola tomava, com a
    // navegação, 426 de 812 px, e o item, o preço e "Remover" ficavam atrás dele.
    const header = document.querySelector('.shop-header-bar')
    for (const dock of document.querySelectorAll('.shop-action-dock')) {
      if (!visible(dock) || getComputedStyle(dock).position !== 'fixed') continue
      const free = dock.getBoundingClientRect().top - (header ? header.offsetHeight : 0)
      const share = Math.round(free / window.innerHeight * 100) / 100
      if (share >= 0.45) continue
      const row = { kind: 'dock', text: label(dock).slice(0, 40), share, rule: 'cartão fixo na base cobre a página com fonte 200 %' }
      // Defeito conhecido com issue aberta para sair (`data-x11-exception="<nome>-<issue>"`):
      // vai para as exceções, à vista, como as de contraste.
      const exception = dock.getAttribute('data-x11-exception')
      if (exception) exceptions.push({ ...row, exception })
      else findings.push(row)
    }

    const vw = document.documentElement.clientWidth
    const scrollX0 = window.scrollX
    const scrollY0 = window.scrollY
    const ctas = document.querySelectorAll('[data-decisive], button, a[role="button"], a[data-slot="button"], [data-cta]')
    for (const el of ctas) {
      const cs = getComputedStyle(el)
      if (cs.display === 'none' || cs.visibility === 'hidden') continue
      if (el.closest('[aria-hidden="true"], [hidden], .sr-only, [data-state="closed"], [inert]')) continue
      const r = el.getBoundingClientRect()
      const name = label(el) || el.getAttribute('aria-label') || ''
      if (!name) continue
      // Encolhido a nada por quem o contém (o texto existe, a caixa não).
      if (r.width < 1 || r.height < 1) {
        // Escondido de propósito por um pai (menu fechado, aba inativa) não é corte.
        if (el.offsetParent === null) continue
        findings.push({ kind: 'cta', text: name, rule: 'some com fonte 200 %', where: where(el) })
        continue
      }
      // Num trilho que rola de lado (pílulas do cardápio, vitrine da home), estar fora da
      // tela é o normal: a cliente chega lá arrastando. Corte é sair de onde não se rola.
      const inRail = (() => {
        for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
          const s = getComputedStyle(a)
          if (['auto', 'scroll'].includes(s.overflowX) && a.scrollWidth > a.clientWidth + 1) return true
          // Carrossel: o slide inteiro fora da janela do carrossel espera a vez dele.
          if (['hidden', 'clip'].includes(s.overflowX)) {
            const ar = a.getBoundingClientRect()
            if (r.left >= ar.right - 1 || r.right <= ar.left + 1) return true
          }
        }
        return false
      })()
      if (!inRail && (r.right > vw + 1 || r.left < -1)) findings.push({ kind: 'cta', text: name, rule: 'sai da largura da tela com fonte 200 %', left: Math.round(r.left), right: Math.round(r.right), vw, where: where(el) })
      const clips = ['hidden', 'clip'].includes(cs.overflowX) || cs.textOverflow === 'ellipsis'
      if (clips && el.scrollWidth > el.clientWidth + 1) findings.push({ kind: 'cta', text: name, rule: 'texto cortado com fonte 200 %', where: where(el) })
      // A linha cortada por `line-clamp`/altura fixa: o texto é mais alto que a caixa.
      if (['hidden', 'clip'].includes(cs.overflowY) && el.scrollHeight > el.clientHeight + 2) findings.push({ kind: 'cta', text: name, rule: 'texto cortado na altura com fonte 200 %', where: where(el) })
      // Botão que só aparece no hover (opacidade zero) não está à vista para ser encoberto.
      if (obscured && !inRail && effectiveOpacity(el) > 0.05) {
        // Levado ao meio da tela (o que a cliente faria rolando), o ponto do elemento é
        // dele? O que não rola até ali (o fim da página sob um cartão fixo) fica embaixo.
        el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' })
        const box = el.getBoundingClientRect()
        const vh = document.documentElement.clientHeight
        const cx = Math.min(Math.max(box.left + Math.min(box.width, 40) / 2, 0), vw - 1)
        const cy = Math.min(Math.max(box.top + box.height / 2, 0), vh - 1)
        const hit = document.elementFromPoint(cx, cy)
        // O cartão da base já é medido pela regra dele (área livre, #3573) e, onde segue com
        // defeito, é exceção declarada (#3590): não se conta duas vezes.
        const byDock = hit && hit.closest('.shop-action-dock')
        if (hit && !byDock && !(hit === el || el.contains(hit) || hit.contains(el)) && paintsOver(hit, el)) {
          // A camada que cobre: o primeiro ancestral fixo ou grudado (barra, cartão da base),
          // para o achado dizer QUEM cobre mesmo quando o ponto cai num texto dentro dela.
          let layer = hit
          while (layer && layer.nodeType === 1 && !['fixed', 'sticky'].includes(getComputedStyle(layer).position)) layer = layer.parentElement
          findings.push({ kind: 'cta', text: name, rule: 'encoberto com fonte 200 %', by: where(hit), layer: layer && layer.nodeType === 1 ? where(layer) : '', where: where(el) })
        }
      }
    }
    if (obscured) window.scrollTo({ left: scrollX0, top: scrollY0, behavior: 'instant' })
  }

  // Inventário da prévia: TODO texto visível da página, decisivo ou não, com tamanho e
  // contraste. Não reprova nada; é o antes e depois que o dono lê.
  const inventory = []
  if (opts.inventory) {
    const seen = new Set()
    for (const host of textCarrier(document.body)) {
      if (seen.has(host)) continue
      seen.add(host)
      const cs = getComputedStyle(host)
      const { bg, overImage } = backgroundOf(host)
      const fg = rgba(cs.color)
      const text = over([fg[0], fg[1], fg[2], fg[3] * effectiveOpacity(host)], bg)
      const size = parseFloat(cs.fontSize)
      const weight = Number(cs.fontWeight) || 400
      inventory.push({
        text: [...host.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').replace(/\s+/g, ' ').trim().slice(0, 60),
        size,
        contrast: Math.round(ratio(text, bg) * 100) / 100,
        large: size >= 24 || (size >= 18.66 && weight >= 600),
        overImage,
        disabled: Boolean(host.closest('[disabled], [aria-disabled="true"]')),
        decisive: Boolean(host.closest('[data-decisive]'))
      })
    }
  }

  const horizontalScroll =document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
  if (horizontalScroll) findings.push({ kind: 'page', text: '', rule: 'rolagem lateral', scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth })

  return { findings, measured, inventory, exceptions }
}
