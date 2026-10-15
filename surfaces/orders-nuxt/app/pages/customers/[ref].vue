<script setup lang="ts">
// Ficha do cliente — quem é, o que comprou, e quem PODE ser a mesma pessoa.
//
// Os candidatos vêm com o motivo escrito ("Mesmo cliente no iFood", "Mesmo CPF",
// "Mesmo nome"): é sugestão, e a unificação é sempre um gesto do gestor, depois da
// prévia lado a lado (`CustomerMergeDialog`).
import type { CustomerAddressProjection, CustomerCandidateProjection } from "~/generated/ordersContract";
import type { CustomerAddressMutationPayload, CustomerDuplicatePayload, CustomerMutationPayload } from "~/types/customers";
import { mutationFieldErrors } from "~/utils/mutationFieldErrors";
import { alertActions } from "../../../../operator-kit/app/utils/alertActions";

const route = useRoute();
const router = useRouter();
const customerRef = computed(() => String(route.params.ref || ""));
const { customer, pending, error, refresh, readMetadata } =
  useCustomerDetail(customerRef);

useHead({ title: computed(() => customer.value?.name || "Cliente") });

const mergeOpen = ref(false);
const mergeWith = ref<CustomerCandidateProjection | null>(null);
function compare(candidate: CustomerCandidateProjection | null) {
  mergeWith.value = candidate;
  mergeOpen.value = true;
}

async function onMerged({
  targetRef,
  sourceRef,
}: {
  targetRef: string;
  sourceRef: string;
}) {
  useSonner.success(
    `${sourceRef} foi unificado a ${targetRef}. Dá para desfazer em Unificações por 24 horas.`,
  );
  if (targetRef !== customerRef.value)
    await router.push(`/customers/${encodeURIComponent(targetRef)}`);
  else await refresh();
}

const canMerge = computed(() =>
  Boolean(
    customer.value?.is_active &&
    customer.value.actions.some((action) => action.ref === "merge_preview"),
  ),
);
const editOpen = ref(false);
const editBusy = ref(false);
const editError = ref("");
const editFieldErrors = ref<Record<string, string>>({});
let editKey = crypto.randomUUID();
watch(editOpen, (open) => {
  if (!open) return;
  editError.value = "";
  editFieldErrors.value = {};
});
async function saveCustomer(payload: CustomerMutationPayload) {
  if (editBusy.value || !customer.value) return;
  editBusy.value = true;
  editError.value = "";
  editFieldErrors.value = {};
  try {
    const response = await updateCustomer(customer.value.ref, payload, editKey);
    if (response.outcome !== "applied") {
      editError.value = "O resultado ainda não foi confirmado. Tente salvar novamente; a mesma intenção será reutilizada.";
      return;
    }
    editKey = crypto.randomUUID();
    editOpen.value = false;
    useSonner.success(`${response.customer.name} foi atualizado.`);
    await refresh();
  } catch (failure) {
    editError.value = httpErrorMessage(failure, "Não foi possível salvar o cliente.");
    editFieldErrors.value = mutationFieldErrors(failure);
    if (httpError(failure).status) editKey = crypto.randomUUID();
  } finally {
    editBusy.value = false;
  }
}
const duplicateOpen = ref(false);
const duplicateBusy = ref(false);
const duplicateError = ref("");
let duplicateKey = crypto.randomUUID();
watch(duplicateOpen, (open) => {
  if (!open) return;
  duplicateError.value = "";
});
async function saveDuplicate(payload: CustomerDuplicatePayload) {
  if (duplicateBusy.value || !customer.value) return;
  duplicateBusy.value = true;
  duplicateError.value = "";
  try {
    const response = await duplicateCustomer(customer.value.ref, payload, duplicateKey);
    if (response.outcome !== "applied" || !response.customer) {
      duplicateError.value = "O resultado ainda não foi confirmado. Tente salvar novamente; a mesma intenção será reutilizada.";
      return;
    }
    duplicateKey = crypto.randomUUID();
    duplicateOpen.value = false;
    useSonner.success(response.customer.name + " foi criado a partir de " + customer.value.name + ".");
    await router.push("/customers/" + encodeURIComponent(response.customer.ref));
  } catch (failure) {
    duplicateError.value = httpErrorMessage(failure, "Não foi possível duplicar o cliente.");
    if (httpError(failure).status) duplicateKey = crypto.randomUUID();
  } finally {
    duplicateBusy.value = false;
  }
}
const addressOpen = ref(false);
const addressDraft = ref<CustomerAddressProjection | null>(null);
const addressBusy = ref(false);
const addressError = ref("");
const addressFieldErrors = ref<Record<string, string>>({});
let addressCreateKey = crypto.randomUUID();
let addressUpdateKey = crypto.randomUUID();
const addressDeleteKeys = new Map<number, string>();

function addAddress() {
  addressDraft.value = null;
  addressError.value = "";
  addressFieldErrors.value = {};
  addressOpen.value = true;
}
function editAddress(address: CustomerAddressProjection) {
  addressDraft.value = address;
  addressError.value = "";
  addressFieldErrors.value = {};
  addressUpdateKey = crypto.randomUUID();
  addressOpen.value = true;
}
async function saveAddress(payload: CustomerAddressMutationPayload) {
  if (addressBusy.value || !customer.value) return;
  addressBusy.value = true;
  addressError.value = "";
  addressFieldErrors.value = {};
  try {
    const response = addressDraft.value
      ? await updateCustomerAddress(customer.value.ref, addressDraft.value.id, payload, addressUpdateKey)
      : await createCustomerAddress(customer.value.ref, payload, addressCreateKey);
    if (response.outcome !== "applied") {
      addressError.value = "O resultado ainda não foi confirmado. Tente salvar novamente; a mesma intenção será reutilizada.";
      return;
    }
    if (addressDraft.value) addressUpdateKey = crypto.randomUUID();
    addressCreateKey = crypto.randomUUID();
    addressOpen.value = false;
    useSonner.success("Endereço salvo.");
    await refresh();
  } catch (failure) {
    addressError.value = httpErrorMessage(failure, "Não foi possível salvar o endereço.");
    addressFieldErrors.value = mutationFieldErrors(failure);
    if (!addressDraft.value && httpError(failure).status) addressCreateKey = crypto.randomUUID();
    if (addressDraft.value && httpError(failure).status) addressUpdateKey = crypto.randomUUID();
  } finally {
    addressBusy.value = false;
  }
}
async function removeAddress(address: CustomerAddressProjection) {
  if (addressBusy.value || !customer.value) return;
  const key = addressDeleteKeys.get(address.id) ?? crypto.randomUUID();
  addressDeleteKeys.set(address.id, key);
  addressBusy.value = true;
  addressError.value = "";
  addressFieldErrors.value = {};
  try {
    const response = await removeCustomerAddress(customer.value.ref, address.id, address.revision, key);
    if (response.outcome !== "applied") {
      addressError.value = "A remoção ainda não foi confirmada. Tente novamente; a mesma intenção será reutilizada.";
      return;
    }
    addressDeleteKeys.delete(address.id);
    addressOpen.value = false;
    useSonner.success("Endereço removido.");
    await refresh();
  } catch (failure) {
    addressError.value = httpErrorMessage(failure, "Não foi possível remover o endereço.");
    addressFieldErrors.value = mutationFieldErrors(failure);
    if (httpError(failure).status) addressDeleteKeys.delete(address.id);
  } finally {
    addressBusy.value = false;
  }
}
const notFound = computed(() => httpError(error.value).status === 404);
// Celular (abaixo de `sm`, README do kit "Barra do topo no celular" e "Toolbar no
// celular"): as ações da toolbar vão para o ⋯ da barra do topo e a leitura (frescor)
// desce para a faixa de texto abaixo da linha. Do `sm` para cima, tudo como está.
const phoneHeaderActions = computed(() => [
  ...(customer.value?.is_active
    ? [
        { label: "Editar cliente", icon: "i-lucide-pencil", onSelect: () => { editOpen.value = true; } },
        { label: "Duplicar cliente", icon: "i-lucide-copy-plus", onSelect: () => { duplicateOpen.value = true; } },
      ]
    : []),
  { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() },
]);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      :title="customer?.name || 'Cliente'"
      :filters-wrap="false"
      :phone-actions="phoneHeaderActions"
      desk-only-filters
    >
      <template #lead>
        <NuxtButton
          to="/customers"
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="ghost"
          square
          aria-label="Voltar para Clientes"
          @click.prevent="router.back()"
        />
      </template>
      <template #filters>
        <NuxtButton
          v-if="customer?.is_active"
          icon="i-lucide-pencil"
          label="Editar cliente"
          color="neutral"
          variant="outline"
          @click="editOpen = true"
        />
        <NuxtButton
          v-if="customer?.is_active"
          icon="i-lucide-copy-plus"
          label="Duplicar cliente"
          color="neutral"
          variant="outline"
          @click="duplicateOpen = true"
        />
        <NuxtButton
          icon="i-lucide-refresh-cw"
          label="Atualizar"
          color="neutral"
          variant="outline"
          :loading="pending"
          @click="refresh()"
        />
      </template>
      <template #filters-end>
        <ReadFreshness
          inline
          :metadata="readMetadata"
          :failed="Boolean(error)"
        />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 space-y-4 overflow-auto p-4 sm:p-6">
      <NuxtEmpty
        v-if="notFound"
        icon="i-lucide-user-x"
        title="Este cadastro não existe"
        :actions="[{ label: 'Voltar para Clientes', to: '/customers' }]"
      />
      <NuxtAlert
        v-else-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Não foi possível carregar a ficha"
        :description="
          httpErrorMessage(error, 'Não foi possível carregar a ficha.')
        "
        :actions="alertActions('error', [
          {
            label: 'Tentar de novo',
            onClick: () => refresh(),
          },
        ])"
      />

      <div v-if="pending && !customer" class="space-y-3">
        <NuxtSkeleton
          v-for="i in 3"
          :key="i"
          class="h-24 w-full"
          aria-label="Carregando cliente"
        />
      </div>

      <div
        v-else-if="customer"
        class="mx-auto grid max-w-5xl gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
      >
        <!-- Absorvido: a ficha diz para onde foi, e não oferece nada além disso. -->
        <NuxtAlert
          v-if="!customer.is_active"
          color="warning"
          variant="subtle"
          icon="i-lucide-merge"
          title="Cadastro unificado ou desativado"
          :description="
            customer.merged_into_ref
              ? `Este cadastro foi unificado a ${customer.merged_into_ref}. Os pedidos e contatos dele estão lá.`
              : 'Este cadastro está desativado.'
          "
          :actions="
            alertActions('warning', customer.merged_into_ref
              ? [
                  {
                    label: `Abrir ${customer.merged_into_ref}`,
                    to: `/customers/${encodeURIComponent(customer.merged_into_ref)}`,
                  },
                ]
              : [])
          "
          data-customer-absorbed
        />

        <NuxtCard
          as="article"
          class="lg:col-span-2"
          data-customer-header
        >
          <div class="flex flex-col gap-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="text-xl font-semibold">{{ customer.name }}</h2>
                <p
                  class="flex flex-wrap items-center gap-2 text-xs text-muted-foreground"
                >
                  <span class="font-mono">{{ customer.ref }}</span>
                  <NuxtBadge
                    v-if="customer.source_label"
                    color="neutral"
                    :label="customer.source_label"
                  />
                  <span v-if="customer.created_display"
                    >Cadastrado em {{ customer.created_display }}</span
                  >
                </p>
              </div>
              <NuxtButton
                v-if="canMerge"
                type="button"
                icon="i-lucide-merge"
                label="Unificar com outro cadastro…"
                data-customer-merge-any
                @click="compare(null)"
              />
            </div>
            <div class="space-y-3">
              <dl class="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                <div class="flex gap-2">
                  <dt class="text-muted-foreground">Telefone</dt>
                  <dd>{{ customer.phone_display || "Sem telefone" }}</dd>
                </div>
                <div class="flex gap-2">
                  <dt class="text-muted-foreground">E-mail</dt>
                  <dd>{{ customer.email || "Sem e-mail" }}</dd>
                </div>
                <div class="flex gap-2">
                  <dt class="text-muted-foreground">CPF</dt>
                  <dd>{{ customer.document_display || "Sem CPF" }}</dd>
                </div>
                <div v-if="customer.birthday_display" class="flex gap-2">
                  <dt class="text-muted-foreground">Aniversário</dt>
                  <dd>{{ customer.birthday_display }}</dd>
                </div>
              </dl>
              <div class="flex flex-wrap gap-2 text-xs">
                <NuxtBadge v-if="customer.price_tier_name" color="neutral" :label="`Preço: ${customer.price_tier_name}`" />
                <NuxtBadge v-if="customer.house_account" color="success" label="Conta na casa" />
                <NuxtBadge v-for="tag in customer.tags" :key="tag" color="neutral" :label="tag" />
              </div>
              <NuxtAlert
                v-if="customer.notes"
                color="info"
                variant="subtle"
                title="Observação"
                :description="customer.notes"
              />
            </div>
          </div>
        </NuxtCard>

        <!-- Quem pode ser a mesma pessoa -->
        <NuxtCard
          v-if="customer.candidates.length"
          as="article"
          class="lg:col-span-2"
          data-customer-candidates
        >
          <div class="flex flex-col gap-3">
            <div>
              <h2 class="op-title">Pode ser a mesma pessoa</h2>
              <p class="op-micro text-muted-foreground">
                Sugestão da tela, com o motivo em cada linha. Confira antes de
                unificar.
              </p>
            </div>
            <ul class="divide-y divide-border">
              <li
                v-for="candidate in customer.candidates"
                :key="candidate.ref"
                class="flex flex-wrap items-center justify-between gap-3 py-2"
              >
                <div class="min-w-0 text-sm">
                  <NuxtLink
                    :to="`/customers/${encodeURIComponent(candidate.ref)}`"
                    class="font-medium hover:underline"
                    >{{ candidate.name }}</NuxtLink
                  >
                  <span class="ms-2 font-mono text-xs text-muted-foreground">{{
                    candidate.ref
                  }}</span>
                  <p class="text-xs text-muted-foreground">
                    <NuxtBadge
                      color="warning"
                      :label="candidate.reason_label"
                    />
                    · {{ candidate.phone_display || "sem telefone" }}
                    <template v-if="candidate.source_label">
                      · {{ candidate.source_label }}</template
                    >
                    · {{ candidate.orders_label }}
                  </p>
                </div>
                <NuxtButton
                  type="button"
                  label="Comparar"
                  :data-customer-compare="candidate.ref"
                  @click="compare(candidate)"
                />
              </li>
            </ul>
          </div>
        </NuxtCard>

        <NuxtCard as="article">
          <div class="flex flex-col gap-3">
            <div>
              <h2 class="op-title">Pedidos</h2>
              <p class="op-micro text-muted-foreground">
                {{ customer.orders_label
                }}<template v-if="customer.total_spent_display">
                  · {{ customer.total_spent_display }} no total</template
                >
                <template v-if="customer.last_order_display">
                  · último {{ customer.last_order_display }}</template
                >
              </p>
            </div>
            <ul
              v-if="customer.recent_orders.length"
              class="divide-y divide-border text-sm"
            >
              <li v-for="order in customer.recent_orders" :key="order.ref">
                <NuxtLink
                  :to="`/${encodeURIComponent(order.ref)}`"
                  class="flex flex-wrap items-center justify-between gap-2 py-1.5 hover:underline"
                >
                  <span
                    ><span class="font-mono text-xs">{{ order.ref }}</span> ·
                    {{ order.channel_label }}</span
                  >
                  <span class="text-xs text-muted-foreground"
                    >{{ order.ordered_at_display }} · {{ order.status_label }} ·
                    {{ order.total_display }}</span
                  >
                </NuxtLink>
              </li>
            </ul>
          </div>
        </NuxtCard>

        <NuxtCard as="article" data-customer-consents>
          <div class="flex flex-col gap-3">
            <div>
              <h2 class="op-title">Consentimentos</h2>
              <p class="op-micro text-muted-foreground">
                Leitura da trilha LGPD. Alterações só acontecem no gesto que registra origem, texto e evidência.
              </p>
            </div>
            <ul v-if="customer.consents.length" class="divide-y divide-border text-sm">
              <li v-for="consent in customer.consents" :key="consent.channel_label" class="flex flex-wrap items-start justify-between gap-2 py-2">
                <div>
                  <span class="font-medium">{{ consent.channel_label }}</span>
                  <p class="text-xs text-muted-foreground">{{ consent.purpose_label }} · {{ consent.proof_label }}</p>
                  <p v-if="consent.source || consent.updated_display" class="text-xs text-muted-foreground">
                    {{ consent.source || "Origem não informada" }}<template v-if="consent.updated_display"> · {{ consent.updated_display }}</template>
                  </p>
                </div>
                <NuxtBadge :color="consent.allowed ? 'success' : consent.status_label === 'Opt-out' ? 'error' : 'neutral'" :label="consent.status_label" />
              </li>
            </ul>
            <NuxtAlert v-else color="info" variant="subtle" title="Nenhum opt-in registrado" description="Sem evidência, a tela não presume autorização para marketing." />
          </div>
        </NuxtCard>

        <NuxtCard as="article">
          <div class="flex flex-col gap-3">
            <div>
              <h2 class="op-title">Identificadores</h2>
              <p class="op-micro text-muted-foreground">
                As chaves pelas quais os canais reconhecem esta pessoa.
              </p>
            </div>
            <ul v-if="customer.identifiers.length" class="space-y-1 text-sm">
              <li
                v-for="identifier in customer.identifiers"
                :key="`${identifier.type_label}:${identifier.value}`"
                class="flex gap-2"
              >
                <span class="text-muted-foreground">{{
                  identifier.type_label
                }}</span>
                <span class="break-all font-mono text-xs leading-5">{{
                  identifier.value
                }}</span>
              </li>
            </ul>
            <p v-else class="text-sm text-muted-foreground">
              Nenhum identificador.
            </p>
            <h2 class="op-title">Endereços</h2>
            <NuxtButton v-if="customer.is_active" variant="outline" icon="i-lucide-map-pin-plus" label="Adicionar" @click="addAddress" />
            <ul v-if="customer.addresses.length" class="mt-1 space-y-1 text-sm">
              <li v-for="address in customer.addresses" :key="address.id" class="flex items-start justify-between gap-2 rounded-md border border-border p-2">
                <div>
                  <span class="font-medium">{{ address.label }}</span>
                  <NuxtBadge v-if="address.is_default" class="ms-2" color="neutral" label="Padrão" />
                  <p>{{ address.formatted_address }}</p>
                  <p v-if="address.complement" class="text-xs text-muted-foreground">{{ address.complement }}</p>
                  <p v-if="!address.is_verified" class="text-xs text-muted-foreground">Ainda não verificado</p>
                </div>
                <NuxtButton v-if="customer.is_active" icon="i-lucide-pencil" color="neutral" variant="ghost" square :aria-label="`Editar ${address.label}`" @click="editAddress(address)" />
              </li>
            </ul>
            <p v-else class="mt-1 text-sm text-muted-foreground">
              Nenhum endereço salvo.
            </p>
          </div>
        </NuxtCard>
      </div>
    </section>

    <CustomerMergeDialog
      v-if="customer"
      v-model:open="mergeOpen"
      :current="customer"
      :initial-other="mergeWith"
      @merged="onMerged"
    />
    <CustomerFormPanel
      v-if="customer"
      v-model:open="editOpen"
      :customer="customer"
      :options="customer.form"
      :busy="editBusy"
      :error="editError"
      :field-errors="editFieldErrors"
      @save="saveCustomer"
    />
    <CustomerDuplicatePanel
      v-if="customer"
      v-model:open="duplicateOpen"
      :source="customer"
      :busy="duplicateBusy"
      :error="duplicateError"
      @save="saveDuplicate"
    />
    <CustomerAddressFormPanel
      v-if="customer"
      v-model:open="addressOpen"
      :address="addressDraft"
      :busy="addressBusy"
      :error="addressError"
      :field-errors="addressFieldErrors"
      @save="saveAddress"
      @remove="removeAddress"
    />
  </main>
</template>
