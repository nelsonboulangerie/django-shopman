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
    <p v-if="settings.error.value && !settings.data.value" class="op-body text-muted-foreground">{{ httpErrorMessage(settings.error.value, "Não deu para ler as impressoras.") }}</p>
    <p v-else-if="!settings.data.value" class="op-body text-muted-foreground">Lendo as impressoras…</p>
    <template v-else>
      <p v-if="!settings.data.value.printers.length" class="rounded-xl border border-dashed p-6 text-center op-body text-muted-foreground">Nenhum terminal ativo. Cadastre o terminal no Admin.</p>
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
            <div class="inline-flex h-11 items-center gap-1 rounded-md bg-secondary p-1" role="group">
              <button
                v-for="width in settings.data.value.roll_widths"
                :key="width"
                type="button"
                class="h-full flex-1 rounded px-3 op-label transition"
                :class="drafts[printer.terminal_ref]?.roll === width ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground'"
                :aria-pressed="drafts[printer.terminal_ref]?.roll === width"
                @click="drafts[printer.terminal_ref]!.roll = width"
              >{{ width }} mm</button>
            </div>
          </fieldset>
          <fieldset class="grid gap-2">
            <legend class="mb-1 op-label text-muted-foreground">Corte do papel</legend>
            <div class="inline-flex h-11 items-center gap-1 rounded-md bg-secondary p-1" role="group">
              <button
                v-for="mode in settings.data.value.cut_modes"
                :key="mode.value"
                type="button"
                class="h-full flex-1 rounded px-3 op-label transition"
                :class="drafts[printer.terminal_ref]?.cut === mode.value ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground'"
                :aria-pressed="drafts[printer.terminal_ref]?.cut === mode.value"
                @click="drafts[printer.terminal_ref]!.cut = mode.value"
              >{{ mode.label }}</button>
            </div>
          </fieldset>
        </div>
        <div class="flex justify-end">
          <UiButton :disabled="!changed(printer) || settings.saving.value === 'printer'" @click="save(printer)">Gravar impressora</UiButton>
        </div>
      </section>
    </template>
  </PosSettingsShell>
</template>
