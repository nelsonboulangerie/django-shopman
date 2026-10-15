<script setup lang="ts">
import { computed, nextTick, reactive, watch } from "vue";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import UiDateField from "../../../operator-kit/app/components/UiDateField.vue";
import { useDirtyForm } from "../../../operator-kit/app/composables/useDirtyForm";
import type { CustomerDetailProjection, CustomerFormOptionsProjection } from "~/generated/ordersContract";
import type { CustomerMutationPayload } from "~/types/customers";

const props = withDefaults(defineProps<{
  open: boolean;
  customer?: CustomerDetailProjection | null;
  options: CustomerFormOptionsProjection;
  busy?: boolean;
  error?: string;
  fieldErrors?: Record<string, string>;
}>(), {
  customer: null,
  busy: false,
  error: "",
  fieldErrors: () => ({}),
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: CustomerMutationPayload];
}>();

type FormState = {
  firstName: string;
  lastName: string;
  customerType: string;
  document: string;
  birthday: string;
  phone: string;
  email: string;
  priceTierRef: string;
  tagsText: string;
  notes: string;
  houseAccount: boolean;
  houseAccountLimit: string;
  fiscalCpfNaNota: boolean;
  fiscalEmailReceipt: boolean;
};

const form = reactive<FormState>({
  firstName: "",
  lastName: "",
  customerType: "individual",
  document: "",
  birthday: "",
  phone: "",
  email: "",
  priceTierRef: "",
  tagsText: "",
  notes: "",
  houseAccount: false,
  houseAccountLimit: "",
  fiscalCpfNaNota: false,
  fiscalEmailReceipt: false,
});

function snapshot(): FormState {
  return {
    firstName: form.firstName.trim(),
    lastName: form.lastName.trim(),
    customerType: form.customerType,
    document: form.document.trim(),
    birthday: form.birthday,
    phone: form.phone.trim(),
    email: form.email.trim(),
    priceTierRef: form.priceTierRef,
    tagsText: form.tagsText.trim(),
    notes: form.notes.trim(),
    houseAccount: form.houseAccount,
    houseAccountLimit: form.houseAccountLimit.trim(),
    fiscalCpfNaNota: form.fiscalCpfNaNota,
    fiscalEmailReceipt: form.fiscalEmailReceipt,
  };
}

const { dirty, changedKeys, capture } = useDirtyForm(snapshot);

function reset() {
  const customer = props.customer;
  Object.assign(form, {
    firstName: customer?.first_name ?? "",
    lastName: customer?.last_name ?? "",
    customerType: customer?.customer_type ?? "individual",
    document: customer?.document ?? "",
    birthday: customer?.birthday ?? "",
    phone: customer?.phone ?? "",
    email: customer?.email ?? "",
    priceTierRef: customer?.price_tier_ref ?? props.options.price_tiers[0]?.value ?? "",
    tagsText: customer?.tags.join(", ") ?? "",
    notes: customer?.notes ?? "",
    houseAccount: customer?.house_account ?? false,
    houseAccountLimit: customer?.house_account_limit ?? "",
    fiscalCpfNaNota: customer?.fiscal_cpf_na_nota ?? false,
    fiscalEmailReceipt: customer?.fiscal_email_receipt ?? false,
  });
  nextTick(capture);
}

watch(() => [props.open, props.customer?.revision, props.options] as const, ([open]) => {
  if (open) reset();
}, { immediate: true });

const disabledReason = computed(() => {
  if (!form.firstName.trim()) return "Informe o nome do cliente.";
  if (form.fiscalCpfNaNota && !form.document.trim()) return "Informe o CPF ou CNPJ usado na nota.";
  if (form.fiscalEmailReceipt && !form.email.trim()) return "Informe o e-mail que receberá a nota.";
  if (form.houseAccountLimit.trim() && !form.houseAccount) return "Ative a conta na casa para definir um limite.";
  return "";
});

function submit() {
  if (disabledReason.value) return;
  emit("save", {
    ...(props.customer?.revision ? { expectedRevision: props.customer.revision } : {}),
    firstName: form.firstName.trim(),
    lastName: form.lastName.trim(),
    customerType: form.customerType,
    document: form.document.trim(),
    birthday: form.birthday,
    phone: form.phone.trim(),
    email: form.email.trim(),
    priceTierRef: form.priceTierRef,
    tags: form.tagsText.split(",").map((tag) => tag.trim()).filter(Boolean),
    notes: form.notes.trim(),
    houseAccount: form.houseAccount,
    houseAccountLimit: form.houseAccount ? form.houseAccountLimit.trim() : "",
    fiscalCpfNaNota: form.fiscalCpfNaNota,
    fiscalEmailReceipt: form.fiscalEmailReceipt,
  });
}
</script>

<template>
  <OperatorFormShell
    :open="open"
    :title="customer ? `Editar ${customer.name}` : 'Cadastrar cliente'"
    description="Identidade, contato e preferências comerciais em uma única ficha. Consentimentos continuam com evidência própria."
    size="wide"
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    :save-label="customer ? 'Salvar cliente' : 'Cadastrar cliente'"
    save-icon="i-lucide-user-round-check"
    :save-disabled="Boolean(disabledReason)"
    :save-disabled-reason="disabledReason"
    :save-attrs="{ 'data-testid': 'customer-submit' }"
    :discard-attrs="{ 'data-testid': 'customer-discard' }"
    @update:open="emit('update:open', $event)"
    @save="submit"
  >
    <NuxtAlert
      v-if="error"
      color="error"
      variant="subtle"
      icon="i-lucide-circle-alert"
      :description="error"
    />

    <OperatorFormSection section-key="identity" title="Identidade" description="O CPF/CNPJ é opcional, mas precisa conferir quando informado.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Nome" required :error="fieldErrors.firstName">
          <NuxtInput v-model="form.firstName" class="w-full" autofocus data-testid="customer-first-name" />
        </NuxtFormField>
        <NuxtFormField label="Sobrenome" :error="fieldErrors.lastName">
          <NuxtInput v-model="form.lastName" class="w-full" />
        </NuxtFormField>
        <NuxtFormField label="Tipo" :error="fieldErrors.customerType">
          <NuxtSelect v-model="form.customerType" :items="options.customer_types" value-key="value" label-key="label" class="w-full" />
        </NuxtFormField>
        <NuxtFormField label="CPF ou CNPJ" :error="fieldErrors.document">
          <NuxtInput v-model="form.document" inputmode="numeric" class="w-full" />
        </NuxtFormField>
        <NuxtFormField label="Data de nascimento" :error="fieldErrors.birthday">
          <UiDateField v-model="form.birthday" label="Data de nascimento" class="w-full" />
        </NuxtFormField>
      </div>
    </OperatorFormSection>

    <OperatorFormSection section-key="contact" title="Contato" description="Telefone e e-mail são normalizados; um contato não pode pertencer a dois cadastros.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Telefone" :error="fieldErrors.phone">
          <NuxtInput v-model="form.phone" type="tel" inputmode="tel" class="w-full" />
        </NuxtFormField>
        <NuxtFormField label="E-mail" :error="fieldErrors.email">
          <NuxtInput v-model="form.email" type="email" inputmode="email" class="w-full" data-testid="customer-email" />
        </NuxtFormField>
      </div>
      <NuxtAlert
        color="info"
        variant="subtle"
        icon="i-lucide-shield-check"
        title="Contato não é consentimento"
        description="Cadastrar telefone ou e-mail não autoriza comunicação. Opt-in e opt-out continuam na trilha LGPD com origem, data e evidência."
      />
    </OperatorFormSection>

    <OperatorFormSection section-key="commercial" title="Relacionamento comercial" description="Grupo comercial altera preço e vantagens; etiquetas só organizam o atendimento.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Grupo comercial" :error="fieldErrors.priceTierRef">
          <NuxtSelect v-model="form.priceTierRef" :items="options.price_tiers" value-key="value" label-key="label" class="w-full" />
        </NuxtFormField>
        <NuxtFormField label="Etiquetas" description="Separe por vírgula. Ex.: vizinho, sem glúten." :error="fieldErrors.tags">
          <NuxtInput v-model="form.tagsText" class="w-full" />
        </NuxtFormField>
        <NuxtCheckbox v-model="form.houseAccount" label="Pode comprar em conta" />
        <NuxtFormField label="Limite da conta (R$)" description="Em branco, sem limite." :error="fieldErrors.houseAccountLimit">
          <NuxtInput v-model="form.houseAccountLimit" inputmode="decimal" :disabled="!form.houseAccount" class="w-full" data-testid="customer-house-limit" />
        </NuxtFormField>
      </div>
    </OperatorFormSection>

    <OperatorFormSection section-key="fiscal" title="Preferências fiscais" description="São padrões do cadastro; cada venda ainda pode ser ajustada.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtCheckbox v-model="form.fiscalCpfNaNota" label="CPF/CNPJ na nota por padrão" />
        <NuxtCheckbox v-model="form.fiscalEmailReceipt" label="Enviar nota por e-mail por padrão" />
      </div>
    </OperatorFormSection>

    <OperatorFormSection section-key="notes" title="Observações internas" description="Aparecem só para a equipe.">
      <NuxtFormField :error="fieldErrors.notes">
        <NuxtTextarea v-model="form.notes" :rows="4" class="w-full" />
      </NuxtFormField>
    </OperatorFormSection>
  </OperatorFormShell>
</template>
