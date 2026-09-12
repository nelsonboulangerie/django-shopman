import { describe, expect, it } from 'vitest'

import { NELSON_FALLBACK_SHOP, resolveNelsonPublicShop } from '../app/utils/nelsonFallback'

describe('identidade pública da Nelson Boulangerie', () => {
  it('mantém a identificação legal completa quando a API estiver indisponível', () => {
    expect(NELSON_FALLBACK_SHOP).toMatchObject({
      brand_name: 'Nelson Boulangerie',
      legal_name: 'N. H. K. Panificadora LTDA',
      document_display: '02.119.381/0001-58',
      email: 'nelson@boulangerie.com.br',
      phone_display: '(43) 3323-1997'
    })
  })

  it('preenche somente os dados públicos ausentes na projeção viva', () => {
    const resolved = resolveNelsonPublicShop({
      ...NELSON_FALLBACK_SHOP,
      legal_name: '',
      email: '',
      phone_display: '',
      brand_name: 'Marca confirmada pela API'
    })

    expect(resolved.brand_name).toBe('Marca confirmada pela API')
    expect(resolved.legal_name).toBe('N. H. K. Panificadora LTDA')
    expect(resolved.email).toBe('nelson@boulangerie.com.br')
    expect(resolved.phone_display).toBe('(43) 3323-1997')
  })
})
