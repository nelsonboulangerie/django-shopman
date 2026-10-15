<script setup lang="ts">
// Etiquetas em lote: adiciona ou remove a mesma etiqueta de vários cadastros de uma vez.
//
// A seleção é da lista e pode atravessar páginas; o servidor aplica numa ida
// (POST customers/bulk/), ignora cadastros inativos ou que sumiram e diz quantos
// entraram. Remover etiqueta que não existe não muda nada, então repetir é seguro.
import { computed, nextTick, reactive, watch } from "vue";

import type { CustomerBulkOperation } from "~/types/customers";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import { useDirtyForm } from "../../../operator-kit/app/composables/useDirtyForm";

const props = withDefaults(defineProps<{
  open: boolean;
  count?: number;
  busy?: boolean;
  error?: string;
}>(), {
  count: 0,
  busy: false,
  error: "",
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: { operation: CustomerBulkOperation; tags: string[] }];
}>();

const operationItems = [
  { value: "add_tags", label: "Adicionar" },
  { value: "remove_tags", label: "Remover" },
];

const form = reactive({ operation: "add_tags" as CustomerBulkOperation, tagsText: "" });
const { dirty, changedKeys, capture } = useDirtyForm(() => ({ ...form }));

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    form.operation = "add_tags";
    form.tagsText = "";
    nextTick(capture);
  },
  { immediate: true },
);

const tags = computed(() =>
  form.tagsText.split(",").map((tag) => tag.trim()).filter(Boolean),
);
const valid = computed(() => tags.value.length > 0);
const disabledReason = computed(() => (valid.value ? "" : "Informe ao menos uma etiqueta."));
const description = computed(() =>
  props.count === 1 ? "Aplica a 1 cliente." : "Aplica a " + props.count + " clientes.",
);

function save() {
  if (!valid.value) return;
  emit("save", { operation: form.operation, tags: tags.value });
}
</script>

<template>
  <OperatorFormShell
    :open="open"
    title="Etiquetas em lote"
    size="standard"
    :description="description"
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    save-label="Aplicar etiquetas"
    save-icon="i-lucide-tags"
    :save-disabled="!valid"
    :save-disabled-reason="disabledReason"
    :save-attrs="{ 'data-testid': 'customer-bulk-submit' }"
    @update:open="emit('update:open', $event)"
    @save="save"
  >
    <NuxtAlert
      v-if="error"
      color="error"
      variant="subtle"
      icon="i-lucide-circle-alert"
      :description="error"
    />
    <NuxtAlert
      color="info"
      variant="subtle"
      icon="i-lucide-users"
      title="Só os cadastros ativos entram"
      description="Cadastros unificados ou desativados ficam de fora, e o aviso diz quantos foram. A etiqueta não mexe em preço: para preço, o caminho é o grupo comercial."
    />

    <OperatorFormSection section-key="tags" title="A ação" description="Uma etiqueta por vez, aplicada a toda a seleção.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Ação">
          <NuxtSelect
            v-model="form.operation"
            :items="operationItems"
            value-key="value"
            label-key="label"
            class="w-full"
          />
        </NuxtFormField>
        <NuxtFormField label="Etiquetas" required description="Separe por vírgula. Ex.: vizinho, sem glúten.">
          <NuxtInput v-model="form.tagsText" class="w-full" data-testid="customer-bulk-tags" />
        </NuxtFormField>
      </div>
    </OperatorFormSection>
  </OperatorFormShell>
</template>
