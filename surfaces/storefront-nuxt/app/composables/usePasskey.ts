// Passkey: entrar com o rosto ou a digital, sem código nenhum.
//
// Este arquivo é, quase inteiro, TRADUÇÃO. O servidor fala JSON (base64url, porque JSON não
// tem bytes) e o `navigator.credentials` fala `ArrayBuffer`. É aqui que WebAuthn mais escorrega:
// converter errado dá "não reconhecemos esta chave", a mensagem menos útil possível para
// entender o que aconteceu.
//
// O que este composable NÃO faz: decidir quem pode cadastrar. Isso é do servidor
// (`identity_confirmation_required` quando a sessão só conhece o número) — regra de segurança
// não mora no cliente, que é justamente onde ela pode ser removida com o DevTools aberto.

/** base64url → bytes. O `-` e o `_` do base64url voltam a `+` e `/`. */
function fromB64url(value: string): Uint8Array {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
  const binary = atob(padded)
  return Uint8Array.from(binary, char => char.charCodeAt(0))
}

/** bytes → base64url, do jeito que o servidor espera receber. */
function toB64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/**
 * ⚠️ O endereço permite WebAuthn?
 *
 * WebAuthn exige um DOMÍNIO REGISTRÁVEL. `localhost` é caso especial e passa; **endereço IP
 * não passa** — o Chrome recusa com `SecurityError: This is an invalid domain.`
 *
 * Isso bate de frente com a convenção de dev deste projeto, que é sempre `127.0.0.1` (nunca
 * `localhost`, por causa do preview). Consequência prática, e é bom saber antes de perder uma
 * hora: **passkey não funciona no dev em 127.0.0.1**. Em staging e produção, que têm domínio
 * de verdade, funciona.
 *
 * Verificar aqui é o que impede a tela de oferecer o que o navegador vai negar — botão que
 * falha ensina a não confiar no botão.
 */
function domainAllowsPasskey(): boolean {
  if (typeof window === 'undefined') return false
  const host = window.location.hostname
  if (host === 'localhost') return true
  const isIPv4 = /^\d{1,3}(\.\d{1,3}){3}$/.test(host)
  const isIPv6 = host.includes(':') || host.startsWith('[')
  return !isIPv4 && !isIPv6
}

/** O aparelho sabe fazer passkey? Sem isto, oferecemos um botão que não faz nada. */
export function passkeySupported(): boolean {
  return (
    typeof window !== 'undefined'
    && typeof window.PublicKeyCredential === 'function'
    && typeof navigator?.credentials?.create === 'function'
    && domainAllowsPasskey()
  )
}

/**
 * ⚠️ Este aparelho tem autenticador PRÓPRIO (Face ID, Touch ID, Windows Hello)?
 *
 * `passkeySupported` só diz que a API existe — num desktop sem biometria ela existe e o fluxo
 * cai em "use seu celular via QR", que é ótimo mas é outra conversa. Convidar alguém a "entrar
 * com o rosto" num computador sem leitor seria prometer o que a tela não entrega.
 */
export async function passkeyIsQuick(): Promise<boolean> {
  if (!passkeySupported()) return false
  const api = window.PublicKeyCredential as unknown as {
    isUserVerifyingPlatformAuthenticatorAvailable?: () => Promise<boolean>
  }
  if (typeof api.isUserVerifyingPlatformAuthenticatorAvailable !== 'function') return false
  try {
    return await api.isUserVerifyingPlatformAuthenticatorAvailable()
  } catch {
    return false
  }
}

type ServerOptions = Record<string, unknown> & {
  challenge: string
  user?: { id: string, name: string, displayName: string }
  excludeCredentials?: { id: string, type: string, transports?: string[] }[]
  allowCredentials?: { id: string, type: string, transports?: string[] }[]
}

/** As opções do servidor com os campos binários convertidos — o que a API do navegador exige. */
function asCredentialOptions(options: ServerOptions): PublicKeyCredentialCreationOptions {
  const native: Record<string, unknown> = { ...options, challenge: fromB64url(options.challenge) }
  if (options.user) {
    native.user = { ...options.user, id: fromB64url(options.user.id) }
  }
  for (const key of ['excludeCredentials', 'allowCredentials'] as const) {
    const list = options[key]
    if (list?.length) {
      native[key] = list.map(cred => ({ ...cred, id: fromB64url(cred.id) }))
    }
  }
  return native as unknown as PublicKeyCredentialCreationOptions
}

/** A credencial criada/assinada, em JSON. Os nomes são os que o servidor lê. */
function asJson(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response as AuthenticatorAttestationResponse
    & AuthenticatorAssertionResponse
  const payload: Record<string, unknown> = {
    id: credential.id,
    rawId: toB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toB64url(response.clientDataJSON)
    } as Record<string, unknown>
  }
  const inner = payload.response as Record<string, unknown>
  if (response.attestationObject) inner.attestationObject = toB64url(response.attestationObject)
  if (response.authenticatorData) inner.authenticatorData = toB64url(response.authenticatorData)
  if (response.signature) inner.signature = toB64url(response.signature)
  if (response.userHandle) inner.userHandle = toB64url(response.userHandle)
  return payload
}

/** Um apelido que a pessoa reconheça na lista, sem perguntar nada a ela. */
function deviceLabel(): string {
  const ua = navigator.userAgent
  if (/iphone/i.test(ua)) return 'iPhone'
  if (/ipad/i.test(ua)) return 'iPad'
  if (/android/i.test(ua)) return 'Celular Android'
  if (/mac/i.test(ua)) return 'Mac'
  if (/windows/i.test(ua)) return 'Windows'
  return 'Este aparelho'
}

export function usePasskey() {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()
  const session = useShopSession()

  const busy = ref(false)
  const error = ref('')
  /** O servidor pediu confirmação antes de deixar cadastrar. A tela oferece o WhatsApp. */
  const needsConfirmation = ref(false)

  /** Cadastrar. Devolve `true` quando ativou. */
  async function enroll(): Promise<boolean> {
    busy.value = true
    error.value = ''
    needsConfirmation.value = false
    try {
      const options = await $fetch<ServerOptions>(
        apiPath('/api/v1/auth/passkey/register/options/'),
        { method: 'POST', headers: await csrfHeaders(), credentials: 'include' }
      )
      const created = await navigator.credentials.create({
        publicKey: asCredentialOptions(options)
      }) as PublicKeyCredential | null
      if (!created) {
        // Cancelou o Face ID: não é erro, é uma escolha. Sem mensagem vermelha.
        return false
      }
      await $fetch(apiPath('/api/v1/auth/passkey/register/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: { credential: asJson(created), label: deviceLabel() }
      })
      return true
    } catch (e) {
      const data = httpError(e).data || {}
      if (data.error_code === 'identity_confirmation_required') {
        needsConfirmation.value = true
        return false
      }
      // `NotAllowedError` = a pessoa cancelou ou o tempo esgotou. Não é falha nossa e não
      // merece alarme: tratar cancelamento como erro ensina a ignorar mensagens.
      if ((e as DOMException)?.name === 'NotAllowedError') return false
      if ((e as DOMException)?.name === 'SecurityError') {
        // Endereço que o WebAuthn não aceita (IP, por exemplo). É configuração do ambiente,
        // não erro de quem clicou — dizer "tente de novo" faria a pessoa tentar em vão.
        error.value = 'Este endereço não permite o acesso rápido.'
        return false
      }
      error.value = errorDetail(e, 'Não conseguimos ativar agora.')
      return false
    } finally {
      busy.value = false
    }
  }

  /** Entrar. Devolve `true` quando a sessão abriu. */
  async function signIn(): Promise<boolean> {
    busy.value = true
    error.value = ''
    try {
      const options = await $fetch<ServerOptions>(
        apiPath('/api/v1/auth/passkey/login/options/'),
        { method: 'POST', headers: await csrfHeaders(), credentials: 'include' }
      )
      const assertion = await navigator.credentials.get({
        publicKey: asCredentialOptions(options)
      }) as PublicKeyCredential | null
      if (!assertion) return false

      const response = await $fetch<Record<string, unknown>>(
        apiPath('/api/v1/auth/passkey/login/'),
        {
          method: 'POST',
          headers: await csrfHeaders(),
          credentials: 'include',
          body: { credential: asJson(assertion) }
        }
      )
      session.setFromAuthSession(response as never)
      return true
    } catch (e) {
      if ((e as DOMException)?.name === 'NotAllowedError') return false
      error.value = errorDetail(e, 'Não reconhecemos esta chave neste aparelho.')
      return false
    } finally {
      busy.value = false
    }
  }

  return { enroll, signIn, busy, error, needsConfirmation, passkeySupported, passkeyIsQuick }
}
