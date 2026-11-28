<script setup lang="ts">
import type {
  CustomerGroupMembersResponse,
  CustomerGroupMutationPayload,
  CustomerGroupProjection,
} from "~/types/customerGroups";
import { groupMembersResultMessage } from "~/presentation/customerGroupMembers";
import { mutationFieldErrors } from "~/utils/mutationFieldErrors";

useHead({ title: "Grupos de clientes" });

const { groups, pending, error, refresh, readMetadata } = useCustomerGroups();
const panelOpen = ref(false);
const editing = ref<CustomerGroupProjection | null>(null);
const duplicating = ref(false);
const busy = ref(false);
const mutationError = ref("");
const fieldErrors = ref<Record<string, string>>({});
let intentionKey = crypto.randomUUID();

const emptyOptions = { channels: [], listings: [], collections: [], discount_types: [] };
const options = computed(() => groups.value?.form ?? emptyOptions);
const items = computed(() => groups.value?.items ?? []);
const columns = [
  { id: "group", header: "Grupo" },
  { id: "advantage", header: "Vantagem" },
  { id: "scope", header: "Onde vale", meta: { supporting: true } },
  { id: "customers", header: "Clientes" },
  { id: "actions", header: "Ações" },
];

function openCreate() {
  editing.value = null;
  duplicating.value = false;
  intentionKey = crypto.randomUUID();
  mutationError.value = "";
  fieldErrors.value = {};
  panelOpen.value = true;
}

function openEdit(group: CustomerGroupProjection) {
  editing.value = group;
  duplicating.value = false;
  intentionKey = crypto.randomUUID();
  mutationError.value = "";
  fieldErrors.value = {};
  panelOpen.value = true;
}

function openDuplicate(group: CustomerGroupProjection) {
  editing.value = group;
  duplicating.value = true;
  intentionKey = crypto.randomUUID();
  mutationError.value = "";
  fieldErrors.value = {};
  panelOpen.value = true;
}

watch(panelOpen, (open) => {
  if (!open) {
    editing.value = null;
    duplicating.value = false;
  }
});

async function save(payload: CustomerGroupMutationPayload) {
  if (busy.value) return;
  busy.value = true;
  mutationError.value = "";
  fieldErrors.value = {};
  try {
    const response = editing.value && !duplicating.value
      ? await updateCustomerGroup(editing.value.ref, payload, intentionKey)
      : await createCustomerGroup(payload, intentionKey);
    if (response.outcome !== "applied" || !response.group) {
      mutationError.value = "O resultado ainda não foi confirmado. Salve novamente; a mesma intenção será reutilizada.";
      return;
    }
    intentionKey = crypto.randomUUID();
    panelOpen.value = false;
    useSonner.success(`${response.group.name} foi ${editing.value && !duplicating.value ? "atualizado" : "criado"}.`);
    await refresh();
  } catch (failure) {
    mutationError.value = httpErrorMessage(failure, "Não foi possível salvar o grupo.");
    fieldErrors.value = mutationFieldErrors(failure);
    if (httpError(failure).status) intentionKey = crypto.randomUUID();
  } finally {
    busy.value = false;
  }
}

// Adicionar clientes ao grupo: os clientes estão fora desta tela, então é diálogo.
const membersOpen = ref(false);
const membersGroup = ref<{ ref: string; name: string } | null>(null);
function openMembers(group: CustomerGroupProjection) {
  membersGroup.value = { ref: group.ref, name: group.name };
  membersOpen.value = true;
}
async function membersSaved(response: CustomerGroupMembersResponse) {
  useSonner.success(groupMembersResultMessage(response));
  await refresh();
}

const phoneHeaderActions = computed(() => [
  { label: "Criar grupo", icon: "i-lucide-badge-plus", onSelect: openCreate },
  { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() },
]);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Grupos de clientes"
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
        />
      </template>
      <template #status>
        <span class="hidden op-micro text-muted-foreground lg:inline">Preço e vantagem com um único dono</span>
      </template>
      <template #filters>
        <div class="flex items-center gap-3">
          <NuxtButton icon="i-lucide-badge-plus" label="Criar grupo" @click="openCreate" />
          <NuxtButton
            icon="i-lucide-refresh-cw"
            label="Atualizar"
            color="neutral"
            variant="outline"
            :loading="pending"
            @click="refresh()"
          />
        </div>
      </template>
      <template #filters-end>
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span v-if="groups" class="text-xs tabular-nums text-muted-foreground">{{ groups.total_label }}</span>
          <ReadFreshness inline :metadata="readMetadata" :failed="Boolean(error)" />
        </div>
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 space-y-4 overflow-auto p-4 sm:p-6">
      <NuxtAlert
        color="info"
        variant="subtle"
        icon="i-lucide-scale"
        title="A melhor vantagem vence"
        description="Ao identificar o cliente, PDV e loja online usam a lista de preço do grupo e escolhem o maior desconto aplicável. Descontos concorrentes não se somam."
      />

      <OperatorTable
        :data="items"
        :columns="columns"
        :row-key="(row: CustomerGroupProjection) => row.ref"
        :row-label="(row: CustomerGroupProjection) => `o grupo ${row.name}`"
        :loading="pending"
        :error="Boolean(error)"
        what="os grupos de clientes"
        empty-icon="i-lucide-badge-percent"
        empty-title="Nenhum grupo comercial cadastrado."
        empty-description="Crie o primeiro grupo para reunir preço, desconto e comunicação da vantagem."
        caption="Grupos comerciais de clientes"
        data-customer-groups
        @retry="refresh()"
      >
        <template #group-cell="{ row }">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-medium">{{ row.original.name }}</span>
              <NuxtBadge v-if="row.original.is_default" color="primary" label="Padrão" />
            </div>
            <span class="block font-mono text-xs text-muted-foreground">{{ row.original.ref }}</span>
            <span v-if="row.original.description" class="mt-1 block max-w-xl text-xs text-muted-foreground">{{ row.original.description }}</span>
          </div>
        </template>
        <template #advantage-cell="{ row }">
          <span class="block text-sm font-medium">{{ row.original.discount_label }}</span>
          <span class="block text-xs text-muted-foreground">
            {{ row.original.listing_name ? `Lista: ${row.original.listing_name}` : "Preço base do canal" }}
          </span>
          <span v-if="row.original.rounding && row.original.discount_type" class="block text-xs text-muted-foreground">Arredonda para R$ 0,00 ou R$ 0,50</span>
          <span
            v-for="advantage in row.original.advantages.filter((item) => item.is_active)"
            :key="advantage.kind"
            class="block text-xs text-muted-foreground"
          >
            {{ advantage.summary_label }}
          </span>
        </template>
        <template #scope-cell="{ row }">
          <span class="block text-sm">{{ row.original.channels_label }}</span>
          <span v-if="row.original.pickup_only && row.original.discount_type" class="block text-xs text-muted-foreground">Somente retirada</span>
        </template>
        <template #customers-cell="{ row }">
          <div class="flex flex-col items-start gap-1">
            <NuxtButton
              :to="`/customers?group=${encodeURIComponent(row.original.ref)}`"
              icon="i-lucide-users"
              :label="row.original.customer_count_label"
              color="neutral"
              variant="ghost"
              :aria-label="`Ver os clientes do grupo ${row.original.name}`"
              :data-customer-group-members-link="row.original.ref"
            />
            <NuxtButton
              type="button"
              icon="i-lucide-user-round-plus"
              label="Adicionar"
              color="neutral"
              variant="outline"
              :aria-label="`Adicionar clientes ao grupo ${row.original.name}`"
              :data-add-customer-group-members="row.original.ref"
              @click="openMembers(row.original)"
            />
          </div>
        </template>
        <template #actions-cell="{ row }">
          <div class="flex flex-wrap items-center gap-2">
            <NuxtButton
              type="button"
              icon="i-lucide-copy"
              label="Duplicar"
              color="neutral"
              variant="ghost"
              :data-duplicate-customer-group="row.original.ref"
              @click="openDuplicate(row.original)"
            />
            <NuxtButton
              type="button"
              icon="i-lucide-pencil"
              label="Editar"
              color="neutral"
              variant="outline"
              :data-edit-customer-group="row.original.ref"
              @click="openEdit(row.original)"
            />
          </div>
        </template>
      </OperatorTable>
    </section>

    <CustomerGroupAddMembersDialog
      v-model:open="membersOpen"
      :group="membersGroup"
      @saved="membersSaved"
    />

    <CustomerGroupFormPanel
      v-model:open="panelOpen"
      :group="editing"
      :duplicate="duplicating"
      :options="options"
      :busy="busy"
      :error="mutationError"
      :field-errors="fieldErrors"
      @save="save"
    />
  </main>
</template>
