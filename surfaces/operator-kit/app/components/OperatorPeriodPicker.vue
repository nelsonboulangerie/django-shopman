<script setup lang="ts">
// Tipo 2 dos controles de data da casa: "Período" (decisão do dono, 02/10/2026).
//
// O desenho é o do B.I., que o dono julgou o melhor da casa e que nasceu lá
// (`bi-nuxt/app/components/BiTopBar.vue`): UM botão que sempre DIZ a janela ativa
// ("28D · 05/09 a 02/10", "Hoje, qui 02/10"); os chips e o personalizado moram no
// popover dele, para a barra não disputar espaço nem rolar em tela estreita. O que
// se acrescentou: ‹ › dos lados, que andam um período IGUAL ao escolhido (dia → dia
// anterior, semana → semana anterior, mês → mês anterior, N dias → os N dias antes),
// e "Voltar para hoje" quando o período não é mais o de hoje.
//
// O popover tem até quatro grupos, sempre na mesma ordem: Período (Dia, Semana,
// Mês, Ano), Próximos (7D, 14D, 28D a partir de hoje), Últimos (7D…Máx até hoje) e
// Personalizado (De/Até). Cada consumidor declara o que faz sentido para ele
// (`presets` e `custom`): a Produção só o dia; as Encomendas olham para a frente;
// o B.I. todo o passado (`PAST_PERIOD_PRESETS`) mais o personalizado. Sem
// personalizado, o popover oferece "Ir para o dia" no lugar dele. Quem tem teto de
// intervalo no servidor diz `max-span-days`: o personalizado recusa com o motivo,
// em vez de o servidor cortar em silêncio.
//
// O estado é do consumidor (`v-model`): quem guarda na URL guarda na URL.
//
// Duas opções para a tela estreita e para a leitura de UM dia (PR-K2 do
// WP-BI-CANON-LAUDO):
// - `compact`: no celular (abaixo de `sm`), o botão diz a forma curta da janela
//   ("Ontem", "28D · 04/09 a 01/10"); do `sm` para cima, a frase inteira. O nome
//   acessível é sempre a frase inteira.
// - "um dia com ‹ ›" (`presets` só com "day", que é o padrão): as setas andam um
//   dia de calendário. Quem sabe que nem todo dia existe na leitura (dia fechado
//   não tem venda) diz para onde cada seta vai com `prev-day`/`next-day`, e a seta
//   sem destino (`""`) fica desligada. É o que substitui o `BiDayStepper`.
import { computed, ref } from "vue";

import {
  CUSTOM_PERIOD,
  PERIOD_PRESETS,
  currentPeriod,
  customPeriod,
  customPeriodError,
  goToDate,
  isCurrentPeriod,
  periodLabel,
  periodShortLabel,
  periodStepLabels,
  resolvePeriod,
  stepPeriod,
  todayIso,
  weekdayAndDate,
  withPreset,
  type PeriodBounds,
  type PeriodSelection,
} from "../presentation/dates";

const props = withDefaults(
  defineProps<{
    modelValue: PeriodSelection;
    /** Granularidades aceitas, na ordem da tela (chaves de `PERIOD_PRESETS`). */
    presets?: readonly string[];
    /** Aceita intervalo personalizado (De/Até). */
    custom?: boolean;
    /** O hoje da loja; omitido, o do dispositivo. */
    today?: string;
    min?: string;
    max?: string;
    /** Onde "Máx" começa. */
    epoch?: string;
    /** O intervalo mais longo aceito no personalizado. */
    maxSpanDays?: number;
    /** Nome do controle para leitor de tela ("Período de análise"). */
    label?: string;
    /** Lado em que o popover se alinha ao botão. */
    align?: "start" | "end";
    /** No celular, o botão diz a forma curta da janela. */
    compact?: boolean;
    /**
     * Só no Dia: para onde ‹ e › andam, quando o dia anterior/seguinte com dado
     * não é o de calendário. Omitido, anda um dia; `""`, a seta fica desligada.
     */
    prevDay?: string;
    nextDay?: string;
  }>(),
  {
    presets: () => ["day"],
    custom: false,
    today: undefined,
    min: undefined,
    max: undefined,
    epoch: undefined,
    maxSpanDays: undefined,
    label: "Período",
    align: "end",
    compact: false,
    prevDay: undefined,
    nextDay: undefined,
  },
);

const emit = defineEmits<{ "update:modelValue": [PeriodSelection] }>();

const bounds = computed<PeriodBounds>(() => ({
  today: props.today || todayIso(),
  min: props.min,
  max: props.max,
  epoch: props.epoch,
  maxSpanDays: props.maxSpanDays,
}));
const range = computed(() => resolvePeriod(props.modelValue, bounds.value));
const buttonLabel = computed(() =>
  periodLabel(props.modelValue, range.value, bounds.value.today),
);
const shortLabel = computed(() =>
  periodShortLabel(props.modelValue, range.value, bounds.value.today),
);
const isDay = computed(() => props.modelValue.preset === "day");
// O passo de um dia: o destino que o consumidor declarou, ou o dia de calendário.
function dayStep(target: string | undefined, direction: 1 | -1) {
  if (!isDay.value || target === undefined)
    return stepPeriod(props.modelValue, direction, bounds.value);
  return target ? goToDate(props.modelValue, target, bounds.value) : null;
}
const prev = computed(() => dayStep(props.prevDay, -1));
const next = computed(() => dayStep(props.nextDay, 1));
const steps = computed(() => {
  const labels = periodStepLabels(props.modelValue.preset);
  if (!isDay.value) return labels;
  return {
    prev: props.prevDay ? `${labels.prev}: ${weekdayAndDate(props.prevDay)}` : labels.prev,
    next: props.nextDay ? `${labels.next}: ${weekdayAndDate(props.nextDay)}` : labels.next,
  };
});
const current = computed(() => isCurrentPeriod(props.modelValue));

const allowed = computed(() =>
  PERIOD_PRESETS.filter((preset) => props.presets.includes(preset.key)),
);
const calendarPresets = computed(() =>
  allowed.value.filter((preset) => preset.kind === "calendar"),
);
const rollingPresets = computed(() =>
  allowed.value.filter((preset) => preset.kind === "rolling"),
);
const upcomingPresets = computed(() =>
  allowed.value.filter((preset) => preset.kind === "upcoming"),
);
const windowCount = computed(
  () => rollingPresets.value.length + upcomingPresets.value.length,
);
// As abas escolhem no toque (`activation-mode="manual"`), nunca no foco: o
// popover põe o foco no primeiro gatilho ao abrir e, no modo automático, isso
// já escolhia "Dia" e fechava o popover de quem estava em 28D (o B.I.).
//
// O NuxtTabs (4.11.3) não repassa ao gatilho chave extra do item: um
// "aria-label" no item morria antes do DOM. O nome por extenso ("Próximos 7
// dias") vai, então, no conteúdo do gatilho (slot padrão), escrito para o leitor
// de tela, e o chip curto ("7D") fica só para o olho.
const presetItems = (presets: typeof allowed.value) =>
  presets.map((preset) => ({
    value: preset.key,
    label: preset.label,
    title: preset.title,
  }));

const open = ref(false);
const customFrom = ref("");
const customTo = ref("");
const jumpTo = ref("");

function set(selection: PeriodSelection | null) {
  if (selection) emit("update:modelValue", selection);
}

function onOpen(value: boolean) {
  if (value) {
    customFrom.value = range.value.date_from;
    customTo.value = range.value.date_to;
    jumpTo.value = range.value.date_from;
  }
  open.value = value;
}

function pick(key: string) {
  set(withPreset(props.modelValue, key, bounds.value));
  open.value = false;
}

// O motivo só aparece depois das duas datas: "Escolha as duas datas" antes de
// qualquer toque seria bronca por nada.
const customError = computed(() =>
  customFrom.value && customTo.value
    ? customPeriodError(customFrom.value, customTo.value, bounds.value)
    : "",
);

function submitCustom() {
  if (!customFrom.value || !customTo.value || customError.value) return;
  set(customPeriod(customFrom.value, customTo.value));
  open.value = false;
}

function submitJump() {
  if (!jumpTo.value) return;
  set(goToDate(props.modelValue, jumpTo.value, bounds.value));
  open.value = false;
}

function backToToday() {
  // Do personalizado, "hoje" é a primeira granularidade que o consumidor aceita.
  if (props.modelValue.preset === CUSTOM_PERIOD) {
    set({ preset: allowed.value[0]?.key ?? "day", from: "", to: "" });
    return;
  }
  set(currentPeriod(props.modelValue));
}
</script>

<template>
  <div
    class="flex flex-wrap items-center gap-2"
    role="group"
    :aria-label="label"
    data-period-picker
  >
    <NuxtFieldGroup>
      <NuxtButton
        color="neutral"
        variant="outline"
        icon="i-lucide-chevron-left"
        square
        class="suite-page:size-control suite-page:justify-center"
        :aria-label="steps.prev"
        :title="steps.prev"
        :disabled="!prev"
        data-period-prev
        @click="set(prev)"
      />
      <NuxtPopover :open="open" :content="{ align }" @update:open="onOpen">
        <NuxtButton
          color="neutral"
          variant="outline"
          icon="i-lucide-calendar-range"
          trailing-icon="i-lucide-chevron-down"
          :label="compact ? undefined : buttonLabel"
          class="suite-page:min-h-control"
          :aria-label="`${label}: ${buttonLabel}`"
          data-period-button
          data-period-label
        >
          <template v-if="compact">
            <span class="max-sm:hidden" data-period-label-full>{{
              buttonLabel
            }}</span>
            <span class="sm:hidden" data-period-label-short>{{
              shortLabel
            }}</span>
          </template>
        </NuxtButton>
        <template #content>
          <div class="w-80 max-w-[calc(100vw-2rem)] p-3" data-period-popover>
            <template
              v-if="
                calendarPresets.length > 1 ||
                (calendarPresets.length && windowCount)
              "
            >
              <p class="mb-2 text-sm font-medium">Período</p>
              <NuxtTabs
                :model-value="modelValue.preset"
                :items="presetItems(calendarPresets)"
                :content="false"
                variant="pill"
                activation-mode="manual"
                aria-label="Período do calendário"
                @update:model-value="pick(String($event))"
              >
                <template #default="{ item }">
                  <span :data-period-preset="item.value">
                    <template v-if="item.title && item.title !== item.label">
                      <span aria-hidden="true">{{ item.label }}</span>
                      <span class="sr-only">{{ item.title }}</span>
                    </template>
                    <template v-else>{{ item.label }}</template>
                  </span>
                </template>
              </NuxtTabs>
            </template>
            <template v-if="upcomingPresets.length">
              <p class="mt-3 mb-2 text-sm font-medium">Próximos</p>
              <NuxtTabs
                :model-value="modelValue.preset"
                :items="presetItems(upcomingPresets)"
                :content="false"
                variant="pill"
                activation-mode="manual"
                aria-label="Próximos dias"
                @update:model-value="pick(String($event))"
              >
                <template #default="{ item }">
                  <span :data-period-preset="item.value">
                    <template v-if="item.title && item.title !== item.label">
                      <span aria-hidden="true">{{ item.label }}</span>
                      <span class="sr-only">{{ item.title }}</span>
                    </template>
                    <template v-else>{{ item.label }}</template>
                  </span>
                </template>
              </NuxtTabs>
            </template>
            <template v-if="rollingPresets.length">
              <p class="mt-3 mb-2 text-sm font-medium">Últimos</p>
              <NuxtTabs
                :model-value="modelValue.preset"
                :items="presetItems(rollingPresets)"
                :content="false"
                variant="pill"
                activation-mode="manual"
                aria-label="Janelas móveis"
                @update:model-value="pick(String($event))"
              >
                <template #default="{ item }">
                  <span :data-period-preset="item.value">
                    <template v-if="item.title && item.title !== item.label">
                      <span aria-hidden="true">{{ item.label }}</span>
                      <span class="sr-only">{{ item.title }}</span>
                    </template>
                    <template v-else>{{ item.label }}</template>
                  </span>
                </template>
              </NuxtTabs>
            </template>

            <NuxtSeparator v-if="allowed.length && custom" class="my-3" />
            <template v-if="custom">
              <p class="mb-2 text-sm font-medium">Personalizado</p>
              <!-- Um campo por linha: o popover tem 20rem, e o campo canônico de
                   data (três segmentos e o gatilho do calendário, tamanho xl) não
                   cabe em meia largura. -->
              <div class="grid gap-2">
                <NuxtFormField label="De">
                  <UiDateField
                    v-model="customFrom"
                    :min="min"
                    :max="max"
                    label="Início do período personalizado"
                    data-period-custom-from
                  />
                </NuxtFormField>
                <NuxtFormField label="Até">
                  <UiDateField
                    v-model="customTo"
                    :min="min"
                    :max="max"
                    label="Fim do período personalizado"
                    data-period-custom-to
                  />
                </NuxtFormField>
              </div>
              <NuxtAlert
                v-if="customError"
                class="mt-2"
                color="error"
                variant="subtle"
                :title="customError"
                data-period-custom-error
              />
              <div class="mt-2">
                <NuxtButton
                  block
                  :disabled="!customFrom || !customTo || !!customError"
                  label="Aplicar período"
                  data-period-custom-apply
                  @click="submitCustom"
                />
              </div>
            </template>
            <template v-else>
              <NuxtSeparator
                v-if="calendarPresets.length > 1 || windowCount"
                class="my-3"
              />
              <NuxtFormField label="Ir para o dia">
                <UiDateField
                  v-model="jumpTo"
                  :min="min"
                  :max="max"
                  label="Data para mostrar"
                  data-period-jump
                />
              </NuxtFormField>
              <div class="mt-2">
                <NuxtButton
                  block
                  :disabled="!jumpTo"
                  label="Mostrar esta data"
                  data-period-jump-apply
                  @click="submitJump"
                />
              </div>
            </template>
          </div>
        </template>
      </NuxtPopover>
      <NuxtButton
        color="neutral"
        variant="outline"
        icon="i-lucide-chevron-right"
        square
        class="suite-page:size-control suite-page:justify-center"
        :aria-label="steps.next"
        :title="steps.next"
        :disabled="!next"
        data-period-next
        @click="set(next)"
      />
    </NuxtFieldGroup>

    <NuxtButton
      v-if="!current"
      color="neutral"
      variant="link"
      label="Voltar para hoje"
      data-period-today
      @click="backToToday"
    />
  </div>
</template>
