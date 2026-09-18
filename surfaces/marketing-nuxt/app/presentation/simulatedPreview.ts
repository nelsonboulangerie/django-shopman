/** A prévia simulada: o conteúdo do anúncio retratado no lugar onde a pessoa vai ver
 *  — a tela cheia do Story, o cartão do Feed, a novidade do Google, o balão da
 *  conversa do WhatsApp.
 *
 *  ⚠️ O retrato se divide por FORMATO, não por plataforma. Instagram e Facebook num
 *  mesmo Feed, com o mesmo conteúdo, são um retrato só; Story e Feed do mesmo
 *  Instagram são dois, porque o enquadramento muda e é o enquadramento que se confere
 *  aqui. Quando duas plataformas do mesmo formato levam conteúdos diferentes, elas
 *  voltam a ser dois retratos — juntá-las mostraria uma delas com o texto da outra.
 *
 *  ⚠️ Mensagem e postagem não se retratam igual: a mensagem chega numa conversa, tem
 *  destinatário e não se apaga; a postagem fica num mural público e se apaga. O
 *  simulador honra essa diferença porque é ela que muda a decisão. */

export type SimulatedSceneKind =
  | "story"
  | "feed"
  | "google_update"
  | "whatsapp_message";

/** O que vai junto do anúncio, já resolvido: texto, hashtags, foto e link. */
export type SimulatedPreviewContent = {
  body: string;
  /** Como o gestor vai ler na tela da pessoa, com a cerquilha. */
  hashtags: string[];
  imageUrl: string;
  link: string;
};

export type SimulatedSceneInput = {
  platform: string;
  platformLabel: string;
  /** `publication_format` do artefato: `story`, `feed` ou `standard`. */
  publicationFormat: string;
  content: SimulatedPreviewContent;
};

export type SimulatedScene = SimulatedPreviewContent & {
  /** Chave estável do retrato, para `v-for` e para o teste nomear o que fotografou. */
  key: string;
  kind: SimulatedSceneKind;
  /** A frase inteira do botão: "Story no Instagram", "Mensagem no WhatsApp". */
  label: string;
  /** As plataformas que compartilham este retrato, por extenso. */
  platformsLabel: string;
  /** Verdadeiro quando o retrato é de mensagem direta, e não de postagem pública. */
  directMessage: boolean;
};

const FORMAT_KINDS: Record<string, SimulatedSceneKind> = {
  story: "story",
  feed: "feed",
  standard: "google_update",
};

/** O formato manda; a plataforma decide quando o artefato não declarou formato.
 *  Artefato histórico sem `publication_format` continua legível (contrato da
 *  superfície), então o retrato precisa de um caminho para ele. */
export function simulatedSceneKind(input: {
  platform: string;
  publicationFormat?: string;
}): SimulatedSceneKind {
  if (input.platform === "whatsapp") return "whatsapp_message";
  const declared = FORMAT_KINDS[String(input.publicationFormat || "").trim()];
  if (declared) return declared;
  return input.platform === "google_business" ? "google_update" : "feed";
}

/** Google e WhatsApp já dizem a plataforma no nome do formato; repeti-la viraria
 *  "Atualização do Google no Google". */
function sceneLabel(kind: SimulatedSceneKind, platformsLabel: string): string {
  if (kind === "google_update") return "Atualização do Google";
  if (kind === "whatsapp_message") return "Mensagem no WhatsApp";
  return `${kind === "story" ? "Story" : "Feed"} no ${platformsLabel}`;
}

/** "Instagram e Facebook" — a vírgula até três, o "e" antes do último. */
export function joinPlatformLabels(labels: readonly string[]): string {
  if (labels.length <= 1) return labels[0] || "";
  return `${labels.slice(0, -1).join(", ")} e ${labels[labels.length - 1]}`;
}

function contentFingerprint(content: SimulatedPreviewContent): string {
  return [
    content.body,
    content.hashtags.join(" "),
    content.imageUrl,
    content.link,
  ].join("");
}

/** Hashtag é guardada limpa e lida com "#": mostrar "padaria" onde sai "#padaria"
 *  não é a prévia do que sai. */
export function displaySimulatedHashtags(raw: readonly unknown[]): string[] {
  return raw
    .filter((tag): tag is string => typeof tag === "string" && tag.length > 0)
    .map((tag) => (tag.startsWith("#") ? tag : `#${tag}`));
}

/** Agrupa as entradas em retratos: um por formato, e um a mais sempre que o conteúdo
 *  daquele formato difere entre plataformas. */
export function simulatedScenes(
  entries: readonly SimulatedSceneInput[],
): SimulatedScene[] {
  const groups = new Map<
    string,
    {
      kind: SimulatedSceneKind;
      platforms: string[];
      platformLabels: string[];
      content: SimulatedPreviewContent;
    }
  >();

  for (const entry of entries) {
    const kind = simulatedSceneKind(entry);
    const groupKey = `${kind}${contentFingerprint(entry.content)}`;
    const existing = groups.get(groupKey);
    if (existing) {
      existing.platforms.push(entry.platform);
      existing.platformLabels.push(entry.platformLabel || entry.platform);
      continue;
    }
    groups.set(groupKey, {
      kind,
      platforms: [entry.platform],
      platformLabels: [entry.platformLabel || entry.platform],
      content: entry.content,
    });
  }

  return [...groups.values()].map((group) => {
    const platformsLabel = joinPlatformLabels(group.platformLabels);
    return {
      ...group.content,
      key: `${group.kind}:${group.platforms.join("+")}`,
      kind: group.kind,
      label: sceneLabel(group.kind, platformsLabel),
      platformsLabel,
      directMessage: group.kind === "whatsapp_message",
    };
  });
}

type ResolvedArtifactLike = {
  body?: string;
  hashtags?: readonly unknown[];
  link?: string;
  image_url?: string;
  provider_fields?: Record<string, unknown>;
};

/** TELA DE EDIÇÃO — o rascunho corrente, como o servidor acabou de resolvê-lo.
 *
 *  É de propósito que este caminho leia a prévia fiel: aqui o gestor está editando, e
 *  o que ele precisa ver é o efeito da edição que está fazendo agora. */
export function scenesFromDraftArtifacts(input: {
  previews: Record<string, { artifact: ResolvedArtifactLike }>;
  platformLabels: Record<string, string>;
}): SimulatedScene[] {
  return simulatedScenes(
    Object.entries(input.previews).map(([platform, preview]) => {
      const artifact = preview.artifact || {};
      return {
        platform,
        platformLabel: input.platformLabels[platform] || platform,
        publicationFormat: String(
          artifact.provider_fields?.publication_format || "",
        ),
        content: {
          body: String(artifact.body || ""),
          hashtags: displaySimulatedHashtags(artifact.hashtags || []),
          imageUrl: String(artifact.image_url || ""),
          link: String(artifact.link || ""),
        },
      };
    }),
  );
}

/** CAIXA DE CONFIRMAÇÃO — o conteúdo CONGELADO do comando.
 *
 *  ⚠️ Esta é a diferença que importa: aqui o retrato NÃO pode sair do anúncio na tela.
 *  O que o servidor vai publicar é o corpo selado no desafio de confirmação, e uma
 *  edição posterior que não entrou nele mostraria ao gestor algo que não vai acontecer.
 *  Foto e formato vêm do anúncio porque não são editáveis no card — o servidor congela
 *  o artefato por hash, e essas duas chaves não viajam no corpo do comando. */
export function scenesFromFrozenCommand(input: {
  frozenBody: Record<string, unknown> | undefined;
  platforms: readonly string[];
  platformLabels: Record<string, string>;
  platformContent?: Record<string, Record<string, unknown>>;
  imageUrl?: string;
}): SimulatedScene[] {
  const body =
    typeof input.frozenBody?.body === "string"
      ? input.frozenBody.body.trim()
      : "";
  const hashtags = displaySimulatedHashtags(
    Array.isArray(input.frozenBody?.hashtags)
      ? (input.frozenBody.hashtags as unknown[])
      : [],
  );
  return simulatedScenes(
    input.platforms.map((platform) => {
      const variant = input.platformContent?.[platform] || {};
      return {
        platform,
        platformLabel: input.platformLabels[platform] || platform,
        publicationFormat: String(variant.publication_format || ""),
        content: {
          body,
          hashtags,
          imageUrl: String(variant.image_url || input.imageUrl || ""),
          link: "",
        },
      };
    }),
  );
}
