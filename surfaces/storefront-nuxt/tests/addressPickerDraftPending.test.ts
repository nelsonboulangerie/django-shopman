import { describe, expect, it } from 'vitest'
import { emptyAddressDraft, pickerDraftPending, selectionFromDraft } from '../app/presentation/address'

// Beta SMS-15: com o formulário aberto e o endereço trocado, o "Continuar" do
// checkout avançava com o endereço ANTIGO e a edição sumia.
const old = { ...emptyAddressDraft(), route: 'Rua Sergipe', street_number: '500', neighborhood: 'Centro', city: 'Londrina', state_code: 'PR', postal_code: '86010-360' }
const edited = { ...old, route: 'Rua Pernambuco', street_number: '77' }

describe('pickerDraftPending', () => {
  it('edição de um salvo aberta é pendente', () => {
    expect(pickerDraftPending({ context: 'checkout', mode: 'form', editingSaved: true, draft: old, selection: selectionFromDraft(old, 7) })).toBe(true)
  })

  it('endereço novo diferente da seleção em vigor é pendente', () => {
    expect(pickerDraftPending({ context: 'checkout', mode: 'form', editingSaved: false, draft: edited, selection: selectionFromDraft(old) })).toBe(true)
  })

  it('formulário que já entregou o que mostra não segura nada', () => {
    expect(pickerDraftPending({ context: 'checkout', mode: 'form', editingSaved: false, draft: old, selection: selectionFromDraft(old) })).toBe(false)
    expect(pickerDraftPending({ context: 'checkout', mode: 'saved', editingSaved: false, draft: edited, selection: selectionFromDraft(old) })).toBe(false)
    expect(pickerDraftPending({ context: 'account', mode: 'form', editingSaved: true, draft: edited, selection: null })).toBe(false)
  })
})
