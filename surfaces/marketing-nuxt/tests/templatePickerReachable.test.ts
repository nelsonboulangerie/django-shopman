import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// ⚠️ Este arquivo existe por causa de um defeito de projeto real: o seletor do template
// aprovado do WhatsApp vivia SÓ dentro do aviso de alcance. E o aviso só aparece quando
// alguma campanha ativa usa WhatsApp E falta template — então a configuração ficava
// invisível quando não havia campanha ativa, e invisível DE NOVO depois de configurada,
// sem como trocar nem conferir.
//
// A regra que este teste guarda: config que existe tem porta fixa. O atalho dentro do
// aviso pode continuar, mas não pode ser o único caminho.
const source = readFileSync(
  fileURLToPath(new URL('../app/pages/index.vue', import.meta.url)),
  'utf8',
)

/** O bloco do aviso de alcance, para sabermos o que está DENTRO dele. */
function reachLimitsBlock(): string {
  const start = source.indexOf('v-if="reachLimits.length"')
  expect(start).toBeGreaterThan(-1)
  const end = source.indexOf('</section>', start)
  expect(end).toBeGreaterThan(start)
  return source.slice(start, end)
}

describe('o seletor de template tem porta fixa', () => {
  it('é alcançável fora do aviso de alcance', () => {
    const insideWarning = reachLimitsBlock().split('openTemplatePicker()').length - 1
    const total = source.split('openTemplatePicker()').length - 1

    // `- 1` porque a declaração da função também casa com o texto.
    expect(total - 1).toBeGreaterThan(insideWarning)
  })

  it('o atalho dentro do aviso continua existindo', () => {
    expect(reachLimitsBlock()).toContain('openTemplatePicker()')
  })
})
