// O toque em Adicionar que a página não chegou a executar (#3171, F-18).
//
// A cliente toca em Adicionar antes de a página hidratar (o script inline guarda o
// toque, `utils/earlyTap.ts`) e sai dela: abre a Sacola, que ainda é um link comum, ou
// recarrega. A página nova não tem o botão daquele produto, ou tem e ele já o
// reclamou. O que ninguém reclamou o app executa aqui, depois de montar, e a sacola
// nasce com o item.
import { parseCartAddKey, takeOrphanEarlyTaps } from '~/utils/earlyTap'

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.hook('app:mounted', () => {
    // Depois dos `onMounted` desta página: cada botão montado reclama o próprio toque
    // primeiro, e o que sobra é órfão.
    setTimeout(() => {
      const { replayEarlyAdd } = useCartState()
      for (const tap of takeOrphanEarlyTaps()) {
        const add = parseCartAddKey(tap.key)
        if (!add) continue
        // O erro já tem aviso próprio no useCartState; aqui só não vira rejeição solta.
        void replayEarlyAdd(add.sku, tap.name, add.qty).catch(() => {})
      }
    }, 0)
  })
})
