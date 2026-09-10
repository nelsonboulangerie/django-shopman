import { describe, expect, it } from 'vitest'
import { CHECKOUT_DRAFT_TTL, parseCheckoutDraft } from '../app/utils/checkoutDraft'

const now = 1_756_000_000_000

function serialized (overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
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
    const { draft, stale } = parseCheckoutDraft(serialized(), now)
    expect(stale).toBe(false)
    expect(draft?.state.name).toBe('Ana')
    expect(draft?.activeStep).toBe('address')
  })

  it('flags a draft older than the TTL as stale, without restoring it', () => {
    const { draft, stale } = parseCheckoutDraft(serialized({ savedAt: now - CHECKOUT_DRAFT_TTL - 1 }), now)
    expect(draft).toBeNull()
    expect(stale).toBe(true)
  })

  it('ignores corrupted payloads without marking them stale', () => {
    expect(parseCheckoutDraft('{corrompido', now)).toEqual({ draft: null, stale: false })
    expect(parseCheckoutDraft(null, now)).toEqual({ draft: null, stale: false })
    expect(parseCheckoutDraft(JSON.stringify('texto'), now)).toEqual({ draft: null, stale: false })
    expect(parseCheckoutDraft(JSON.stringify({ savedAt: now }), now)).toEqual({ draft: null, stale: false })
  })

  it('drops an active step that does not exist for the drafted fulfillment', () => {
    const { draft } = parseCheckoutDraft(serialized({ state: { fulfillment_type: 'pickup' } }), now)
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
    }), now)
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
    }), now)
    expect(draft?.addressSelection?.savedAddressId).toBeNull()
    expect(draft?.addressSelection?.formattedAddress).toContain('Av. Brasil')
    expect(draft?.addressSelection?.deliveryInstructions).toBe('portaria')
  })

  it('rejects a malformed address selection instead of restoring garbage', () => {
    const { draft } = parseCheckoutDraft(serialized({ addressSelection: { savedAddressId: 'x', formattedAddress: '  ' } }), now)
    expect(draft?.addressSelection).toBeNull()
  })

  it('keeps drafts without address selection restorable (older drafts)', () => {
    const { draft } = parseCheckoutDraft(serialized(), now)
    expect(draft?.addressSelection).toBeNull()
  })

  it('reopens the notes toggle when the drafted notes carry text', () => {
    const withNotes = parseCheckoutDraft(serialized({ state: { notes: 'tocar o interfone' } }), now)
    expect(withNotes.draft?.notesOpen).toBe(true)
    const withoutNotes = parseCheckoutDraft(serialized(), now)
    expect(withoutNotes.draft?.notesOpen).toBe(false)
  })

  it('validates the pending address label shape', () => {
    const valid = parseCheckoutDraft(serialized({ pendingAddressLabel: { key: 'other', custom: 'Casa da mãe' } }), now)
    expect(valid.draft?.pendingAddressLabel).toEqual({ key: 'other', custom: 'Casa da mãe' })
    const invalid = parseCheckoutDraft(serialized({ pendingAddressLabel: { key: 'castle' } }), now)
    expect(invalid.draft?.pendingAddressLabel).toBeNull()
  })
})
