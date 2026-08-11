// Apresentação pura do Marketing — sem Vue, sem fetch, sem Date.now() implícito.
// Traduz o contrato da projection para o que o gestor lê no card.
//
// Regra que vale para todo este arquivo: número que o backend não mandou não
// se inventa. Audiência vazia é resposta normal (ninguém opt-in ainda), e a
// frase precisa dizer isso em vez de fingir alcance.

import type { AudienceRules, Announcement, PlatformResult } from "~/types/campaign";

/** Rótulos das origens de audiência, na ordem em que a frase os lê. */
const AUDIENCE_LABELS: ReadonlyArray<readonly [string, string]> = [
  ["favorites_count", "favoritos"],
  ["bought_count", "recompra"],
  ["alerts_count", "alertas"],
];

/**
 * "12 favoritos, 28 recompra, 3 alertas = 43 clientes".
 *
 * O total vem do backend (já deduplicado por telefone), NÃO da soma das partes:
 * quem favoritou e também recompra é uma pessoa só, e somar mentiria pra cima.
 */
export function audienceSummary(audience: Record<string, number> | undefined): string {
  const counts = audience ?? {};
  const parts = AUDIENCE_LABELS.filter(([key]) => (counts[key] ?? 0) > 0).map(
    ([key, label]) => `${counts[key]} ${label}`,
  );
  const total = counts.total ?? 0;

  if (total === 0) return "Ninguém para avisar por enquanto";
  if (parts.length === 0) return `${total} ${total === 1 ? "cliente" : "clientes"}`;
  return `${parts.join(", ")} = ${total} ${total === 1 ? "cliente" : "clientes"}`;
}

/** Quantos VIPs recebem antes, e com quanto de vantagem. */
export function vipSummary(audience: Record<string, number> | undefined): string {
  const counts = audience ?? {};
  const vips = counts.vip_count ?? 0;
  const delay = counts.vip_delay_minutes ?? 0;
  if (vips === 0 || delay === 0) return "";
  return `${vips} ${vips === 1 ? "VIP recebe" : "VIPs recebem"} ${delay} min antes`;
}

/**
 * "expira em 12 min" — o prazo é a informação urgente do card.
 *
 * Frescor é efêmero: sem prazo visível o gestor não sabe que revisar amanhã é
 * o mesmo que descartar.
 */
export function expiryLabel(minutes: number): string {
  if (minutes < 0) return "";
  if (minutes === 0) return "expirou";
  if (minutes < 60) return `expira em ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `expira em ${hours} h`;
}

/** Prazo curto pede destaque; prazo largo não deve gritar. */
export function expiryTone(minutes: number): "urgent" | "warning" | "calm" | "none" {
  if (minutes < 0) return "none";
  if (minutes <= 10) return "urgent";
  if (minutes <= 30) return "warning";
  return "calm";
}

const PLATFORM_ICONS: Record<string, string> = {
  instagram: "lucide:instagram",
  facebook: "lucide:facebook",
  google_business: "lucide:map-pin",
  whatsapp: "lucide:message-circle",
};

export function platformIcon(platform: string): string {
  return PLATFORM_ICONS[platform] ?? "lucide:share-2";
}

// Os quatro estados que o handler grava (`shopman/shop/handlers/campaign.py`)
// mais o `queued` que a projection usa para plataforma ainda sem resposta.
const RESULT_LABELS: Record<string, string> = {
  published: "publicado",
  sent: "enviado",
  // Onda de WhatsApp entrega por pessoa: parte chegar e parte falhar é resultado
  // comum, e chamar isso de "enviado" esconderia quem não recebeu.
  partial: "enviado em parte",
  queued: "na fila",
  pending_manual: "aguardando envio manual",
  failed: "falhou",
};

export function resultLabel(status: string): string {
  return RESULT_LABELS[status] ?? status;
}

export function resultTone(status: string): "ok" | "pending" | "fail" {
  // `sent` é o "publicado" do WhatsApp: a onda saiu para a audiência.
  if (status === "published" || status === "sent") return "ok";
  // Parcial pende para FALHA, não para ok: alguém não recebeu, e o gestor tem de
  // decidir o que fazer com essas pessoas.
  if (status === "failed" || status === "partial") return "fail";
  return "pending";
}

/**
 * Um announcement "deu certo"? Só quando TODAS as plataformas alvejadas publicaram.
 *
 * Parcial não é sucesso: se o Google saiu e o Instagram falhou, o gestor
 * precisa ver isso como pendência, não como pronto.
 */
export function announcementOutcome(results: PlatformResult[]): "published" | "partial" | "failed" | "pending" {
  if (results.length === 0) return "pending";
  // `sent` conta como saída: é o "publicado" do WhatsApp.
  const published = results.filter((r) => r.status === "published" || r.status === "sent").length;
  const failed = results.filter((r) => r.status === "failed" || r.status === "partial").length;

  if (published === results.length) return "published";
  if (failed === results.length) return "failed";
  if (published > 0 || failed > 0) return "partial";
  return "pending";
}

/** Hashtags são guardadas limpas; o "#" é da leitura, não do dado. */
export function displayHashtag(tag: string): string {
  const clean = tag.trim().replace(/^#+/, "");
  return clean ? `#${clean}` : "";
}

/** Texto colado do gestor vira lista de tags — aceita "#a #b", "a, b" e quebras. */
export function parseHashtags(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((tag) => tag.trim().replace(/^#+/, ""))
    .filter(Boolean);
}

/** Frase do resumo de público: "favoritos, alertas, recompra em 90 dias".
 *
 *  ⚠️ Conhecia só três das nove regras. Uma campanha para "leais" ou para o grupo
 *  atacado — configurada, funcionando, alcançando gente — aparecia na lista como "Sem
 *  audiência direta". O resumo mentia justamente sobre a decisão mais importante da
 *  campanha, e o gestor não tinha por que desconfiar dele.
 */
export function audienceRulesSummary(
  rules: AudienceRules | undefined,
  labels: AudienceLabels = {},
): string {
  const parts: string[] = [];
  if (rules?.favorites) parts.push("favoritos");
  if (rules?.alerts) parts.push("alertas");
  if (rules?.bought_within_days) parts.push(`recompra em ${rules.bought_within_days} dias`);
  if (rules?.groups?.length) parts.push(named(rules.groups, labels.groups));
  if (rules?.rfm_segments?.length) parts.push(named(rules.rfm_segments, labels.segments));
  if (rules?.churn_risk_min) parts.push("quem está sumindo");
  if (rules?.birthday_today) parts.push("aniversariantes de hoje");
  if (parts.length === 0) return "Sem público definido";

  // "Cruzando" primeiro, porque muda o SENTIDO do que vem depois: a mesma lista de
  // regras alcança gente diferente somada e cruzada.
  const prefix = rules?.match === "all" && parts.length > 1 ? "cruzando " : "";
  const vip = rules?.vip_first_minutes;
  const suffix = vip ? `, melhores clientes ${vip} min antes` : "";
  return prefix + parts.join(", ") + suffix;
}

/** Rótulos vindos do servidor. Grupo e segmento têm dono no guestman
 *  (`CustomerGroup.name`, `RFM_SEGMENTS`), e a projection já os entrega em
 *  `options.customer_groups` / `options.rfm_segments`.
 *
 *  ⚠️ Traduzi esses refs à mão aqui por um instante, e o mapa saiu com quatro segmentos
 *  que este sistema não tem (`potential_loyalist`, `new_customer`, `cant_lose`,
 *  `hibernating` — o vocabulário real tem seis e está em `insights/models.py:15`). É a
 *  demonstração do risco: cópia de vocabulário não avisa quando divergir.
 */
export type AudienceLabels = {
  groups?: Record<string, string>;
  segments?: Record<string, string>;
};

/** Refs em rótulos, na ordem escolhida. Ref sem rótulo conhecido volta como veio. */
function named(refs: string[], labels: Record<string, string> | undefined): string {
  return refs.map((ref) => labels?.[ref] ?? ref).join(", ");
}

/** `Choice[]` (como a projection entrega) em mapa ref → rótulo. */
export function choiceLabels(choices: { value: string; label: string }[] | undefined) {
  return Object.fromEntries((choices ?? []).map((c) => [c.value, c.label]));
}

/** "Instagram, Google Meu Negócio" a partir dos refs, na ordem escolhida. */
export function platformsSummary(platforms: string[], labels: Record<string, string>): string {
  if (platforms.length === 0) return "Nenhuma plataforma";
  return platforms.map((ref) => labels[ref] ?? ref).join(", ");
}

/** Hora local curta ("18/07 às 07:30"). ISO vazio → string vazia, sem "Invalid Date". */
export function shortDateTime(iso: string): string {
  if (!iso) return "";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Um announcement pendente ainda vale a revisão?
 *
 * O sweeper do backend expira em ciclos de minutos; a tela não pode oferecer
 * "Publicar" num card que já venceu entre um fetch e outro.
 */
export function isStillReviewable(announcement: Announcement): boolean {
  return announcement.status === "pending_review" && announcement.expires_in_minutes !== 0;
}
