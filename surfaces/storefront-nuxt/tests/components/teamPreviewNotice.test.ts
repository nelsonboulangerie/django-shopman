// DEV-2026-096: o selo da versão de teste da equipe. A linha só aparece com `team_preview`
// no shell (o servidor decide quem é da equipe); o botão chama o comando do servidor e
// relê o shell, sem decidir versão nenhuma no cliente.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import ShopFooter from '~/components/ShopFooter.vue'
import TeamPreviewNotice from '~/components/TeamPreviewNotice.vue'
import { STOREFRONT_SHELL_KEY } from '~/composables/useStorefrontShell'
import type { ShellResponse, TeamPreviewProjection } from '~/types/shopman'

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  refresh: vi.fn(),
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() })
}))

mockNuxtImport('$fetch', () => mocks.fetch)
mockNuxtImport('useStorefrontShell', () => () => ({ refresh: mocks.refresh }))
mockNuxtImport('useSonner', () => mocks.toast)

const TEST_VERSION: TeamPreviewProjection = {
  opted_out: false,
  message: 'Você está vendo a versão de teste da equipe: escolher o dia antes de montar a sacola e dúvidas respondidas na sacola.',
  features: ['escolher o dia antes de montar a sacola', 'dúvidas respondidas na sacola'],
  action_label: 'Ver a versão de sempre'
}

const USUAL_VERSION: TeamPreviewProjection = {
  opted_out: true,
  message: 'Você está vendo a versão de sempre, sem as novidades em teste da equipe.',
  features: TEST_VERSION.features,
  action_label: 'Voltar à versão de teste'
}

function setShell (teamPreview: TeamPreviewProjection | null) {
  const shell: Record<string, unknown> = { experience: [] }
  if (teamPreview) shell.team_preview = teamPreview
  useNuxtApp().payload.data[STOREFRONT_SHELL_KEY] = { shell, cart: {} } as unknown as ShellResponse
}

async function flush () {
  await new Promise(resolve => setTimeout(resolve, 0))
  await nextTick()
}

describe('selo da versão de teste da equipe', () => {
  beforeEach(() => {
    mocks.fetch.mockReset().mockResolvedValue({ opted_out: true })
    mocks.refresh.mockReset().mockResolvedValue(undefined)
    mocks.toast.error.mockReset()
    setShell(null)
  })

  it('sem team_preview no shell (cliente comum, anônimo), nada aparece', async () => {
    const notice = await mountSuspended(TeamPreviewNotice, { props: { placement: 'account' } })
    expect(notice.find('[data-team-preview]').exists()).toBe(false)
    const footer = await mountSuspended(ShopFooter)
    expect(footer.find('[data-team-preview]').exists()).toBe(false)
  })

  it('com team_preview, a frase do servidor e o botão, no rodapé e na conta', async () => {
    setShell(TEST_VERSION)
    const footer = await mountSuspended(ShopFooter)
    const line = footer.find('[data-team-preview][data-team-preview-placement="footer"]')
    expect(line.exists()).toBe(true)
    expect(line.text()).toContain(TEST_VERSION.message)
    expect(line.find('[data-team-preview-action]').text()).toBe('Ver a versão de sempre')

    const account = await mountSuspended(TeamPreviewNotice, { props: { placement: 'account' } })
    expect(account.find('[data-team-preview-placement="account"]').text()).toContain(TEST_VERSION.message)
  })

  it('"Ver a versão de sempre" chama o POST e relê o shell', async () => {
    setShell(TEST_VERSION)
    const wrapper = await mountSuspended(TeamPreviewNotice, { props: { placement: 'account' } })
    await wrapper.find('[data-team-preview-action]').trigger('click')
    await flush()

    expect(mocks.fetch).toHaveBeenCalledTimes(1)
    const [url, options] = mocks.fetch.mock.calls[0]!
    expect(String(url)).toContain('/api/v1/storefront/experience/opt-out/')
    expect(options).toMatchObject({ method: 'POST', credentials: 'include' })
    expect(mocks.refresh).toHaveBeenCalledWith({ dedupe: 'cancel' })
  })

  it('"Voltar à versão de teste" desfaz pelo DELETE e relê o shell', async () => {
    setShell(USUAL_VERSION)
    const wrapper = await mountSuspended(TeamPreviewNotice, { props: { placement: 'footer' } })
    expect(wrapper.text()).toContain(USUAL_VERSION.message)
    await wrapper.find('[data-team-preview-action]').trigger('click')
    await flush()

    expect(mocks.fetch.mock.calls[0]![1]).toMatchObject({ method: 'DELETE' })
    expect(mocks.refresh).toHaveBeenCalledWith({ dedupe: 'cancel' })
  })

  it('falha do comando avisa e não relê', async () => {
    setShell(TEST_VERSION)
    mocks.fetch.mockRejectedValue(new Error('rede'))
    const wrapper = await mountSuspended(TeamPreviewNotice, { props: { placement: 'account' } })
    await wrapper.find('[data-team-preview-action]').trigger('click')
    await flush()

    expect(mocks.toast.error).toHaveBeenCalled()
    expect(mocks.refresh).not.toHaveBeenCalled()
  })
})
