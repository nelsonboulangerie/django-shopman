<script setup lang="ts">
// O cadastro do fornecedor no casco da suíte: criar, editar e duplicar, com os
// contatos como parte do cadastro (antes eles só existiam no Admin). A cópia
// traz contatos e termos comerciais, e não o CNPJ: identidade não se duplica.
import type { PurchaseFormMode, Supplier, SupplierContact } from "~/types/purchase";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import { useDirtyForm } from "../../../operator-kit/app/composables/useDirtyForm";

const props = withDefaults(
  defineProps<{
    open: boolean;
    mode: PurchaseFormMode;
    source?: Supplier | null;
    busy?: boolean;
    error?: string;
  }>(),
  { source: null, busy: false, error: "" },
);

type ContactSave = {
  contactId: string | null;
  name: string;
  role: SupplierContact["role"];
  email: string;
  phone: string;
  notes: string;
  isPrimary: boolean;
  isActive: boolean;
};
const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: Record<string, unknown>];
  "save-contact": [payload: ContactSave];
}>();

const ROLE_OPTIONS = [
  { value: "sales", label: "Comercial" },
  { value: "finance", label: "Financeiro" },
  { value: "quality", label: "Qualidade" },
  { value: "general", label: "Geral" },
];

const form = reactive({
  ref: "",
  name: "",
  tradeName: "",
  document: "",
  email: "",
  phone: "",
  isActive: true,
  leadTimeDaysText: "",
  paymentTerm: "",
});
const contact = reactive({
  open: false,
  id: "",
  name: "",
  role: "sales" as SupplierContact["role"],
  email: "",
  phone: "",
  notes: "",
  isPrimary: false,
  isActive: true,
});

const isDuplicate = computed(() => props.mode === "duplicate");
const isEdit = computed(() => props.mode === "edit");
const title = computed(() => (isDuplicate.value ? "Duplicar fornecedor" : isEdit.value ? "Editar fornecedor" : "Novo fornecedor"));
const description = computed(() => {
  if (isDuplicate.value) return props.source ? "Cópia de " + props.source.displayName + " (" + props.source.ref + ")." : "";
  if (isEdit.value) return props.source ? props.source.displayName + " (" + props.source.ref + ")." : "";
  return "Cadastra a empresa com quem se compra, com os contatos e as condições.";
});
const saveLabel = computed(() => (isDuplicate.value ? "Duplicar fornecedor" : isEdit.value ? "Salvar fornecedor" : "Criar fornecedor"));
const duplicateNote =
  "A cópia traz os contatos e as condições comerciais (prazo e pagamento). Não traz o CNPJ nem o de-para de nota: confira antes de usar.";

function resetContact() {
  contact.open = false;
  contact.id = "";
  contact.name = "";
  contact.role = "sales";
  contact.email = "";
  contact.phone = "";
  contact.notes = "";
  contact.isPrimary = false;
  contact.isActive = true;
}

function reset() {
  const source = props.source;
  if (props.mode === "create" || !source) {
    form.ref = "";
    form.name = "";
    form.tradeName = "";
    form.document = "";
    form.email = "";
    form.phone = "";
    form.isActive = true;
    form.leadTimeDaysText = "";
    form.paymentTerm = "";
  } else if (isDuplicate.value) {
    form.ref = source.ref + "-2";
    form.name = source.name + " (cópia)";
    form.tradeName = "";
    form.document = "";
    form.email = "";
    form.phone = "";
    form.isActive = true;
    form.leadTimeDaysText = source.leadTimeDays ? String(source.leadTimeDays) : "";
    form.paymentTerm = source.paymentTerm;
  } else {
    form.ref = source.ref;
    form.name = source.name;
    form.tradeName = source.tradeName;
    form.document = source.document;
    form.email = source.email;
    form.phone = source.phone;
    form.isActive = source.isActive;
    form.leadTimeDaysText = source.leadTimeDays ? String(source.leadTimeDays) : "";
    form.paymentTerm = source.paymentTerm;
  }
  resetContact();
}

const { dirty, changedKeys, capture } = useDirtyForm(() => ({ ...form, contact: { ...contact } }));
const activeSection = ref<string | null>("identity");

watch(
  () => [props.open, props.mode, props.source?.ref],
  () => {
    if (!props.open) return;
    reset();
    activeSection.value = "identity";
    capture();
  },
  { immediate: true },
);

const leadTimeNumber = computed(() => {
  const text = form.leadTimeDaysText.trim();
  if (!text) return 0;
  const value = Number(text.replace(",", "."));
  return Number.isFinite(value) && value >= 0 ? Math.round(value) : null;
});
const leadTimeInvalid = computed(() => form.leadTimeDaysText.trim() !== "" && leadTimeNumber.value === null);
const sameSourceRef = computed(
  () => isDuplicate.value && Boolean(props.source) && form.ref.trim().toLowerCase() === props.source!.ref.trim().toLowerCase(),
);
const valid = computed(() => {
  if (isDuplicate.value && !form.ref.trim()) return false;
  if (isDuplicate.value && sameSourceRef.value) return false;
  if (!form.name.trim()) return false;
  if (leadTimeInvalid.value) return false;
  return true;
});
const saveDisabledReason = computed(() => {
  if (isDuplicate.value && !form.ref.trim()) return "Informe a referência da cópia.";
  if (isDuplicate.value && sameSourceRef.value) return "A referência da cópia precisa ser diferente da original.";
  if (!form.name.trim()) return "Informe a razão social para salvar.";
  if (leadTimeInvalid.value) return "O prazo de entrega é um número de dias.";
  return "";
});

function submit() {
  if (!valid.value) return;
  const leadTimeDays = leadTimeInvalid.value ? 0 : leadTimeNumber.value ?? 0;
  if (isDuplicate.value) {
    emit("save", { ref: form.ref.trim(), name: form.name.trim() });
    return;
  }
  const payload = {
    name: form.name.trim(),
    tradeName: form.tradeName.trim(),
    document: form.document.trim(),
    email: form.email.trim(),
    phone: form.phone.trim(),
    isActive: form.isActive,
    leadTimeDays,
    paymentTerm: form.paymentTerm.trim(),
  };
  if (isEdit.value) {
    emit("save", payload);
    return;
  }
  emit("save", { ref: form.ref.trim(), ...payload });
}

// ── Contatos ─────────────────────────────────────────────────────────────────
const contacts = computed(() => props.source?.contacts ?? []);

function newContact() {
  resetContact();
  contact.open = true;
  contact.isPrimary = contacts.value.length === 0;
  activeSection.value = "contacts";
}
function editContact(person: SupplierContact) {
  contact.open = true;
  contact.id = person.id;
  contact.name = person.name;
  contact.role = person.role;
  contact.email = person.email;
  contact.phone = person.phone;
  contact.notes = person.notes;
  contact.isPrimary = person.isPrimary;
  contact.isActive = person.isActive;
  activeSection.value = "contacts";
}
const contactValid = computed(
  () => contact.name.trim() !== "" && (contact.email.trim() !== "" || contact.phone.trim() !== ""),
);
const contactDisabledReason = computed(() => {
  if (!contact.name.trim()) return "Informe o nome do contato.";
  if (!contact.email.trim() && !contact.phone.trim()) return "Informe e-mail ou telefone: sem isso a mensagem não chega.";
  return "";
});
function submitContact() {
  if (!contactValid.value) return;
  emit("save-contact", {
    contactId: contact.id || null,
    name: contact.name.trim(),
    role: contact.role,
    email: contact.email.trim(),
    phone: contact.phone.trim(),
    notes: contact.notes.trim(),
    isPrimary: contact.isPrimary,
    isActive: contact.isActive,
  });
}
function roleLabel(role: string): string {
  return ROLE_OPTIONS.find((option) => option.value === role)?.label ?? role;
}
</script>

<template>
  <OperatorFormShell
    :open="open"
    :title="title"
    :description="description"
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    :save-label="saveLabel"
    :save-disabled="!valid"
    :save-disabled-reason="saveDisabledReason"
    :active-section="activeSection"
    :save-attrs="{ 'data-testid': 'supplier-form-save' }"
    :discard-attrs="{ 'data-testid': 'supplier-form-discard' }"
    action-label="Cadastro do fornecedor"
    @update:open="(value: boolean) => emit('update:open', value)"
    @save="submit"
  >
    <div class="flex flex-col gap-4" data-supplier-form>
      <NuxtAlert v-if="error" color="error" variant="subtle" icon="i-lucide-circle-alert" :description="error" />
      <NuxtAlert
        v-if="isDuplicate"
        color="info"
        variant="subtle"
        icon="i-lucide-copy"
        title="O que a cópia traz"
        :description="duplicateNote"
      />

      <OperatorFormSection section-key="identity" title="Identificação" description="A empresa, do jeito que ela aparece na nota.">
        <div class="grid gap-3 sm:grid-cols-2">
          <NuxtFormField label="Referência" :required="isDuplicate" hint="Identificador curto, sem acento. Vazio gera do nome.">
            <NuxtInput v-model="form.ref" :disabled="isEdit" placeholder="moinho-sp" data-testid="supplier-ref" data-focus-control />
          </NuxtFormField>
          <NuxtFormField label="Razão social" required>
            <NuxtInput v-model="form.name" placeholder="Moinho São Paulo Ltda." data-testid="supplier-name" />
          </NuxtFormField>
          <NuxtFormField label="Nome fantasia" hint="Como a casa chama no dia a dia.">
            <NuxtInput v-model="form.tradeName" placeholder="Moinho SP" data-testid="supplier-trade-name" />
          </NuxtFormField>
          <NuxtFormField label="CNPJ/Documento">
            <NuxtInput v-model="form.document" placeholder="12.345.678/0001-90" data-testid="supplier-document" />
          </NuxtFormField>
          <NuxtFormField label="E-mail da central">
            <NuxtInput v-model="form.email" type="email" placeholder="compras@fornecedor.com.br" />
          </NuxtFormField>
          <NuxtFormField label="Telefone da central">
            <NuxtInput v-model="form.phone" placeholder="(43) 3333-0000" />
          </NuxtFormField>
          <div class="flex items-center sm:col-span-2">
            <NuxtCheckbox v-model="form.isActive" label="Ativo" description="Inativo sai dos pedidos, sem apagar o histórico." />
          </div>
        </div>
      </OperatorFormSection>

      <OperatorFormSection
        v-if="!isDuplicate"
        section-key="commercial"
        title="Condições comerciais"
        description="O que o pedido de compra e a reposição usam."
      >
        <div class="grid gap-3 sm:grid-cols-2">
          <NuxtFormField label="Prazo de entrega (dias)">
            <NuxtInput v-model="form.leadTimeDaysText" inputmode="numeric" placeholder="3" data-testid="supplier-lead-time" />
          </NuxtFormField>
          <NuxtFormField label="Condição de pagamento">
            <NuxtInput v-model="form.paymentTerm" placeholder="28 dias" data-testid="supplier-payment-term" />
          </NuxtFormField>
        </div>
      </OperatorFormSection>

      <OperatorFormSection
        v-if="isEdit && source"
        section-key="contacts"
        title="Contatos"
        description="As pessoas do fornecedor, e para qual assunto cada uma atende."
      >
        <ul v-if="contacts.length" class="flex flex-col divide-y divide-default">
          <li v-for="person in contacts" :key="person.id" class="flex items-start justify-between gap-2 py-2">
            <span class="min-w-0">
              <span class="block text-sm font-medium" :class="person.isActive ? '' : 'text-muted line-through'">{{ person.name }}</span>
              <span class="block text-xs text-muted">
                {{ roleLabel(person.role) }}
                <template v-if="person.isPrimary"> · principal</template>
                <template v-if="person.email"> · {{ person.email }}</template>
                <template v-if="person.phone"> · {{ person.phone }}</template>
              </span>
            </span>
            <span class="flex shrink-0 items-center gap-1">
              <NuxtBadge v-if="!person.isActive" color="neutral" label="Inativo" />
              <NuxtButton label="Editar" color="neutral" variant="ghost" @click="editContact(person)" />
            </span>
          </li>
        </ul>
        <p v-else class="text-xs text-muted">Nenhum contato. O pedido de compra cai na central do fornecedor.</p>

        <form v-if="contact.open" class="mt-2 flex flex-col gap-3 rounded-lg bg-elevated/60 p-3" data-testid="contact-form" @submit.prevent="submitContact()">
          <div class="grid gap-3 sm:grid-cols-2">
            <NuxtFormField label="Nome" required>
              <NuxtInput v-model="contact.name" data-testid="contact-name" />
            </NuxtFormField>
            <NuxtFormField label="Assunto">
              <NuxtSelect v-model="contact.role" :items="ROLE_OPTIONS" class="w-full" />
            </NuxtFormField>
            <NuxtFormField label="E-mail">
              <NuxtInput v-model="contact.email" type="email" data-testid="contact-email" />
            </NuxtFormField>
            <NuxtFormField label="Telefone/WhatsApp">
              <NuxtInput v-model="contact.phone" data-testid="contact-phone" />
            </NuxtFormField>
            <NuxtFormField label="Observações" class="sm:col-span-2" hint="Horário em que atende, quem substitui nas férias.">
              <NuxtTextarea v-model="contact.notes" :rows="2" />
            </NuxtFormField>
            <div class="flex flex-wrap items-center gap-4 sm:col-span-2">
              <NuxtCheckbox v-model="contact.isPrimary" label="Principal do assunto" />
              <NuxtCheckbox v-model="contact.isActive" label="Ativo" />
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <NuxtButton
              type="submit"
              :label="contact.id ? 'Salvar contato' : 'Adicionar contato'"
              :disabled="!contactValid || busy"
              data-testid="contact-submit"
            />
            <NuxtButton label="Cancelar" color="neutral" variant="outline" @click="resetContact()" />
            <span v-if="contactDisabledReason" class="text-xs text-muted">{{ contactDisabledReason }}</span>
          </div>
        </form>
        <NuxtButton
          v-else
          label="Adicionar contato"
          icon="i-lucide-plus"
          color="neutral"
          variant="outline"
          class="self-start"
          :disabled="busy"
          data-testid="contact-add"
          @click="newContact()"
        />
      </OperatorFormSection>
    </div>
  </OperatorFormShell>
</template>
