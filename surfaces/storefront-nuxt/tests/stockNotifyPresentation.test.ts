import { describe, expect, it } from 'vitest'
import { notifyConfirmationMessage } from '~/presentation/stockNotify'

describe('notifyConfirmationMessage', () => {
  it('confirma somente o opt-in feito após identidade verificada', () => {
    expect(notifyConfirmationMessage()).toBe(
      'Aviso recorrente ativo. Você pode gerenciá-lo nas preferências.'
    )
  })
})
