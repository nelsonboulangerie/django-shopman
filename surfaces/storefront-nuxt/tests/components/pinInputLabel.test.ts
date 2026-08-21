import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'

import PinInput from '~/components/Ui/PinInput/PinInput.vue'

// O campo do código de acesso é o ÚLTIMO passo do login: quem depende de leitor
// de tela ouve o rótulo de cada casa antes de digitar. A reka-ui rotula sozinha,
// em inglês ("pin input 1 of 6"), e nada no nosso código dizia o contrário — a
// tela inteira em português com seis campos falando inglês.
//
// Este teste monta o componente de verdade porque o que interessa é o atributo
// que sobra no <input> depois do merge de fallthrough: afirmar isso lendo o
// código-fonte não provaria que o nosso rótulo venceu o da biblioteca.
describe('campo do código de acesso', () => {
  it('rotula cada casa em português, sobrepondo o rótulo da biblioteca', async () => {
    const pin = await mountSuspended(PinInput, { props: { inputCount: 6, otp: true, type: 'number' } })

    // Só as casas visíveis: a reka-ui ainda monta um input escondido de apoio,
    // que não é campo de digitação e não precisa de rótulo.
    const casas = pin.findAll('input[data-slot="pin-input-input"]')
    const labels = casas.map(input => input.attributes('aria-label'))

    expect(labels).toEqual([
      'Dígito 1 de 6',
      'Dígito 2 de 6',
      'Dígito 3 de 6',
      'Dígito 4 de 6',
      'Dígito 5 de 6',
      'Dígito 6 de 6'
    ])
    // Controle positivo: as seis casas existem mesmo (a lista acima não passa
    // por estar vazia, que é o que aconteceria se nada tivesse renderizado).
    expect(casas).toHaveLength(6)
  })
})
