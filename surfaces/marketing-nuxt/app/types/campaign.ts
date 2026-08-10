// Contrato do Marketing — espelha `shopman/backstage/projections/marketing.py`.
// Chaves em inglês (convenção de projection); rótulos ficam na apresentação.

export interface PlatformResult {
  platform: string;
  label: string;
  status: "published" | "pending_manual" | "failed" | "queued" | string;
  detail: string;
  url: string;
}

export interface Announcement {
  pk: number;
  status: string;
  status_label: string;
  body: string;
  image_url: string;
  hashtags: string[];
  link: string;
  platforms: string[];
  audience: Record<string, number>;
  audience_total: number;
  platform_results: PlatformResult[];
  trigger: string;
  trigger_label: string;
  rule_name: string;
  template_name: string;
  sku: string;
  created_at: string;
  expires_at: string;
  /** -1 = não expira; 0 = o prazo já passou. */
  expires_in_minutes: number;
  published_at: string;
  approved_by: string;
  /** Quem recusou, e por quê. Vazios em tudo que não foi recusado. */
  rejected_by: string;
  rejected_reason: string;
}

export interface CampaignStats {
  pending_count: number;
  published_today: number;
  audience_reached_today: number;
  failed_today: number;
}

/** O que impede ou limita a entrega de UMA plataforma, visto antes de publicar.
 *
 *  `blocking` separa dois estados que não podem parecer iguais: bloqueio (nada sai por
 *  ali) e limitação (sai, mas não para todo mundo).
 */
export interface ReachLimit {
  code: string;
  platform: string;
  platform_label: string;
  title: string;
  detail: string;
  action: string;
  blocking: boolean;
}

export interface CampaignBoard {
  pending: Announcement[];
  recent: Announcement[];
  stats: CampaignStats;
  reach_limits: ReachLimit[];
  /** Credencial de IA presente neste ambiente. */
  ai_assist_available: boolean;
}

export interface Campaign {
  pk: number;
  name: string;
  trigger: string;
  trigger_label: string;
  trigger_filter: Record<string, unknown>;
  template_id: number;
  template_name: string;
  platforms: string[];
  audience_rules: AudienceRules;
  /** `ref` da oferta anunciada. Vazio = campanha sem desconto atrás. */
  promotion_ref: string;
  schedule: Record<string, unknown>;
  /** Frase pronta do agendamento — decidida no servidor, nunca reinterpretada aqui. */
  schedule_label: string;
  /** Cria a ocasião sozinho (`once`/`recurring`), em vez de só adiar um evento. */
  fires_on_its_own: boolean;
  /** Dispara sozinho, mas já não tem próxima ocasião: data passada ou período findo. */
  exhausted: boolean;
  requires_approval: boolean;
  expires_after_minutes: number;
  is_active: boolean;
}

export interface AudienceRules {
  favorites?: boolean;
  alerts?: boolean;
  bought_within_days?: number;
  vip_first_minutes?: number;
}

export interface AnnouncementTemplate {
  pk: number;
  name: string;
  body: string;
  variables: string[];
  use_ai_generation: boolean;
  image_source: string;
  is_active: boolean;
}

export interface Choice {
  value: string;
  label: string;
}

export interface CampaignOptions {
  triggers: Choice[];
  platforms: Choice[];
  templates: AnnouncementTemplate[];
  variables: string[];
  /** Vocabulário de público — vem do backend para a tela nunca oferecer o que o
   *  resolvedor não conhece. */
  customer_groups: Choice[];
  rfm_segments: Choice[];
  /** Ofertas vivas que MONTAM sacola. O servidor já tirou as que valem para tudo:
   *  oferecê-las daria ao gestor um botão que promete o que não cumpre. */
  offers: Choice[];
}

/** Público escolhido para UM disparo. Não altera a campanha salva. */
export interface ChosenAudience {
  groups?: string[];
  rfm_segments?: string[];
  churn_risk_min?: number;
  birthday_today?: boolean;
  bought_skus?: string[];
  bought_collections?: string[];
  bought_within_days?: number;
  vip_first_minutes?: number;
}

/** Templates aprovados da plataforma + o escolhido agora. */
export interface WhatsAppTemplateResponse {
  current: string;
  available: { ns: string; name: string }[];
  /** `false` = não foi possível consultar a plataforma (≠ "não há template"). */
  can_list: boolean;
  configured: boolean;
}

export interface BoardResponse {
  board: CampaignBoard;
}

export interface RulesResponse {
  rules: Campaign[];
}

export interface OptionsResponse {
  options: CampaignOptions;
}

export interface HistoryResponse {
  announcements: Announcement[];
}

/** Edições do card enviadas junto com a aprovação. */
export interface AnnouncementEdits {
  body?: string;
  hashtags?: string[];
  platforms?: string[];
  image_url?: string;
  publish_at?: string;
}
