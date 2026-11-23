import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'

import AddressPicker from '~/components/AddressPicker.vue'
import { emptyAddressDraft, selectionFromDraft } from '~/presentation/address'

// #3281, item 3 (achado da J15): no checkout, quem reabre o endereço e confirma OUTRO
// continuava vendo, em cima do formulário, a linha do endereço anterior. Fora da área,
// a tela dizia "Ainda não entregamos nesse endereço" embaixo de "Avenida Saul Elkind",
// com o formulário mostrando a Estrada do Limoeiro: a linha de cima mentia.
const before = {
  ...emptyAddressDraft(),
  route: 'Avenida Saul Elkind',
  street_number: '2000',
  neighborhood: 'Lago Parque',
  city: 'Londrina',
  state_code: 'PR',
  postal_code: '86082-000'
}

describe('AddressPicker no checkout: a linha aceita acompanha o endereço confirmado', () => {
  it('confirmar um endereço novo troca a linha de cima por ele', async () => {
    const picker = await mountSuspended(AddressPicker, {
      props: { context: 'checkout', selection: selectionFromDraft(before) }
    })
    // Reaberto (Editar): o formulário vem com o endereço em vigor, e a linha diz qual é.
    expect(picker.find('[data-address-accepted]').text()).toContain('Avenida Saul Elkind, 2000')

    await picker.find('#address-route').setValue('Estrada do Limoeiro')
    await picker.find('#address-number').setValue('10')
    await picker.find('#address-neighborhood').setValue('Irerê')
    await picker.find('[data-address-confirm]').trigger('click')

    const emitted = picker.emitted('update:selection') ?? []
    expect(emitted.at(-1)?.[0]).toMatchObject({ formattedAddress: 'Estrada do Limoeiro, 10 - Irerê - Londrina/PR' })
    expect(picker.emitted('confirmed')).toHaveLength(1)
    const accepted = picker.find('[data-address-accepted]').text()
    expect(accepted).toContain('Estrada do Limoeiro, 10')
    expect(accepted).not.toContain('Saul Elkind')
    picker.unmount()
  })
})
