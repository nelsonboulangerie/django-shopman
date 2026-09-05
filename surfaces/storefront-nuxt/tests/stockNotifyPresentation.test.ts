// "Avise-me": o número que a casa vai usar precisa voltar formatado para a tela
// ANTES do envio — a normalização repara o que foi digitado, e reparo invisível
// já mandou a mensagem para outra pessoa.
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

  // O caso do defeito: 8 dígitos sem DDD ganham o DDD da loja, viram 10 dígitos
  // e o reparo insere o nono. Quem digitou tem que VER isso.
  it('revela o DDD da loja e o nono dígito que o normalizador insere', () => {
    expect(notifyPhoneTarget('9840-4900', '43')).toBe('+55 (43) 99840-4900')
  })

  it('revela o nono dígito inserido num número de 10 dígitos com DDD', () => {
    expect(notifyPhoneTarget('(43) 9840-4900', '')).toBe('+55 (43) 99840-4900')
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
      'Pronto. Avisaremos você no +55 (43) 99840-4900.'
    )
  })

  it('sem telefone (cliente logado assina com o da conta) fica na frase calma', () => {
    expect(notifyConfirmationMessage('')).toBe(
      'Pronto. Avisaremos você quando estiver disponível.'
    )
  })
})
