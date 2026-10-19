<script setup lang="ts">
// Mudar grupo em lote: põe a seleção da lista num grupo comercial, ou tira dela.
//
// O grupo vem de fora da tela, então é diálogo (D9). O cliente pode estar em vários
// grupos: adicionar não tira dos outros, e tirar devolve ao grupo padrão quem ficaria
// sem nenhum. O servidor aplica numa ida (POST customers/groups/<ref>/members/) e
// repetir não muda nada.
import type { CustomerGroupMembersOperation } from "~/types/customerGroups";
import {
  GROUP_MEMBER_OPERATIONS,
  groupMembersActionLabel,
  groupMembersHint,
} from "~/presentation/customerGroupMembers";

const props = withDefaults(
  defineProps<{
    open: boolean;
    count?: number;
    groups?: { value: string; label: string }[];
    /** O grupo que recorta a lista: vem escolhido, porque é o mais provável. */
    initialGroup?: string;
    busy?: boolean;
    error?: string;
  }>(),
  {
    count: 0,
    groups: () => [],
    initialGroup: "",
    busy: false,
    error: "",
  },
);

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [
    payload: { operation: CustomerGroupMembersOperation; groupRef: string },
  ];
}>();

const operation = ref<CustomerGroupMembersOperation>("add");
const groupRef = ref("");

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    // Quem abriu a lista recortada por um grupo veio, quase sempre, tirar dele.
    operation.value = props.initialGroup ? "remove" : "add";
    groupRef.value = props.groups.some(
      (group) => group.value === props.initialGroup,
    )
      ? props.initialGroup
      : "";
  },
  { immediate: true },
);

const groupName = computed(
  () =>
    props.groups.find((group) => group.value === groupRef.value)?.label ?? "",
);
const actionLabel = computed(() =>
  groupMembersActionLabel(operation.value, props.count, groupName.value),
);

function close(open: boolean) {
  if (!open && props.busy) return;
  emit("update:open", open);
}

function confirm() {
  if (!groupRef.value || props.busy) return;
  emit("save", { operation: operation.value, groupRef: groupRef.value });
}
</script>

<template>
  <NuxtModal
    :open="open"
    title="Mudar grupo"
    :description="
      count === 1
        ? 'Vale para 1 cliente selecionado.'
        : `Vale para ${count} clientes selecionados.`
    "
    data-customer-group-bulk-dialog
    @update:open="close"
  >
    <template #body>
      <div class="grid gap-4">
        <NuxtFormField
          label="O que fazer"
          :description="groupMembersHint(operation)"
        >
          <NuxtRadioGroup
            v-model="operation"
            :items="GROUP_MEMBER_OPERATIONS"
            variant="card"
            data-customer-group-bulk-operation
          />
        </NuxtFormField>
        <NuxtFormField label="Grupo" required>
          <NuxtSelect
            v-model="groupRef"
            :items="groups"
            value-key="value"
            label-key="label"
            placeholder="Escolha o grupo"
            class="w-full"
            data-customer-group-bulk-group
          />
        </NuxtFormField>
        <NuxtAlert
          v-if="error"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :description="error"
        />
      </div>
    </template>
    <template #footer>
      <div
        class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end"
      >
        <p v-if="!groupRef" class="text-xs text-muted-foreground sm:me-auto">
          Escolha o grupo.
        </p>
        <NuxtButton
          label="Voltar"
          color="neutral"
          variant="outline"
          :disabled="busy"
          @click="close(false)"
        />
        <NuxtButton
          :label="actionLabel"
          :title="actionLabel"
          :aria-label="actionLabel"
          icon="i-lucide-users"
          color="primary"
          :disabled="busy || !groupRef"
          :loading="busy"
          data-customer-group-bulk-confirm
          @click="confirm"
        />
      </div>
    </template>
  </NuxtModal>
</template>
