// Compartilhar o pedido — uma mensagem, não um link solto.
//
// Duas armadilhas moram aqui, e as duas produzem o MESMO sintoma (o cliente
// abre o WhatsApp e só vê a URL crua, sem a frase):
//
// 1. `https://wa.me/?text=…` tem o telefone VAZIO. `wa.me/<numero>` é o
//    "click to chat"; sem número a URL cai na página "Continue to Chat" do
//    WhatsApp, que não é um destino de compartilhamento e perde o `text`. O
//    endpoint documentado para "mande este texto, escolha o destinatário" é
//    `https://api.whatsapp.com/send?text=`.
//
// 2. `navigator.share({ text, url })` — passar os dois faz a maioria dos
//    destinos (WhatsApp inclusive) usar SÓ o `url` e descartar o `text`. A URL
//    vai DENTRO do texto; o campo `url` não é preenchido.

/** A mensagem completa: a frase e o link, juntos, como o destinatário vai ler. */
export function shareMessage (text: string, url: string): string {
  const frase = text.trim()
  const link = url.trim()
  if (!frase) return link
  if (!link) return frase
  return `${frase} ${link}`
}

/** Link de fallback para quando não há Web Share API (desktop). */
export function whatsAppShareHref (message: string): string {
  if (!message.trim()) return ''
  return `https://api.whatsapp.com/send?text=${encodeURIComponent(message)}`
}

/** A URL canônica do pedido — sem query string da sessão (canal, UTM, etc.).
 *
 *  `window.location.href` carregava o que estivesse na barra de endereço, então
 *  o cliente compartilhava `?channel=…` junto sem querer. */
export function orderShareUrl (origin: string, ref: string): string {
  if (!origin || !ref) return ''
  return `${origin.replace(/\/+$/, '')}/pedido/${encodeURIComponent(ref)}`
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
