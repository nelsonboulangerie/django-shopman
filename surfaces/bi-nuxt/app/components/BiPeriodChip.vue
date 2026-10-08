<script setup lang="ts">
// O período no celular (prévia `depois-marketing-bi-celular` (b), pino 6): um gatilho
// na barra de cima que diz a janela ("28D ⌄"), com as mesmas opções do desktop num
// NuxtPopover (as janelas móveis, os períodos atuais e o personalizado). A janela é a
// mesma da URL (`useBiWindow`): trocar aqui troca em todas as seções.
// ⚠️ É um segundo seletor de período paralelo ao OperatorPeriodPicker do kit; morre
// quando o kit ganhar a variante de gatilho compacto (onda 0, PR 0.3/0.7). Do tablet
// para cima o gatilho some: lá o período é o BiWindowPicker do cabeçalho, e antes os
// dois seletores apareciam juntos (laudo, Anexo D).
import {
  PERIOD_PRESETS_CALENDAR,
  PERIOD_PRESETS_ROLLING,
  customPeriodError,
} from "../../../operator-kit/app/presentation/dates";

const { selection, range, bounds, setPreset, applyCustom } = useBiWindow();

const open = ref(false);
const from = ref("");
const to = ref("");

const chipLabel = computed(() => {
  if (selection.value.preset === "custom") return `${range.value.date_from.slice(8, 10)}/${range.value.date_from.slice(5, 7)}+`;
  const preset = [...PERIOD_PRESETS_ROLLING, ...PERIOD_PRESETS_CALENDAR].find((item) => item.key === selection.value.preset);
  return preset?.label ?? "28D";
});
const customError = computed(() => (from.value && to.value ? customPeriodError(from.value, to.value, bounds.value) : ""));

watch(open, (value) => {
  if (!value) return;
  from.value = range.value.date_from;
  to.value = range.value.date_to;
});

function pick(key: string) {
  setPreset(key);
  open.value = false;
}

function submitCustom() {
  if (!from.value || !to.value || customError.value) return;
  applyCustom(from.value, to.value);
  open.value = false;
}
</script>

<template>
  <NuxtPopover v-model:open="open" :content="{ align: 'end', sideOffset: 6, collisionPadding: 8 }">
    <NuxtButton
      color="primary"
      variant="soft"
      trailing-icon="i-lucide-chevron-down"
      class="tnum md:hidden"
      :label="chipLabel"
      :aria-label="`Período de análise: ${chipLabel}`"
      data-bi-period-chip
    />
    <template #content>
      <!-- `max-w-[calc(100vw-1rem)]`: num celular de 320 px o painel de 20rem passaria
           da tela; meio rem de folga de cada lado, o mesmo `collisionPadding` de 8 px. -->
      <div class="grid w-80 max-w-[calc(100vw-1rem)] gap-3 p-3" data-bi-period-panel>
        <div>
          <p class="mb-1.5 op-eyebrow text-muted-foreground">Últimos</p>
          <div class="grid grid-cols-4 gap-1.5">
            <NuxtButton
              v-for="preset in PERIOD_PRESETS_ROLLING"
              :key="preset.key"
              :color="selection.preset === preset.key ? 'primary' : 'neutral'"
              :variant="selection.preset === preset.key ? 'soft' : 'outline'"
              class="tnum justify-center"
              :label="preset.label"
              :aria-label="preset.title"
              :aria-pressed="selection.preset === preset.key"
              @click="pick(preset.key)"
            />
          </div>
        </div>
        <div>
          <p class="mb-1.5 op-eyebrow text-muted-foreground">Período atual</p>
          <div class="grid grid-cols-4 gap-1.5">
            <NuxtButton
              v-for="preset in PERIOD_PRESETS_CALENDAR"
              :key="preset.key"
              :color="selection.preset === preset.key ? 'primary' : 'neutral'"
              :variant="selection.preset === preset.key ? 'soft' : 'outline'"
              class="justify-center"
              :label="preset.label"
              :aria-pressed="selection.preset === preset.key"
              @click="pick(preset.key)"
            />
          </div>
        </div>
        <NuxtForm :state="{ from, to }" class="grid grid-cols-2 gap-2" @submit="submitCustom">
          <p class="col-span-2 op-eyebrow text-muted-foreground">Personalizado</p>
          <NuxtFormField label="De">
            <UiDateField v-model="from" :max="bounds.max" label="Início do período" />
          </NuxtFormField>
          <NuxtFormField label="Até">
            <UiDateField v-model="to" :max="bounds.max" label="Fim do período" />
          </NuxtFormField>
          <NuxtAlert v-if="customError" class="col-span-2" color="error" variant="subtle" :title="customError" />
          <NuxtButton
            type="submit"
            class="col-span-2 justify-center"
            label="Ver este período"
            :disabled="!from || !to || Boolean(customError)"
          />
        </NuxtForm>
      </div>
    </template>
  </NuxtPopover>
</template>
