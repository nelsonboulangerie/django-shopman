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
} from "~/types/campaign";
import { useMarketingDraft } from "~/composables/useMarketingDraft";
import type { MarketingDraftPayload } from "~/utils/marketingDraft";
import {
  resolveScheduleInput,
  scheduleSummary,
} from "~/utils/marketingSchedule";
import type { ScheduleFold } from "~/utils/marketingSchedule";

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
  whatsappTemplate?: string;
  busy?: boolean;
  draftOwner?: string;
  shopTimezone?: string;
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
  is_active: "Regra ativa",
  schedule: "Agendamento",
  audience_rules: "Público",
};

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
    promotionRef.value = rule?.promotion_ref ?? "";
    isActive.value = rule?.is_active ?? true;

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

const canSubmit = computed(
  () =>
    !props.busy &&
    name.value.trim().length > 0 &&
    trigger.value !== "" &&
    templateId.value !== null &&
    platforms.value.length > 0 &&
    (!schedules.value || scheduleReady.value),
);

const scheduleReady = computed(() =>
  scheduleKind.value === "once"
    ? onceAt.value !== "" &&
      (Boolean(props.rule && !scheduleTouched.value) || onceResolution.value.ok)
    : fireAt.value !== "" && dateRangeValid.value,
);

function toggleWeekday(day: number) {
  scheduleTouched.value = true;
  const index = weekdays.value.indexOf(day);
  if (index >= 0) weekdays.value.splice(index, 1);
  else weekdays.value.push(day);
}

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

function toggleChoice(target: string[], value: string) {
  const index = target.indexOf(value);
  if (index >= 0) target.splice(index, 1);
  else target.push(value);
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

function togglePlatform(value: string) {
  const index = platforms.value.indexOf(value);
  if (index >= 0) platforms.value.splice(index, 1);
  else platforms.value.push(value);
}

function submit() {
  if (!canSubmit.value) return;
  draft.flush();
  const payload = campaignPayload();
  payload.name = name.value.trim();
  emit("submit", payload);
}
</script>

<template>
  <form class="space-y-5" @submit.prevent="submit">
    <DraftRecoveryNotice
      :state="draft.state.value"
      :saved-at="draft.savedAt.value"
      :conflicts="draft.conflicts.value"
      :labels="DRAFT_LABELS"
      @keep-local="draft.keepLocal()"
      @keep-server="draft.keepServer()"
      @discard="draft.discard()"
    />
    <div>
      <label for="rule-name" class="mb-1 block text-xs font-medium text-muted-foreground"
        >Nome da campanha</label
      >
      <UiInput
        id="rule-name"
        v-model="name"
        type="text"
        placeholder="Fornada de pães → redes"
      />
    </div>

    <div class="grid gap-4 sm:grid-cols-2">
      <div>
        <label for="rule-trigger" class="mb-1 block text-xs font-medium text-muted-foreground"
          >Quando acontecer</label
        >
        <UiNativeSelect
          id="rule-trigger"
          v-model="trigger"
          class="w-full"
        >
          <option
            v-for="choice in triggers"
            :key="choice.value"
            :value="choice.value"
          >
            {{ choice.label }}
          </option>
        </UiNativeSelect>
      </div>

      <div>
        <label for="rule-template" class="mb-1 block text-xs font-medium text-muted-foreground"
          >Usar o modelo</label
        >
        <UiNativeSelect
          id="rule-template"
          v-model="templateId"
          class="w-full"
        >
          <option
            v-for="template in templates"
            :key="template.pk"
            :value="template.pk"
          >
            {{ template.name }}
          </option>
        </UiNativeSelect>
        <p
          v-if="templates.length === 0"
          class="mt-1 text-xs text-muted-foreground"
        >
          Nenhum modelo cadastrado ainda.
          <NuxtLink to="/templates" class="font-medium underline"
            >Crie o primeiro aqui</NuxtLink
          >
          antes de criar a campanha.
        </p>
      </div>
    </div>

    <!-- A prévia mora ao lado da escolha do texto: é aqui que o gestor decide a frase, e é
         aqui que ele precisa ver a frase resolvida. -->
    <AnnouncementPreview
      v-if="templateId"
      :body="chosenBody"
      :platforms="platforms"
      :platform-labels="platformLabels"
      :platform-content="chosenPlatformVariants"
      :promotion-ref="promotionRef"
      :use-ai="chosenUsesAi"
      :whatsapp-template="whatsappTemplate"
    />

    <!-- A oferta que o anúncio leva. Quando escolhida, o {{link}} da mensagem aponta
         para a oferta e o clique monta a sacola com o preço resolvido NA HORA — não no
         envio, que é quando o preço envelheceria. -->
    <div v-if="offers.length">
      <label for="rule-offer" class="mb-1 block text-xs font-medium text-muted-foreground"
        >Anunciar a oferta</label
      >
      <UiNativeSelect
        id="rule-offer"
        v-model="promotionRef"
        class="w-full"
      >
        <option value="">Nenhuma — só contar a novidade</option>
        <option v-for="offer in offers" :key="offer.value" :value="offer.value">
          {{ offer.label }}
        </option>
      </UiNativeSelect>
      <p class="mt-1 text-xs text-muted-foreground">
        Com oferta, quem toca no link já recebe a sacola montada.
      </p>
    </div>

    <!-- Sem este bloco, "agendado" era escolhível e insatisfazível: o gestor salvava e
         a campanha nunca disparava. -->
    <fieldset
      v-if="schedules"
      class="rounded-lg border border-border bg-card p-4"
    >
      <legend class="px-1 text-xs font-medium text-muted-foreground">Quando disparar</legend>

      <div class="flex gap-2">
        <!-- Segmentos nativos mantêm aria-pressed e a troca exclusiva sem fingir envio de formulário. -->
        <button
          v-for="option in [
            { value: 'recurring', label: 'Toda semana' },
            { value: 'once', label: 'Uma vez' },
          ]"
          :key="option.value"
          type="button"
          :aria-pressed="scheduleKind === option.value"
          class="rounded-md border px-3 py-1.5 text-sm font-medium transition"
          :class="
            scheduleKind === option.value
              ? 'border-primary bg-primary/10 text-primary'
              : 'border-border hover:bg-muted'
          "
          @click="chooseScheduleKind(option.value as 'once' | 'recurring')"
        >
          {{ option.label }}
        </button>
      </div>

      <div v-if="scheduleKind === 'once'" class="mt-3">
        <label for="rule-once-at" class="mb-1 block text-xs font-medium text-muted-foreground"
          >Dia e hora</label
        >
        <div class="flex flex-wrap items-center gap-2">
          <UiInput
            id="rule-once-at"
            v-model="onceAt"
            type="datetime-local"
            class="sm:w-64"
            @update:model-value="
              scheduleTouched = true;
              onceFold = '';
            "
          />
          <span class="text-xs font-semibold text-muted-foreground">{{
            timezoneName
          }}</span>
        </div>
        <p
          v-if="
            scheduleTouched &&
            onceResolution.problem &&
            onceResolution.problem !== 'ambiguous'
          "
          class="mt-1 text-xs text-destructive"
          role="alert"
        >
          {{ onceResolution.detail }}
        </p>
        <fieldset
          v-if="scheduleTouched && onceResolution.problem === 'ambiguous'"
          class="mt-2 rounded-md border border-warning/40 bg-warning/5 p-2"
        >
          <legend class="px-1 text-xs font-semibold">
            Horário repetido pela mudança do relógio
          </legend>
          <p class="text-xs text-muted-foreground">
            {{ onceResolution.detail }}
          </p>
          <div class="mt-1 flex flex-wrap gap-3 text-xs">
            <!-- Rádios nativos distinguem as duas ocorrências do mesmo horário ambíguo. -->
            <label
              v-for="(candidate, index) in onceResolution.candidates"
              :key="candidate.instant"
              class="flex items-center gap-1.5"
            >
              <input
                v-model="onceFold"
                type="radio"
                :value="index === 0 ? 'earlier' : 'later'"
              />
              {{ index === 0 ? "Primeira" : "Segunda" }} ocorrência (UTC{{
                candidate.offset
              }})
            </label>
          </div>
        </fieldset>
        <p
          v-if="
            scheduleTouched && onceResolution.ok && onceResolution.candidate
          "
          class="mt-1 text-xs text-muted-foreground"
        >
          Instante exato:
          {{
            scheduleSummary(onceResolution.candidate.instant, timezoneName)
          }}
          · UTC{{ onceResolution.candidate.offset }}.
        </p>
        <p class="mt-1 text-xs text-muted-foreground">
          Dispara uma única vez. Depois disso a campanha não volta sozinha.
        </p>
      </div>

      <div v-else class="mt-3 space-y-3">
        <div>
          <label for="rule-fire-at" class="mb-1 block text-xs font-medium text-muted-foreground"
            >Hora</label
          >
          <UiInput
            id="rule-fire-at"
            v-model="fireAt"
            type="time"
            class="w-28"
            @update:model-value="scheduleTouched = true"
          />
        </div>

        <div>
          <p class="mb-1 text-xs font-medium text-muted-foreground">Nos dias</p>
          <div class="flex flex-wrap gap-1.5">
            <!-- Botões de dia permanecem nativos para expor o estado múltiplo com aria-pressed. -->
            <button
              v-for="(label, day) in WEEKDAY_LABELS"
              :key="label"
              type="button"
              :aria-pressed="weekdays.includes(day)"
              class="rounded-md border px-2.5 py-1 text-xs font-medium capitalize transition"
              :class="
                weekdays.includes(day)
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border hover:bg-muted'
              "
              @click="toggleWeekday(day)"
            >
              {{ label }}
            </button>
          </div>
          <p class="mt-1 text-xs text-muted-foreground">
            Nenhum dia marcado quer dizer todos os dias.
          </p>
        </div>

        <div class="grid gap-3 sm:grid-cols-2">
          <div>
            <label for="rule-starts-on" class="mb-1 block text-xs font-medium text-muted-foreground">
              Começar em (opcional)
            </label>
            <UiInput
              id="rule-starts-on"
              v-model="startsOn"
              type="date"
              @update:model-value="scheduleTouched = true"
            />
          </div>
          <div>
            <label for="rule-ends-on" class="mb-1 block text-xs font-medium text-muted-foreground">
              Parar depois de (opcional)
            </label>
            <UiInput
              id="rule-ends-on"
              v-model="endsOn"
              type="date"
              @update:model-value="scheduleTouched = true"
            />
          </div>
        </div>
        <p v-if="extraWindows.length" class="text-xs text-muted-foreground">
          Horários adicionais preservados:
          {{ extraWindows.map((window) => window.join("–")).join(", ") }}.
        </p>
        <p v-if="!dateRangeValid" class="text-xs text-destructive" role="alert">
          A data final precisa ser igual ou posterior à data inicial.
        </p>
        <p class="text-xs text-muted-foreground">
          Horários em {{ timezoneName }}. Se o relógio pular esse horário,
          aquela data é ignorada; se repetir, a primeira ocorrência dispara uma
          única vez.
        </p>
      </div>
    </fieldset>

    <p
      v-if="!schedules && preservedTriggerFilterKeys.length"
      class="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
    >
      Os filtros do evento ({{ preservedTriggerFilterKeys.join(", ") }}) serão
      preservados.
    </p>

    <fieldset>
      <legend class="mb-1 text-xs font-medium text-muted-foreground">Entregar por</legend>
      <div class="flex flex-wrap gap-1.5">
        <!-- Checkboxes nativos sr-only preservam semântica enquanto as pílulas ampliam os alvos. -->
        <label
          v-for="option in platformOptions"
          :key="option.value"
          class="inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors"
          :class="
            platforms.includes(option.value)
              ? 'border-primary bg-primary/10 text-foreground'
              : 'border-border text-muted-foreground hover:bg-muted'
          "
        >
          <input
            type="checkbox"
            class="sr-only"
            :aria-label="option.label"
            :checked="platforms.includes(option.value)"
            @change="togglePlatform(option.value)"
          />
          {{ option.label }}
        </label>
      </div>
      <p class="mt-1.5 text-xs text-muted-foreground">
        Instagram, Facebook e Google criam uma publicação pública por plataforma.
        WhatsApp envia uma mensagem por pessoa elegível. Mensagens diretas do
        Instagram ainda não fazem parte deste app.
      </p>
    </fieldset>

    <fieldset class="rounded-lg border border-border p-3">
      <legend class="px-1 text-xs font-medium text-muted-foreground">Avisar quem</legend>
      <div class="space-y-2.5">
        <!-- Checkboxes permanecem nativos porque não há primitivo compartilhado de seleção binária. -->
        <label class="flex items-center gap-2 text-sm">
          <input
            v-model="favorites"
            type="checkbox"
            class="size-4 rounded border-border"
          />
          Quem favoritou o produto
        </label>
        <!-- ⚠️ O rótulo dizia "me avise quando sair do forno" e a regra pega TODA a
             fila de avisos do produto — inclusive quem espera reposição de um item de
             prateleira. Quem escolhe o eixo é o servidor, pela natureza do produto, e
             o gestor não tem como (nem por que) separar os dois aqui. -->
        <label class="flex items-start gap-2 text-sm">
          <input v-model="alerts" type="checkbox" class="mt-0.5 size-4 rounded border-border">
          <span>
            Quem pediu "me avise" deste produto
            <span class="block text-xs text-muted-foreground">
              A fila do sino da loja: fornada para pão, reposição para o resto.
            </span>
           </span>
        </label>
        <!-- Número nativo compacto mantém v-model.number e a unidade visível na mesma linha. -->
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <label class="flex items-center gap-2">
            <input
              v-model="boughtOn"
              type="checkbox"
              class="size-4 rounded border-border"
            />
            Quem comprou nos últimos
          </label>
          <input
            v-model.number="boughtDays"
            type="number"
            min="1"
            max="365"
            :disabled="!boughtOn"
            aria-label="Dias de recompra"
            class="h-8 w-20 rounded-md border border-border bg-background px-2 text-sm disabled:opacity-50"
          />
          <span :class="boughtOn ? '' : 'text-muted-foreground'">dias</span>
        </div>
        <!-- Número nativo compacto mantém v-model.number e a unidade visível na mesma linha. -->
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <label for="rule-vip">VIPs recebem</label>
          <input
            id="rule-vip"
            v-model.number="vipFirstMinutes"
            type="number"
            min="0"
            max="120"
            class="h-8 w-20 rounded-md border border-border bg-background px-2 text-sm"
          />
          <span>minutos antes</span>
          <span class="text-xs text-muted-foreground"
            >(0 = todo mundo junto)</span
          >
        </div>

        <div class="border-t border-border pt-3">
          <label
            for="rule-audience-match"
            class="mb-1 block text-xs font-medium text-muted-foreground"
          >
            Quando houver vários critérios
          </label>
          <UiNativeSelect
            id="rule-audience-match"
            v-model="audienceMatch"
            class="w-auto"
          >
            <option value="any">Atender a qualquer um</option>
            <option value="all">Atender a todos</option>
          </UiNativeSelect>
        </div>

        <fieldset v-if="tags?.length">
          <legend
            class="mb-1.5 text-xs font-semibold uppercase text-muted-foreground"
          >
            Etiquetas
          </legend>
          <div class="flex flex-wrap gap-1.5">
            <!-- Chips nativos preservam seleção múltipla e aria-pressed em pouco espaço. -->
            <button
              v-for="tag in tags"
              :key="tag.value"
              type="button"
              :aria-pressed="selectedTags.includes(tag.value)"
              class="rounded-full border px-2.5 py-1 text-xs transition"
              :class="
                selectedTags.includes(tag.value)
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border hover:bg-muted'
              "
              @click="toggleChoice(selectedTags, tag.value)"
            >
              {{ tag.label }}
            </button>
          </div>
        </fieldset>

        <fieldset v-if="priceTiers?.length">
          <legend
            class="mb-1.5 text-xs font-semibold uppercase text-muted-foreground"
          >
            Faixa de preço
          </legend>
          <div class="flex flex-wrap gap-1.5">
            <!-- Chips nativos preservam seleção múltipla e aria-pressed em pouco espaço. -->
            <button
              v-for="tier in priceTiers"
              :key="tier.value"
              type="button"
              :aria-pressed="selectedPriceTiers.includes(tier.value)"
              class="rounded-full border px-2.5 py-1 text-xs transition"
              :class="
                selectedPriceTiers.includes(tier.value)
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border hover:bg-muted'
              "
              @click="toggleChoice(selectedPriceTiers, tier.value)"
            >
              {{ tier.label }}
            </button>
          </div>
        </fieldset>

        <fieldset v-if="rfmSegments?.length">
          <legend
            class="mb-1.5 text-xs font-semibold uppercase text-muted-foreground"
          >
            Comportamento de compra
          </legend>
          <div class="flex flex-wrap gap-1.5">
            <!-- Chips nativos preservam seleção múltipla e aria-pressed em pouco espaço. -->
            <button
              v-for="segment in rfmSegments"
              :key="segment.value"
              type="button"
              :aria-pressed="selectedRfmSegments.includes(segment.value)"
              class="rounded-full border px-2.5 py-1 text-xs transition"
              :class="
                selectedRfmSegments.includes(segment.value)
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border hover:bg-muted'
              "
              @click="toggleChoice(selectedRfmSegments, segment.value)"
            >
              {{ segment.label }}
            </button>
          </div>
        </fieldset>

        <label class="flex items-center gap-2 text-sm">
          <input
            v-model="birthdayToday"
            type="checkbox"
            class="size-4 rounded border-border"
          />
          Aniversariantes de hoje
        </label>

        <!-- Número nativo compacto mantém v-model.number e a unidade visível na mesma linha. -->
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <label class="flex items-center gap-2">
            <input
              v-model="churnRiskOn"
              type="checkbox"
              class="size-4 rounded border-border"
            />
            Risco de não voltar a partir de
          </label>
          <input
            v-model.number="churnRiskMin"
            type="number"
            min="0"
            max="1"
            step="0.05"
            :disabled="!churnRiskOn"
            aria-label="Risco mínimo de não voltar"
            class="h-8 w-20 rounded-md border border-border bg-background px-2 text-sm disabled:opacity-50"
          />
        </div>

        <!-- Número nativo compacto mantém v-model.number e a unidade visível na mesma linha. -->
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <label for="rule-preferred-window"
            >Respeitar horário preferido em uma janela de</label
          >
          <input
            id="rule-preferred-window"
            v-model.number="preferredHourWindowHours"
            type="number"
            min="0"
            max="12"
            class="h-8 w-20 rounded-md border border-border bg-background px-2 text-sm"
          />
          <span>horas</span>
          <span class="text-xs text-muted-foreground"
            >(0 = não segmentar por horário)</span
          >
        </div>

        <p
          v-if="preservedAudienceKeys.length"
          class="rounded-md bg-muted/50 px-2.5 py-2 text-xs text-muted-foreground"
        >
          Filtros protegidos ({{ preservedAudienceKeys.join(", ") }}) serão
          preservados sem alteração.
        </p>
      </div>
      <p class="mt-2 text-xs text-muted-foreground">
        Só quem aceitou receber novidades entra na conta. Assinatura de alerta
        por produto já é um aceite daquele produto.
      </p>
    </fieldset>

    <!-- Checkboxes permanecem nativos porque não há primitivo compartilhado de seleção binária. -->
    <div class="space-y-2.5">
      <label class="flex items-center gap-2 text-sm">
        <input
          v-model="requiresApproval"
          type="checkbox"
          class="size-4 rounded border-border"
        />
        Revisar antes de publicar
      </label>
      <p
        v-if="!requiresApproval"
        class="pl-6 text-xs text-warning"
      >
        Sem revisão, o anúncio sai sozinho assim que o evento acontecer.
      </p>
      <!-- Número nativo compacto mantém v-model.number e a unidade visível na mesma linha. -->
      <div class="flex flex-wrap items-center gap-2 text-sm">
        <label for="rule-expiry">O anúncio aguarda revisão por</label>
        <input
          id="rule-expiry"
          v-model.number="expiresAfterMinutes"
          type="number"
          min="0"
          max="1440"
          class="h-8 w-20 rounded-md border border-border bg-background px-2 text-sm"
        />
        <span>minutos</span>
        <span class="text-xs text-muted-foreground">(0 = sem prazo)</span>
      </div>
      <label class="flex items-center gap-2 text-sm">
        <input
          v-model="isActive"
          type="checkbox"
          class="size-4 rounded border-border"
        />
        Regra ativa
      </label>
    </div>

    <div class="flex items-center gap-2 pt-1">
      <UiButton type="submit" :disabled="!canSubmit">
        <Icon
          :name="busy ? 'line-md:loading-loop' : 'lucide:check'"
          class="size-4"
        />
        {{ rule ? "Salvar" : "Criar campanha" }}
      </UiButton>
      <UiButton type="button" variant="outline" @click="emit('cancel')">
        Cancelar
      </UiButton>
    </div>
  </form>
</template>
