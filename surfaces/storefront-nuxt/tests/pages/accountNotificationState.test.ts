import { describe, expect, it, vi } from 'vitest'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'
import PreferencesPage from '~/pages/conta/preferencias.vue'
import { readBody } from 'h3'

let saved: unknown
registerEndpoint('/api/v1/account/preferences/notifications/', { method: 'POST', handler: async (event) => {
  saved = await readBody(event)
  return { notification_preferences: [] }
} })

registerEndpoint('/api/v1/account/summary/', () => ({
  food_preferences: [],
  notification_preferences: [
    { key: 'sms', label: 'SMS', description: 'Receber notificações por SMS', enabled: false, order_notifications_enabled: true },
    { key: 'email', label: 'Email', description: 'Receber novidades por email', enabled: false, order_notifications_enabled: false },
    { key: 'push', label: 'Push', description: 'Receber novidades no navegador', enabled: false, order_notifications_enabled: null }
  ],
  stock_alert_subscriptions: []
}))

describe('preferências: ausente e bloqueado têm estados diferentes', () => {
  it('mostra recados permitidos com ação direta de bloquear sem autorizar novidades', async () => {
    clearNuxtData()
    const page = await mountSuspended(PreferencesPage)
    await vi.waitFor(() => expect(page.text()).toContain('Avisos de pedido: permitidos.'))
    expect(page.text()).toContain('Avisos de pedido: bloqueados.')
    expect(page.find('#notification-pref-sms').attributes('aria-checked')).toBe('false')
    expect(page.find('#notification-pref-email').attributes('aria-checked')).toBe('false')
    expect(page.text()).toContain('Bloquear avisos por SMS')
    expect(page.text()).not.toContain('Bloquear avisos por Email')
    expect(page.text()).toContain('Avisos de pedido: não foi possível consultar.')
    const block = page.findAll('button').find(button => button.text() === 'Bloquear avisos por SMS')
    expect(block).toBeDefined()
    await block!.trigger('click')
    await vi.waitFor(() => expect(saved).toEqual({ channel: 'sms', enabled: false }))
    page.unmount()
  })
})
