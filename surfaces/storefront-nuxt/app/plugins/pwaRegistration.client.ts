import { useRegisterSW } from 'virtual:pwa-register/vue'
import { bindPwaUpdateRegistration } from '~/composables/usePwaUpdate'

// Porte do `operator-kit/runtime/plugins/pwaRegistration.client.ts`.
//
// `registerType: 'prompt'` guarda o worker novo em "waiting" até todas as janelas do
// host fecharem. Num app instalado que fica dias aberto isso nunca acontece, e o
// aviso só aparece se o navegador chegar a buscar o `sw.js`. Guardar o registro aqui
// é o que dá a `usePwaUpdateCheck` como PERGUNTAR (`registration.update()`).
//
// Plugin, e não componente: plugin roda em toda carga do app, inclusive quando o Nuxt
// renderiza `error.vue` no lugar do `app.vue`.
export default defineNuxtPlugin(() => {
  let swRegistration: ServiceWorkerRegistration | undefined
  const registration = useRegisterSW({
    immediate: true,
    onRegisteredSW: (_url: string, active: ServiceWorkerRegistration | undefined) => {
      swRegistration = active
    }
  })
  bindPwaUpdateRegistration({
    needRefresh: registration.needRefresh,
    updateServiceWorker: registration.updateServiceWorker,
    checkForUpdate: async () => {
      if (!swRegistration) return false
      await swRegistration.update()
      return true
    }
  })
})
