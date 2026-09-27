import { afterEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import NavigationFeedback from '~/components/NavigationFeedback.vue'

function navigationLink (href: string) {
  const link = document.createElement('a')
  link.href = href
  link.textContent = 'Abrir'
  link.addEventListener('click', event => event.preventDefault())
  link.getBoundingClientRect = () => ({
    x: 24,
    y: 120,
    top: 120,
    left: 24,
    right: 120,
    bottom: 168,
    width: 96,
    height: 48,
    toJSON: () => ({})
  }) as DOMRect
  document.body.append(link)
  return link
}

afterEach(() => {
  document.body.querySelectorAll('[data-navigation-feedback-test]').forEach(node => node.remove())
  vi.useRealTimers()
})

describe('NavigationFeedback', () => {
  it('confirma no ponto do toque e só mostra a mensagem global quando a espera passa de 300ms', async () => {
    vi.useFakeTimers()
    const wrapper = await mountSuspended(NavigationFeedback)
    const link = navigationLink('/sacola')
    link.dataset.navigationFeedbackTest = 'true'

    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
    await nextTick()

    expect(wrapper.find('[data-navigation-origin-feedback]').exists()).toBe(true)
    expect(wrapper.find('[data-navigation-origin-feedback]').text()).toContain('Abrindo…')
    expect(wrapper.find('[data-navigation-delayed-feedback]').exists()).toBe(false)

    vi.advanceTimersByTime(299)
    await nextTick()
    expect(wrapper.find('[data-navigation-delayed-feedback]').exists()).toBe(false)

    vi.advanceTimersByTime(1)
    await nextTick()
    expect(wrapper.find('[data-navigation-delayed-feedback]').text()).toContain('Ainda abrindo sua sacola…')
    expect(wrapper.get('[role="status"]').text()).toContain('Ainda abrindo sua sacola…')

    window.dispatchEvent(new Event('pageshow'))
    await nextTick()
    expect(wrapper.find('[data-navigation-origin-feedback]').exists()).toBe(false)
    expect(wrapper.find('[data-navigation-delayed-feedback]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('ignora links externos e navegação para a própria URL', async () => {
    vi.useFakeTimers()
    const wrapper = await mountSuspended(NavigationFeedback)
    const external = navigationLink('https://example.com/outro')
    external.dataset.navigationFeedbackTest = 'true'
    const current = navigationLink(window.location.href)
    current.dataset.navigationFeedbackTest = 'true'

    external.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
    current.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
    await nextTick()

    expect(wrapper.find('[data-navigation-origin-feedback]').exists()).toBe(false)
    vi.advanceTimersByTime(500)
    await nextTick()
    expect(wrapper.find('[data-navigation-delayed-feedback]').exists()).toBe(false)
    wrapper.unmount()
  })
})
