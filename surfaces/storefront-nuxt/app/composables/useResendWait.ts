import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'

/**
 * A espera de reenvio do código SEM código que valha (#3241).
 *
 * Logo depois de entrar pelo código, o do login já foi usado, e a espera de 60 s do
 * Doorman ainda o conta: pedir outro código para confirmar a identidade volta
 * `cooldown` sem nada enviado. Não é erro de ninguém. A tela diz que o código de há
 * pouco já não vale e quanto falta para pedir outro, e libera o "Enviar código" quando a
 * espera acaba, em vez de afirmar "Enviamos um código" com um erro vermelho embaixo.
 *
 * `open` liga o relógio só enquanto o diálogo está aberto.
 */
export function useResendWait (open: Ref<boolean>) {
  const retryAtMs = ref(0)
  const nowMs = ref(Date.now())
  let clock: ReturnType<typeof setInterval> | null = null

  watch(open, (isOpen) => {
    if (clock) clearInterval(clock)
    clock = isOpen ? setInterval(() => { nowMs.value = Date.now() }, 1000) : null
  })
  onBeforeUnmount(() => { if (clock) clearInterval(clock) })

  const waitSeconds = computed(() => Math.max(0, Math.ceil((retryAtMs.value - nowMs.value) / 1000)))

  /** Lê a recusa do pedido de código: `true` quando era a espera de reenvio. */
  function fromCooldown (data: Record<string, unknown> | null | undefined): boolean {
    const retryAfter = typeof data?.retry_after_seconds === 'number' ? data.retry_after_seconds : 0
    if (data?.error_code !== 'cooldown' || retryAfter <= 0) return false
    nowMs.value = Date.now()
    retryAtMs.value = nowMs.value + retryAfter * 1000
    return true
  }

  function reset () {
    retryAtMs.value = 0
  }

  return { waitSeconds, fromCooldown, reset }
}

/** A frase da espera, igual nos dois diálogos de confirmação de identidade. */
export function resendWaitMessage (seconds: number): string {
  const unit = seconds === 1 ? 'segundo' : 'segundos'
  return `O código enviado há pouco já não vale. Peça um novo em ${seconds} ${unit}.`
}
