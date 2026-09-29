import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { isTextEntryControl, useMobileFormViewport } from '~/composables/useMobileFormViewport'

const media = vi.fn((query: string) => ({
  matches: query.includes('max-width') || query.includes('pointer: coarse'),
  media: query,
  addEventListener: () => {},
  removeEventListener: () => {}
}))

beforeEach(() => {
  vi.stubGlobal('matchMedia', media)
  document.documentElement.classList.remove('shop-form-keyboard-open')
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
  document.documentElement.classList.remove('shop-form-keyboard-open')
})

describe('useMobileFormViewport', () => {
  it('distingue campo de digitação de rádio e botão', () => {
    expect(isTextEntryControl(document.createElement('input'))).toBe(true)
    expect(isTextEntryControl(document.createElement('textarea'))).toBe(true)
    const radio = document.createElement('input')
    radio.type = 'radio'
    expect(isTextEntryControl(radio)).toBe(false)
    expect(isTextEntryControl(document.createElement('button'))).toBe(false)
  })

  it('recolhe o chrome durante a digitação e o restaura no blur', async () => {
    const root = ref<HTMLElement | null>(null)
    const Harness = defineComponent({
      setup () {
        const keyboard = useMobileFormViewport(root)
        return () => h('main', {
          ref: root,
          onFocusin: keyboard.onFocusIn,
          onFocusout: keyboard.onFocusOut
        }, [h('input', { id: 'editor' }), h('input', { id: 'choice', type: 'radio' })])
      }
    })
    const wrapper = await mountSuspended(Harness, { attachTo: document.body })
    const editor = wrapper.find<HTMLInputElement>('#editor')

    await editor.trigger('focusin')
    expect(document.documentElement.classList.contains('shop-form-keyboard-open')).toBe(true)

    ;(editor.element as HTMLInputElement).blur()
    await editor.trigger('focusout')
    await new Promise(resolve => requestAnimationFrame(resolve))
    await nextTick()
    expect(document.documentElement.classList.contains('shop-form-keyboard-open')).toBe(false)
    wrapper.unmount()
  })
})
