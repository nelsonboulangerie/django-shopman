import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { parse } from 'vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

// O pedido não retirado (#2613, decisão do dono de 17 e 18/11/2026).
//
// A regra tem um texto só, aprovado pelo dono, e mora em dois lugares: a cláusula dos
// Termos (que a cliente aceita ao entrar) e a revisão do checkout da encomenda (que ela
// lê antes de enviar e pagar). A trava de `legalVersion.test.ts` não deixa a constante
// virar a fonte da cláusula (ela mede o texto do `.vue`), então a frase é escrita nos
// dois arquivos, e esta trava reprova se uma mudar sem a outra.
const REGRA = 'Pedido não retirado até o fim do expediente do dia combinado: o que ainda puder voltar à venda é devolvido pelo mesmo meio de pagamento; o que se perdeu fica com a loja.'

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

describe('pedido não retirado: uma regra, o mesmo texto nos Termos e no checkout', () => {
  it('os Termos trazem a cláusula com o texto aprovado', () => {
    expect(texto('app/pages/termos.vue')).toContain(REGRA)
  })

  it('a revisão do checkout repete a mesma frase, palavra por palavra', () => {
    expect(texto('app/pages/finalizar.vue')).toContain(REGRA)
  })

  it('a linha do checkout aparece na encomenda para retirar, e leva aos Termos', () => {
    const checkout = readFileSync(resolve(raiz, 'app/pages/finalizar.vue'), 'utf8')
    expect(checkout).toContain('const showUnclaimedOrderRule = computed(() => isPickup.value && Boolean(state.delivery_date) && !isTodaySelected.value)')
    expect(checkout).toContain('<p v-if="showUnclaimedOrderRule" class="mt-3 shop-meta" data-review-unclaimed-rule>')
    expect(checkout).toContain('to="/termos#pickup-and-delivery"')
    // A âncora do link existe nos Termos.
    expect(readFileSync(resolve(raiz, 'app/pages/termos.vue'), 'utf8')).toContain('<LegalSection id="pickup-and-delivery">')
  })

  it('a regra não usa travessão', () => {
    expect(REGRA).not.toMatch(/[—–]/)
  })
})
