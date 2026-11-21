// No boot seguinte a uma troca de versão da loja instalada, conta a troca ao Django
// (#2379): a marca foi escrita pelo `PwaUpdatePrompt` antes de o worker novo assumir,
// e só agora, com o bundle novo rodando, a versão de chegada é conhecida.
import { PWA_UPDATE_ENDPOINT, reportPwaUpdateApplied } from '~/utils/pwaUpdateReport'

export default defineNuxtPlugin(() => {
  const apiPath = useShopmanApiPath()
  const endpoint = apiPath(PWA_UPDATE_ENDPOINT)
  const appVersion = String(useRuntimeConfig().public.appVersion ?? '')
  // Fire-and-forget: telemetria nunca segura o boot nem aparece para a cliente.
  void reportPwaUpdateApplied(appVersion, body =>
    $fetch(endpoint, { method: 'POST', body, credentials: 'include' })
  )
})
