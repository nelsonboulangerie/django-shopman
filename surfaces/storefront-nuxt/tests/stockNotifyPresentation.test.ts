import { describe, expect, it } from 'vitest'
import { favoriteNotedAlertMessage, notifyConfirmationMessage } from '~/presentation/stockNotify'

describe('notifyConfirmationMessage', () => {
  it('confirma somente o opt-in feito após identidade verificada', () => {
    expect(notifyConfirmationMessage()).toBe(
      'Aviso recorrente ativo. Você pode gerenciá-lo nas preferências.'
    )
  })
})

describe('favoriteNotedAlertMessage', () => {
  it('diz que o favorito ativou o aviso e onde gerenciá-lo', () => {
    expect(favoriteNotedAlertMessage()).toBe(
      'Salvo nos favoritos, com aviso ativo: avisamos pelo WhatsApp quando voltar. Você pode gerenciá-lo nas preferências.'
    )
  })
})
