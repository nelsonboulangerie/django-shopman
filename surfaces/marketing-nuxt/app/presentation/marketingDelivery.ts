/** O vocabulário do que sai daqui, num lugar só.
 *
 * São três palavras e elas não são sinônimas: **mensagem** é direta, vai para uma
 * pessoa e não se apaga; **postagem** é pública, vai para o mural e se apaga; e
 * **anúncio** é o objeto que se revisa antes de virar uma coisa ou a outra. O ato
 * genérico é disparar. */

/** WhatsApp é o único canal que fala com uma pessoa por vez; o resto é mural. */
const DIRECT_MESSAGE_PLATFORMS = new Set(["whatsapp"]);

export function includesDirectMessage(platforms: readonly string[]): boolean {
  return platforms.some((platform) => DIRECT_MESSAGE_PLATFORMS.has(platform));
}

export function includesPublicPost(platforms: readonly string[]): boolean {
  return platforms.some((platform) => !DIRECT_MESSAGE_PLATFORMS.has(platform));
}

/** O nome do último gesto — o único do caminho que faz alguma coisa sair.
 *
 * Três destinos, três verbos, porque são três atos diferentes: mensagem se **envia**,
 * postagem se **publica**, e quando o anúncio faz os dois não existe verbo específico
 * — aí vale o genérico da casa, **disparar**. Agendar vence os três, porque ali
 * "agora" mentiria sobre o quando. */
export function deliveryActionLabel(options: {
  platforms: readonly string[];
  scheduled?: boolean;
}): string {
  if (options.scheduled) return "Agendar";
  const message = includesDirectMessage(options.platforms);
  const post = includesPublicPost(options.platforms);
  if (message && post) return "Disparar agora";
  if (message) return "Enviar agora";
  return "Publicar agora";
}

/** A foto que vai sair com o anúncio.
 *
 * ⚠️ `announcement.image_url` é o campo óbvio e quase sempre está vazio: a imagem de
 * verdade mora no conteúdo POR PLATAFORMA (`platform_content.instagram.image_url`),
 * porque cada mural tem o seu formato. Quem procurar só no campo do topo conclui que o
 * anúncio não tem foto quando ele tem — foi o que aconteceu aqui na primeira tentativa. */
export function outgoingImageUrl(announcement: {
  image_url?: string;
  platform_content?: Record<string, Record<string, unknown>>;
}): string {
  const top = String(announcement.image_url || "").trim();
  if (top) return top;
  for (const content of Object.values(announcement.platform_content ?? {})) {
    const candidate = String(
      (content as { image_url?: unknown })?.image_url || "",
    ).trim();
    if (candidate) return candidate;
  }
  return "";
}
