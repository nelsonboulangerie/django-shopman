import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AddressLocationDivergence from '../../app/components/AddressLocationDivergence.vue'

const stubs = {
  UiAlert: { template: '<div><slot /></div>' },
  UiAlertTitle: { template: '<h2><slot /></h2>' },
  UiAlertDescription: { template: '<p><slot /></p>' },
  UiButton: {
    emits: ['click'],
    template: '<button v-bind="$attrs" @click="$emit(\'click\')"><slot /></button>'
  },
  Icon: { template: '<span />' }
}

function render (props: Record<string, unknown>) {
  return mount(AddressLocationDivergence, { props, global: { stubs } })
}

describe('AddressLocationDivergence', () => {
  it('has no DOM or interaction when the dedicated mode is off', () => {
    const wrapper = render({ mode: 'off' })
    expect(wrapper.find('[data-address-location-check]').exists()).toBe(false)
  })

  it('asks for location only after an explicit button gesture', async () => {
    const wrapper = render({ mode: 'visible', state: 'idle' })
    expect(wrapper.text()).toContain('usar sua localização uma vez')
    await wrapper.get('[data-address-location-check-request]').trigger('click')
    expect(wrapper.emitted('request')).toHaveLength(1)
  })

  it('renders the gentle non-blocking mismatch decisions in safe DOM order', async () => {
    const wrapper = render({ mode: 'visible', state: 'diverged' })
    const actions = wrapper.findAll('[data-location-action]')

    expect(actions.map(action => action.attributes('data-location-action'))).toEqual([
      'keep', 'use-current', 'review-map', 'dismiss'
    ])
    expect(wrapper.text()).not.toContain('endereço errado')

    await actions[0]?.trigger('click')
    expect(wrapper.emitted('keep')).toHaveLength(1)
  })

  it('never exposes the mismatch during measure mode', () => {
    const wrapper = render({ mode: 'measure', state: 'diverged' })
    expect(wrapper.find('[data-address-location-mismatch]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Seu endereço continua selecionado')
  })

  it('keeps imprecise and failed checks recoverable', async () => {
    const wrapper = render({ mode: 'visible', state: 'inconclusive' })
    expect(wrapper.get('[role="status"]').text()).toContain('comparar com segurança')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('request')).toHaveLength(1)
  })

  it('lets an unavailable saved point become a new destination without claiming proximity', async () => {
    const wrapper = render({
      mode: 'visible',
      state: 'unavailable',
      canReviewMap: false,
      canUseCurrent: true
    })

    expect(wrapper.text()).toContain('não tem um ponto preciso')
    expect(wrapper.text()).not.toMatch(/perto|longe/)
    await wrapper.get('[data-location-action="use-current"]').trigger('click')
    expect(wrapper.emitted('use-current')).toHaveLength(1)
  })
})
