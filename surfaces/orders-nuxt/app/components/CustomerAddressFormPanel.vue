<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import { useConfirm } from "../../../operator-kit/app/composables/useConfirm";
import type { CustomerAddressProjection } from "~/generated/ordersContract";
import type { CustomerAddressMutationPayload } from "~/types/customers";

const props = withDefaults(defineProps<{
  open: boolean;
  address?: CustomerAddressProjection | null;
  busy?: boolean;
  error?: string;
  fieldErrors?: Record<string, string>;
}>(), { address: null, busy: false, error: "", fieldErrors: () => ({}) });

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: CustomerAddressMutationPayload];
  remove: [address: CustomerAddressProjection];
}>();

const form = reactive({
  label: "home",
  labelCustom: "",
  formattedAddress: "",
  route: "",
  streetNumber: "",
  complement: "",
  neighborhood: "",
  city: "",
  stateCode: "",
  postalCode: "",
  deliveryInstructions: "",
  isDefault: false,
});
const baseline = ref("");

function state() {
  return Object.fromEntries(Object.entries(form).map(([key, value]) => [key, typeof value === "string" ? value.trim() : value]));
}
function reset() {
  const address = props.address;
  Object.assign(form, {
    label: address?.label_code ?? "home",
    labelCustom: address?.label_code === "other" ? address.label : "",
    formattedAddress: address?.formatted_address ?? "",
    route: address?.route ?? "",
    streetNumber: address?.street_number ?? "",
    complement: address?.complement ?? "",
    neighborhood: address?.neighborhood ?? "",
    city: address?.city ?? "",
    stateCode: address?.state_code ?? "",
    postalCode: address?.postal_code ?? "",
    deliveryInstructions: address?.delivery_instructions ?? "",
    isDefault: address?.is_default ?? false,
  });
  baseline.value = JSON.stringify(state());
}
watch(() => [props.open, props.address?.revision] as const, ([open]) => { if (open) reset(); }, { immediate: true });

const changedKeys = computed(() => {
  const before = JSON.parse(baseline.value || "{}") as Record<string, unknown>;
  return Object.entries(state()).filter(([key, value]) => before[key] !== value).map(([key]) => key);
});
const disabledReason = computed(() => {
  if (!form.formattedAddress.trim()) return "Informe o endereço completo.";
  if (form.label === "other" && !form.labelCustom.trim()) return "Dê um nome ao endereço.";
  return "";
});

function submit() {
  if (disabledReason.value) return;
  emit("save", {
    ...(props.address?.revision ? { expectedRevision: props.address.revision } : {}),
    ...state(),
  } as CustomerAddressMutationPayload);
}

const confirm = useConfirm();
async function remove() {
  if (!props.address) return;
  const accepted = await confirm({
    title: `Remover ${props.address.label.toLowerCase()}?`,
    description: "O endereço sai do cadastro. Pedidos antigos preservam o endereço que já foi gravado neles.",
    confirmLabel: "Remover endereço",
    cancelLabel: "Manter endereço",
  });
  if (accepted) emit("remove", props.address);
}
</script>

<template>
  <OperatorFormShell
    :open="open"
    :title="address ? `Editar ${address.label}` : 'Adicionar endereço'"
    description="Endereço de entrega do cadastro. Edição manual remove o selo de verificação até nova conferência."
    size="wide"
    :dirty="changedKeys.length > 0"
    :dirty-count="changedKeys.length"
    :busy="busy"
    :save-label="address ? 'Salvar endereço' : 'Adicionar endereço'"
    save-icon="i-lucide-map-pin-check"
    :save-disabled="Boolean(disabledReason)"
    :save-disabled-reason="disabledReason"
    :save-attrs="{ 'data-testid': 'address-submit' }"
    @update:open="emit('update:open', $event)"
    @save="submit"
  >
    <template #lead>
      <NuxtButton v-if="address" color="error" variant="ghost" icon="i-lucide-trash-2" label="Remover" :disabled="busy" @click="remove" />
    </template>
    <NuxtAlert v-if="error" color="error" variant="subtle" icon="i-lucide-circle-alert" :description="error" />
    <OperatorFormSection section-key="address" title="Endereço" description="Use a linha completa e, quando souber, preencha os componentes para facilitar a entrega.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Rótulo" :error="fieldErrors.label">
          <NuxtSelect v-model="form.label" :items="[{ value: 'home', label: 'Casa' }, { value: 'work', label: 'Trabalho' }, { value: 'other', label: 'Outro' }]" value-key="value" label-key="label" class="w-full" />
        </NuxtFormField>
        <NuxtFormField v-if="form.label === 'other'" label="Nome do endereço" required :error="fieldErrors.labelCustom">
          <NuxtInput v-model="form.labelCustom" class="w-full" />
        </NuxtFormField>
        <NuxtFormField label="Endereço completo" required class="sm:col-span-2" :error="fieldErrors.formattedAddress">
          <NuxtInput v-model="form.formattedAddress" class="w-full" data-testid="address-formatted" />
        </NuxtFormField>
        <NuxtFormField label="Logradouro" :error="fieldErrors.route"><NuxtInput v-model="form.route" class="w-full" /></NuxtFormField>
        <NuxtFormField label="Número" :error="fieldErrors.streetNumber"><NuxtInput v-model="form.streetNumber" class="w-full" /></NuxtFormField>
        <NuxtFormField label="Complemento" :error="fieldErrors.complement"><NuxtInput v-model="form.complement" class="w-full" /></NuxtFormField>
        <NuxtFormField label="Bairro" :error="fieldErrors.neighborhood"><NuxtInput v-model="form.neighborhood" class="w-full" /></NuxtFormField>
        <NuxtFormField label="Cidade" :error="fieldErrors.city"><NuxtInput v-model="form.city" class="w-full" /></NuxtFormField>
        <NuxtFormField label="UF" :error="fieldErrors.stateCode"><NuxtInput v-model="form.stateCode" maxlength="5" class="w-full uppercase" /></NuxtFormField>
        <NuxtFormField label="CEP" :error="fieldErrors.postalCode"><NuxtInput v-model="form.postalCode" inputmode="numeric" class="w-full" /></NuxtFormField>
        <NuxtFormField
          label="Preferência"
          :description="address?.is_default ? 'Para trocar o padrão, edite outro endereço e marque-o como padrão.' : 'Usado primeiro nas próximas entregas.'"
        >
          <NuxtCheckbox v-model="form.isDefault" label="Endereço padrão" :disabled="Boolean(address?.is_default)" />
        </NuxtFormField>
      </div>
    </OperatorFormSection>
    <OperatorFormSection section-key="delivery" title="Instruções de entrega" description="Portaria, referência e orientação que ajudam quem entrega.">
      <NuxtFormField :error="fieldErrors.deliveryInstructions">
        <NuxtTextarea v-model="form.deliveryInstructions" :rows="3" class="w-full" />
      </NuxtFormField>
    </OperatorFormSection>
  </OperatorFormShell>
</template>
