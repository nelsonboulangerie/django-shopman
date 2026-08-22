// Favoritos otimistas (WP-S1): toggle reflete na hora, reverte em falha, e é
// no-op (retorna null) para cliente anônimo. Versão incrementa só no sucesso.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return () => fn
})

async function authed (is: boolean) {
  const { useShopSession } = await import('~/composables/useShopSession')
  const s = useShopSession()
  s.reset()
  if (is) s.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana' })
}

async function loadFavorites () {
  const { useFavoritesState } = await import('~/composables/useFavoritesState')
  return useFavoritesState()
}

describe('useFavoritesState', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
    fetchMock.mockReset()
  })

  it('anonymous toggle is a no-op returning null', async () => {
    await authed(false)
    const fav = await loadFavorites()

    const res = await fav.toggle('CROISSANT', false)
    expect(res).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('optimistic add flips immediately and bumps version on success', async () => {
    await authed(true)
    fetchMock.mockResolvedValue({})
    const fav = await loadFavorites()
    const before = fav.version.value

    const res = await fav.toggle('BRIOCHE', false)
    expect(res).toBe(true)
    expect(fav.isFavorite('BRIOCHE')).toBe(true)
    expect(fav.version.value).toBe(before + 1)
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST')
  })

  it('reverts the optimistic flip when the server rejects', async () => {
    await authed(true)
    fetchMock.mockRejectedValue(Object.assign(new Error('500'), { data: { detail: 'x' } }))
    const fav = await loadFavorites()

    await expect(fav.toggle('SONHO', false)).rejects.toThrow()
    expect(fav.isFavorite('SONHO')).toBe(false) // revertido ao estado anterior
  })

  it('removing a favorite uses DELETE', async () => {
    await authed(true)
    fetchMock.mockResolvedValue({})
    const fav = await loadFavorites()

    await fav.toggle('PAO', true)
    expect(fav.isFavorite('PAO')).toBe(false)
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('DELETE')
  })
})
