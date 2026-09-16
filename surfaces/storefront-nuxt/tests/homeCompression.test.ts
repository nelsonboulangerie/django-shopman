import { gunzipSync } from 'node:zlib'
import { describe, expect, it, vi } from 'vitest'
import {
  encodingPreference,
  mergeVary,
  prepareHomeRepresentation,
  removeHeaderValue,
  setHeaderValue
} from '../server/utils/homeCompression'

describe('compressão transacional da home', () => {
  it('funde todas as fontes de Vary sem duplicar nomes', () => {
    expect(mergeVary(['Accept-Language', 'Origin, accept-language'], 'Accept-Encoding'))
      .toBe('Accept-Language, Origin, Accept-Encoding')
    expect(mergeVary(['Origin', '*'], 'Accept-Encoding')).toBe('*')
  })

  it('atualiza comprimento e remove validator sem depender da caixa', () => {
    const headers = { ETag: 'old-validator', 'content-LENGTH': '120', 'X-Test': 'preserved' }

    removeHeaderValue(headers, 'etag')
    setHeaderValue(headers, 'Content-Length', '42')

    expect(headers).toEqual({ 'X-Test': 'preserved', 'Content-Length': '42' })
  })

  it('respeita preferência e recusas explícitas de codificação', () => {
    expect(encodingPreference('gzip')).toEqual({ gzip: 1, identity: 1 })
    expect(encodingPreference('gzip;q=0.5, identity;q=1')).toEqual({ gzip: 0.5, identity: 1 })
    expect(encodingPreference('gzip;q=0, *;q=1')).toEqual({ gzip: 0, identity: 1 })
    expect(encodingPreference('gzip;q=0, identity;q=0, *;q=0')).toEqual({ gzip: 0, identity: 0 })
  })

  it('só publica o corpo gzip depois de concluir a compressão', async () => {
    const original = '<main>Nelson</main>'
    const representation = await prepareHomeRepresentation(original, 'gzip')

    expect(representation.kind).toBe('gzip')
    if (representation.kind !== 'gzip') throw new Error('gzip não preparado')
    expect(gunzipSync(representation.body).toString()).toBe(original)
  })

  it('preserva o corpo original quando uma falha assíncrona permite identity', async () => {
    const original = { html: '<main>Nelson</main>' }
    const failure = new Error('encoder failure')
    const compressor = vi.fn(async () => {
      await Promise.resolve()
      throw failure
    })

    const representation = await prepareHomeRepresentation(original, 'gzip, identity;q=0.5', compressor)

    expect(compressor).toHaveBeenCalledOnce()
    expect(representation).toEqual({ kind: 'identity', body: original, error: failure })
  })

  it('não envia identity após falha se o cliente a recusou', async () => {
    const failure = new Error('encoder failure')
    const representation = await prepareHomeRepresentation(
      '<main>Nelson</main>',
      'gzip, identity;q=0',
      async () => { throw failure }
    )

    expect(representation).toEqual({ kind: 'not-acceptable', error: failure })
  })
})
