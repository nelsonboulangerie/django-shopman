// A espera de reenvio sem código que valha (#3241): a confirmação de identidade logo
// depois de entrar não diz "Enviamos um código" com um erro vermelho; conta o tempo.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { resendWaitMessage, useResendWait } from '~/composables/useResendWait'

afterEach(() => {
  vi.useRealTimers()
})

async function mountWait () {
  const open = ref(false)
  let api: ReturnType<typeof useResendWait> | undefined
  await mountSuspended(defineComponent({
    setup () {
      api = useResendWait(open)
      return () => h('div')
    }
  }))
  return { open, api: api! }
}

describe('useResendWait', () => {
  it('a espera de reenvio vira contagem, não erro', async () => {
    vi.useFakeTimers()
    const { open, api } = await mountWait()
    open.value = true
    await nextTick()

    expect(api.fromCooldown({ error_code: 'cooldown', retry_after_seconds: 42 })).toBe(true)
    expect(api.waitSeconds.value).toBe(42)

    vi.advanceTimersByTime(40_000)
    expect(api.waitSeconds.value).toBe(2)
    vi.advanceTimersByTime(3_000)
    expect(api.waitSeconds.value).toBe(0)
  })

  it('outra recusa não é espera de reenvio', async () => {
    const { api } = await mountWait()
    expect(api.fromCooldown({ error_code: 'rate_limit', retry_after_seconds: 30 })).toBe(false)
    expect(api.fromCooldown({ error_code: 'cooldown' })).toBe(false)
    expect(api.fromCooldown(null)).toBe(false)
    expect(api.waitSeconds.value).toBe(0)
  })

  it('reset tira a espera', async () => {
    const { api } = await mountWait()
    api.fromCooldown({ error_code: 'cooldown', retry_after_seconds: 10 })
    api.reset()
    expect(api.waitSeconds.value).toBe(0)
  })

  it('a frase diz o que houve e quanto falta, sem travessão', () => {
    expect(resendWaitMessage(42)).toBe(
      'Um código foi enviado a este número há pouco. Por segurança, o próximo pode ser pedido em 42 segundos.'
    )
    expect(resendWaitMessage(1)).toContain('em 1 segundo.')
    expect(resendWaitMessage(42)).not.toContain('—')
  })
})
