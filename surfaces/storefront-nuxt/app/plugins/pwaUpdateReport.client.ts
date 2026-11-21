// No boot seguinte a uma troca de versão da loja instalada, conta a troca ao Django
// (#2379): a marca foi escrita pelo `PwaUpdatePrompt` antes de o worker novo assumir,
// e só agora, com o bundle novo rodando, a versão de chegada é conhecida.
import { PWA_UPDATE_ENDPOINT, reportPwaUpdateApplied } from '~/utils/pwaUpdateReport'

export default defineNuxtPlugin(() => {
  const apiPath = useShopmanApiPath()
  const endpoint = apiPath(PWA_UPDATE_ENDPOINT)
  const appVersion = String(useRuntimeConfig().public.appVersion ?? '')
  // Fire-and-forget: telemetria nunca segura o boot nem aparece para a cliente.
  // O `await` sem retorno é de propósito: devolver o `$fetch` tipado faz o TypeScript
  // comparar a resposta de cada rota do Nitro com `Promise<unknown>` e estourar a
  // pilha (TS2321, typecheck do CI do #3038).
  void reportPwaUpdateApplied(appVersion, async (body) => {
    await $fetch(endpoint, { method: 'POST', body, credentials: 'include' })
  })
})
