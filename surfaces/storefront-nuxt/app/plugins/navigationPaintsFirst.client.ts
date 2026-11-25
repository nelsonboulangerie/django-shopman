// Pinta antes de trabalhar (DEV-2026-094): a troca de página espera UM quadro pintado.
//
// Espelho de `surfaces/operator-kit/app/plugins/navigationPaintsFirst.client.ts` (a loja
// não estende a layer dos operadores). Medido em 25/11/2026: a montagem da tela nova
// prende a thread principal por centenas de milissegundos, e o que diz "o toque chegou"
// (link esmaecido, barra de rota, giro do botão) já está no DOM mas não pinta. Este
// guarda roda depois do middleware e só deixa a navegação seguir depois do próximo
// quadro. Custo: um quadro (~16 ms) por troca de página; aba em segundo plano não pinta,
// por isso a espera tem teto curto e nunca segura a navegação.
export function nextPaint (ceilingMs = 50): Promise<void> {
  return new Promise((resolve) => {
    let done = false
    const finish = () => {
      if (done) return
      done = true
      resolve()
    }
    requestAnimationFrame(() => setTimeout(finish, 0))
    setTimeout(finish, ceilingMs)
  })
}

export default defineNuxtPlugin({
  name: 'storefront:navigation-paints-first',
  setup (nuxtApp) {
    const router = useRouter()
    router.beforeEach(async (to, from) => {
      if (nuxtApp.isHydrating || to.path === from.path) return
      await nextPaint()
    })
  }
})
