/**
 * Confete do momento yoin — comemorar sem ocupar layout.
 *
 * O banner "Pedido recebido" ficava fixo no topo do acompanhamento, competindo
 * com o painel de status e repetindo uma notícia velha (no fluxo Pix ele
 * aterrissava DEPOIS do pagamento). A celebração virou efêmera: aparece, some,
 * e não rouba espaço de quem só quer saber do pedido.
 *
 * Sem biblioteca: um canvas fixo, `pointer-events-none`, removido ao terminar.
 *
 * `prefers-reduced-motion` é respeitado de verdade — quem pediu menos movimento
 * não vê animação nenhuma, e a função sai sem desenhar nada.
 */

type Particula = {
  x: number
  y: number
  vx: number
  vy: number
  rot: number
  vrot: number
  cor: string
  tam: number
}

const CORES_PADRAO = ['#7B2D3B', '#C9A227', '#F2E8D5', '#4A5D45']
const DURACAO_MS = 1800
const GRAVIDADE = 0.12

function corDaMarca (): string[] {
  if (typeof window === 'undefined') return CORES_PADRAO
  const raiz = getComputedStyle(document.documentElement)
  const tokens = ['--primary', '--brass', '--secondary']
    .map(t => raiz.getPropertyValue(t).trim())
    .filter(Boolean)
    .map(v => (v.startsWith('#') || v.startsWith('rgb') || v.startsWith('oklch') ? v : `oklch(${v})`))
  return tokens.length ? tokens : CORES_PADRAO
}

export function prefereMenosMovimento (): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Dispara o confete. Não faz nada no servidor nem com movimento reduzido.
 * Devolve `true` quando chegou a animar — útil em teste.
 */
export function dispararConfetti (quantidade = 70): boolean {
  if (typeof window === 'undefined' || typeof document === 'undefined') return false
  if (prefereMenosMovimento()) return false

  const canvas = document.createElement('canvas')
  canvas.setAttribute('aria-hidden', 'true')
  canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:60'
  const dpr = window.devicePixelRatio || 1
  canvas.width = window.innerWidth * dpr
  canvas.height = window.innerHeight * dpr
  const ctx = canvas.getContext('2d')
  if (!ctx) return false
  ctx.scale(dpr, dpr)
  document.body.appendChild(canvas)

  const cores = corDaMarca()
  const particulas: Particula[] = Array.from({ length: quantidade }, () => ({
    x: window.innerWidth / 2 + (Math.random() - 0.5) * window.innerWidth * 0.6,
    y: window.innerHeight * 0.28 + (Math.random() - 0.5) * 60,
    vx: (Math.random() - 0.5) * 7,
    vy: Math.random() * -6 - 2,
    rot: Math.random() * Math.PI,
    vrot: (Math.random() - 0.5) * 0.3,
    cor: cores[Math.floor(Math.random() * cores.length)]!,
    tam: 5 + Math.random() * 5
  }))

  const inicio = performance.now()
  let frame = 0

  function passo (agora: number) {
    const decorrido = agora - inicio
    if (decorrido >= DURACAO_MS) {
      canvas.remove()
      return
    }
    ctx!.clearRect(0, 0, window.innerWidth, window.innerHeight)
    ctx!.globalAlpha = Math.max(0, 1 - decorrido / DURACAO_MS)
    for (const p of particulas) {
      p.x += p.vx
      p.y += p.vy
      p.vy += GRAVIDADE
      p.rot += p.vrot
      ctx!.save()
      ctx!.translate(p.x, p.y)
      ctx!.rotate(p.rot)
      ctx!.fillStyle = p.cor
      ctx!.fillRect(-p.tam / 2, -p.tam / 2, p.tam, p.tam * 0.6)
      ctx!.restore()
    }
    frame = requestAnimationFrame(passo)
  }

  frame = requestAnimationFrame(passo)

  // Sair da página no meio da animação não pode deixar canvas nem loop soltos.
  window.addEventListener('pagehide', () => {
    cancelAnimationFrame(frame)
    canvas.remove()
  }, { once: true })

  return true
}
