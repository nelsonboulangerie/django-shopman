import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// ⚠️ Este arquivo nasceu de um defeito de projeto: o seletor do template aprovado do
// WhatsApp vivia SÓ dentro do aviso de alcance do painel — e o aviso só aparece quando
// alguma campanha ativa usa WhatsApp E falta template. A config ficava invisível quando não
// havia campanha ativa, e invisível DE NOVO depois de configurada.
//
// A correção final não foi dar um botão ao painel: foi dar **casa** à configuração. Ela mora
// em `/platforms`, e o painel volta a ser só decisão.
function read (path: string): string {
  return readFileSync(fileURLToPath(new URL(path, import.meta.url)), 'utf8')
}

describe('a configuração de plataforma tem casa', () => {
  it('o seletor de template vive na tela de Plataformas', () => {
    const page = read('../app/pages/platforms.vue')
    expect(page).toContain('onChooseTemplate')
    expect(page).toContain('Testar no meu WhatsApp')
  })

  it('o painel NÃO configura plataforma — só decide', () => {
    const board = read('../app/pages/index.vue')
    expect(board).not.toContain('onChooseTemplate')
    expect(board).not.toContain('Testar no meu WhatsApp')
    expect(board).not.toContain('useWhatsAppTemplate')
  })

  it('o aviso do painel aponta a casa em vez de configurar', () => {
    expect(read('../app/pages/index.vue')).toContain('/platforms')
  })
})
