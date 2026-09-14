// "Avise-me": o número que a casa vai usar precisa voltar formatado para a tela
// ANTES do envio, sem inventar um dígito que pode identificar outra pessoa.
import { describe, expect, it } from 'vitest'
import { notifyConfirmationMessage, notifyPhoneTarget } from '~/presentation/stockNotify'

describe('notifyPhoneTarget', () => {
  it('cala enquanto o número está pela metade', () => {
    expect(notifyPhoneTarget('', '43')).toBe('')
    expect(notifyPhoneTarget('(43) 9', '43')).toBe('')
    expect(notifyPhoneTarget('(43) 9840', '43')).toBe('')
  })

  it('mostra o celular completo com o país explícito', () => {
    expect(notifyPhoneTarget('(43) 99840-4900', '43')).toBe('+55 (43) 99840-4900')
  })

  it('revela o DDD da loja para um celular completo', () => {
    expect(notifyPhoneTarget('99840-4900', '43')).toBe('+55 (43) 99840-4900')
  })

  it('recusa celular incompleto sem inventar o nono dígito', () => {
    expect(notifyPhoneTarget('(43) 9840-4900', '')).toBe('')
    expect(notifyPhoneTarget('9840-4900', '43')).toBe('')
  })

  it('fixo de 10 dígitos aparece como foi digitado, sem reparo', () => {
    expect(notifyPhoneTarget('(43) 3321-4900', '')).toBe('+55 (43) 3321-4900')
  })

  it('colar com +55 não vira DDD 55', () => {
    expect(notifyPhoneTarget('+5543998404900', '')).toBe('+55 (43) 99840-4900')
  })
})

describe('notifyConfirmationMessage', () => {
  it('nomeia o número quando ele é conhecido', () => {
    expect(notifyConfirmationMessage('+5543998404900')).toBe(
      'Pedido recebido para +55 (43) 99840-4900. Entre com esse WhatsApp para conferir ou reativar.'
    )
  })

  it('sem telefone (cliente logado assina com o da conta) fica na frase calma', () => {
    expect(notifyConfirmationMessage('')).toBe(
      'Aviso recorrente ativo. Você pode gerenciá-lo nas preferências.'
    )
  })
})
