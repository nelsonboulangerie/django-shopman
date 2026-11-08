import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { whatsAppShareHref } from '../app/utils/share'

const SUMMARY = 'Pedido WEB-1 na Nelson Boulangerie\n2× Croissant\nRetirada: hoje · 15:00 às 15:30'

describe('link de fallback do WhatsApp', () => {
  it('usa o endpoint de envio, nao o click-to-chat sem telefone', () => {
    // `wa.me/?text=` tem o telefone VAZIO e cai na pagina "Continue to Chat",
    // que perde o texto — era por isso que so o link cru chegava.
    const href = whatsAppShareHref(SUMMARY)

    expect(href).toContain('api.whatsapp.com/send')
    expect(href).not.toContain('wa.me/?')
  })

  it('leva o resumo inteiro, com as quebras de linha', () => {
    const href = whatsAppShareHref(SUMMARY)

    expect(new URL(href).searchParams.get('text'))
      .toBe(SUMMARY)
  })

  it('sem mensagem nao oferece link', () => {
    expect(whatsAppShareHref('   ')).toBe('')
  })
})

describe('Enviar resumo do pedido', () => {
  it('manda o texto do servidor e nenhum link do pedido', () => {
    // O link do pedido so abre para quem o fez: quem o recebia via
    // "Nao encontramos este pedido" (beta 06/11).
    const page = readFileSync(resolve(__dirname, '../app/pages/pedido/[ref]/index.vue'), 'utf8')

    expect(page).toContain("tracking.value?.share_text?.trim()")
    expect(page).not.toContain('orderShareUrl')
    expect(page).not.toContain('window.location.origin')
  })
})
