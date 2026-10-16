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
      <NuxtButton icon="i-lucide-plus" label="Nova maquininha" data-settings-card-machine-add @click="addNew" />
    </template>
    <OperatorScreenState v-if="settings.error.value && !settings.data.value" state="error" what="as maquininhas" @retry="settings.refresh()" />
    <OperatorScreenState v-else-if="!settings.data.value" state="loading" what="as maquininhas" />
    <template v-else>
      <OperatorScreenState
        v-if="!settings.data.value.card_machines.length"
        state="empty"
        icon="i-lucide-credit-card"
        title="Nenhuma maquininha cadastrada."
        description="Cadastre a primeira em Nova maquininha."
      />
      <ul v-else class="divide-y divide-border rounded-xl border border-border bg-card">
        <li
          v-for="machine in settings.data.value.card_machines"
          :key="machine.ref"
          class="flex items-center gap-3 px-4 py-3"
          :data-settings-card-machine="machine.ref"
        >
          <span class="grid size-10 place-items-center rounded-lg bg-secondary"><Icon name="lucide:credit-card" class="size-5" aria-hidden="true" /></span>
          <NuxtButton
            color="neutral"
            variant="ghost"
            class="justify-start -my-1 min-w-0 flex-1 flex-col items-start gap-0 text-left"
            :data-settings-card-machine-edit="machine.ref"
            @click="edit(machine)"
          >
            <span class="block w-full truncate op-label font-semibold" :class="machine.active ? '' : 'text-muted-foreground line-through'">{{ machine.label }}</span>
            <span class="block w-full truncate op-micro font-normal text-muted-foreground">
              {{ machine.identification }} · {{ machine.with_order ? `na entrega ${machine.with_order}` : (machine.active ? "no balcão" : "desativada") }}
            </span>
          </NuxtButton>
          <UiSwitch
            :model-value="machine.active"
            :disabled="Boolean(machine.with_order) || settings.saving.value === 'card_machine'"
            :aria-label="`${machine.label} ativa`"
            @update:model-value="toggle(machine)"
          />
        </li>
      </ul>
    </template>

    <NuxtModal
      :open="Boolean(editing)"
      :title="editing?.ref ? 'Maquininha' : 'Nova maquininha'"
      description="O nome é o que o entregador lê; a identificação é o número de série ou a etiqueta colada nela."
      :ui="{ content: 'sm:max-w-sm' }"
      data-settings-card-machine-dialog
      @update:open="(value) => { if (!value) editing = null; }"
    >
      <template #body>
        <form v-if="editing" id="card-machine-form" class="grid gap-3" @submit.prevent="submit">
          <NuxtFormField label="Nome">
            <NuxtInput v-model="editing.label" class="w-full" placeholder="Maquininha 2" autofocus />
          </NuxtFormField>
          <NuxtFormField label="Identificação">
            <NuxtInput v-model="editing.identification" class="w-full" placeholder="SN 0042" />
          </NuxtFormField>
        </form>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton color="neutral" variant="outline" label="Cancelar" @click="editing = null" />
          <NuxtButton
            type="submit"
            form="card-machine-form"
            :label="editing?.ref ? 'Gravar' : 'Cadastrar'"
            :loading="settings.saving.value === 'card_machine'"
            :disabled="settings.saving.value === 'card_machine'"
          />
        </div>
      </template>
    </NuxtModal>
  </PosSettingsShell>
</template>
