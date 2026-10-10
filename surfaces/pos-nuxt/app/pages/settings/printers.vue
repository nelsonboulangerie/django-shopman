<script setup lang="ts">
// PDV › Ajustes › Impressoras (UX-15): o rolo e a guilhotina de cada terminal
// (`Terminal.metadata.hardware.printer`), e quais estações sem tela imprimem em
// cada um. O resto da impressora (colunas aferidas, etiqueta) segue no Admin.
import type { PosPrinterSetting } from "~/types/settings";

useHead({ title: "Impressoras" });

const settings = usePosSettings();
const drafts = reactive<Record<string, { roll: number | null; cut: string }>>({});
watch(() => settings.data.value?.printers, (printers) => {
  for (const printer of printers || []) {
    drafts[printer.terminal_ref] = { roll: printer.roll_width_mm, cut: printer.cut_mode || "partial" };
  }
}, { immediate: true });
function changed(printer: PosPrinterSetting) {
  const draft = drafts[printer.terminal_ref];
  return Boolean(draft) && (draft!.roll !== printer.roll_width_mm || draft!.cut !== (printer.cut_mode || "partial"));
}
function save(printer: PosPrinterSetting) {
  const draft = drafts[printer.terminal_ref];
  if (!draft) return;
  void settings.save("printer", { terminal_ref: printer.terminal_ref, roll_width_mm: draft.roll, cut_mode: draft.cut }, `Impressora de ${printer.label} gravada.`);
}
</script>

<template>
  <PosSettingsShell title="Impressoras" subtitle="rolo e corte de cada balcão">
    <OperatorScreenState v-if="settings.error.value && !settings.data.value" state="error" what="as impressoras" @retry="settings.refresh()" />
    <OperatorScreenState v-else-if="!settings.data.value" state="loading" what="as impressoras" />
    <template v-else>
      <OperatorScreenState
        v-if="!settings.data.value.printers.length"
        state="empty"
        icon="i-lucide-printer"
        title="Nenhum terminal ativo."
        description="Cadastre o terminal no Admin."
      />
      <section
        v-for="printer in settings.data.value.printers"
        :key="printer.terminal_ref"
        class="grid gap-4 rounded-xl border border-border bg-card p-4"
        :data-settings-printer="printer.terminal_ref"
      >
        <header class="flex items-center gap-3">
          <span class="grid size-11 place-items-center rounded-lg bg-secondary"><Icon name="lucide:printer" class="size-5" aria-hidden="true" /></span>
          <div class="min-w-0 flex-1">
            <h2 class="truncate op-title">{{ printer.label }}</h2>
            <p class="op-micro text-muted-foreground">
              {{ printer.stations.length ? `Imprime também para: ${printer.stations.join(", ")}` : (printer.location || "Recibo do balcão") }}
            </p>
          </div>
        </header>
        <div class="grid gap-4 sm:grid-cols-2">
          <fieldset class="grid gap-2">
            <legend class="mb-1 op-label text-muted-foreground">Largura do rolo</legend>
            <NuxtFieldGroup class="w-full" data-settings-roll>
              <NuxtButton
                v-for="width in settings.data.value.roll_widths"
                :key="width"
                color="neutral"
                variant="outline"
                active-color="primary"
                active-variant="solid"
                :active="drafts[printer.terminal_ref]?.roll === width"
                :aria-pressed="drafts[printer.terminal_ref]?.roll === width"
                class="flex-1 justify-center"
                :label="`${width} mm`"
                @click="drafts[printer.terminal_ref]!.roll = width"
              />
            </NuxtFieldGroup>
          </fieldset>
          <fieldset class="grid gap-2">
            <legend class="mb-1 op-label text-muted-foreground">Corte do papel</legend>
            <NuxtFieldGroup class="w-full" data-settings-cut>
              <NuxtButton
                v-for="mode in settings.data.value.cut_modes"
                :key="mode.value"
                color="neutral"
                variant="outline"
                active-color="primary"
                active-variant="solid"
                :active="drafts[printer.terminal_ref]?.cut === mode.value"
                :aria-pressed="drafts[printer.terminal_ref]?.cut === mode.value"
                class="flex-1 justify-center"
                :label="mode.label"
                @click="drafts[printer.terminal_ref]!.cut = mode.value"
              />
            </NuxtFieldGroup>
          </fieldset>
        </div>
        <div class="flex justify-end">
          <NuxtButton
            label="Gravar impressora"
            :loading="settings.saving.value === 'printer'"
            :disabled="!changed(printer) || settings.saving.value === 'printer'"
            @click="save(printer)"
          />
        </div>
      </section>
    </template>
  </PosSettingsShell>
</template>
