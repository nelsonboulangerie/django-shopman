<script setup lang="ts">
// PDV › Ajustes › Envio à cozinha (UX-15): as estações de preparo e separação, o que
// cada uma recebe (coleções), se imprime (estação sem tela) e o ENVIO AUTOMÁTICO,
// opcional por estação e desligado por padrão (decisão do dono, plano §13 item 3).
// Ligado, a linha nova daquela estação sai sozinha quando o operador deixa a
// comanda ou ela fica parada (`pages/index.vue`, `autoFireLeftovers`).
import type { PosKitchenStationSetting } from "~/types/settings";

useHead({ title: "Envio à cozinha" });

const settings = usePosSettings();
function toggle(station: PosKitchenStationSetting) {
  void settings.save(
    "kitchen_station",
    { station_ref: station.ref, auto_fire: !station.auto_fire },
    station.auto_fire ? `${station.name}: envio automático desligado.` : `${station.name}: envio automático ligado.`,
  );
}
</script>

<template>
  <PosSettingsShell title="Envio à cozinha" subtitle="estações e envio automático">
    <div v-if="settings.error.value && !settings.data.value" class="flex flex-wrap items-center gap-3 rounded-xl border border-dashed p-4">
      <p class="min-w-0 flex-1 op-body text-muted-foreground">{{ httpErrorMessage(settings.error.value, "Não deu para ler as estações. Confira a conexão e tente de novo.") }}</p>
      <UiButton variant="outline" @click="settings.refresh()">Tentar de novo</UiButton>
    </div>
    <p v-else-if="!settings.data.value" class="op-body text-muted-foreground">Lendo as estações…</p>
    <template v-else>
      <p class="op-body text-muted-foreground">
        Com o envio automático ligado, a linha nova da estação vai sozinha quando você sai da comanda ou ela fica um minuto e meio parada. Desligado, só vai no "Enviar à cozinha".
      </p>
      <p v-if="!settings.data.value.kitchen_stations.length" class="rounded-xl border border-dashed p-6 text-center op-body text-muted-foreground">Nenhuma estação ativa. Cadastre as estações no Admin.</p>
      <ul v-else class="divide-y divide-border rounded-xl border border-border bg-card">
        <li
          v-for="station in settings.data.value.kitchen_stations"
          :key="station.ref"
          class="flex items-center gap-3 px-4 py-3"
          :data-settings-kitchen-station="station.ref"
        >
          <span class="grid size-10 place-items-center rounded-lg bg-secondary"><Icon name="lucide:chef-hat" class="size-5" aria-hidden="true" /></span>
          <div class="min-w-0 flex-1">
            <p class="truncate op-label font-semibold">{{ station.name }} <span class="font-normal text-muted-foreground">· {{ station.type_label }}</span></p>
            <p class="truncate op-micro text-muted-foreground">
              {{ station.collections.length ? station.collections.join(", ") : "Recebe o que nenhuma outra estação recebe" }}{{ station.print_terminal ? ` · imprime em ${station.print_terminal}` : "" }}
            </p>
          </div>
          <label class="flex shrink-0 items-center gap-2 op-micro text-muted-foreground">
            <span class="max-sm:sr-only">envio automático</span>
            <UiSwitch
              :model-value="station.auto_fire"
              :disabled="settings.saving.value === 'kitchen_station'"
              :aria-label="`Envio automático de ${station.name}`"
              :data-settings-auto-fire="station.ref"
              @update:model-value="toggle(station)"
            />
          </label>
        </li>
      </ul>
    </template>
  </PosSettingsShell>
</template>
