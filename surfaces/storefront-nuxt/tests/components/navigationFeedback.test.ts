import { afterEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import NavigationFeedback from '~/components/NavigationFeedback.vue'

function navigationLink (href: string) {
  const link = document.createElement('a')
  link.href = href
  link.textContent = 'Abrir'
  link.dataset.navigationFeedbackTest = 'true'
  link.dataset.receivedClicks = '0'
  link.addEventListener('click', (event) => {
    link.dataset.receivedClicks = String(Number(link.dataset.receivedClicks) + 1)
    event.preventDefault()
  })
  document.body.append(link)
  return link
}

function advanceToNextPaint () {
  vi.advanceTimersByTime(17)
}

afterEach(() => {
  document.body.querySelectorAll('[data-navigation-feedback-test]').forEach(node => node.remove())
  vi.useRealTimers()
})

describe('NavigationFeedback', () => {
  it('fica silencioso até 200ms e então mostra o overlay contextual de tela inteira', async () => {
    vi.useFakeTimers()
    const wrapper = await mountSuspended(NavigationFeedback)
    const link = navigationLink('/menu')

    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
    await nextTick()

    expect(wrapper.find('[data-navigation-wait-overlay]').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toBe('')

    vi.advanceTimersByTime(199)
    await nextTick()
    expect(wrapper.find('[data-navigation-wait-overlay]').exists()).toBe(false)

    vi.advanceTimersByTime(1)
    advanceToNextPaint()
    await nextTick()

    expect(wrapper.find('[data-navigation-wait-overlay]').exists()).toBe(true)
    expect(wrapper.get('[data-navigation-wait-card]').text()).toContain('Abrindo o cardápio…')
    expect(wrapper.get('[data-navigation-wait-card]').text()).toContain('Confirmando o que está disponível agora.')
    expect(wrapper.get('[role="status"]').text()).toContain('Abrindo o cardápio…')
    expect(wrapper.find('[data-navigation-origin-feedback]').exists()).toBe(false)
    expect(wrapper.find('[data-navigation-delayed-feedback]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('cancela antes do primeiro paint quando a navegação termina em até 200ms', async () => {
    vi.useFakeTimers()
    const wrapper = await mountSuspended(NavigationFeedback)
    const link = navigationLink('/sacola')

    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
    vi.advanceTimersByTime(200)
    window.dispatchEvent(new Event('pageshow'))
    advanceToNextPaint()
    await nextTick()

    expect(wrapper.find('[data-navigation-wait-overlay]').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toBe('')
    wrapper.unmount()
  })

  it('nunca engole um segundo clique no mesmo destino enquanto a navegação está ativa', async () => {
    vi.useFakeTimers()
    const wrapper = await mountSuspended(NavigationFeedback)
    const link = navigationLink('/menu')

    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
    vi.advanceTimersByTime(217)
    await nextTick()

    expect(link.dataset.receivedClicks).toBe('2')
    expect(wrapper.get('[data-navigation-wait-overlay]').classes()).toContain('pointer-events-none')
    wrapper.unmount()
  })

  it('evita um flash curto depois que o overlay já ficou visível', async () => {
    vi.useFakeTimers()
    const wrapper = await mountSuspended(NavigationFeedback)
    const link = navigationLink('/produto/PAO')

    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
    vi.advanceTimersByTime(217)
    await nextTick()
    expect(wrapper.find('[data-navigation-wait-overlay]').exists()).toBe(true)

    const nuxtApp = useNuxtApp()
    await nuxtApp.callHook('page:finish', undefined)
    await nextTick()
    expect(wrapper.find('[data-navigation-wait-overlay]').exists()).toBe(true)

    vi.advanceTimersByTime(300)
    await nextTick()
    expect(wrapper.find('[data-navigation-wait-overlay]').exists()).toBe(true)

    vi.advanceTimersByTime(20)
    await nextTick()
    expect(wrapper.find('[data-navigation-wait-overlay]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('ignora links externos e navegação para a própria URL', async () => {
    vi.useFakeTimers()
    const wrapper = await mountSuspended(NavigationFeedback)
    const external = navigationLink('https://example.com/outro')
    const current = navigationLink(window.location.href)

    external.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
    current.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
    vi.advanceTimersByTime(500)
    await nextTick()

    expect(wrapper.find('[data-navigation-wait-overlay]').exists()).toBe(false)
    wrapper.unmount()
  })
})
