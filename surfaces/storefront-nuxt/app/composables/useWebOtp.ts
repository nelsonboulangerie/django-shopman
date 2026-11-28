// Código do SMS preenchido sozinho no Chrome do Android (WebOTP).
//
// O SMS de entrada termina com `@www.nelsonboulangerie.com.br #<código>`: a linha prende o
// código ao domínio da loja, e o navegador só o entrega a esta página. No iPhone quem
// resolve é o `autocomplete="one-time-code"` do campo (sugestão no teclado); no Android é
// esta chamada, que espera o SMS chegar e devolve o código sem a pessoa sair da tela.
//
// A espera vive só enquanto a etapa do código está na tela: sair dela (trocar telefone,
// entrar, desmontar) aborta. Navegador sem suporte não faz nada, e o campo continua
// digitável como sempre: o atalho nunca é condição.

type OtpCredential = Credential & { code?: string }

export function webOtpSupported (): boolean {
  return typeof window !== 'undefined'
    && 'OTPCredential' in window
    && typeof navigator?.credentials?.get === 'function'
}

export function useWebOtp (active: Ref<boolean>, onCode: (code: string) => void) {
  let controller: AbortController | null = null

  function stop () {
    controller?.abort()
    controller = null
  }

  /** Começa (ou recomeça, depois de um reenvio) a esperar o SMS. */
  async function listen () {
    stop()
    if (!webOtpSupported()) return
    const current = new AbortController()
    controller = current
    try {
      const credential = await navigator.credentials.get({
        otp: { transport: ['sms'] },
        signal: current.signal
      } as CredentialRequestOptions) as OtpCredential | null
      if (current.signal.aborted) return
      const code = String(credential?.code || '').replace(/\D/g, '').slice(0, 6)
      if (code.length === 6) onCode(code)
    } catch {
      // Abortado, recusado ou tempo esgotado: a pessoa digita ou cola, como sempre.
    } finally {
      if (controller === current) controller = null
    }
  }

  if (import.meta.client) {
    watch(active, (value) => {
      if (value) void listen()
      else stop()
    }, { immediate: true })
    onBeforeUnmount(stop)
  }

  return { listen, stop }
}
