// Enviar o resumo do pedido: uma mensagem de texto, sem link.
//
// O texto vem pronto do servidor (itens, quando, onde). Link do pedido NÃO vai:
// ele só abre para quem fez o pedido, e quem o recebia pelo WhatsApp caía em
// "Não encontramos este pedido" (beta 06/11).
//
// Duas armadilhas de compartilhamento moram aqui, e as duas produziam o mesmo
// sintoma (o destino perde a frase):
//
// 1. `https://wa.me/?text=…` tem o telefone VAZIO. `wa.me/<numero>` é o
//    "click to chat"; sem número a URL cai na página "Continue to Chat" do
//    WhatsApp, que não é um destino de compartilhamento e perde o `text`. O
//    endpoint documentado para "mande este texto, escolha o destinatário" é
//    `https://api.whatsapp.com/send?text=`.
//
// 2. `navigator.share({ text, url })` — passar os dois faz a maioria dos
//    destinos (WhatsApp inclusive) usar SÓ o `url` e descartar o `text`. Aqui
//    só vai o `text`.

/** Link de fallback para quando não há Web Share API (desktop). */
export function whatsAppShareHref (message: string): string {
  if (!message.trim()) return ''
  return `https://api.whatsapp.com/send?text=${encodeURIComponent(message)}`
}

/** True quando o compartilhamento nativo do sistema está disponível. */
export function canShareNatively (): boolean {
  return typeof navigator !== 'undefined' && typeof navigator.share === 'function'
}

/** Abre a folha de compartilhamento do sistema. Devolve false se não deu.
 *
 *  Cancelar (`AbortError`) não é erro: o cliente desistiu, e a tela não deve
 *  reagir a isso. */
export async function shareNatively (message: string): Promise<boolean> {
  if (!canShareNatively()) return false
  try {
    await navigator.share({ text: message })
    return true
  } catch {
    return false
  }
}
