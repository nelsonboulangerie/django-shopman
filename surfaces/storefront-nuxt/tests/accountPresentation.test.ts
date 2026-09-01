import { describe, expect, it } from 'vitest'
import type { AccountLoyalty, AccountSummary, Action, OrderHistoryItem } from '~/types/shopman'
import {
  ORDER_FILTER_OPTIONS,
  accountGreeting,
  accountNavCards,
  addressSheetDescription,
  addressSheetTitle,
  deviceIcon,
  loyaltyStampSlots,
  loyaltyStampsLabel,
  loyaltyView,
  orderRowEmphasisClass,
  ordersCountLabel,
  orderStatusAccentClass,
  orderStatusDotClass,
  ordersEmptyCopy,
  reorderActionFrom,
  splitOrdersByActive
} from '~/presentation/account'

function loyalty (overrides: Partial<AccountLoyalty> = {}): AccountLoyalty {
  return {
    tier_display: 'Cliente Ouro',
    points_balance: 1500,
    stamps_current: 3,
    stamps_target: 8,
    stamps_range: [1, 2, 3, 4, 5, 6, 7, 8],
    transactions: [],
    ...overrides
  }
}

describe('accountGreeting', () => {
  it('saúda pelo primeiro nome', () => {
    expect(accountGreeting('Pablo')).toBe('Olá, Pablo')
  })
  it('cai para saudação neutra sem nome', () => {
    expect(accountGreeting('')).toBe('Olá')
    expect(accountGreeting(null)).toBe('Olá')
    expect(accountGreeting('  ')).toBe('Olá')
  })
})

describe('loyaltyStampSlots', () => {
  it('preenche até o atual e mantém o alvo', () => {
    const slots = loyaltyStampSlots(loyalty())
    expect(slots).toHaveLength(8)
    expect(slots.filter(s => s.filled)).toHaveLength(3)
    expect(slots[0]).toEqual({ index: 1, filled: true })
    expect(slots[7]).toEqual({ index: 8, filled: false })
  })
  it('deriva do alvo quando não há stamps_range', () => {
    const slots = loyaltyStampSlots(loyalty({ stamps_range: [], stamps_target: 5, stamps_current: 2 }))
    expect(slots).toHaveLength(5)
    expect(slots.filter(s => s.filled)).toHaveLength(2)
  })
  it('nunca passa do alvo se o atual exceder', () => {
    const slots = loyaltyStampSlots(loyalty({ stamps_current: 99, stamps_target: 8 }))
    expect(slots.filter(s => s.filled)).toHaveLength(8)
  })
  it('é vazio sem fidelidade', () => {
    expect(loyaltyStampSlots(null)).toEqual([])
  })
})

describe('loyaltyView', () => {
  it('consolida a vitrine', () => {
    const view = loyaltyView(loyalty())
    expect(view.available).toBe(true)
    expect(view.tierDisplay).toBe('Cliente Ouro')
    expect(view.pointsBalance).toBe(1500)
    expect(view.remaining).toBe(5)
    expect(view.cardComplete).toBe(false)
    expect(view.progressPercent).toBe(38)
    expect(view.hasStamps).toBe(true)
  })
  it('marca cartela completa', () => {
    const view = loyaltyView(loyalty({ stamps_current: 8, stamps_target: 8 }))
    expect(view.cardComplete).toBe(true)
    expect(view.progressPercent).toBe(100)
    expect(view.remaining).toBe(0)
    expect(view.stampsLabel).toContain('completa')
  })
  it('indisponível quando ausente', () => {
    const view = loyaltyView(null)
    expect(view.available).toBe(false)
    expect(view.slots).toEqual([])
  })
  it('detecta transações', () => {
    const view = loyaltyView(loyalty({ transactions: [{ points: 100, description: 'Pedido', date_display: 'hoje', is_credit: true }] }))
    expect(view.hasTransactions).toBe(true)
  })
})

describe('loyaltyStampsLabel', () => {
  it('singular para 1 selo', () => {
    expect(loyaltyStampsLabel(1, false, 8)).toBe('Falta 1 selo para a próxima recompensa')
  })
  it('plural para vários', () => {
    expect(loyaltyStampsLabel(5, false, 8)).toBe('Faltam 5 selos para a próxima recompensa')
  })
  it('vazio sem alvo', () => {
    expect(loyaltyStampsLabel(0, false, 0)).toBe('')
  })
})

describe('orderStatusAccentClass', () => {
  it('mapeia tons do backend', () => {
    expect(orderStatusAccentClass('success')).toBe('border-l-emerald-500')
    expect(orderStatusAccentClass('warning')).toBe('border-l-amber-500')
    expect(orderStatusAccentClass('danger')).toBe('border-l-destructive')
    expect(orderStatusAccentClass('info')).toBe('border-l-blue-500')
    expect(orderStatusAccentClass(undefined)).toBe('border-l-blue-500')
  })
})

describe('orderStatusDotClass', () => {
  it('mapeia tons do backend para o ponto', () => {
    expect(orderStatusDotClass('success')).toBe('bg-emerald-500')
    expect(orderStatusDotClass('warning')).toBe('bg-amber-500')
    expect(orderStatusDotClass('danger')).toBe('bg-destructive')
    expect(orderStatusDotClass(undefined)).toBe('bg-blue-500')
  })
})

describe('reorderActionFrom', () => {
  const reorder: Action = {
    ref: 'reorder', kind: 'mutation', label: 'Repetir', priority: 'secondary',
    enabled: true, reason: '', method: 'POST', href: '/api/v1/orders/X/reorder/',
    payload_schema: {}, idempotency: 'required', confirmation: {}
  }
  it('encontra a ação de refazer habilitada', () => {
    expect(reorderActionFrom({ actions: [reorder] })).toBe(reorder)
  })
  it('ignora desabilitada', () => {
    expect(reorderActionFrom({ actions: [{ ...reorder, enabled: false }] })).toBeNull()
  })
  it('null sem ações', () => {
    expect(reorderActionFrom({ actions: undefined })).toBeNull()
  })
})

describe('ordersEmptyCopy', () => {
  it('varia por filtro', () => {
    expect(ordersEmptyCopy('ativos').title).toContain('andamento')
    expect(ordersEmptyCopy('anteriores').title).toContain('finalizado')
    expect(ordersEmptyCopy('todos').title).toContain('ainda não')
  })
})

describe('ORDER_FILTER_OPTIONS', () => {
  it('tem os três filtros do backend', () => {
    expect(ORDER_FILTER_OPTIONS.map(o => o.value)).toEqual(['todos', 'ativos', 'anteriores'])
  })
})

describe('address sheet copy', () => {
  it('título por modo', () => {
    expect(addressSheetTitle('create')).toBe('Adicionar endereço')
    expect(addressSheetTitle('edit')).toBe('Editar endereço')
  })
  it('descrição por modo', () => {
    expect(addressSheetDescription('create')).toContain('uma vez')
    expect(addressSheetDescription('edit')).toContain('Ajuste')
  })
})

describe('deviceIcon', () => {
  it('telefone', () => {
    expect(deviceIcon('iPhone de Pablo')).toBe('lucide:smartphone')
    expect(deviceIcon('Android')).toBe('lucide:smartphone')
  })
  it('computador', () => {
    expect(deviceIcon('MacBook Pro')).toBe('lucide:laptop')
    expect(deviceIcon('Windows PC')).toBe('lucide:laptop')
  })
  it('fallback', () => {
    expect(deviceIcon('Navegador desconhecido')).toBe('lucide:monitor')
    expect(deviceIcon(null)).toBe('lucide:monitor')
  })
})

describe('accountNavCards', () => {
  it('expõe as seções com rotas pt-BR', () => {
    const cards = accountNavCards(null)
    expect(cards.map(c => c.to)).toEqual([
      '/conta/pedidos',
      '/conta/enderecos',
      '/conta/favoritos',
      '/conta/perfil',
      '/conta/preferencias',
      '/conta/seguranca'
    ])
  })
  it('badge de Pedidos prioriza os em andamento', () => {
    const summary = { active_order_count: 2, total_order_count: 8 } as AccountSummary
    const cards = accountNavCards(summary)
    expect(cards[0]!.count).toBe(2)
  })
  it('sem ativos, badge cai para o total', () => {
    const summary = { active_order_count: 0, total_order_count: 8 } as AccountSummary
    expect(accountNavCards(summary)[0]!.count).toBe(8)
  })
  it('contagem null sem summary', () => {
    expect(accountNavCards(null)[0]!.count).toBeNull()
  })
})

describe('ordersCountLabel', () => {
  it('compõe ativos e total', () => {
    expect(ordersCountLabel(2, 8)).toBe('2 pedidos em andamento (8 pedidos no total)')
  })
  it('singular nos dois eixos', () => {
    expect(ordersCountLabel(1, 1)).toBe('1 pedido em andamento (1 pedido no total)')
  })
  it('sem ativos, só o total', () => {
    expect(ordersCountLabel(0, 8)).toBe('8 pedidos')
    expect(ordersCountLabel(0, 1)).toBe('1 pedido')
  })
  it('sem pedidos, convite', () => {
    expect(ordersCountLabel(0, 0)).toBe('Nenhum pedido ainda')
  })
  it('nunca mostra total menor que os ativos', () => {
    expect(ordersCountLabel(3, 0)).toBe('3 pedidos em andamento (3 pedidos no total)')
  })
})

describe('splitOrdersByActive', () => {
  it('agrupa pelo is_active do backend preservando a ordem', () => {
    const orders = [
      { ref: 'A', is_active: true },
      { ref: 'B', is_active: false },
      { ref: 'C', is_active: true }
    ] as OrderHistoryItem[]
    const { active, past } = splitOrdersByActive(orders)
    expect(active.map(o => o.ref)).toEqual(['A', 'C'])
    expect(past.map(o => o.ref)).toEqual(['B'])
  })
  it('sem a flag, trata como finalizado', () => {
    const { active, past } = splitOrdersByActive([{ ref: 'X' } as OrderHistoryItem])
    expect(active).toEqual([])
    expect(past.map(o => o.ref)).toEqual(['X'])
  })
})

describe('orderRowEmphasisClass', () => {
  it('ativo fica em cor plena', () => {
    expect(orderRowEmphasisClass(true)).toBe('')
  })
  it('finalizado recua e volta no hover/focus', () => {
    const cls = orderRowEmphasisClass(false)
    expect(cls).toContain('opacity-70')
    expect(cls).toContain('saturate-50')
    expect(cls).toContain('hover:opacity-100')
    expect(cls).toContain('focus-within:opacity-100')
  })
})
