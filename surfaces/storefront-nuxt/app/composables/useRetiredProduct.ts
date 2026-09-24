// PRODUTO APAGADO NÃO É "NUNCA EXISTIU".
//
// A loja respondia 404 no endereço de um produto que saiu do cardápio, e 404
// significa "nunca vi isso aqui". A verdade é outra: existia, saiu, e não volta
// — quem chega ali veio de um link que já foi bom. Decisão do dono em
// 23/09/2026: dizer **não existe mais** (410) e oferecer a prateleira de onde o
// produto saiu, para a pessoa não terminar num beco.
//
// O 410 é também o sinal certo para a busca: o Google tira a página mais rápido
// do que com 404, sem ficar tentando de novo por semanas.
//
// Quem NÃO entra aqui: produto despublicado. Ele continua no catálogo e pode
// voltar (a mini baguete saiu da vitrine e ficou para a encomenda do
// restaurante). Para esse, 404 é o sinal reversível — e é o que ele já dá.

export interface RetiredProduct {
  /** Ref da coleção a oferecer; '' quando não há prateleira viva. */
  collection: string
  collection_name: string
}

export function retiredFromPayload (payload: unknown, sku: string): RetiredProduct | null {
  const gone = (payload as { gone?: Record<string, unknown> } | null)?.gone
  const entry = gone && typeof gone === 'object' ? (gone as Record<string, unknown>)[sku] : null
  if (!entry || typeof entry !== 'object') return null
  const record = entry as Record<string, unknown>
  return {
    collection: typeof record.collection === 'string' ? record.collection : '',
    collection_name: typeof record.collection_name === 'string' ? record.collection_name : ''
  }
}

/** Consulta a lápide do SKU. Falha de rede devolve `null`: cai no 404 de sempre. */
export async function fetchRetiredProduct (url: string, sku: string): Promise<RetiredProduct | null> {
  try {
    return retiredFromPayload(await $fetch(url), sku)
  } catch {
    return null
  }
}
