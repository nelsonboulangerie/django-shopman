<script setup lang="ts">
// PDV › Ajustes › Maquininhas (UX-15): as maquininhas de entrega (`DeliveryDevice`),
// com quem cada uma está agora, ativar/desativar e cadastrar uma nova. A que está
// numa entrega não se desativa (volta primeiro).
import type { PosCardMachineSetting } from "~/types/settings";

useHead({ title: "Maquininhas" });

const settings = usePosSettings();
const editing = ref<{ ref: string; label: string; identification: string; active: boolean } | null>(null);
function edit(machine: PosCardMachineSetting) {
  editing.value = { ref: machine.ref, label: machine.label, identification: machine.identification, active: machine.active };
}
function addNew() {
  editing.value = { ref: "", label: "", identification: "", active: true };
}
async function submit() {
  const draft = editing.value;
  if (!draft) return;
  const ok = await settings.save("card_machine", { ...draft }, draft.ref ? "Maquininha gravada." : "Maquininha cadastrada.");
  if (ok) editing.value = null;
}
function toggle(machine: PosCardMachineSetting) {
  void settings.save(
    "card_machine",
    { ref: machine.ref, label: machine.label, active: !machine.active },
    machine.active ? `${machine.label} desativada.` : `${machine.label} ativada.`,
  );
}
</script>

<template>
  <PosSettingsShell title="Maquininhas" subtitle="as que vão com a entrega">
    <template #actions>
      <UiButton class="gap-1.5" data-settings-card-machine-add @click="addNew">
        <Icon name="lucide:plus" class="size-4" />Nova maquininha
      </UiButton>
    </template>
    <div v-if="settings.error.value && !settings.data.value" class="flex flex-wrap items-center gap-3 rounded-xl border border-dashed p-4">
      <p class="min-w-0 flex-1 op-body text-muted-foreground">{{ httpErrorMessage(settings.error.value, "Não deu para ler as maquininhas. Confira a conexão e tente de novo.") }}</p>
      <UiButton variant="outline" @click="settings.refresh()">Tentar de novo</UiButton>
    </div>
    <p v-else-if="!settings.data.value" class="op-body text-muted-foreground">Lendo as maquininhas…</p>
    <template v-else>
      <p v-if="!settings.data.value.card_machines.length" class="rounded-xl border border-dashed p-6 text-center op-body text-muted-foreground">Nenhuma maquininha cadastrada.</p>
      <ul v-else class="divide-y divide-border rounded-xl border border-border bg-card">
        <li
          v-for="machine in settings.data.value.card_machines"
          :key="machine.ref"
          class="flex items-center gap-3 px-4 py-3"
          :data-settings-card-machine="machine.ref"
        >
          <span class="grid size-10 place-items-center rounded-lg bg-secondary"><Icon name="lucide:credit-card" class="size-5" aria-hidden="true" /></span>
          <button type="button" class="min-w-0 flex-1 text-left" @click="edit(machine)">
            <p class="truncate op-label font-semibold" :class="machine.active ? '' : 'text-muted-foreground line-through'">{{ machine.label }}</p>
            <p class="truncate op-micro text-muted-foreground">
              {{ machine.identification }} · {{ machine.with_order ? `na entrega ${machine.with_order}` : (machine.active ? "no balcão" : "desativada") }}
            </p>
          </button>
          <UiSwitch
            :model-value="machine.active"
            :disabled="Boolean(machine.with_order) || settings.saving.value === 'card_machine'"
            :aria-label="`${machine.label} ativa`"
            @update:model-value="toggle(machine)"
          />
        </li>
      </ul>
    </template>

    <UiDialog :open="Boolean(editing)" @update:open="(value) => { if (!value) editing = null; }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>{{ editing?.ref ? "Maquininha" : "Nova maquininha" }}</UiDialogTitle>
          <UiDialogDescription>O nome é o que o entregador lê; a identificação é o número de série ou a etiqueta colada nela.</UiDialogDescription>
        </UiDialogHeader>
        <form v-if="editing" class="grid gap-3" @submit.prevent="submit">
          <label class="grid gap-1.5">
            <span class="op-label text-muted-foreground">Nome</span>
            <UiInput v-model="editing.label" placeholder="Maquininha 2" autofocus />
          </label>
          <label class="grid gap-1.5">
            <span class="op-label text-muted-foreground">Identificação</span>
            <UiInput v-model="editing.identification" placeholder="SN 0042" />
          </label>
          <UiDialogFooter class="gap-2">
            <UiButton type="button" variant="outline" @click="editing = null">Cancelar</UiButton>
            <UiButton type="submit" :disabled="settings.saving.value === 'card_machine'">{{ editing.ref ? "Gravar" : "Cadastrar" }}</UiButton>
          </UiDialogFooter>
        </form>
      </UiDialogContent>
    </UiDialog>
  </PosSettingsShell>
</template>
