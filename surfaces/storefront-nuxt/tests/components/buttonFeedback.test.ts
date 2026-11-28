import { describe, expect, it, vi } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import UiButton from '~/components/Ui/Button.vue'

describe('UiButton — feedback imediato e bloqueio acessível', () => {
  it('troca o ícone pelo spinner e anuncia o estado ocupado', async () => {
    const wrapper = await mountSuspended(UiButton, {
      props: { loading: true, icon: 'lucide:check', text: 'Salvar' }
    })

    expect(wrapper.attributes('aria-busy')).toBe('true')
    expect(wrapper.attributes('aria-disabled')).toBe('true')
    expect(wrapper.text()).toContain('Salvar')
    expect(wrapper.text()).toContain('Aguarde.')
    expect(wrapper.findAll('svg')).toHaveLength(1)
    expect(wrapper.html()).not.toContain('lucide:check')
  })

  it('confirma visualmente um clique aceito sem duplicar o handler', async () => {
    vi.useFakeTimers()
    const onClick = vi.fn()
    const wrapper = await mountSuspended(UiButton, {
      props: { onClick, text: 'Continuar' }
    })

    await wrapper.trigger('click')
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(wrapper.attributes('data-acknowledged')).toBe('true')

    vi.advanceTimersByTime(450)
    await nextTick()
    expect(wrapper.attributes('data-acknowledged')).toBeUndefined()
    vi.useRealTimers()
  })

  it('não ativa link desabilitado por mouse ou teclado', async () => {
    const onClick = vi.fn()
    const wrapper = await mountSuspended(UiButton, {
      props: { as: 'a', href: '/finalizar', disabled: true, onClick, text: 'Finalizar' }
    })

    expect(wrapper.attributes('aria-disabled')).toBe('true')
    expect(wrapper.attributes('tabindex')).toBe('-1')
    await wrapper.trigger('click')
    expect(onClick).not.toHaveBeenCalled()
  })
  // DEV-2026-094: o clique que devolve promessa deixa o botão ocupado sozinho.
  it('clique assíncrono: gira, trava e ignora o toque repetido até assentar', async () => {
    let release!: () => void
    const onClick = vi.fn(() => new Promise<void>((resolve) => { release = resolve }))
    const wrapper = await mountSuspended(UiButton, { props: { onClick, text: 'Salvar' } })

    await wrapper.trigger('click')
    await nextTick()
    expect(wrapper.attributes('aria-busy')).toBe('true')
    expect(wrapper.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Aguarde.')
    await wrapper.trigger('click')
    expect(onClick).toHaveBeenCalledTimes(1)

    release()
    await new Promise(resolve => setTimeout(resolve, 0))
    await nextTick()
    expect(wrapper.attributes('aria-busy')).toBeUndefined()
    expect(wrapper.attributes('disabled')).toBeUndefined()
  })

  it('a promessa recusada também solta o botão', async () => {
    const onClick = vi.fn(() => Promise.reject(new Error('falhou')))
    const wrapper = await mountSuspended(UiButton, { props: { onClick, text: 'Salvar' } })
    await wrapper.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    await nextTick()
    expect(wrapper.attributes('aria-busy')).toBeUndefined()
  })

  it('clique síncrono não deixa o botão ocupado', async () => {
    const onClick = vi.fn()
    const wrapper = await mountSuspended(UiButton, { props: { onClick, text: 'Abrir' } })
    await wrapper.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    await nextTick()
    expect(wrapper.attributes('aria-busy')).toBeUndefined()
    expect(wrapper.attributes('disabled')).toBeUndefined()
  })
})
