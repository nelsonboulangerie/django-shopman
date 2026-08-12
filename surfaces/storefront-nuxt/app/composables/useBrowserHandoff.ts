// Atravessar do navegador embutido do WhatsApp para o navegador DE VERDADE dela.
//
// ⚠️ O motivo é um fato de plataforma: o webview do WhatsApp (WKWebView no iOS, WebView no
// Android) tem **pote de cookie próprio**. Sessão e aparelho confiado conquistados ali não
// existem no Safari/Chrome que ela usa no resto do dia — "confirmado para sempre neste
// aparelho" era, na prática, "neste webview".
//
// Em vez de sofrer isso, atravessamos de propósito, no momento em que já sabemos quem ela é.
// E é a porta de entrada da passkey: cadastrar credencial dentro do webview do WhatsApp é
// irregular; no navegador de verdade, não é.
//
// Não existe UM mecanismo universal para sair de um webview, então há três degraus, do bom ao
// honesto — e o último nunca falha porque é o menu do próprio WhatsApp.

/** O user agent do ambiente, se houver um.
 *
 *  ⚠️ `typeof navigator` e não `import.meta.client`: a checagem tem de ser sobre o AMBIENTE
 *  (existe navigator?), não sobre a fase do Nuxt. Amarrar no `import.meta.client` fazia estas
 *  funções puras responderem errado fora do runtime do Nuxt — e a primeira vítima foi o
 *  próprio teste, que pedia iOS e recebia o esquema de Android.
 */
function currentUserAgent(): string {
  return typeof navigator === 'undefined' ? '' : navigator.userAgent || ''
}

/** Estamos dentro de um navegador embutido? Só aí a travessia faz sentido. */
export function isInAppBrowser(userAgent?: string): boolean {
  const ua = (userAgent ?? currentUserAgent()).toLowerCase()
  if (!ua) return false
  // WhatsApp, Instagram e o navegador do Facebook (FBAN/FBAV) — os três que importam para
  // uma padaria que vive no WhatsApp e posta no Instagram.
  return ua.includes('whatsapp') || ua.includes('instagram') || ua.includes('fban') || ua.includes('fbav')
}

/** iOS? Decide QUAL truque tentar — os dois são de plataforma, não há um só que sirva. */
function isIOS(userAgent?: string): boolean {
  return /iphone|ipad|ipod/i.test(userAgent ?? currentUserAgent())
}

/**
 * Monta a URL que tenta abrir o navegador do sistema.
 *
 * - **Android**: `intent://…#Intent;scheme=https;package=com.android.chrome;end` é o
 *   mecanismo DOCUMENTADO do Android para entregar uma navegação a outro app. Funciona na
 *   maioria dos webviews.
 * - **iOS**: `x-safari-https://…` abre o Safari de dentro de um webview. Funciona em muita
 *   coisa, mas **não é abençoado pela Apple** e pode parar sem aviso — por isso existe o
 *   terceiro degrau.
 */
export function systemBrowserUrl(url: string, userAgent?: string): string {
  if (isIOS(userAgent)) {
    return url.replace(/^https:\/\//, 'x-safari-https://')
  }
  const withoutScheme = url.replace(/^https?:\/\//, '')
  return `intent://${withoutScheme}#Intent;scheme=https;package=com.android.chrome;end`
}

export function useBrowserHandoff() {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()
  const route = useRoute()

  const working = ref(false)
  /** O truque não pegou: a tela passa a ensinar o menu do WhatsApp, que sempre funciona. */
  const needsManualStep = ref(false)
  const failed = ref(false)

  async function crossOver() {
    working.value = true
    needsManualStep.value = false
    failed.value = false
    try {
      const response = await $fetch<{ url: string }>(apiPath('/api/v1/auth/handoff/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: { next: route.fullPath }
      })
      if (!response?.url) {
        failed.value = true
        return
      }

      // ⚠️ O truque não avisa quando falha: se o esquema não for entendido, o webview
      // simplesmente não navega. Então marcamos "faça pelo menu" depois de um instante — se
      // a travessia deu certo, esta página já não está visível e a instrução não incomoda
      // ninguém.
      window.location.href = systemBrowserUrl(response.url)
      setTimeout(() => { needsManualStep.value = true }, 1200)
    } catch {
      failed.value = true
    } finally {
      working.value = false
    }
  }

  return { crossOver, working, needsManualStep, failed, isInAppBrowser }
}
