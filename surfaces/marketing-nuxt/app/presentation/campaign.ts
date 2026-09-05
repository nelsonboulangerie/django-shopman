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

  if (total === 0) return alertsNote(counts) || "Ninguém para avisar por enquanto";
  if (parts.length === 0) return `${total} ${total === 1 ? "cliente" : "clientes"}`;
  return `${parts.join(", ")} = ${total} ${total === 1 ? "cliente" : "clientes"}`;
}

/**
 * Por que a fila de "me avise" deste produto está vazia — em uma frase.
 *
 * ⚠️ O gestor abriu o Marketing, leu "ninguém para avisar" na Baguette e achou que o
 * sistema tinha perdido a inscrição que o pai dele acabara de fazer. Não tinha: a
 * inscrição existia, o estoque voltou 7 minutos depois, o aviso saiu e a linha foi
 * consumida. A conta estava certa e a tela, muda — e tela muda com número surpreendente
 * é indistinguível de tela quebrada.
 *
 * Fala só do pedaço "alertas", nunca do total: com outras regras ligadas o total tem
 * outros donos, e uma frase sobre a fila de avisos continua verdadeira ao lado deles.
 *
 * Vazio quando a regra `alerts` nem rodou (sem produto no evento, ou desligada) ou
 * quando ela achou alguém — só o zero precisa de voz.
 */
export function alertsNote(
  counts: { alerts_count?: number; alerts_notified_count?: number } | undefined,
): string {
  const pending = counts?.alerts_count;
  if (pending === undefined || pending > 0) return "";
  const already = counts?.alerts_notified_count ?? 0;
  if (already === 1) return "A pessoa que pediu aviso deste produto já foi avisada";
  if (already > 1) return `As ${already} pessoas que pediram aviso deste produto já foram avisadas`;
  return "Ninguém pediu para ser avisado deste produto ainda";
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
 * "Expira em 12 min" — o prazo é a informação urgente do card.
 *
 * Frescor é efêmero: sem prazo visível o gestor não sabe que revisar amanhã é
 * o mesmo que descartar.
 */
export function expiryLabel(minutes: number): string {
  if (minutes < 0) return "";
  if (minutes === 0) return "Expirou";
  if (minutes < 60) return `Expira em ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `Expira em ${hours} h`;
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

/** Frase do resumo de público: "Favoritos, alertas, recompra em 90 dias".
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
  // `fixed` = frase nossa (copy de UI, começa com maiúscula quando abre o resumo);
  // o resto é rótulo/ref vindo de dados, que fica exatamente como veio.
  const parts: { text: string; fixed: boolean }[] = [];
  if (rules?.favorites) parts.push({ text: "favoritos", fixed: true });
  if (rules?.alerts) parts.push({ text: "alertas", fixed: true });
  if (rules?.bought_within_days) {
    parts.push({ text: `recompra em ${rules.bought_within_days} dias`, fixed: true });
  }
  if (rules?.price_tiers?.length) {
    parts.push({ text: named(rules.price_tiers, labels.priceTiers), fixed: false });
  }
  if (rules?.tags?.length) parts.push({ text: named(rules.tags, labels.tags), fixed: false });
  if (rules?.rfm_segments?.length) {
    parts.push({ text: named(rules.rfm_segments, labels.segments), fixed: false });
  }
  if (rules?.churn_risk_min) parts.push({ text: "quem está sumindo", fixed: true });
  if (rules?.birthday_today) parts.push({ text: "aniversariantes de hoje", fixed: true });
  if (parts.length === 0) return "Sem público definido";

  // "Cruzando" primeiro, porque muda o SENTIDO do que vem depois: a mesma lista de
  // regras alcança gente diferente somada e cruzada.
  const prefix = rules?.match === "all" && parts.length > 1 ? "cruzando " : "";
  const vip = rules?.vip_first_minutes;
  const suffix = vip ? `, melhores clientes ${vip} min antes` : "";
  const summary = prefix + parts.map((part) => part.text).join(", ") + suffix;
  // Sentence case só quando a abertura é copy nossa; rótulo de dado não se reescreve.
  if (!prefix && !parts[0]!.fixed) return summary;
  return summary.charAt(0).toUpperCase() + summary.slice(1);
}

/** Rótulos vindos do servidor. Faixa de preço e segmento têm dono no guestman
 *  (`PriceTier.name`, `RFM_SEGMENTS`), e a projection já os entrega em
 *  `options.price_tiers` / `options.rfm_segments`.
 *
 *  ⚠️ Traduzi esses refs à mão aqui por um instante, e o mapa saiu com quatro segmentos
 *  que este sistema não tem (`potential_loyalist`, `new_customer`, `cant_lose`,
 *  `hibernating` — o vocabulário real tem seis e está em `insights/models.py:15`). É a
 *  demonstração do risco: cópia de vocabulário não avisa quando divergir.
 */
export type AudienceLabels = {
  priceTiers?: Record<string, string>;
  tags?: Record<string, string>;
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

/**
 * O que dizer depois de aprovar — pela RESPOSTA do servidor, nunca pelo corpo enviado.
 *
 * ⚠️ O toast lia o corpo ENVIADO: sem data ele dizia "Anúncio publicado." mesmo quando
 * o servidor tinha AGENDADO (campanha com janela de horas preferidas nasce com data na
 * próxima janela). O gestor fechava a tela achando que já estava no ar. Quem sabe o que
 * aconteceu é o servidor, e ele devolve `scheduled`.
 */
export function approvalMessage(resposta: { scheduled?: boolean } | null | undefined): string {
  return resposta?.scheduled ? "Anúncio agendado." : "Anúncio publicado.";
}

/**
 * O corpo do "Publicar": sem data marcada, o gestor quer AGORA.
 *
 * ⚠️ Sem `publish_now`, aprovar sem data deixava o anúncio parado esperando a agenda que
 * a campanha tinha posto sozinha — e o botão se chama "Publicar".
 */
export function approvalBody<T extends { publish_at?: string }>(
  edits: T,
): T & { publish_now?: boolean } {
  return edits.publish_at ? { ...edits } : { ...edits, publish_now: true };
}

//: As chaves de audiência que ESTE formulário controla. Tudo o que não está aqui foi
//: configurado em outro lugar (Admin: tags, segmento RFM, `match`) e não é dele para
//: apagar.
const AUDIENCE_KEYS_OWNED_BY_THE_FORM = [
  "favorites",
  "alerts",
  "bought_within_days",
  "vip_first_minutes",
] as const;

/**
 * As regras de audiência a enviar: as do formulário POR CIMA das que já existiam.
 *
 * ⚠️ O `submit()` montava o objeto DO ZERO com quatro chaves, e o PATCH sobrescreve o
 * JSON inteiro. O gestor abria "Editar" numa campanha com tags, segmento RFM e
 * `match: "all"`, mudava só o nome, salvava — e perdia dez chaves.
 *
 * ⚠️ E a direção importa: com favoritos, alertas e histórico de compra ligados, perder
 * `match: "all"` troca INTERSEÇÃO por UNIÃO. O disparo vai para MAIS gente do que o
 * gestor pediu, sem aviso — o erro que não dá para desfazer depois de a mensagem sair.
 *
 * O mesmo cuidado que o `schedule` já tinha ("só mandamos quando ele é a causa, para
 * não apagar um `preferred_hours` configurado no Admin"), agora aqui.
 *
 * Desligar uma chave do formulário a REMOVE, e isso é deliberado: o serviço lê
 * "0 dias" como "não usa", então mandar zero e omitir dizem a mesma coisa — mas omitir
 * é o que o resto do código espera ver.
 */
export function mergeAudienceRules(
  original: AudienceRules | null | undefined,
  doFormulario: AudienceRules,
): AudienceRules {
  const merged: AudienceRules = { ...(original ?? {}) };
  for (const chave of AUDIENCE_KEYS_OWNED_BY_THE_FORM) {
    delete merged[chave];
  }
  return { ...merged, ...doFormulario };
}
