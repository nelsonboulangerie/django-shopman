<script setup lang="ts">
// Duplicar cliente: cria um cadastro novo a partir de outro, sem herdar identidade.
//
// A cópia é do servidor (POST customers/<ref>/duplicate/): leva o relacionamento
// comercial e os endereços, e deixa de fora documento, telefone e e-mail, que são
// únicos por cadastro. Aqui só se escolhe o nome da cópia e se confirma a intenção.
import { computed, nextTick, reactive, watch } from "vue";

import type { CustomerDetailProjection } from "~/generated/ordersContract";
import type { CustomerDuplicatePayload } from "~/types/customers";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import { useDirtyForm } from "../../../operator-kit/app/composables/useDirtyForm";

const props = withDefaults(defineProps<{
  open: boolean;
  source?: CustomerDetailProjection | null;
  busy?: boolean;
  error?: string;
}>(), {
  source: null,
  busy: false,
  error: "",
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: CustomerDuplicatePayload];
}>();

const form = reactive({ firstName: "", lastName: "" });
const { dirty, changedKeys, capture } = useDirtyForm(() => ({ ...form }));

watch(
  () => [props.open, props.source?.ref, props.source?.revision] as const,
  () => {
    if (!props.open || !props.source) return;
    form.firstName = props.source.first_name;
    form.lastName = props.source.last_name
      ? props.source.last_name + " (cópia)"
      : "(cópia)";
    nextTick(capture);
  },
  { immediate: true },
);

const description = computed(() =>
  props.source ? "Cópia de " + props.source.name + " (" + props.source.ref + ")." : "",
);
const valid = computed(() => Boolean(form.firstName.trim()) && Boolean(props.source?.revision));
const disabledReason = computed(() => (valid.value ? "" : "Informe o nome da cópia."));

function save() {
  if (!valid.value || !props.source) return;
  emit("save", {
    expectedRevision: props.source.revision,
    firstName: form.firstName.trim(),
    lastName: form.lastName.trim(),
  });
}
</script>

<template>
  <OperatorFormShell
    :open="open"
    title="Duplicar cliente"
    size="standard"
    :description="description"
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    save-label="Duplicar cliente"
    save-icon="i-lucide-copy-plus"
    :save-disabled="!valid"
    :save-disabled-reason="disabledReason"
    :save-attrs="{ 'data-testid': 'customer-duplicate-submit' }"
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
      icon="i-lucide-shield-check"
      title="O que a cópia leva"
      description="Leva grupo comercial, etiquetas, conta na casa, preferências fiscais e endereços. Não leva CPF/CNPJ, telefone nem e-mail: identidade e contato são únicos por cadastro. Informe os novos na ficha depois de criar."
    />

    <OperatorFormSection section-key="identity" title="Nome da cópia" description="Só o nome se define agora; o resto se edita na ficha.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Nome" required>
          <NuxtInput v-model="form.firstName" class="w-full" autofocus data-testid="customer-duplicate-first-name" />
        </NuxtFormField>
        <NuxtFormField label="Sobrenome">
          <NuxtInput v-model="form.lastName" class="w-full" data-testid="customer-duplicate-last-name" />
        </NuxtFormField>
      </div>
    </OperatorFormSection>
  </OperatorFormShell>
</template>
