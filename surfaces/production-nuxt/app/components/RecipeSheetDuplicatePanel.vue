<script setup lang="ts">
// Duplicar a ficha de execução no casco canônico: a cópia nasce INATIVA (é
// revisão) e leva itens e operação; o carimbo de quem revisou a validade não
// viaja, então a cópia pede nova confirmação. Quem grava é a página.
import type { RecipeSheetDetailProjection, RecipeSheetDuplicatePayload } from "~/types/recipeBook";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import { useDirtyForm } from "../../../operator-kit/app/composables/useDirtyForm";

const props = defineProps<{
  open: boolean;
  source: RecipeSheetDetailProjection | null;
  busy?: boolean;
}>();
const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: RecipeSheetDuplicatePayload];
}>();

const form = reactive({ name: "", ref: "", outputSku: "" });
const { dirty, changedKeys, capture } = useDirtyForm(() => ({ ...form }));

watch(
  () => [props.open, props.source?.revision],
  () => {
    if (!props.open || !props.source) return;
    form.name = props.source.name + " (cópia)";
    form.ref = "";
    form.outputSku = props.source.output_sku;
    nextTick(capture);
  },
  { immediate: true },
);

const valid = computed(() => !!form.name.trim() && !!props.source?.revision);
const disabledReason = computed(() => (valid.value ? "" : "Informe o nome da nova ficha."));

function save() {
  if (!valid.value || !props.source) return;
  emit("save", {
    name: form.name.trim(),
    ...(form.ref.trim() ? { ref: form.ref.trim() } : {}),
    ...(form.outputSku.trim() ? { output_sku: form.outputSku.trim().toUpperCase() } : {}),
    expectedRevision: props.source.revision,
  });
}
</script>

<template>
  <OperatorFormShell
    :open="open"
    title="Duplicar ficha de execução"
    size="standard"
    :description="source ? `Cópia de ${source.name}. Leva ingredientes e operação; nasce inativa.` : ''"
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    save-label="Duplicar ficha"
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
      title="A cópia nasce inativa"
      description="É uma ficha em revisão. Ativar depois depende de não haver outra ativa para o mesmo SKU."
    />

    <OperatorFormSection section-key="identity" title="Nova identidade" description="Nome obrigatório; referência vazia é gerada do nome.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Nome" required class="sm:col-span-2">
          <NuxtInput v-model="form.name" class="w-full" autofocus data-focus-control />
        </NuxtFormField>
        <NuxtFormField label="Referência" description="Sem acento; deixe vazia para gerar.">
          <NuxtInput v-model="form.ref" class="w-full" :ui="{ base: 'font-mono' }" />
        </NuxtFormField>
        <NuxtFormField label="SKU de saída" description="Normalmente o mesmo da cópia.">
          <NuxtInput v-model="form.outputSku" class="w-full" :ui="{ base: 'font-mono uppercase' }" />
        </NuxtFormField>
      </div>
    </OperatorFormSection>
  </OperatorFormShell>
</template>
