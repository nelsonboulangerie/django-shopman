import { describe, expect, it } from 'vitest'

import {
  continueInConversationAction,
  openElsewhereNotices,
  passageErrorMessage,
  PASSAGE_FALLBACK_ERROR
} from '~/presentation/cartPassage'
import type { Action, CartOpenElsewhere } from '~/types/shopman'

function action (overrides: Partial<Action> = {}): Action {
  return {
    ref: 'bring_cart',
    kind: 'mutation',
    label: 'Trazer para cá',
    priority: 'secondary',
    enabled: true,
    reason: '',
    method: 'POST',
    href: '/api/v1/cart/bring/',
    payload_schema: { channel: 'whatsapp' },
    idempotency: 'none',
    confirmation: {},
    ...overrides
  }
}

function elsewhere (bring: Action): CartOpenElsewhere {
  return {
    channel: 'whatsapp',
    channel_label: 'WhatsApp',
    items_count: 3,
    items_phrase: '3 itens',
    subtotal_q: 270,
    subtotal_display: 'R$ 2,70',
    bring
  }
}

describe('a sacola aberta no WhatsApp (#3515)', () => {
  it('avisa e oferece trazer só com a ação ligada (X1)', () => {
    const [notice] = openElsewhereNotices({ open_elsewhere: [elsewhere(action())] })
    expect(notice!.text).toBe('Você tem outra sacola no WhatsApp: 3 itens (R$ 2,70).')
    expect(notice!.consequence).toBe('Ao trazer, ela sai do WhatsApp.')
    expect(notice!.bring?.label).toBe('Trazer para cá')
  })

  it('com a ação desligada, avisa sem botão e diz que ela fica lá', () => {
    const [notice] = openElsewhereNotices({ open_elsewhere: [elsewhere(action({ enabled: false }))] })
    expect(notice!.bring).toBeNull()
    expect(notice!.consequence).toBe('Ela fica lá, separada desta.')
  })

  it('sem outra sacola, não há aviso', () => {
    expect(openElsewhereNotices({})).toEqual([])
    expect(openElsewhereNotices({ open_elsewhere: [] })).toEqual([])
  })

  it('nenhuma frase usa travessão', () => {
    const [on] = openElsewhereNotices({ open_elsewhere: [elsewhere(action())] })
    expect(`${on!.text} ${on!.consequence}`).not.toMatch(/[—–]/)
  })
})

describe('Continuar pelo WhatsApp (OC-16)', () => {
  const continueAction = action({ ref: 'continue_in_conversation', label: 'Continuar pelo WhatsApp', href: '/api/v1/cart/continue-in-conversation/' })

  it('só aparece quando o servidor manda a ação ligada (X1)', () => {
    expect(continueInConversationAction({ is_empty: false, continue_in_conversation: continueAction })?.label).toBe('Continuar pelo WhatsApp')
    expect(continueInConversationAction({ is_empty: false, continue_in_conversation: null })).toBeNull()
    expect(continueInConversationAction({ is_empty: false })).toBeNull()
    expect(continueInConversationAction({ is_empty: false, continue_in_conversation: { ...continueAction, enabled: false } })).toBeNull()
  })

  it('com a sacola vazia, nunca', () => {
    expect(continueInConversationAction({ is_empty: true, continue_in_conversation: continueAction })).toBeNull()
  })
})

describe('recusa da passagem', () => {
  it('diz a frase do servidor, ou a genérica que não promete nada', () => {
    expect(passageErrorMessage({ data: { detail: 'A outra sacola mudou agora há pouco.' } })).toBe('A outra sacola mudou agora há pouco.')
    expect(passageErrorMessage(new Error('rede'))).toBe(PASSAGE_FALLBACK_ERROR)
    expect(passageErrorMessage(null)).toBe(PASSAGE_FALLBACK_ERROR)
  })
})
