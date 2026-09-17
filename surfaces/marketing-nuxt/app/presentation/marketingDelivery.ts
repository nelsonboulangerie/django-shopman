/** Como se chama, em português de gente, o que vai acontecer quando o gestor confirmar.
 *
 * O botão de decisão e o botão da caixa de confirmação precisam dizer a MESMA coisa.
 * Enquanto a caixa dizia "Confirmar consequência", o gestor lia jargão exatamente no
 * momento em que precisava entender o efeito — e ler jargão na hora da decisão é o que
 * faz uma tela parecer protocolo em vez de trabalho.
 */

/** WhatsApp é o único canal que fala com uma pessoa por vez; o resto é mural. */
const DIRECT_MESSAGE_PLATFORMS = new Set(["whatsapp"]);

export function includesDirectMessage(platforms: readonly string[]): boolean {
  return platforms.some((platform) => DIRECT_MESSAGE_PLATFORMS.has(platform));
}

export function includesPublicPublication(platforms: readonly string[]): boolean {
  return platforms.some((platform) => !DIRECT_MESSAGE_PLATFORMS.has(platform));
}

/** O nome do último gesto — o único do caminho que faz alguma coisa sair.
 *
 * Antes este rótulo mudava com o destino: "Enviar agora" para WhatsApp, "Publicar
 * agora" para mural, "Entregar agora" para os dois. A distinção é verdadeira, mas ela
 * já está escrita na linha acima do botão, que diz o que vai para cada plataforma — e
 * repeti-la no botão custava a palavra que a casa usa no resto do caminho. Disparar é
 * essa palavra.
 *
 * O agendamento é a exceção que não se abre mão: ali "agora" mentiria sobre o quando. */
export function deliveryActionLabel(options: { scheduled?: boolean }): string {
  return options.scheduled ? "Agendar" : "Disparar agora";
}
