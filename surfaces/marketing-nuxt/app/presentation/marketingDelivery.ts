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

/** O verbo do efeito: entregar cobre os dois, enviar é mensagem, publicar é mural. */
export function deliveryActionLabel(options: {
  platforms: readonly string[];
  scheduled?: boolean;
}): string {
  if (options.scheduled) return "Agendar";
  const direct = includesDirectMessage(options.platforms);
  const publication = includesPublicPublication(options.platforms);
  if (direct && publication) return "Entregar agora";
  if (direct) return "Enviar agora";
  return "Publicar agora";
}
