<script setup lang="ts">
import type { RecipeDuplicatePayload, RecipeEntryDetailProjection } from "~/types/recipeBook";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import { useDirtyForm } from "../../../operator-kit/app/composables/useDirtyForm";

const props = defineProps<{
  open: boolean;
  source: RecipeEntryDetailProjection | null;
  fromVersion?: number | null;
  busy?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: RecipeDuplicatePayload];
}>();

const form = reactive({ name: "", ref: "", outputSku: "" });
const { dirty, changedKeys, capture } = useDirtyForm(() => ({ ...form }));

watch(
  () => [props.open, props.source?.ref, props.fromVersion],
  () => {
    if (!props.open || !props.source) return;
    form.name = `${props.source.name} (cópia)`;
    form.ref = "";
    form.outputSku = "";
    nextTick(capture);
  },
  { immediate: true },
);

const valid = computed(() => !!form.name.trim() && !!props.source?.revision);
const disabledReason = computed(() => valid.value ? "" : "Informe o nome da nova receita.");

function save() {
  if (!valid.value || !props.source) return;
  emit("save", {
    name: form.name.trim(),
    ...(form.ref.trim() ? { ref: form.ref.trim() } : {}),
    ...(form.outputSku.trim() ? { outputSku: form.outputSku.trim().toUpperCase() } : {}),
    ...(props.fromVersion ? { fromVersion: props.fromVersion } : {}),
    expectedRevision: props.source.revision,
  });
}
</script>

<template>
  <OperatorFormShell
    :open="open"
    title="Duplicar receita"
    :description="source ? `Cópia da versão ${fromVersion ?? source.current_version_number ?? 'mais recente'} de ${source.name}.` : ''"
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    save-label="Duplicar receita"
    save-icon="i-lucide-copy-plus"
    :save-disabled="!valid"
    :save-disabled-reason="disabledReason"
    @update:open="emit('update:open', $event)"
    @save="save"
  >
    <NuxtAlert
      color="info"
      variant="subtle"
      icon="i-lucide-copy"
      title="A cópia nasce como rascunho"
      description="Leva fórmula, rendimento, etapas e notas. Não cria ficha ativa nem herda capacidade, validade ou histórico de produção."
    />

    <OperatorFormSection section-key="identity" title="Nova identidade" description="Nome obrigatório; referência vazia é gerada do nome.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Nome" required class="sm:col-span-2">
          <NuxtInput v-model="form.name" class="w-full" autofocus />
        </NuxtFormField>
        <NuxtFormField label="Referência" description="Sem acento; deixe vazia para gerar.">
          <NuxtInput v-model="form.ref" class="w-full" :ui="{ base: 'font-mono' }" />
        </NuxtFormField>
        <NuxtFormField label="SKU de saída" description="Pode ser associado depois.">
          <NuxtInput v-model="form.outputSku" class="w-full" :ui="{ base: 'font-mono uppercase' }" />
        </NuxtFormField>
      </div>
    </OperatorFormSection>
  </OperatorFormShell>
</template>
