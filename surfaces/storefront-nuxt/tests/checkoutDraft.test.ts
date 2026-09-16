import { describe, expect, it } from 'vitest'
import { CHECKOUT_DRAFT_TTL, parseCheckoutDraft } from '../app/utils/checkoutDraft'

const now = 1_756_000_000_000

function serialized (overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    version: 2,
    context: 'context-A',
    savedAt: now - 60_000,
    state: {
      name: 'Ana',
      fulfillment_type: 'delivery',
      delivery_address: 'R. das Flores, 123 - Jardim - Londrina/PR',
      notes: '',
      ...(overrides.state as Record<string, unknown> | undefined)
    },
    activeStep: 'address',
    ...overrides
  })
}

describe('parseCheckoutDraft', () => {
  it('restores a fresh draft with its active step', () => {
    const { draft, stale } = parseCheckoutDraft(serialized(), now, 'context-A')
    expect(stale).toBe(false)
    expect(draft?.state.name).toBe('Ana')
    expect(draft?.activeStep).toBe('address')
  })

  it('flags a draft older than the TTL as stale, without restoring it', () => {
    const { draft, stale } = parseCheckoutDraft(serialized({ savedAt: now - CHECKOUT_DRAFT_TTL - 1 }), now, 'context-A')
    expect(draft).toBeNull()
    expect(stale).toBe(true)
  })

  it('ignores corrupted payloads without marking them stale', () => {
    expect(parseCheckoutDraft('{corrompido', now, 'context-A')).toEqual({ draft: null, stale: false })
    expect(parseCheckoutDraft(null, now, 'context-A')).toEqual({ draft: null, stale: false })
    expect(parseCheckoutDraft(JSON.stringify('texto'), now, 'context-A')).toEqual({ draft: null, stale: false })
    expect(parseCheckoutDraft(JSON.stringify({ savedAt: now }), now, 'context-A')).toEqual({ draft: null, stale: true })
  })

  it('drops an active step that does not exist for the drafted fulfillment', () => {
    const { draft } = parseCheckoutDraft(serialized({ state: { fulfillment_type: 'pickup' } }), now, 'context-A')
    expect(draft?.activeStep).toBeNull()
  })

  it('restores the address selection of a saved address', () => {
    const { draft } = parseCheckoutDraft(serialized({
      addressSelection: {
        savedAddressId: 7,
        formattedAddress: 'R. das Flores, 123',
        structured: { route: 'R. das Flores' },
        complement: 'ap 42',
        deliveryInstructions: ''
      }
    }), now, 'context-A')
    expect(draft?.addressSelection?.savedAddressId).toBe(7)
    expect(draft?.addressSelection?.complement).toBe('ap 42')
  })

  it('restores the address selection of a new (unsaved) address', () => {
    const { draft } = parseCheckoutDraft(serialized({
      addressSelection: {
        savedAddressId: null,
        formattedAddress: 'Av. Brasil, 90 - Centro - Londrina/PR',
        structured: { route: 'Av. Brasil', street_number: '90' },
        complement: '',
        deliveryInstructions: 'portaria'
      }
    }), now, 'context-A')
    expect(draft?.addressSelection?.savedAddressId).toBeNull()
    expect(draft?.addressSelection?.formattedAddress).toContain('Av. Brasil')
    expect(draft?.addressSelection?.deliveryInstructions).toBe('portaria')
  })

  it('rejects a malformed address selection instead of restoring garbage', () => {
    const { draft } = parseCheckoutDraft(serialized({ addressSelection: { savedAddressId: 'x', formattedAddress: '  ' } }), now, 'context-A')
    expect(draft?.addressSelection).toBeNull()
  })

  it('keeps drafts without address selection restorable (older drafts)', () => {
    const { draft } = parseCheckoutDraft(serialized(), now, 'context-A')
    expect(draft?.addressSelection).toBeNull()
  })

  it('reopens the notes toggle when the drafted notes carry text', () => {
    const withNotes = parseCheckoutDraft(serialized({ state: { notes: 'tocar o interfone' } }), now, 'context-A')
    expect(withNotes.draft?.notesOpen).toBe(true)
    const withoutNotes = parseCheckoutDraft(serialized(), now, 'context-A')
    expect(withoutNotes.draft?.notesOpen).toBe(false)
  })

  it('validates the pending address label shape', () => {
    const valid = parseCheckoutDraft(serialized({ pendingAddressLabel: { key: 'other', custom: 'Casa da mãe' } }), now, 'context-A')
    expect(valid.draft?.pendingAddressLabel).toEqual({ key: 'other', custom: 'Casa da mãe' })
    const invalid = parseCheckoutDraft(serialized({ pendingAddressLabel: { key: 'castle' } }), now, 'context-A')
    expect(invalid.draft?.pendingAddressLabel).toBeNull()
  })
})


describe('draft isolation and validation', () => {
  it('rejects another principal/cart and unscoped legacy PII', () => {
    expect(parseCheckoutDraft(serialized(), now, 'context-B').draft).toBeNull()
    expect(parseCheckoutDraft(serialized({ version: 1 }), now, 'context-A').draft).toBeNull()
  })
  it('rejects a future timestamp and wrong field types', () => {
    for (const change of [{ savedAt: now + 1 }, { state: { name: {} } }, { state: { is_gift: 'false' } }]) {
      expect(parseCheckoutDraft(serialized(change), now, 'context-A').draft).toBeNull()
    }
  })
  it('retains the attempt correlation in the same authorized context', () => {
    expect(parseCheckoutDraft(serialized({ attemptKey: 'checkout-a' }), now, 'context-A').draft?.attemptKey).toBe('checkout-a')
  })
})
