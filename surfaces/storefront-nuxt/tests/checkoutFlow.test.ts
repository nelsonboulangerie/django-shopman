import { describe, expect, it } from 'vitest'
import {
  checkoutDateBounds,
  checkoutDateChoices,
  datepickerDisabledDates,
  initialCheckoutDate,
  checkoutStepForField,
  checkoutStepState,
  checkoutSteps,
  firstCheckoutError,
  isCheckoutDateUnavailable,
  parseClosedDateEntries,
  quickCheckoutDateOptions,
  isClosedWeekday,
  isCustomCheckoutDate,
  notesToggleState,
  paymentMethodHint,
  reconciledWindowRef,
  checkoutWindows,
  earliestCheckoutWindowRef,
  canContinueCheckoutWhen,
  shouldOfferPickupSwap,
  weekdayDateLabel
} from '../app/utils/checkoutFlow'
import type { PickupSlotProjection } from '../app/types/shopman'

const now = new Date(2026, 4, 20, 12)

const slots: PickupSlotProjection[] = [{
  ref: 'slot-early',
  label: '10:00',
  starts_at: '2026-05-20T10:00:00',
  enabled: false,
  reason: 'Lotado',
  is_earliest: false
}, {
  ref: 'slot-late',
  label: '11:00',
  starts_at: '2026-05-20T11:00:00',
  enabled: true,
  reason: '',
  is_earliest: true
}]

describe('checkout flow view model', () => {
  it('derives available checkout dates from projected preorder and closed-date facts', () => {
    const bounds = checkoutDateBounds({ max_preorder_days: 2 }, now)
    const closedDates = parseClosedDateEntries('[{"date":"2026-05-20"},{"from":"2026-05-22","to":"2026-05-23"}]')

    expect(bounds.todayValue).toBe('2026-05-20')
    expect(bounds.maxDateValue).toBe('2026-05-22')
    expect(isCheckoutDateUnavailable('2026-05-19', bounds, closedDates)).toBe(true)
    expect(isCheckoutDateUnavailable('2026-05-20', bounds, closedDates)).toBe(true)
    expect(isCheckoutDateUnavailable('2026-05-21', bounds, closedDates)).toBe(false)
    expect(isCheckoutDateUnavailable('2026-05-22', bounds, closedDates)).toBe(true)
    expect(quickCheckoutDateOptions(bounds, closedDates)).toEqual([
      { label: 'Hoje', value: '2026-05-20', disabled: true },
      { label: 'Amanhã', value: '2026-05-21', disabled: false }
    ])
  })

  it('takes the preorder window only from the projection, never from a local number', () => {
    // Beta 06/11: a home prometia 7 dias e o calendário deixou escolher 22. O teto
    // é o `max_preorder_days` que o servidor manda; sem ele, só hoje.
    expect(checkoutDateBounds({ max_preorder_days: 7 }, now).maxDateValue).toBe('2026-05-27')
    expect(checkoutDateBounds({ max_preorder_days: 30 }, now).maxDateValue).toBe('2026-06-19')
    expect(checkoutDateBounds(null, now).maxDateValue).toBe('2026-05-20')
  })

  it('disables the quick date shortcuts on a weekday the shop does not open', () => {
    // Fallback local do "Quando" (só entra quando `available_dates` vem vazia).
    // Sem repassar `closed_weekdays`, "Amanhã" nascia clicável num dia fechado e
    // o passo travava sem dizer por quê — enquanto o calendário ao lado, que
    // recebe o mesmo fato, já pintava o dia como indisponível.
    const bounds = checkoutDateBounds({ max_preorder_days: 2 }, now)
    const thursday = 3 // 2026-05-21, convenção Python (segunda = 0)

    expect(quickCheckoutDateOptions(bounds, [], [thursday])).toEqual([
      { label: 'Hoje', value: '2026-05-20', disabled: false },
      { label: 'Amanhã', value: '2026-05-21', disabled: true }
    ])
  })

  it('keeps the progressive section order canonical for pickup and delivery', () => {
    expect(checkoutSteps('pickup')).toEqual(['fulfillment', 'when', 'payment'])
    expect(checkoutSteps('delivery')).toEqual(['fulfillment', 'address', 'when', 'payment'])
  })

  it('maps projected action and field errors into surface section states', () => {
    expect(checkoutStepState({
      step: 'payment',
      steps: ['fulfillment', 'when', 'payment'],
      activeStep: 'payment',
      fieldErrors: {},
      action: { enabled: false, reason: 'Carrinho indisponível' } as any
    })).toBe('blocked')

    expect(checkoutStepState({
      step: 'when',
      steps: ['fulfillment', 'when', 'payment'],
      activeStep: 'payment',
      fieldErrors: { delivery_time_slot: 'Escolha um horário.' }
    })).toBe('error')

    expect(checkoutStepState({
      step: 'payment',
      steps: ['fulfillment', 'when', 'payment'],
      activeStep: 'payment',
      fieldErrors: { recipient_phone: 'Telefone do destinatário inválido.' }
    })).toBe('error')

    expect(checkoutStepForField('saved_address_id')).toBe('address')
    expect(checkoutStepForField('payment_method')).toBe('payment')
  })

  it('reconciles stale pickup slots against the current projected slots', () => {
    expect(reconciledWindowRef('slot-early', slots, null)).toBe('slot-late')
    expect(reconciledWindowRef('', slots, 'slot-late')).toBe('slot-late')
    // Turno de retirada herdado não viaja na entrega: fora da grade, vale a mais cedo dela.
    expect(reconciledWindowRef('slot-09', [{ ...slots[1]!, ref: '14:00-14:30' }], null)).toBe('14:00-14:30')
    expect(reconciledWindowRef('slot-09', [], null)).toBe('')
  })
})

describe('isClosedWeekday', () => {
  // closed_weekdays usa índice Python: 6 = domingo.
  it('rejeita dia da semana sem expediente (domingo) e aceita os abertos', () => {
    expect(isClosedWeekday('2026-06-14', [6])).toBe(true) // 2026-06-14 = domingo
    expect(isClosedWeekday('2026-06-15', [6])).toBe(false) // segunda
    expect(isClosedWeekday('2026-06-14', [])).toBe(false)
  })
})

describe('isCheckoutDateUnavailable com closed_weekdays', () => {
  const bounds = { todayValue: '2026-06-13', maxDateValue: '2026-07-13' }
  it('marca indisponível um domingo fechado dentro do range', () => {
    expect(isCheckoutDateUnavailable('2026-06-14', bounds, [], [6])).toBe(true)
    expect(isCheckoutDateUnavailable('2026-06-15', bounds, [], [6])).toBe(false)
  })
})

describe('weekdayDateLabel', () => {
  it('formata dia da semana + data capitalizado', () => {
    expect(weekdayDateLabel('2026-06-13')).toMatch(/, 13\/06$/)
    expect(weekdayDateLabel('2026-06-13')[0]).toMatch(/[A-Z]/)
    expect(weekdayDateLabel('')).toBe('')
  })
})

describe('isCustomCheckoutDate', () => {
  const quick = [{ label: 'Hoje', value: '2026-06-13', disabled: false }, { label: 'Amanhã', value: '2026-06-14', disabled: false }]
  it('detecta data fora dos atalhos', () => {
    expect(isCustomCheckoutDate('2026-06-18', quick)).toBe(true)
    expect(isCustomCheckoutDate('2026-06-13', quick)).toBe(false)
    expect(isCustomCheckoutDate('', quick)).toBe(false)
  })
})

describe('paymentMethodHint', () => {
  it('descreve cada método pelo que o cliente espera', () => {
    expect(paymentMethodHint('pix')).toBe('Pague com Pix no app do banco')
    expect(paymentMethodHint('card')).toBe('Pagamento em ambiente seguro')
    expect(paymentMethodHint('card', 'Stripe')).toBe('Pagamento seguro via Stripe')
    expect(paymentMethodHint('cartao', 'Efí')).toBe('Pagamento seguro via Efí')
    expect(paymentMethodHint('cash')).toBe('Pague ao receber')
    expect(paymentMethodHint('boleto')).toBe('')
  })
})

describe('shouldOfferPickupSwap', () => {
  const base = { field: 'delivery_address', fulfillmentType: 'delivery' as const, hasPickup: true, hasAddress: true }

  it('offers pickup when delivery is out of area and the customer already gave an address', () => {
    expect(shouldOfferPickupSwap(base)).toBe(true)
  })

  it('stays silent on a blank address (filling error, not coverage)', () => {
    expect(shouldOfferPickupSwap({ ...base, hasAddress: false })).toBe(false)
  })

  it('stays silent when pickup is not available on the channel', () => {
    expect(shouldOfferPickupSwap({ ...base, hasPickup: false })).toBe(false)
  })

  it('only reacts to the delivery_address field on a delivery order', () => {
    expect(shouldOfferPickupSwap({ ...base, field: 'payment_method' })).toBe(false)
    expect(shouldOfferPickupSwap({ ...base, fulfillmentType: 'pickup' })).toBe(false)
    expect(shouldOfferPickupSwap({ ...base, field: null })).toBe(false)
  })
})

describe('firstCheckoutError', () => {
  it('returns the highest-priority error by flow order', () => {
    const errors = { recipient_phone: 'tel inválido', name: 'informe o nome' }
    expect(firstCheckoutError(errors)).toEqual({ key: 'name', message: 'informe o nome' })
  })

  it('surfaces a lone downstream error (o gate não pode falhar em silêncio)', () => {
    expect(firstCheckoutError({ recipient_phone: 'tel do destinatário inválido' }))
      .toEqual({ key: 'recipient_phone', message: 'tel do destinatário inválido' })
  })

  it('falls back to any present error not in the canonical order', () => {
    expect(firstCheckoutError({ weird_field: 'algo' })).toEqual({ key: 'weird_field', message: 'algo' })
  })

  it('returns null when there are no errors', () => {
    expect(firstCheckoutError({})).toBeNull()
  })
})

describe('notesToggleState', () => {
  it('stashes the typed note when the toggle closes, and empties the payload field', () => {
    expect(notesToggleState(false, 'tocar o interfone', '')).toEqual({ notes: '', stashed: 'tocar o interfone' })
  })

  it('restores the stashed note when the toggle reopens', () => {
    expect(notesToggleState(true, '', 'tocar o interfone')).toEqual({ notes: 'tocar o interfone', stashed: '' })
  })

  it('keeps the current note over the stash when reopening with text already present', () => {
    expect(notesToggleState(true, 'nota atual', 'nota antiga')).toEqual({ notes: 'nota atual', stashed: '' })
  })

  it('keeps an earlier stash when closing again without new text', () => {
    expect(notesToggleState(false, '   ', 'nota antiga')).toEqual({ notes: '', stashed: 'nota antiga' })
  })
})

describe('janela de entrega (P2-30a)', () => {
  const pickup = slots
  const delivery: PickupSlotProjection[] = [
    { ref: '14:00-14:30', label: '14:00 às 14:30', starts_at: '', enabled: true, reason: '', is_earliest: true }
  ]
  const projection = {
    pickup_slots: pickup,
    delivery_windows: delivery,
    earliest_slot_ref: 'slot-late',
    earliest_delivery_window_ref: '14:00-14:30'
  }
  const bounds = { todayValue: '2026-05-20', maxDateValue: '2026-05-30' }

  it('a entrega lê a grade de entrega, nunca os turnos de retirada', () => {
    expect(checkoutWindows(projection, 'delivery')).toBe(delivery)
    expect(checkoutWindows(projection, 'pickup')).toBe(pickup)
    expect(earliestCheckoutWindowRef(projection, 'delivery')).toBe('14:00-14:30')
    expect(earliestCheckoutWindowRef(projection, 'pickup')).toBe('slot-late')
  })

  it('entrega só segue com uma janela escolhida e habilitada', () => {
    const form = { delivery_date: '2026-05-21', delivery_time_slot: '', fulfillment_type: 'delivery' as const }
    expect(canContinueCheckoutWhen(form, delivery, null, bounds, [])).toBe(false)
    expect(canContinueCheckoutWhen({ ...form, delivery_time_slot: '14:00-14:30' }, delivery, delivery[0]!, bounds, [])).toBe(true)
    // Dia sem grade de entrega: não segue (o servidor recusaria).
    expect(canContinueCheckoutWhen(form, [], null, bounds, [])).toBe(false)
    // Retirada sem turnos configurados continua livre, como antes.
    expect(canContinueCheckoutWhen({ ...form, fulfillment_type: 'pickup' }, [], null, bounds, [])).toBe(true)
  })
})


describe('calendário depois do encerramento', () => {
  it('não abre o pedido antes da fornada que a sacola espera (um pedido, uma data)', () => {
    // Beta 09/11: sacola com Kuro Pan da fornada de quarta (22/05 aqui), e o
    // Quando abria em "Hoje", oferecendo hoje e amanhã.
    const bounds = checkoutDateBounds({ max_preorder_days: 7 }, now, '2026-05-22')
    const titleFor = (value: string) => (value === '2026-05-21' ? 'Amanhã' : 'Próxima fornada')

    expect(bounds.todayValue).toBe('2026-05-20')
    expect(bounds.floorValue).toBe('2026-05-22')
    expect(bounds.minDate).toEqual(new Date(2026, 4, 22))
    expect(isCheckoutDateUnavailable('2026-05-20', bounds, [])).toBe(true)
    expect(isCheckoutDateUnavailable('2026-05-21', bounds, [])).toBe(true)
    expect(isCheckoutDateUnavailable('2026-05-22', bounds, [])).toBe(false)
    expect(canContinueCheckoutWhen(
      { delivery_date: '2026-05-20', delivery_time_slot: '', fulfillment_type: 'pickup' }, [], null, bounds, []
    )).toBe(false)

    // "Hoje" e "Amanhã" aparecem DESABILITADOS (a frase do motivo sai acima),
    // e o dia da fornada entra como caixa própria.
    expect(checkoutDateChoices(['2026-05-20', '2026-05-21', '2026-05-22'], bounds, titleFor)).toEqual([
      { value: '2026-05-20', title: 'Hoje', disabled: true },
      { value: '2026-05-21', title: 'Amanhã', disabled: true },
      { value: '2026-05-22', title: 'Próxima fornada', disabled: false }
    ])
    // Abre na data da fornada, nunca em "Hoje"; a data lembrada só vale se válida.
    expect(initialCheckoutDate('', false, ['2026-05-20', '2026-05-21', '2026-05-22'], bounds, '2026-05-20')).toBe('2026-05-22')
    expect(initialCheckoutDate('2026-05-20', false, ['2026-05-20', '2026-05-22'], bounds, '2026-05-20')).toBe('2026-05-22')
    expect(initialCheckoutDate('2026-05-25', true, ['2026-05-20', '2026-05-22'], bounds, '2026-05-20')).toBe('2026-05-25')
    // Fornada num dia sem `available_dates` carregadas: o piso mesmo.
    expect(initialCheckoutDate('', false, [], bounds, '2026-05-20')).toBe('2026-05-22')
  })

  it('sem fornada futura na sacola, o Quando segue como sempre', () => {
    const titleFor = (value: string) => (value === '2026-05-21' ? 'Amanhã' : 'Próxima fornada')
    const plain = checkoutDateBounds({ max_preorder_days: 7 }, now)
    // Piso no passado (ou hoje) não muda nada.
    const stale = checkoutDateBounds({ max_preorder_days: 7 }, now, '2026-05-19')

    for (const bounds of [plain, stale]) {
      expect(bounds.floorValue).toBe('2026-05-20')
      expect(bounds.minDate).toEqual(new Date(2026, 4, 20))
      expect(checkoutDateChoices(['2026-05-20', '2026-05-21'], bounds, titleFor)).toEqual([
        { value: '2026-05-20', title: 'Hoje', disabled: false },
        { value: '2026-05-21', title: 'Amanhã', disabled: false }
      ])
      expect(initialCheckoutDate('', false, ['2026-05-20', '2026-05-21'], bounds, '2026-05-20')).toBe('2026-05-20')
    }
    // Hoje fechado: a primeira caixa já é a próxima data.
    expect(checkoutDateChoices(['2026-05-21'], plain, titleFor)).toEqual([
      { value: '2026-05-21', title: 'Amanhã', disabled: false }
    ])
  })

  it('desabilita hoje sem fechar os próximos dias de atendimento', () => {
    expect(datepickerDisabledDates([], [], '2026-05-20')).toEqual([new Date(2026, 4, 20)])
    expect(datepickerDisabledDates([], [], '')).toEqual([])
  })
})
