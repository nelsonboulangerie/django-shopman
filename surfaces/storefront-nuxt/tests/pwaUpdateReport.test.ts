import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  PWA_UPDATE_ENDPOINT,
  PWA_UPDATE_STORAGE_KEY,
  markPwaUpdateApplied,
  reportPwaUpdateApplied,
  takePwaUpdateMark
} from '~/utils/pwaUpdateReport'

// #2379: a loja instalada conta ao Django que trocou de versão. A marca é escrita antes
// da troca e enviada no boot seguinte, com a versão de chegada.
describe('relato da troca de versão da loja instalada', () => {
  // O projeto `unit` roda em Node, sem navegador: um `localStorage` em memória.
  beforeEach(() => {
    const store = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, String(value)) },
      removeItem: (key: string) => { store.delete(key) },
      clear: () => store.clear()
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('o boot seguinte envia as duas versões e o gatilho, uma vez só', async () => {
    markPwaUpdateApplied({ trigger: 'prompt', from_version: 'abc1234' })
    const post = vi.fn().mockResolvedValue(undefined)

    const report = await reportPwaUpdateApplied('def5678', post)

    expect(report).toEqual({ trigger: 'prompt', from_version: 'abc1234', to_version: 'def5678' })
    expect(post).toHaveBeenCalledWith({ trigger: 'prompt', from_version: 'abc1234', to_version: 'def5678' })
    // Apagada antes do envio: o próximo boot não repete o relato.
    expect(localStorage.getItem(PWA_UPDATE_STORAGE_KEY)).toBeNull()
    expect(await reportPwaUpdateApplied('def5678', post)).toBeNull()
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('sem troca pendente, não envia nada', async () => {
    const post = vi.fn()
    expect(await reportPwaUpdateApplied('def5678', post)).toBeNull()
    expect(post).not.toHaveBeenCalled()
  })

  it('a falha de rede perde o relato, não repete', async () => {
    markPwaUpdateApplied({ trigger: 'navigation', from_version: 'abc1234' })
    const post = vi.fn().mockRejectedValue(new Error('offline'))

    expect(await reportPwaUpdateApplied('def5678', post)).toEqual({
      trigger: 'navigation',
      from_version: 'abc1234',
      to_version: 'def5678'
    })
    expect(takePwaUpdateMark()).toBeNull()
  })

  it('marca adulterada ou de outro app não vira relato', () => {
    localStorage.setItem(PWA_UPDATE_STORAGE_KEY, JSON.stringify({ trigger: 'idle', from_version: 'x' }))
    expect(takePwaUpdateMark()).toBeNull()
    localStorage.setItem(PWA_UPDATE_STORAGE_KEY, '{quebrado')
    expect(takePwaUpdateMark()).toBeNull()
  })

  it('o relato vai pela API da loja, no gêmeo do endpoint do kit', () => {
    expect(PWA_UPDATE_ENDPOINT).toBe('/api/v1/storefront/client-pwa-update/')
  })
})
