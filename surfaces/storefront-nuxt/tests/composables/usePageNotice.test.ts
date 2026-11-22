// O aviso de página (#3242): a frase que um gesto deixa para a página seguinte ler.
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { usePageNotice } from '~/composables/usePageNotice'

async function mountNotice () {
  let api: ReturnType<typeof usePageNotice> | undefined
  await mountSuspended(defineComponent({
    setup () {
      api = usePageNotice()
      return () => h('div')
    }
  }))
  return api!
}

describe('usePageNotice', () => {
  it('guarda a frase e a página em que ela aparece, e o X a tira', async () => {
    const notice = await mountNotice()
    notice.show('Pronto, sua conta foi excluída.', '/')
    expect(notice.notice.value).toEqual({ message: 'Pronto, sua conta foi excluída.', path: '/' })
    notice.dismiss()
    expect(notice.notice.value).toBeNull()
  })

  it('é um aviso só, compartilhado: quem lê vê o que o gesto deixou', async () => {
    const writer = await mountNotice()
    const reader = await mountNotice()
    writer.show('Pronto.', '/')
    expect(reader.notice.value?.message).toBe('Pronto.')
    reader.dismiss()
    expect(writer.notice.value).toBeNull()
  })

  it('a ação e o tom são opcionais e só entram quando vêm (#3267)', async () => {
    const notice = await mountNotice()
    notice.show('Sua sacola ficou vazia antes do envio.', '/finalizar', {
      tone: 'attention',
      action: { label: 'Ver o cardápio', to: '/menu' }
    })
    expect(notice.notice.value).toEqual({
      message: 'Sua sacola ficou vazia antes do envio.',
      path: '/finalizar',
      tone: 'attention',
      action: { label: 'Ver o cardápio', to: '/menu' }
    })
    notice.show('Pronto.', '/')
    expect(notice.notice.value).toEqual({ message: 'Pronto.', path: '/' })
  })
})
