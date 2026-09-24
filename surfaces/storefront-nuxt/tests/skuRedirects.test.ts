import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import { createEvent } from 'h3'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  loadSkuRedirects,
  productSkuFromPath,
  redirectRetiredSku,
  resetSkuRedirectCache
} from '../server/utils/skuRedirects'

function eventFor (path: string) {
  const req = new IncomingMessage(new Socket())
  req.method = 'GET'
  req.url = path
  req.headers = { host: 'www.loja.test' }
  const res = new ServerResponse(req)
  return { event: createEvent(req, res), res }
}

const MAP = { CT: 'CRO', CROISSANT: 'CRO', PC: 'PCHOC' }
const fetchMap = () => Promise.resolve(MAP)

beforeEach(() => resetSkuRedirectCache())

describe('productSkuFromPath', () => {
  it('lê o código da PDP', () => {
    expect(productSkuFromPath('/produto/CT')).toBe('CT')
    expect(productSkuFromPath('/produto/CT/')).toBe('CT')
    expect(productSkuFromPath('/produto/QUEIJO-CAMEMBERT-ILEDEFRANCE-125')).toBe('QUEIJO-CAMEMBERT-ILEDEFRANCE-125')
  })

  it('ignora o que não é a própria página de produto', () => {
    expect(productSkuFromPath('/menu')).toBe('')
    expect(productSkuFromPath('/produto/CT/avaliacoes')).toBe('')
    expect(productSkuFromPath('/produtos')).toBe('')
  })
})

describe('redirectRetiredSku', () => {
  it('manda o código aposentado para o de hoje, com 301', async () => {
    const { event, res } = eventFor('/produto/CT')
    expect(await redirectRetiredSku(event, fetchMap)).toBe(true)
    expect(res.statusCode).toBe(301)
    expect(res.getHeader('location')).toBe('/produto/CRO')
  })

  it('preserva a query de campanha', async () => {
    const { event, res } = eventFor('/produto/CROISSANT?utm_source=instagram')
    await redirectRetiredSku(event, fetchMap)
    expect(res.getHeader('location')).toBe('/produto/CRO?utm_source=instagram')
  })

  it('não mexe no código vivo', async () => {
    const { event, res } = eventFor('/produto/CRO')
    expect(await redirectRetiredSku(event, fetchMap)).toBe(false)
    expect(res.statusCode).toBe(200)
  })

  it('não mexe em rota que não é de produto', async () => {
    const { event } = eventFor('/menu')
    expect(await redirectRetiredSku(event, fetchMap)).toBe(false)
  })

  // Mapa fora do ar não pode derrubar a loja: sem ele, o 404 de sempre.
  it('segue em frente quando o mapa falha', async () => {
    const { event, res } = eventFor('/produto/CT')
    const falha = () => Promise.reject(new Error('backend fora'))
    expect(await redirectRetiredSku(event, falha)).toBe(false)
    expect(res.statusCode).toBe(200)
  })
})

describe('loadSkuRedirects', () => {
  it('busca uma vez dentro da validade e renova depois dela', async () => {
    const fetcher = vi.fn().mockResolvedValue(MAP)
    await loadSkuRedirects(fetcher, 1_000)
    await loadSkuRedirects(fetcher, 200_000)
    expect(fetcher).toHaveBeenCalledTimes(1)
    await loadSkuRedirects(fetcher, 1_000 + 5 * 60 * 1000 + 1)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
})
