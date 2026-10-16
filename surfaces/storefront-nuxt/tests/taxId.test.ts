import { describe, expect, it } from 'vitest'
import {
  TAX_ID_INVALID_MESSAGE,
  TAX_ID_WHY,
  taxIdError,
  formatTaxId,
  isValidTaxId,
  taxIdLooksComplete
} from '../app/presentation/taxId'

describe('CPF/CNPJ da nota da entrega', () => {
  it('confere o dígito verificador, não só a contagem', () => {
    expect(isValidTaxId('529.982.247-25')).toBe(true)
    expect(isValidTaxId('529.982.247-00')).toBe(false)
    expect(isValidTaxId('111.111.111-11')).toBe(false)
    expect(isValidTaxId('11.222.333/0001-81')).toBe(true)
    expect(isValidTaxId('5299822472')).toBe(false)
  })

  it('formata enquanto se digita', () => {
    expect(formatTaxId('52998224725')).toBe('529.982.247-25')
    expect(formatTaxId('5299822')).toBe('529.982.2')
    expect(formatTaxId('11222333000181')).toBe('11.222.333/0001-81')
  })

  it('vazio nunca é erro: na entrega o documento é opcional (13/10/2026)', () => {
    expect(taxIdError('')).toBe('')
    expect(taxIdError('52998224725')).toBe('')
  })

  it('documento errado é erro sempre', () => {
    expect(taxIdError('52998224700')).toBe(TAX_ID_INVALID_MESSAGE)
  })

  it('não acusa o CPF pela metade', () => {
    expect(taxIdLooksComplete('529.982.24')).toBe(false)
    expect(taxIdLooksComplete('529.982.247-25')).toBe(true)
  })

  it('a copy é convite, sem travessão', () => {
    for (const text of [TAX_ID_INVALID_MESSAGE, TAX_ID_WHY]) {
      expect(text).not.toMatch(/—|a gente/)
    }
    expect(TAX_ID_WHY).toMatch(/se quiser/)
  })
})
