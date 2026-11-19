import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { parse } from 'vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

// O pedido não retirado (#2613, decisão do dono de 17 e 18/11/2026).
//
// A regra mora em dois lugares. A cláusula inteira, aprovada pelo dono, fica nos Termos
// (que a cliente aceita ao entrar). A revisão do checkout da encomenda, que ela lê antes
// de enviar e pagar, traz o RESUMO, numa oração, com o link para a cláusula (dono,
// 19/11/2026: no card "Antes de enviar" o texto tem de ser ultra conciso e inequívoco).
//
// O resumo pode encurtar, mas não pode esconder a parte que custa à cliente: nem tudo
// é devolvido. É o "só" da frase, e esta trava reprova se ele sair.
const REGRA = 'Pedido não retirado até o fim do expediente do dia combinado: o que ainda puder voltar à venda é devolvido pelo mesmo meio de pagamento; o que se perdeu fica com a loja.'
const RESUMO = 'Sem retirada no dia combinado, só devolvemos o que voltar à venda.'

const raiz = resolve(__dirname, '..')

// Nó da árvore do template, como o compilador do Vue o entrega: texto (tipo 2),
// comentário (tipo 3), elemento e raiz (com filhos).
interface NoDoTemplate { type: number, content?: string, children?: NoDoTemplate[] }

const NO_DE_TEXTO = 2

function textosDe (no: NoDoTemplate, saida: string[]): string[] {
  if (no.type === NO_DE_TEXTO && typeof no.content === 'string') saida.push(no.content)
  for (const filho of no.children || []) textosDe(filho, saida)
  return saida
}

/**
 * O texto que a cliente lê no template, tirado da ÁRVORE que o compilador do Vue
 * monta, e não de uma limpeza de marcação por expressão regular (que pode deixar
 * pedaço de comentário para trás). Comentário e marcação não são nós de texto; o
 * que sobra são as palavras, com os espaços colapsados.
 */
function texto (caminho: string): string {
  const { descriptor } = parse(readFileSync(resolve(raiz, caminho), 'utf8'))
  const arvore = descriptor.template?.ast as NoDoTemplate | undefined
  if (!arvore) throw new Error(`${caminho} não tem <template>`)
  return textosDe(arvore, []).join(' ').replace(/\s+/g, ' ').replace(/ ([:;.,])/g, '$1')
}

describe('pedido não retirado: a cláusula nos Termos, o resumo no checkout', () => {
  it('os Termos trazem a cláusula com o texto aprovado', () => {
    expect(texto('app/pages/termos.vue')).toContain(REGRA)
  })

  it('a revisão do checkout traz o resumo, e não uma segunda cópia da cláusula', () => {
    const revisao = texto('app/pages/finalizar.vue')
    expect(revisao).toContain(RESUMO)
    expect(revisao).not.toContain(REGRA)
  })

  it('o resumo diz as três coisas da cláusula: sem retirada, no dia combinado, e que nem tudo volta', () => {
    expect(RESUMO).toMatch(/^Sem retirada/)
    expect(RESUMO).toContain('no dia combinado')
    // "só devolvemos": o que não puder voltar à venda fica com a loja.
    expect(RESUMO).toMatch(/\bsó devolvemos\b/)
    expect(RESUMO).toContain('voltar à venda')
    expect(REGRA).toContain('voltar à venda')
    expect(REGRA).toContain('dia combinado')
  })

  it('a linha do checkout aparece na encomenda para retirar, e leva aos Termos', () => {
    const checkout = readFileSync(resolve(raiz, 'app/pages/finalizar.vue'), 'utf8')
    expect(checkout).toContain('const showUnclaimedOrderRule = computed(() => isPickup.value && Boolean(state.delivery_date) && !isTodaySelected.value)')
    // A frase mora no card "Antes de enviar" da revisão, e só nasce com a regra.
    expect(checkout).toMatch(/<div v-if="showUnclaimedOrderRule"[^>]*>\s*<Icon [^>]*\/>\s*<p class="text-sm" data-review-unclaimed-rule>/)
    expect(checkout.match(/data-review-unclaimed-rule/g)).toHaveLength(1)
    expect(checkout).toContain('to="/termos#pickup-and-delivery"')
    // A âncora do link existe nos Termos.
    expect(readFileSync(resolve(raiz, 'app/pages/termos.vue'), 'utf8')).toContain('<LegalSection id="pickup-and-delivery">')
  })

  it('a regra não usa travessão', () => {
    expect(RESUMO).not.toMatch(/[—–]/)
    expect(REGRA).not.toMatch(/[—–]/)
  })
})
