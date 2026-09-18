/** O vocabulário do que sai daqui, num lugar só.
 *
 * São três palavras e elas não são sinônimas: **mensagem** é direta, vai para uma
 * pessoa e não se apaga; **postagem** é pública, vai para o mural e se apaga; e
 * **anúncio** é o objeto que se revisa antes de virar uma coisa ou a outra. O ato
 * genérico é disparar. */

import { formatCount } from "~/presentation/campaign";
import { platformResultLabel } from "~/presentation/marketingResult";

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

/** O que o disparo alcança — uma linha por destino, cada uma na SUA grandeza.
 *
 * ⚠️ Mensagem conta PESSOAS; postagem conta a si mesma. Um número só, chamado
 * "destinos", faz "37" valer para as duas coisas — e a diferença entre 37 pessoas e um
 * mural repetido 37 vezes é a diferença entre um disparo e um acidente.
 *
 * ⚠️ As plataformas de mural NÃO se juntam numa linha só. "Instagram, Facebook · 1
 * postagem em cada" obriga o leitor a distribuir o "1" entre as duas, e com uma
 * plataforma sozinha o "em cada" fica sem complemento e não quer dizer nada.
 *
 * Isto morava dentro da caixa de confirmação, que é a peça que acertou primeiro. O
 * diálogo de recuperação — onde o gestor autoriza REENVIO — continuava no modelo
 * antigo, e é exatamente o lugar onde chamar postagem de destino custa mais caro. */
export function reachLines(input: {
  platforms: readonly string[];
  audienceCount: number;
}): string[] {
  const platforms = (input.platforms ?? []).filter(Boolean);
  const lines: string[] = [];
  if (includesDirectMessage(platforms)) {
    const count = Math.max(0, Math.trunc(input.audienceCount || 0));
    lines.push(
      `WhatsApp · ${formatCount(count)} ${count === 1 ? "pessoa" : "pessoas"}`,
    );
  }
  for (const platform of platforms.filter(
    (platform) => !DIRECT_MESSAGE_PLATFORMS.has(platform),
  )) {
    lines.push(`${platformResultLabel(platform)} · 1 postagem`);
  }
  return lines;
}
