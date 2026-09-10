import type { AuthSessionResponse } from '~/types/shopman'
import { loginDestination } from '~/utils/loginDestination'

// Guarda de auth compartilhada pelas páginas autenticadas (/conta/* e o checkout).
// Resolve a sessão uma vez (SSR com cookie), popula useShopSession e redireciona para
// o login preservando o destino — sem flash da tela gated. Zero guard inline por página.
export default defineNuxtRouteMiddleware(async (to, from) => {
  const apiPath = useShopmanApiPath()
  const session = useShopSession()
  const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

  const auth = await $fetch<AuthSessionResponse>(apiPath('/api/auth/session/'), {
    credentials: 'include',
    headers: requestHeaders
  }).catch(() => null)

  session.setFromAuthSession(auth)

  if (!auth?.is_authenticated) {
    // ⚠️ O destino não é sempre a rota barrada — ver `loginDestination`.
    //
    // Não há botão "Entrar" na loja: a única porta é a aba "Conta". Gravar
    // cegamente `to.fullPath` fazia quem tocava nela só para se identificar
    // voltar para `/conta`, uma tela que não pediu, perdendo a página em que
    // estava. "Entrar" e "ver minha conta" eram o mesmo gesto.
    const destino = loginDestination(to.fullPath, from?.fullPath)
    return navigateTo(`/entrar?next=${encodeURIComponent(destino)}`)
  }
})
