<script setup lang="ts">
// Formulário de campanha — "que evento vira o quê, para quem, onde".
//
// Apresentacional: o pai é dono do fetch e da escrita; aqui mora só o estado do
// formulário. O vocabulário (gatilhos, plataformas, modelos) vem do backend,
// nunca hardcoded — gatilho novo no domínio aparece aqui sem deploy de front.
import type { AudienceRules, Campaign, Choice, AnnouncementTemplate } from "~/types/campaign";

const props = defineProps<{
  rule: Campaign | null; // null = criando
  triggers: Choice[];
  platformOptions: Choice[];
  templates: AnnouncementTemplate[];
  offers: Choice[];
  busy?: boolean;
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

// Audiência: toggles simples em cima do JSON que o serviço lê.
// Agendamento que DISPARA — só existe com o gatilho "agendado", porque nos outros a
// causa é o evento e este bloco não teria o que responder. O JSON montado aqui é o
// mesmo que `services/campaign_schedule.py` lê; o servidor recusa o par impossível.
const scheduleKind = ref<"once" | "recurring">("recurring");
const onceAt = ref("");
const fireAt = ref("07:00");
const weekdays = ref<number[]>([]);
const endsOn = ref("");

const WEEKDAY_LABELS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]; // 0 = segunda

const schedules = computed(() => trigger.value === "schedule");

const favorites = ref(false);
const alerts = ref(false);
const boughtOn = ref(false);
const boughtDays = ref(90);
const vipFirstMinutes = ref(0);

// Estado novo a cada campanha aberta — senão o formulário herdaria a anterior.
watch(
  () => props.rule?.pk ?? null,
  () => {
    const rule = props.rule;
    const audience: AudienceRules = rule?.audience_rules ?? {};

    name.value = rule?.name ?? "";
    trigger.value = rule?.trigger ?? props.triggers[0]?.value ?? "";
    templateId.value = rule?.template_id ?? props.templates[0]?.pk ?? null;
    platforms.value = [...(rule?.platforms ?? [])];
    requiresApproval.value = rule?.requires_approval ?? true;
    expiresAfterMinutes.value = rule?.expires_after_minutes ?? 0;
    promotionRef.value = rule?.promotion_ref ?? "";
    isActive.value = rule?.is_active ?? true;

    const schedule = (rule?.schedule ?? {}) as Record<string, unknown>;
    scheduleKind.value = schedule.type === "once" ? "once" : "recurring";
    onceAt.value = typeof schedule.at === "string" ? schedule.at.slice(0, 16) : "";
    const firstWindow = Array.isArray(schedule.windows) ? schedule.windows[0] : null;
    fireAt.value = Array.isArray(firstWindow) ? String(firstWindow[0]) : "07:00";
    weekdays.value = Array.isArray(schedule.weekdays) ? schedule.weekdays.map(Number) : [];
    endsOn.value = typeof schedule.ends_on === "string" ? schedule.ends_on : "";

    favorites.value = Boolean(audience.favorites);
    alerts.value = Boolean(audience.alerts);
    boughtOn.value = Boolean(audience.bought_within_days);
    boughtDays.value = audience.bought_within_days || 90;
    vipFirstMinutes.value = audience.vip_first_minutes || 0;
  },
  { immediate: true },
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
  scheduleKind.value === "once" ? onceAt.value !== "" : fireAt.value !== "",
);

function toggleWeekday(day: number) {
  const index = weekdays.value.indexOf(day);
  if (index >= 0) weekdays.value.splice(index, 1);
  else weekdays.value.push(day);
}

function buildSchedule(): Record<string, unknown> {
  if (scheduleKind.value === "once") return { type: "once", at: onceAt.value };
  // O fim da janela é inerte para quem dispara (só o início vira ocasião), mas o
  // formato exige o par — daí uma hora depois, sem inventar significado nenhum.
  // `?? 0` porque um `<input type="time">` pode chegar vazio: sem isso o fim virava
  // "NaN:NaN", o servidor descartava a janela e a campanha nunca disparava — em silêncio.
  const [rawHour, rawMinute] = fireAt.value.split(":");
  const hour = Number(rawHour) || 0;
  const minute = Number(rawMinute) || 0;
  const end = `${String((hour + 1) % 24).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  return {
    type: "recurring",
    windows: [[fireAt.value, end]],
    // Vazio = a semana toda, igual ao servidor. Não mandamos os 7 dias à mão.
    ...(weekdays.value.length > 0 ? { weekdays: [...weekdays.value].sort() } : {}),
    ...(endsOn.value ? { ends_on: endsOn.value } : {}),
  };
}

function togglePlatform(value: string) {
  const index = platforms.value.indexOf(value);
  if (index >= 0) platforms.value.splice(index, 1);
  else platforms.value.push(value);
}

function submit() {
  if (!canSubmit.value) return;
  emit("submit", {
    name: name.value.trim(),
    trigger: trigger.value,
    template_id: templateId.value,
    platforms: [...platforms.value],
    requires_approval: requiresApproval.value,
    expires_after_minutes: expiresAfterMinutes.value,
    promotion_ref: promotionRef.value,
    is_active: isActive.value,
    // Só mandamos `schedule` quando ele é a causa. Nos gatilhos de evento a chave fica
    // de fora para não apagar um `preferred_hours` configurado no Admin.
    ...(schedules.value ? { schedule: buildSchedule() } : {}),
    audience_rules: {
      favorites: favorites.value,
      alerts: alerts.value,
      // Chave ausente quando desligado: o serviço lê "0 dias" como "não usa".
      ...(boughtOn.value ? { bought_within_days: boughtDays.value } : {}),
      ...(vipFirstMinutes.value > 0 ? { vip_first_minutes: vipFirstMinutes.value } : {}),
    },
  });
}
</script>

<template>
  <form class="space-y-5" @submit.prevent="submit">
    <div>
      <label for="rule-name" class="mb-1 block text-sm font-medium">Nome da campanha</label>
      <input
        id="rule-name"
        v-model="name"
        type="text"
        placeholder="Fornada de pães → redes"
        class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
      >
    </div>

    <div class="grid gap-4 sm:grid-cols-2">
      <div>
        <label for="rule-trigger" class="mb-1 block text-sm font-medium">Quando acontecer</label>
        <select
          id="rule-trigger"
          v-model="trigger"
          class="h-9 w-full rounded-md border border-border bg-background px-2 text-sm outline-none focus:ring-1 focus:ring-ring"
        >
          <option v-for="choice in triggers" :key="choice.value" :value="choice.value">
            {{ choice.label }}
          </option>
        </select>
      </div>

      <div>
        <label for="rule-template" class="mb-1 block text-sm font-medium">Usar o modelo</label>
        <select
          id="rule-template"
          v-model="templateId"
          class="h-9 w-full rounded-md border border-border bg-background px-2 text-sm outline-none focus:ring-1 focus:ring-ring"
        >
          <option v-for="template in templates" :key="template.pk" :value="template.pk">
            {{ template.name }}
          </option>
        </select>
        <p v-if="templates.length === 0" class="mt-1 text-xs text-muted-foreground">
          Nenhum modelo cadastrado ainda.
          <NuxtLink to="/templates" class="font-medium underline">Crie o primeiro aqui</NuxtLink>
          antes de criar a campanha.
        </p>
      </div>
    </div>

    <!-- A oferta que o anúncio leva. Quando escolhida, o {{link}} da mensagem aponta
         para a oferta e o clique monta a sacola com o preço resolvido NA HORA — não no
         envio, que é quando o preço envelheceria. -->
    <div v-if="offers.length">
      <label for="rule-offer" class="mb-1 block text-sm font-medium">Anunciar a oferta</label>
      <select
        id="rule-offer"
        v-model="promotionRef"
        class="h-9 w-full rounded-md border border-border bg-background px-2 text-sm outline-none focus:ring-1 focus:ring-ring"
      >
        <option value="">Nenhuma — só contar a novidade</option>
        <option v-for="offer in offers" :key="offer.value" :value="offer.value">
          {{ offer.label }}
        </option>
      </select>
      <p class="mt-1 text-xs text-muted-foreground">
        Com oferta, quem toca no link já recebe a sacola montada.
      </p>
    </div>

    <!-- Sem este bloco, "agendado" era escolhível e insatisfazível: o gestor salvava e
         a campanha nunca disparava. -->
    <fieldset v-if="schedules" class="rounded-lg border border-border bg-card p-4">
      <legend class="px-1 text-sm font-medium">Quando disparar</legend>

      <div class="flex gap-2">
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
          @click="scheduleKind = option.value as 'once' | 'recurring'"
        >
          {{ option.label }}
        </button>
      </div>

      <div v-if="scheduleKind === 'once'" class="mt-3">
        <label for="rule-once-at" class="mb-1 block text-sm font-medium">Dia e hora</label>
        <input
          id="rule-once-at"
          v-model="onceAt"
          type="datetime-local"
          class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring sm:w-64"
        >
        <p class="mt-1 text-xs text-muted-foreground">
          Dispara uma única vez. Depois disso a campanha não volta sozinha.
        </p>
      </div>

      <div v-else class="mt-3 space-y-3">
        <div>
          <label for="rule-fire-at" class="mb-1 block text-sm font-medium">Hora</label>
          <input
            id="rule-fire-at"
            v-model="fireAt"
            type="time"
            class="h-9 w-28 rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
          >
        </div>

        <div>
          <p class="mb-1 text-sm font-medium">Nos dias</p>
          <div class="flex flex-wrap gap-1.5">
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

        <div>
          <label for="rule-ends-on" class="mb-1 block text-sm font-medium">
            Parar depois de (opcional)
          </label>
          <input
            id="rule-ends-on"
            v-model="endsOn"
            type="date"
            class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring sm:w-48"
          >
        </div>
      </div>
    </fieldset>

    <fieldset>
      <legend class="mb-1 text-sm font-medium">Publicar em</legend>
      <div class="flex flex-wrap gap-1.5">
        <label
          v-for="option in platformOptions"
          :key="option.value"
          class="inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors"
          :class="platforms.includes(option.value)
            ? 'border-primary bg-primary/10 text-foreground'
            : 'border-border text-muted-foreground hover:bg-muted'"
        >
          <input
            type="checkbox"
            class="sr-only"
            :aria-label="option.label"
            :checked="platforms.includes(option.value)"
            @change="togglePlatform(option.value)"
          >
          {{ option.label }}
        </label>
      </div>
    </fieldset>

    <fieldset class="rounded-lg border border-border p-3">
      <legend class="px-1 text-sm font-medium">Avisar quem</legend>
      <div class="space-y-2.5">
        <label class="flex items-center gap-2 text-sm">
          <input v-model="favorites" type="checkbox" class="size-4 rounded border-border">
          Quem favoritou o produto
        </label>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="alerts" type="checkbox" class="size-4 rounded border-border">
          Quem pediu "me avise quando sair do forno"
        </label>
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <label class="flex items-center gap-2">
            <input v-model="boughtOn" type="checkbox" class="size-4 rounded border-border">
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
          >
          <span :class="boughtOn ? '' : 'text-muted-foreground'">dias</span>
        </div>
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <label for="rule-vip">VIPs recebem</label>
          <input
            id="rule-vip"
            v-model.number="vipFirstMinutes"
            type="number"
            min="0"
            max="120"
            class="h-8 w-20 rounded-md border border-border bg-background px-2 text-sm"
          >
          <span>minutos antes</span>
          <span class="text-xs text-muted-foreground">(0 = todo mundo junto)</span>
        </div>
      </div>
      <p class="mt-2 text-xs text-muted-foreground">
        Só quem aceitou receber novidades entra na conta. Assinatura de alerta por produto
        já é um aceite daquele produto.
      </p>
    </fieldset>

    <div class="space-y-2.5">
      <label class="flex items-center gap-2 text-sm">
        <input v-model="requiresApproval" type="checkbox" class="size-4 rounded border-border">
        Revisar antes de publicar
      </label>
      <p v-if="!requiresApproval" class="pl-6 text-xs text-amber-700 dark:text-amber-400">
        Sem revisão, o announcement sai sozinho assim que o evento acontecer.
      </p>
      <div class="flex flex-wrap items-center gap-2 text-sm">
        <label for="rule-expiry">O announcement aguarda revisão por</label>
        <input
          id="rule-expiry"
          v-model.number="expiresAfterMinutes"
          type="number"
          min="0"
          max="1440"
          class="h-8 w-20 rounded-md border border-border bg-background px-2 text-sm"
        >
        <span>minutos</span>
        <span class="text-xs text-muted-foreground">(0 = sem prazo)</span>
      </div>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="isActive" type="checkbox" class="size-4 rounded border-border">
        Regra ativa
      </label>
    </div>

    <div class="flex items-center gap-2 pt-1">
      <button
        type="submit"
        :disabled="!canSubmit"
        class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
      >
        <Icon :name="busy ? 'line-md:loading-loop' : 'lucide:check'" class="size-4" />
        {{ rule ? "Salvar" : "Criar campanha" }}
      </button>
      <button
        type="button"
        class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted"
        @click="emit('cancel')"
      >
        Cancelar
      </button>
    </div>
  </form>
</template>
