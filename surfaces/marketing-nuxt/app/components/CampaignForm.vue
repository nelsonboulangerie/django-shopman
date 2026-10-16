<script setup lang="ts">
// Formulário de campanha — "que evento vira o quê, para quem, onde".
//
// Apresentacional: o pai é dono do fetch e da escrita; aqui mora só o estado do
// formulário. O vocabulário (gatilhos, plataformas, modelos) vem do backend,
// nunca hardcoded — gatilho novo no domínio aparece aqui sem deploy de front.
import type {
  AudienceRules,
  Campaign,
  Choice,
  AnnouncementTemplate,
  MarketingPlatformCapability,
} from "~/types/campaign";
import { useMarketingDraft } from "~/composables/useMarketingDraft";
import {
  audienceRulesSummary,
  choiceLabels,
  platformsSummary,
} from "~/presentation/campaign";
import {
  platformReadinessNote,
  readinessByPlatform,
  readinessStatusClass,
} from "~/presentation/platformReadiness";
import type { PlatformReadiness } from "~/presentation/platformReadiness";
import type { MarketingDraftPayload } from "~/utils/marketingDraft";
import {
  resolveScheduleInput,
  scheduleSummary,
} from "~/utils/marketingSchedule";
import type { ScheduleFold } from "~/utils/marketingSchedule";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

const props = defineProps<{
  rule: Campaign | null; // null = criando
  triggers: Choice[];
  platformOptions: Choice[];
  templates: AnnouncementTemplate[];
  offers: Choice[];
  priceTiers?: Choice[];
  tags?: Choice[];
  rfmSegments?: Choice[];
  /** Rótulos de plataforma e template do WhatsApp: a prévia precisa dos dois para não
   *  prometer o que o envio não faz. */
  platformLabels: Record<string, string>;
  /** Allow-list executável projetada pelo servidor. O composer usa apenas esta
   *  lista; o catálogo teórico de providers nunca vira opção de disparo. */
  deliveryCapabilities?: MarketingPlatformCapability[];
  /** Estado e motivo por plataforma (`/marketing/platforms/`). Ausente = tudo pronto.
   *  Sinaliza a opção e explica, ANTES do clique, onde a campanha não vai sair. */
  platformReadiness?: PlatformReadiness[];
  whatsappTemplate?: string;
  busy?: boolean;
  draftOwner?: string;
  shopTimezone?: string;
  /** Oferta escolhida antes de abrir uma campanha nova (atalho da V2). */
  initialPromotionRef?: string;
}>();

const emit = defineEmits<{
  submit: [payload: Record<string, unknown>];
  cancel: [];
}>();

const name = ref("");
const trigger = ref("");
const templateId = ref<number | null>(null);
const platforms = ref<string[]>([]);
const requiresApproval = ref(true);
const expiresAfterMinutes = ref(0);
// A oferta que a campanha anuncia. Vazio = a campanha só conta uma novidade.
const promotionRef = ref("");
const isActive = ref(true);
const baseAudienceRules = ref<Record<string, unknown>>({});
const baseSchedule = ref<Record<string, unknown>>({});
const currentStep = ref(0);

const COMPOSER_STEPS = [
  { label: "Objetivo", hint: "Dê nome e escolha o que inicia a campanha." },
  { label: "Destinos", hint: "Escolha onde cada consequência acontecerá." },
  { label: "Conteúdo", hint: "Confira o modelo, a oferta e as composições." },
  { label: "Público e momento", hint: "Defina público, horário e revisão." },
  { label: "Revisar", hint: "Confira o que será salvo antes de criar." },
] as const;

// Audiência: toggles simples em cima do JSON que o serviço lê.
// Agendamento que DISPARA — só existe com o gatilho "agendado", porque nos outros a
// causa é o evento e este bloco não teria o que responder. O JSON montado aqui é o
// mesmo que `services/campaign_schedule.py` lê; o servidor recusa o par impossível.
const scheduleKind = ref<"once" | "recurring">("recurring");
const onceAt = ref("");
const onceFold = ref<ScheduleFold>("");
const fireAt = ref("07:00");
const weekdays = ref<number[]>([]);
const startsOn = ref("");
const endsOn = ref("");
const extraWindows = ref<string[][]>([]);
const scheduleTouched = ref(false);

const WEEKDAY_LABELS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]; // 0 = segunda

const schedules = computed(() => trigger.value === "schedule");

const favorites = ref(false);
const alerts = ref(false);
const boughtOn = ref(false);
const boughtDays = ref(90);
const vipFirstMinutes = ref(0);
const preferredHourWindowHours = ref(0);
const audienceMatch = ref<"any" | "all">("any");
const selectedPriceTiers = ref<string[]>([]);
const selectedTags = ref<string[]>([]);
const selectedRfmSegments = ref<string[]>([]);
const churnRiskOn = ref(false);
const churnRiskMin = ref(0.7);
const birthdayToday = ref(false);

const PRODUCT_AUDIENCE_ITEMS: Array<Choice & { hint?: string }> = [
  { value: "favorites", label: "Quem favoritou o produto" },
  {
    value: "alerts",
    label: 'Quem pediu "me avise" deste produto',
    hint: "A fila do sino da loja: lote para pão, reposição para o resto.",
  },
];
const productAudience = computed<string[]>({
  get: () => [
    ...(favorites.value ? ["favorites"] : []),
    ...(alerts.value ? ["alerts"] : []),
  ],
  set: (next) => {
    favorites.value = next.includes("favorites");
    alerts.value = next.includes("alerts");
  },
});

const MANAGED_AUDIENCE_KEYS = new Set([
  "alerts",
  "birthday_today",
  "bought_within_days",
  "churn_risk_min",
  "favorites",
  "match",
  "preferred_hour_window_hours",
  "price_tiers",
  "rfm_segments",
  "tags",
  "vip_first_minutes",
]);

const DRAFT_LABELS = {
  name: "Nome",
  trigger: "Gatilho",
  template_id: "Modelo",
  platforms: "Plataformas",
  requires_approval: "Revisão antes de publicar",
  expires_after_minutes: "Prazo de revisão",
  promotion_ref: "Oferta",
  is_active: "Campanha ligada",
  schedule: "Agendamento",
  audience_rules: "Público",
};

// ⚠️ A tela imprimia a CHAVE do JSON ("collections, skus", "bought_skus") quando
// avisava que um filtro salvo seria preservado. Chave é contrato com o servidor,
// não vocabulário do gestor: aqui vira rótulo; chave que o formulário não conhece
// vira contagem, nunca texto em inglês.
const TRIGGER_FILTER_LABELS: Record<string, string> = {
  collections: "coleções",
  skus: "produtos",
  quality_min: "qualidade mínima do lote",
  quality_min_share: "parcela mínima na qualidade",
  max_remaining: "estoque máximo restante",
};
const PRESERVED_AUDIENCE_LABELS: Record<string, string> = {
  bought_skus: "produtos comprados",
  bought_collections: "coleções compradas",
};

/** "coleções, produtos" — ou "coleções e mais 1 critério" quando a chave é nova. */
function preservedSummary(
  keys: string[],
  labels: Record<string, string>,
): string {
  const named = keys.flatMap((key) => (labels[key] ? [labels[key]] : []));
  const unknown = keys.length - named.length;
  const rest = unknown
    ? `${unknown} ${unknown === 1 ? "critério" : "critérios"}`
    : "";
  if (!named.length) return rest;
  return rest ? `${named.join(", ")} e mais ${rest}` : named.join(", ");
}

const audienceLabels = computed(() => ({
  priceTiers: choiceLabels(props.priceTiers ?? []),
  tags: choiceLabels(props.tags ?? []),
  segments: choiceLabels(props.rfmSegments ?? []),
}));

/** Frase de um agendamento salvo, para o aviso de conflito do rascunho. */
function scheduleDraftSummary(schedule: Record<string, unknown>): string {
  if (schedule.type === "once" && typeof schedule.at === "string") {
    return scheduleSummary(schedule.at, timezoneName.value) || "uma vez";
  }
  const windows = Array.isArray(schedule.windows)
    ? schedule.windows
        .filter(Array.isArray)
        .map((window) => String(window[0]))
        .join(", ")
    : "";
  const days = Array.isArray(schedule.weekdays)
    ? schedule.weekdays
        .map((day) => WEEKDAY_LABELS[Number(day)])
        .filter(Boolean)
        .join(", ")
    : "";
  if (!windows) return "sem horário definido";
  return days ? `${days} às ${windows}` : `todo dia às ${windows}`;
}

// Prontidão por plataforma: a opção ganha cor e palavra, e a escolhida que não
// publica ganha a frase completa embaixo — antes do clique, não depois de aprovar.
const readinessMap = computed(() =>
  readinessByPlatform(props.platformReadiness),
);
function readinessNote(option: Choice) {
  return platformReadinessNote(readinessMap.value[option.value], option.label);
}
const selectedReadinessNotes = computed(() =>
  props.platformOptions
    .filter((option) => platforms.value.includes(option.value))
    .map((option) => ({ platform: option.value, ...readinessNote(option) }))
    .filter((note) => note.tone !== "ready"),
);
const platformChoiceItems = computed(() =>
  props.platformOptions.map((option) => ({
    ...option,
    "data-readiness": readinessNote(option).tone,
  })),
);

/** O aviso de conflito pede uma frase, não JSON: o formulário é quem sabe ler o campo. */
function describeDraftValue(field: string, value: unknown): string | undefined {
  if (field === "platforms" && Array.isArray(value)) {
    return platformsSummary(value.map(String), props.platformLabels);
  }
  if (field === "audience_rules" && value && typeof value === "object") {
    return audienceRulesSummary(value as AudienceRules, audienceLabels.value);
  }
  if (field === "schedule" && value && typeof value === "object") {
    return scheduleDraftSummary(value as Record<string, unknown>);
  }
  return undefined;
}

function cloneRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

// Estado novo a cada campanha aberta — senão o formulário herdaria a anterior.
watch(
  () => props.rule?.pk ?? null,
  () => {
    const rule = props.rule;
    const audience: AudienceRules = rule?.audience_rules ?? {};
    baseAudienceRules.value = cloneRecord(audience);

    name.value = rule?.name ?? "";
    trigger.value = rule?.trigger ?? props.triggers[0]?.value ?? "";
    templateId.value = rule?.template_id ?? props.templates[0]?.pk ?? null;
    platforms.value = [...(rule?.platforms ?? [])];
    requiresApproval.value = rule?.requires_approval ?? true;
    expiresAfterMinutes.value = rule?.expires_after_minutes ?? 0;
    promotionRef.value = rule?.promotion_ref ?? props.initialPromotionRef ?? "";
    isActive.value = rule?.is_active ?? true;
    currentStep.value = 0;

    const schedule = (rule?.schedule ?? {}) as Record<string, unknown>;
    baseSchedule.value = cloneRecord(schedule);
    scheduleKind.value = schedule.type === "once" ? "once" : "recurring";
    onceAt.value =
      typeof schedule.at === "string" ? schedule.at.slice(0, 16) : "";
    onceFold.value = "";
    const firstWindow = Array.isArray(schedule.windows)
      ? schedule.windows[0]
      : null;
    fireAt.value = Array.isArray(firstWindow)
      ? String(firstWindow[0])
      : "07:00";
    extraWindows.value = Array.isArray(schedule.windows)
      ? schedule.windows
          .slice(1)
          .filter(Array.isArray)
          .map((window) => window.map(String))
      : [];
    weekdays.value = Array.isArray(schedule.weekdays)
      ? schedule.weekdays.map(Number)
      : [];
    startsOn.value =
      typeof schedule.starts_on === "string" ? schedule.starts_on : "";
    endsOn.value = typeof schedule.ends_on === "string" ? schedule.ends_on : "";

    favorites.value = Boolean(audience.favorites);
    alerts.value = Boolean(audience.alerts);
    boughtOn.value = Boolean(audience.bought_within_days);
    boughtDays.value = audience.bought_within_days || 90;
    vipFirstMinutes.value = audience.vip_first_minutes || 0;
    preferredHourWindowHours.value = audience.preferred_hour_window_hours || 0;
    audienceMatch.value = audience.match === "all" ? "all" : "any";
    selectedPriceTiers.value = stringList(audience.price_tiers);
    selectedTags.value = stringList(audience.tags);
    selectedRfmSegments.value = stringList(audience.rfm_segments);
    churnRiskOn.value = Number(audience.churn_risk_min || 0) > 0;
    churnRiskMin.value = Number(audience.churn_risk_min || 0.7);
    birthdayToday.value = Boolean(audience.birthday_today);
    scheduleTouched.value = false;
  },
  { immediate: true },
);

const timezoneName = computed(() => props.shopTimezone || "UTC");
const onceResolution = computed(() =>
  resolveScheduleInput({
    localValue: onceAt.value,
    timeZone: timezoneName.value,
    fold: onceFold.value,
  }),
);
const dateRangeValid = computed(
  () => !startsOn.value || !endsOn.value || startsOn.value <= endsOn.value,
);
const recurrencePeriod = computed({
  get: () => ({ start: startsOn.value, end: endsOn.value }),
  set: (next: { start?: string; end?: string }) => {
    startsOn.value = next.start ?? "";
    endsOn.value = next.end ?? "";
    scheduleTouched.value = true;
  },
});

const canSubmit = computed(
  () =>
    !props.busy &&
    name.value.trim().length > 0 &&
    trigger.value !== "" &&
    templateId.value !== null &&
    platforms.value.length > 0 &&
    (!schedules.value || scheduleReady.value),
);

const stepReady = computed(() => [
  name.value.trim().length > 0 && trigger.value !== "",
  platforms.value.length > 0,
  templateId.value !== null,
  !schedules.value || scheduleReady.value,
  canSubmit.value,
]);

function stepEnabled(index: number): boolean {
  return index === 0 || stepReady.value.slice(0, index).every(Boolean);
}

const stepperItems = computed(() =>
  COMPOSER_STEPS.map((step, index) => ({
    title: step.label,
    description: step.hint,
    disabled: !stepEnabled(index),
  })),
);

function goToStep(index: number) {
  if (index < 0 || index >= COMPOSER_STEPS.length || !stepEnabled(index))
    return;
  currentStep.value = index;
}

function nextStep() {
  if (!stepReady.value[currentStep.value]) return;
  goToStep(Math.min(currentStep.value + 1, COMPOSER_STEPS.length - 1));
}

const scheduleReady = computed(() =>
  scheduleKind.value === "once"
    ? onceAt.value !== "" &&
      (Boolean(props.rule && !scheduleTouched.value) || onceResolution.value.ok)
    : fireAt.value !== "" && dateRangeValid.value,
);

function buildSchedule(): Record<string, unknown> {
  if (
    props.rule &&
    Object.keys(baseSchedule.value).length > 0 &&
    !scheduleTouched.value &&
    props.rule.trigger === trigger.value
  ) {
    return cloneRecord(baseSchedule.value);
  }
  const preserved = cloneRecord(baseSchedule.value);
  for (const key of [
    "type",
    "at",
    "windows",
    "weekdays",
    "starts_on",
    "ends_on",
    "timezone",
  ]) {
    Reflect.deleteProperty(preserved, key);
  }
  if (scheduleKind.value === "once") {
    return {
      ...preserved,
      type: "once",
      at: onceResolution.value.candidate?.instant ?? onceAt.value,
      timezone: timezoneName.value,
    };
  }
  // O fim da janela é inerte para quem dispara (só o início vira ocasião), mas o
  // formato exige o par — daí uma hora depois, sem inventar significado nenhum.
  // `?? 0` porque um `<input type="time">` pode chegar vazio: sem isso o fim virava
  // "NaN:NaN", o servidor descartava a janela e a campanha nunca disparava — em silêncio.
  const [rawHour, rawMinute] = fireAt.value.split(":");
  const hour = Number(rawHour) || 0;
  const minute = Number(rawMinute) || 0;
  const end = `${String((hour + 1) % 24).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  return {
    ...preserved,
    type: "recurring",
    timezone: timezoneName.value,
    windows: [[fireAt.value, end], ...extraWindows.value],
    // Vazio = a semana toda, igual ao servidor. Não mandamos os 7 dias à mão.
    ...(weekdays.value.length > 0
      ? { weekdays: [...weekdays.value].sort() }
      : {}),
    ...(startsOn.value ? { starts_on: startsOn.value } : {}),
    ...(endsOn.value ? { ends_on: endsOn.value } : {}),
  };
}

function sameStringSet(left: string[], value: unknown): boolean {
  const right = stringList(value);
  return (
    [...new Set(left)].sort().join("\u0000") ===
    [...new Set(right)].sort().join("\u0000")
  );
}

function updateBoolean(
  result: Record<string, unknown>,
  key: string,
  value: boolean,
) {
  if (value === Boolean(baseAudienceRules.value[key])) return;
  if (value) result[key] = true;
  else Reflect.deleteProperty(result, key);
}

function updateNumber(
  result: Record<string, unknown>,
  key: string,
  value: number,
  include: boolean,
) {
  const before = Number(baseAudienceRules.value[key] || 0);
  const after = include ? Number(value) : 0;
  if (before === after) return;
  if (include) result[key] = after;
  else Reflect.deleteProperty(result, key);
}

function updateList(
  result: Record<string, unknown>,
  key: string,
  value: string[],
) {
  if (sameStringSet(value, baseAudienceRules.value[key])) return;
  if (value.length) result[key] = [...value];
  else Reflect.deleteProperty(result, key);
}

function buildAudienceRules(): Record<string, unknown> {
  const result = cloneRecord(baseAudienceRules.value);
  updateBoolean(result, "favorites", favorites.value);
  updateBoolean(result, "alerts", alerts.value);
  updateBoolean(result, "birthday_today", birthdayToday.value);
  updateNumber(result, "bought_within_days", boughtDays.value, boughtOn.value);
  updateNumber(
    result,
    "vip_first_minutes",
    vipFirstMinutes.value,
    vipFirstMinutes.value > 0,
  );
  updateNumber(
    result,
    "preferred_hour_window_hours",
    preferredHourWindowHours.value,
    preferredHourWindowHours.value > 0,
  );
  updateNumber(result, "churn_risk_min", churnRiskMin.value, churnRiskOn.value);
  updateList(result, "price_tiers", selectedPriceTiers.value);
  updateList(result, "tags", selectedTags.value);
  updateList(result, "rfm_segments", selectedRfmSegments.value);
  const originalMatch = baseAudienceRules.value.match === "all" ? "all" : "any";
  if (audienceMatch.value !== originalMatch) {
    if (audienceMatch.value === "all") result.match = "all";
    else delete result.match;
  }
  return result;
}

const preservedAudienceKeys = computed(() =>
  Object.keys(baseAudienceRules.value).filter(
    (key) => !MANAGED_AUDIENCE_KEYS.has(key),
  ),
);

const preservedTriggerFilterKeys = computed(() =>
  Object.keys(props.rule?.trigger_filter ?? {}),
);

function chooseScheduleKind(value: "once" | "recurring") {
  scheduleTouched.value = true;
  scheduleKind.value = value;
}

function eventScheduleAfterTriggerChange(): Record<string, unknown> {
  const preserved = cloneRecord(baseSchedule.value);
  for (const key of [
    "type",
    "at",
    "windows",
    "weekdays",
    "starts_on",
    "ends_on",
    "timezone",
  ]) {
    Reflect.deleteProperty(preserved, key);
  }
  return { ...preserved, type: "immediate" };
}

function campaignPayload(): MarketingDraftPayload {
  const payload: MarketingDraftPayload = {
    name: name.value,
    trigger: trigger.value,
    template_id: templateId.value,
    platforms: [...platforms.value],
    requires_approval: requiresApproval.value,
    expires_after_minutes: expiresAfterMinutes.value,
    promotion_ref: promotionRef.value,
    is_active: isActive.value,
    ...(schedules.value ? { schedule: buildSchedule() } : {}),
    audience_rules: buildAudienceRules(),
  };
  if (props.rule?.trigger === "schedule" && !schedules.value) {
    payload.schedule = eventScheduleAfterTriggerChange();
  }
  return payload;
}

function campaignBase(): MarketingDraftPayload {
  const rule = props.rule;
  if (!rule) {
    const defaultTrigger = props.triggers[0]?.value ?? "";
    return {
      name: "",
      trigger: defaultTrigger,
      template_id: props.templates[0]?.pk ?? null,
      platforms: [],
      requires_approval: true,
      expires_after_minutes: 0,
      promotion_ref: "",
      is_active: true,
      ...(defaultTrigger === "schedule"
        ? {
            schedule: {
              type: "recurring",
              timezone: timezoneName.value,
              windows: [["07:00", "08:00"]],
            },
          }
        : {}),
      audience_rules: {},
    };
  }
  return {
    name: rule.name,
    trigger: rule.trigger,
    template_id: rule.template_id,
    platforms: [...rule.platforms],
    requires_approval: rule.requires_approval,
    expires_after_minutes: rule.expires_after_minutes,
    promotion_ref: rule.promotion_ref ?? "",
    is_active: rule.is_active,
    ...(rule.trigger === "schedule"
      ? { schedule: cloneRecord(rule.schedule) }
      : {}),
    audience_rules: cloneRecord(rule.audience_rules),
  };
}

function applyCampaignDraft(payload: MarketingDraftPayload) {
  name.value = typeof payload.name === "string" ? payload.name : "";
  trigger.value = typeof payload.trigger === "string" ? payload.trigger : "";
  templateId.value =
    typeof payload.template_id === "number" ? payload.template_id : null;
  platforms.value = Array.isArray(payload.platforms)
    ? payload.platforms.map(String)
    : [];
  requiresApproval.value = payload.requires_approval !== false;
  expiresAfterMinutes.value = Number(payload.expires_after_minutes || 0);
  promotionRef.value =
    typeof payload.promotion_ref === "string" ? payload.promotion_ref : "";
  isActive.value = payload.is_active !== false;

  const audience = cloneRecord(payload.audience_rules);
  baseAudienceRules.value = audience;
  favorites.value = Boolean(audience.favorites);
  alerts.value = Boolean(audience.alerts);
  boughtOn.value = Boolean(audience.bought_within_days);
  boughtDays.value = Number(audience.bought_within_days || 90);
  vipFirstMinutes.value = Number(audience.vip_first_minutes || 0);
  preferredHourWindowHours.value = Number(
    audience.preferred_hour_window_hours || 0,
  );
  audienceMatch.value = audience.match === "all" ? "all" : "any";
  selectedPriceTiers.value = stringList(audience.price_tiers);
  selectedTags.value = stringList(audience.tags);
  selectedRfmSegments.value = stringList(audience.rfm_segments);
  churnRiskOn.value = Number(audience.churn_risk_min || 0) > 0;
  churnRiskMin.value = Number(audience.churn_risk_min || 0.7);
  birthdayToday.value = Boolean(audience.birthday_today);

  const schedule = payload.schedule
    ? cloneRecord(payload.schedule)
    : cloneRecord(props.rule?.schedule);
  baseSchedule.value = schedule;
  scheduleKind.value = schedule.type === "once" ? "once" : "recurring";
  onceAt.value =
    typeof schedule.at === "string" ? schedule.at.slice(0, 16) : "";
  onceFold.value = "";
  const firstWindow = Array.isArray(schedule.windows)
    ? schedule.windows[0]
    : null;
  fireAt.value = Array.isArray(firstWindow) ? String(firstWindow[0]) : "07:00";
  extraWindows.value = Array.isArray(schedule.windows)
    ? schedule.windows
        .slice(1)
        .filter(Array.isArray)
        .map((window) => window.map(String))
    : [];
  weekdays.value = Array.isArray(schedule.weekdays)
    ? schedule.weekdays.map(Number)
    : [];
  startsOn.value =
    typeof schedule.starts_on === "string" ? schedule.starts_on : "";
  endsOn.value = typeof schedule.ends_on === "string" ? schedule.ends_on : "";
  scheduleTouched.value = false;
}

const draft = useMarketingDraft({
  owner: () => props.draftOwner ?? "",
  resource: () => `campaign:${props.rule?.pk ?? "new"}`,
  version: () => props.rule?.updated_at ?? "new",
  base: campaignBase,
  current: campaignPayload,
  apply: applyCampaignDraft,
});

/** O texto do modelo escolhido — é ele que a prévia resolve. */
const chosenBody = computed(
  () => props.templates.find((t) => t.pk === templateId.value)?.body ?? "",
);

/** Overrides editoriais exatos usados pelo resolver de cada plataforma. */
const chosenPlatformVariants = computed(
  () =>
    props.templates.find((t) => t.pk === templateId.value)?.platform_variants ??
    {},
);

/** O modelo escolhido oferece uma sugestão separada durante a revisão? */
const chosenUsesAi = computed(
  () =>
    props.templates.find((t) => t.pk === templateId.value)?.use_ai_generation ??
    false,
);

const selectedTemplate = computed(
  () =>
    props.templates.find((template) => template.pk === templateId.value) ??
    null,
);

const templateOptions = computed(() =>
  props.templates.map((template) => ({
    value: template.pk,
    label: template.name,
    keywords: `${template.pk} ${template.body}`,
  })),
);

const offerOptions = computed(() => [
  {
    value: "",
    label: "Nenhuma (só contar a novidade)",
  },
  ...props.offers,
]);

const deliveryCapabilityMap = computed(() =>
  Object.fromEntries(
    (props.deliveryCapabilities ?? []).map((capability) => [
      capability.platform,
      capability,
    ]),
  ),
);

/** O formato efetivo do modelo, limitado ao que o domínio realmente despacha. */
const compositionRows = computed(() =>
  platforms.value.map((platform) => {
    const capability = deliveryCapabilityMap.value[platform];
    const requested = String(
      chosenPlatformVariants.value[platform]?.publication_format ||
        capability?.default_format ||
        "",
    );
    const format = capability?.formats.find((item) => item.ref === requested);
    return {
      platform,
      platformLabel:
        props.platformLabels[platform] ?? capability?.label ?? platform,
      deliveryLabel:
        capability?.delivery_kind === "direct_message"
          ? "Mensagem direta"
          : "Publicação pública",
      formatLabel: format?.label ?? "Formato definido pela plataforma",
    };
  }),
);

const selectedTriggerLabel = computed(
  () =>
    props.triggers.find((item) => item.value === trigger.value)?.label ??
    trigger.value,
);
const selectedOfferLabel = computed(
  () =>
    props.offers.find((item) => item.value === promotionRef.value)?.label ??
    "Sem oferta",
);
const reviewAudience = computed(() =>
  platforms.value.includes("whatsapp")
    ? audienceRulesSummary(
        buildAudienceRules() as AudienceRules,
        audienceLabels.value,
      )
    : "Público das contas selecionadas",
);

// As listas com busca (`NuxtSelectMenu`) devolvem o ITEM escolhido; o formulário
// guarda só o valor. Ler e gravar pelo item mantém o v-model honesto nos dois lados.
const selectedTemplateOption = computed(() =>
  templateOptions.value.find((option) => option.value === templateId.value),
);
function chooseTemplate(item: unknown) {
  const value =
    item && typeof item === "object"
      ? (item as { value: number }).value
      : item;
  templateId.value = typeof value === "number" ? value : null;
}
const selectedOfferOption = computed(() =>
  offerOptions.value.find((option) => option.value === promotionRef.value),
);
function chooseOffer(item: unknown) {
  const value =
    item && typeof item === "object" ? (item as Choice).value : item;
  promotionRef.value = String(value ?? "");
}

const SCHEDULE_KIND_ITEMS = [
  { label: "Toda semana", value: "recurring" },
  { label: "Uma vez", value: "once" },
];
const scheduleKindChoice = computed({
  get: () => scheduleKind.value,
  set: (next: string) =>
    chooseScheduleKind(next === "once" ? "once" : "recurring"),
});

const onceFoldItems = computed(() =>
  (onceResolution.value.candidates ?? []).map((candidate, index) => ({
    label: `${index === 0 ? "Primeira" : "Segunda"} ocorrência (UTC${candidate.offset})`,
    value: index === 0 ? "earlier" : "later",
  })),
);
const onceFoldChoice = computed({
  get: () => onceFold.value,
  set: (next: string) => {
    onceFold.value = next === "earlier" || next === "later" ? next : "";
  },
});

// O NuxtCheckboxGroup trabalha com valor em texto; o dia segue número no formulário.
const WEEKDAY_ITEMS = WEEKDAY_LABELS.map((label, day) => ({
  label,
  value: String(day),
}));
const weekdaysChoice = computed({
  get: () => weekdays.value.map(String),
  set: (next: string[]) => {
    scheduleTouched.value = true;
    weekdays.value = next.map(Number);
  },
});

const AUDIENCE_MATCH_ITEMS = [
  { label: "Atender a qualquer um", value: "any" },
  { label: "Atender a todos", value: "all" },
];

function submit() {
  if (!canSubmit.value) return;
  draft.flush();
  const payload = campaignPayload();
  payload.name = name.value.trim();
  emit("submit", payload);
}
</script>

<template>
  <NuxtForm
    :state="{ name, trigger, templateId, platforms }"
    class="mx-auto w-full max-w-5xl space-y-5"
    @submit="submit"
  >
    <DraftRecoveryNotice
      :state="draft.state.value"
      :saved-at="draft.savedAt.value"
      :conflicts="draft.conflicts.value"
      :labels="DRAFT_LABELS"
      :describe="describeDraftValue"
      @keep-local="draft.keepLocal()"
      @keep-server="draft.keepServer()"
      @discard="draft.discard()"
    />

    <!-- As cinco etapas. O título carrega o número para o leitor de tela ("2. Destinos")
         e some no celular, onde a frase da etapa atual vem logo abaixo. -->
    <div class="campaign-stepper">
      <NuxtStepper
        :model-value="currentStep"
        :items="stepperItems"
        :linear="false"
        size="sm"
        aria-label="Etapas da campanha"
        @update:model-value="goToStep(Number($event))"
      >
        <template #title="{ item }">
          <span class="sr-only"
            >{{ stepperItems.indexOf(item as never) + 1 }}. </span
          ><span class="max-sm:sr-only">{{ item.title }}</span>
        </template>
        <template #description="{ item }">
          <span class="max-sm:hidden">{{ item.description }}</span>
        </template>
      </NuxtStepper>
      <span class="sr-only" role="status" aria-live="polite">
        Etapa {{ currentStep + 1 }} de {{ COMPOSER_STEPS.length }}
      </span>
      <p class="mt-3 text-sm text-muted-foreground sm:hidden">
        <strong class="text-highlighted"
          >{{ currentStep + 1 }}. {{ COMPOSER_STEPS[currentStep]?.label }}.</strong
        >
        {{ COMPOSER_STEPS[currentStep]?.hint }}
      </p>
    </div>

    <NuxtFormField v-show="currentStep === 0" label="Nome da campanha">
      <NuxtInput
        id="rule-name"
        v-model="name"
        type="text"
        placeholder="Lote de pães → redes"
        class="w-full"
      />
    </NuxtFormField>

    <div
      v-show="currentStep === 0 || currentStep === 2"
      class="grid gap-4 sm:grid-cols-2"
    >
      <NuxtFormField v-show="currentStep === 0" label="Quando acontecer">
        <NuxtSelect
          id="rule-trigger"
          v-model="trigger"
          :items="triggers"
          placeholder="Escolha o que inicia a campanha"
          class="w-full"
        />
      </NuxtFormField>

      <div v-show="currentStep === 2" class="space-y-2">
        <NuxtFormField label="Usar o modelo">
          <NuxtSelectMenu
            id="rule-template"
            :model-value="selectedTemplateOption"
            :items="templateOptions"
            placeholder="Escolha o modelo"
            :search-input="{ placeholder: 'Buscar modelo' }"
            :filter-fields="['label', 'keywords']"
            class="w-full"
            @update:model-value="chooseTemplate"
          />
        </NuxtFormField>
        <NuxtAlert
          v-if="templates.length === 0"
          color="info"
          variant="subtle"
          title="Nenhum modelo cadastrado ainda."
          description="Crie o primeiro modelo antes de criar a campanha."
          :actions="alertActions('info', [
            {
              label: 'Criar o primeiro modelo',
              to: '/settings/templates',
              size: 'md',
            },
          ])"
        />
      </div>
    </div>

    <!-- A prévia mora ao lado da escolha do texto: é aqui que o gestor decide a frase, e é
         aqui que ele precisa ver a frase resolvida. -->
    <AnnouncementPreview
      v-if="templateId"
      v-show="currentStep === 2"
      :body="chosenBody"
      :platforms="platforms"
      :platform-labels="platformLabels"
      :platform-content="chosenPlatformVariants"
      :promotion-ref="promotionRef"
      :use-ai="chosenUsesAi"
      :whatsapp-template="whatsappTemplate"
    />

    <!-- A oferta que o anúncio leva. Quando escolhida, o {{link}} da mensagem aponta
         para a oferta e o clique monta a sacola com o preço resolvido NA HORA, e não no
         envio, que é quando o preço envelheceria. -->
    <NuxtFormField
      v-if="offers.length"
      v-show="currentStep === 2"
      label="Anunciar a oferta"
      description="Com oferta, quem toca no link já recebe a sacola montada."
    >
      <NuxtSelectMenu
        id="rule-offer"
        :model-value="selectedOfferOption"
        :items="offerOptions"
        placeholder="Escolha a oferta"
        :search-input="{ placeholder: 'Buscar oferta' }"
        class="w-full"
        @update:model-value="chooseOffer"
      />
    </NuxtFormField>

    <!-- Sem este bloco, "agendado" era escolhível e insatisfazível: o gestor salvava e
         a campanha nunca disparava. -->
    <NuxtCard v-if="schedules" v-show="currentStep === 3">
      <fieldset class="space-y-4">
        <legend class="mb-3 text-sm font-medium text-highlighted">
          Quando disparar
        </legend>

        <NuxtTabs
          v-model="scheduleKindChoice"
          :items="SCHEDULE_KIND_ITEMS"
          :content="false"
          variant="pill"
          aria-label="Frequência do disparo"
        />

        <div v-if="scheduleKind === 'once'" class="space-y-3">
          <NuxtFormField
            label="Dia e hora"
            :hint="timezoneName"
            description="Dispara uma única vez. Depois disso a campanha não volta sozinha."
            :error="
              scheduleTouched &&
              onceResolution.problem &&
              onceResolution.problem !== 'ambiguous'
                ? onceResolution.detail
                : undefined
            "
          >
            <UiDateTimeField
              id="rule-once-at"
              v-model="onceAt"
              label="Dia e hora do disparo"
              class="sm:max-w-md"
              @update:model-value="
                scheduleTouched = true;
                onceFold = '';
              "
            />
          </NuxtFormField>
          <template
            v-if="scheduleTouched && onceResolution.problem === 'ambiguous'"
          >
            <NuxtAlert
              color="warning"
              variant="subtle"
              title="Horário repetido pela mudança do relógio"
              :description="onceResolution.detail"
            />
            <NuxtRadioGroup
              v-model="onceFoldChoice"
              :items="onceFoldItems"
              legend="Qual das duas ocorrências"
              orientation="horizontal"
            />
          </template>
          <p
            v-if="
              scheduleTouched && onceResolution.ok && onceResolution.candidate
            "
            class="text-xs text-muted-foreground"
          >
            Instante exato:
            {{ scheduleSummary(onceResolution.candidate.instant, timezoneName) }}
            · UTC{{ onceResolution.candidate.offset }}.
          </p>
        </div>

        <div v-else class="space-y-4">
          <NuxtFormField label="Hora" :hint="timezoneName">
            <UiTimeField
              id="rule-fire-at"
              v-model="fireAt"
              label="Hora do disparo"
              class="w-32"
              @update:model-value="scheduleTouched = true"
            />
          </NuxtFormField>

          <!-- Os dias refluem para caber (o grupo quebra linha), em vez de o alvo de
               toque encolher: sete dias lado a lado não cabem numa tela de 320. -->
          <div>
            <NuxtCheckboxGroup
              v-model="weekdaysChoice"
              :items="WEEKDAY_ITEMS"
              legend="Nos dias"
              orientation="horizontal"
              variant="card"
            />
            <p class="mt-1 text-xs text-muted-foreground">
              Nenhum dia marcado quer dizer todos os dias.
            </p>
          </div>

          <NuxtFormField
            label="Período de veiculação (opcional)"
            description="Deixe o início ou o fim vazio quando a recorrência não tiver esse limite."
            :error="
              dateRangeValid
                ? undefined
                : 'A data final precisa ser igual ou posterior à data inicial.'
            "
          >
            <UiDateRangeField
              id="rule-period"
              v-model="recurrencePeriod"
              label="Período de veiculação da recorrência"
              class="max-w-full sm:max-w-md"
            />
          </NuxtFormField>
          <p v-if="extraWindows.length" class="text-xs text-muted-foreground">
            Horários adicionais preservados:
            {{ extraWindows.map((window) => window.join(" a ")).join(", ") }}.
          </p>
          <p class="text-xs text-muted-foreground">
            Horários em {{ timezoneName }}. Se o relógio pular esse horário,
            aquela data é ignorada; se repetir, a primeira ocorrência dispara uma
            única vez.
          </p>
        </div>
      </fieldset>
    </NuxtCard>

    <p
      v-if="!schedules && preservedTriggerFilterKeys.length"
      v-show="currentStep === 3"
      class="text-xs text-muted-foreground"
    >
      Os filtros do evento já salvos ({{
        preservedSummary(preservedTriggerFilterKeys, TRIGGER_FILTER_LABELS)
      }}) continuam valendo.
    </p>

    <div v-show="currentStep === 1" class="space-y-3">
      <!-- Uma pergunta, várias respostas: o grupo canônico assume fieldset, legenda,
           teclado e modelo. A variante `table` mantém cada destino como uma linha
           inteira de toque. -->
      <NuxtCheckboxGroup
        v-model="platforms"
        :items="platformChoiceItems"
        variant="table"
      >
        <template #legend>Disparado via</template>
        <template #label="{ item }">
          <span>{{ item.label }}</span>
          <span
            v-if="readinessNote(item as Choice).badge"
            class="ml-1.5 text-xs"
            :class="readinessStatusClass(readinessNote(item as Choice).tone)"
          >
            · {{ readinessNote(item as Choice).badge }}
          </span>
        </template>
      </NuxtCheckboxGroup>
      <!-- Prontidão é pré-condição de PUBLICAR, não de configurar: a campanha salva,
           mas o gestor sabe agora, e não depois de aprovar, onde ela não vai sair. O
           aviso leva aonde se resolve. -->
      <NuxtAlert
        v-for="note in selectedReadinessNotes"
        :key="note.platform"
        :color="note.tone === 'blocked' ? 'error' : 'warning'"
        variant="subtle"
        :title="note.text"
        :description="
          note.tone !== 'limited'
            ? 'A campanha pode ser salva assim mesmo.'
            : undefined
        "
        :actions="alertActions(note.tone === 'blocked' ? 'error' : 'warning',
          note.tone !== 'limited'
            ? [
                {
                  label: 'Ver em Plataformas',
                  to: { path: '/settings/platforms' },
                  size: 'md' as const,
                },
              ]
            : []
        )"
      />
      <p class="text-xs text-muted-foreground">
        Instagram, Facebook e Google criam uma postagem pública por plataforma.
        WhatsApp envia uma mensagem por pessoa elegível. Mensagens diretas do
        Instagram ainda não fazem parte deste app.
      </p>
    </div>

    <NuxtCard
      v-if="platforms.includes('whatsapp')"
      v-show="currentStep === 3"
    >
      <fieldset class="space-y-4">
        <legend class="mb-3 text-sm font-medium text-highlighted">
          Público alvo
        </legend>
        <!-- A fila de "me avise" cobre lote e reposição. As duas respostas formam uma
             pergunta única sobre sinais deste produto, então usam o grupo canônico. -->
        <NuxtCheckboxGroup
          v-model="productAudience"
          :items="PRODUCT_AUDIENCE_ITEMS"
          description-key="hint"
          legend="Sinais deste produto"
          variant="card"
        />
        <!-- ⚠️ O número e a UNIDADE são um grupo só (`inline-flex`): quebrar ENTRE o
             número e a unidade deixava o campo sem dizer de quê era o número. -->
        <div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
          <NuxtCheckbox v-model="boughtOn" label="Quem comprou nos últimos" />
          <span class="inline-flex items-center gap-2">
            <NuxtInputNumber
              v-model="boughtDays"
              :min="1"
              :max="365"
              :disabled="!boughtOn"
              aria-label="Dias de recompra"
              class="w-32"
            />
            <span :class="boughtOn ? '' : 'text-muted-foreground'">dias</span>
          </span>
        </div>
        <!-- D5: "(0 = todo mundo junto)" obrigava a decorar o que o campo faz vazio.
             A frase descreve o valor que ESTÁ na tela. -->
        <NuxtFormField
          label="VIPs recebem"
          :description="
            vipFirstMinutes > 0
              ? 'Os VIPs recebem primeiro; o restante da lista recebe depois desse intervalo.'
              : 'Todo mundo recebe junto.'
          "
        >
          <span class="inline-flex items-center gap-2 text-sm">
            <NuxtInputNumber
              id="rule-vip"
              v-model="vipFirstMinutes"
              :min="0"
              :max="120"
              class="w-32"
            />
            <span>minutos antes</span>
          </span>
        </NuxtFormField>

        <NuxtFormField label="Quando houver vários critérios">
          <NuxtSelect
            id="rule-audience-match"
            v-model="audienceMatch"
            :items="AUDIENCE_MATCH_ITEMS"
            class="min-w-56"
          />
        </NuxtFormField>

        <NuxtCheckboxGroup
          v-if="tags?.length"
          v-model="selectedTags"
          :items="tags"
          legend="Etiquetas"
          orientation="horizontal"
        />

        <NuxtCheckboxGroup
          v-if="priceTiers?.length"
          v-model="selectedPriceTiers"
          :items="priceTiers"
          orientation="horizontal"
        >
          <template #legend>Faixa de preço</template>
        </NuxtCheckboxGroup>

        <NuxtCheckboxGroup
          v-if="rfmSegments?.length"
          v-model="selectedRfmSegments"
          :items="rfmSegments"
          legend="Comportamento de compra"
          orientation="horizontal"
        />

        <NuxtCheckbox v-model="birthdayToday" label="Aniversariantes de hoje" />

        <!-- Este número não tem unidade (é uma fração de 0 a 1), então não há par
             para manter junto. -->
        <div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
          <NuxtCheckbox
            v-model="churnRiskOn"
            label="Risco de não voltar a partir de"
          />
          <NuxtInputNumber
            v-model="churnRiskMin"
            :min="0"
            :max="1"
            :step="0.05"
            :disabled="!churnRiskOn"
            aria-label="Risco mínimo de não voltar"
            class="w-32"
          />
        </div>

        <NuxtFormField
          label="Respeitar horário preferido em uma janela de"
          :description="
            preferredHourWindowHours > 0
              ? 'Quem costuma comprar dentro dessa janela recebe na hora de sempre; os demais recebem agora.'
              : 'O horário preferido de cada pessoa não é considerado: todos recebem agora.'
          "
        >
          <span class="inline-flex items-center gap-2 text-sm">
            <NuxtInputNumber
              id="rule-preferred-window"
              v-model="preferredHourWindowHours"
              :min="0"
              :max="12"
              class="w-32"
            />
            <span>horas</span>
          </span>
        </NuxtFormField>

        <p
          v-if="preservedAudienceKeys.length"
          class="text-xs text-muted-foreground"
        >
          Filtros de público já salvos ({{
            preservedSummary(preservedAudienceKeys, PRESERVED_AUDIENCE_LABELS)
          }}) continuam valendo, sem alteração.
        </p>
        <p class="text-xs text-muted-foreground">
          Só quem aceitou receber novidades entra na conta. Assinatura de alerta
          por produto já é um aceite daquele produto.
        </p>
      </fieldset>
    </NuxtCard>

    <p v-else v-show="currentStep === 3" class="text-xs text-muted-foreground">
      Estas publicações vão para o público geral das plataformas. A lista de
      contatos só é usada quando o WhatsApp está selecionado.
    </p>

    <div v-show="currentStep === 3" class="space-y-3">
      <NuxtCheckbox v-model="requiresApproval" label="Revisar antes de publicar" />
      <!-- ⚠️ "sai sozinho" não dizia o ato, e o ato depende do destino: mensagem se
           envia, postagem se publica, e o genérico dos dois é disparar. -->
      <NuxtAlert
        v-if="!requiresApproval"
        color="warning"
        variant="subtle"
        title="Sem revisão, o anúncio é disparado assim que o evento acontecer, sem passar por você."
      />
      <NuxtFormField
        label="O anúncio aguarda revisão por"
        :description="
          expiresAfterMinutes > 0
            ? 'Sem revisão até lá, o anúncio caduca e nada é disparado.'
            : 'O anúncio espera a revisão sem prazo: não caduca sozinho.'
        "
      >
        <span class="inline-flex items-center gap-2 text-sm">
          <NuxtInputNumber
            id="rule-expiry"
            v-model="expiresAfterMinutes"
            :min="0"
            :max="1440"
            class="w-32"
          />
          <span>minutos</span>
        </span>
      </NuxtFormField>
      <NuxtCheckbox v-model="isActive" label="Campanha ligada" />
    </div>

    <NuxtCard v-show="currentStep === 4" aria-labelledby="campaign-review-title">
      <div class="space-y-4">
        <div>
          <p class="text-xs font-semibold text-primary">5 · Revisar</p>
          <h3 id="campaign-review-title" class="mt-1 text-base font-semibold">
            {{ rule ? "Salvar esta campanha" : "Criar esta campanha" }}
          </h3>
          <p class="mt-1 text-sm text-muted-foreground">
            Cada destino é independente: uma falha em um não apaga nem duplica os
            demais.
          </p>
        </div>

        <dl class="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt class="text-xs text-muted-foreground">Objetivo interno</dt>
            <dd class="font-medium">{{ name || "Sem nome" }}</dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">Quando começa</dt>
            <dd class="font-medium">{{ selectedTriggerLabel }}</dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">Conteúdo</dt>
            <dd class="font-medium">
              {{ selectedTemplate?.name || "Sem modelo" }}
            </dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">Oferta</dt>
            <dd class="font-medium">{{ selectedOfferLabel }}</dd>
          </div>
          <div class="sm:col-span-2">
            <dt class="text-xs text-muted-foreground">Público</dt>
            <dd class="font-medium">{{ reviewAudience }}</dd>
          </div>
        </dl>

        <div>
          <p class="mb-2 text-xs font-medium text-muted-foreground">
            Composições que serão geradas
          </p>
          <ul class="space-y-2" data-testid="campaign-compositions">
            <li
              v-for="row in compositionRows"
              :key="row.platform"
              class="flex items-center justify-between gap-3 rounded-md bg-elevated px-3 py-2"
            >
              <span>
                <strong class="block text-sm">{{ row.platformLabel }}</strong>
                <small class="text-xs text-muted-foreground">{{
                  row.deliveryLabel
                }}</small>
              </span>
              <span class="text-right text-xs font-medium">{{
                row.formatLabel
              }}</span>
            </li>
          </ul>
        </div>

        <p class="text-xs text-muted-foreground">
          Aqui aparecem somente formatos que o Shopman já consegue despachar.
          Recursos apenas catalogados para o futuro não entram nesta campanha.
        </p>
      </div>
    </NuxtCard>

    <div class="flex flex-wrap items-center gap-2 border-t border-default pt-4">
      <NuxtButton
        label="Cancelar"
        color="neutral"
        variant="outline"
        @click="emit('cancel')"
      />
      <NuxtButton
        v-if="currentStep > 0"
        label="Voltar"
        color="neutral"
        variant="outline"
        @click="goToStep(currentStep - 1)"
      />
      <span class="min-w-0 flex-1 text-center text-xs text-muted-foreground">
        Etapa {{ currentStep + 1 }} de {{ COMPOSER_STEPS.length }}
      </span>
      <NuxtButton
        v-if="currentStep < COMPOSER_STEPS.length - 1"
        label="Continuar"
        :disabled="!stepReady[currentStep]"
        @click="nextStep"
      />
      <NuxtButton
        v-else
        type="submit"
        icon="i-lucide-check"
        :label="rule ? 'Salvar' : 'Criar campanha'"
        :loading="busy"
        :disabled="!canSubmit"
      />
    </div>
  </NuxtForm>
</template>

<style scoped>
/* O Reka embute "Step N of M" em inglês, sem opção de tradução; a etapa em pt-BR é o
   status logo abaixo do stepper. (A mesma saída do `UiStepper` do kit.) */
.campaign-stepper :deep([data-slot="root"] > [role="status"]) {
  display: none;
}
</style>
