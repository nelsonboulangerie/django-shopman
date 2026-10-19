<script setup lang="ts">
// Adicionar clientes ao grupo: busca, marca vários e adiciona numa ida.
//
// Os clientes estão fora da tela do grupo, então é diálogo (D9). A marcação
// atravessa buscas: dá para achar a Ana, buscar o Bruno e adicionar os dois juntos.
// Quem já está no grupo aparece marcado e travado. Adicionar não tira o cliente dos
// outros grupos dele.
import type { CustomerRowProjection } from "~/generated/ordersContract";
import type { CustomerGroupMembersResponse } from "~/types/customerGroups";
import {
  groupMembersActionLabel,
  isAlreadyMember,
} from "~/presentation/customerGroupMembers";

const props = defineProps<{
  open: boolean;
  group: { ref: string; name: string } | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  saved: [response: CustomerGroupMembersResponse];
}>();

const search = ref("");
const results = ref<CustomerRowProjection[]>([]);
const searching = ref(false);
const searchError = ref("");
const chosen = ref<Map<string, string>>(new Map());
const busy = ref(false);
const submitError = ref("");
let intentionKey = crypto.randomUUID();
let searchRun = 0;

async function runSearch(q: string) {
  const run = ++searchRun;
  searching.value = true;
  searchError.value = "";
  try {
    const rows = await searchCustomers(q);
    if (run === searchRun) results.value = rows;
  } catch (failure) {
    if (run === searchRun)
      searchError.value = httpErrorMessage(
        failure,
        "A busca falhou. Tente de novo.",
      );
  } finally {
    if (run === searchRun) searching.value = false;
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    search.value = "";
    results.value = [];
    chosen.value = new Map();
    submitError.value = "";
    intentionKey = crypto.randomUUID();
    void runSearch("");
  },
  { immediate: true },
);

watchDebounced(
  search,
  (q) => {
    if (props.open) void runSearch(q.trim());
  },
  { debounce: 300 },
);

function toggle(row: CustomerRowProjection, value: boolean | "indeterminate") {
  const next = new Map(chosen.value);
  if (value === true) next.set(row.ref, row.name);
  else next.delete(row.ref);
  chosen.value = next;
  intentionKey = crypto.randomUUID();
}

const memberOf = (row: CustomerRowProjection) =>
  props.group ? isAlreadyMember(row.groups, props.group.ref) : false;

const actionLabel = computed(() =>
  groupMembersActionLabel("add", chosen.value.size, props.group?.name ?? ""),
);
const chosenNames = computed(() => [...chosen.value.values()].join(", "));

function close(open: boolean) {
  if (!open && busy.value) return;
  emit("update:open", open);
}

async function confirm() {
  if (!props.group || !chosen.value.size || busy.value) return;
  busy.value = true;
  submitError.value = "";
  try {
    const response = await changeCustomerGroupMembers(
      props.group.ref,
      { operation: "add", refs: [...chosen.value.keys()] },
      intentionKey,
    );
    if (response.outcome !== "applied") {
      submitError.value =
        "O resultado ainda não foi confirmado. Tente de novo; a mesma intenção será reutilizada.";
      return;
    }
    emit("saved", response);
    emit("update:open", false);
  } catch (failure) {
    submitError.value = httpErrorMessage(
      failure,
      "Não foi possível adicionar os clientes.",
    );
    if (httpError(failure).status) intentionKey = crypto.randomUUID();
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <NuxtModal
    :open="open"
    :title="
      group ? `Adicionar clientes ao grupo ${group.name}` : 'Adicionar clientes'
    "
    description="Marque quantos quiser, em uma ou mais buscas. Os outros grupos de cada cliente continuam."
    scrollable
    data-customer-group-add-members
    @update:open="close"
  >
    <template #body>
      <div class="grid gap-3">
        <NuxtFormField label="Buscar cliente">
          <NuxtInput
            v-model="search"
            class="w-full"
            type="search"
            autocomplete="off"
            icon="i-lucide-search"
            placeholder="Nome, telefone, CPF…"
            data-customer-group-add-search
          />
        </NuxtFormField>

        <NuxtAlert
          v-if="searchError"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :description="searchError"
        />
        <NuxtSkeleton
          v-else-if="searching && !results.length"
          class="h-24 w-full"
          aria-label="Buscando clientes"
        />
        <NuxtEmpty
          v-else-if="!results.length"
          icon="i-lucide-user-search"
          :title="
            search.trim()
              ? 'Nenhum cliente com essa busca'
              : 'Nenhum cliente cadastrado'
          "
        />
        <ul
          v-else
          class="divide-y divide-default"
          aria-label="Clientes encontrados"
          :aria-busy="searching"
          data-customer-group-add-results
        >
          <li
            v-for="row in results"
            :key="row.ref"
            class="py-2"
            :data-customer-group-add-row="row.ref"
          >
            <NuxtCheckbox
              :model-value="memberOf(row) || chosen.has(row.ref)"
              :disabled="memberOf(row) || busy"
              :label="row.name"
              :description="
                memberOf(row)
                  ? 'Já está no grupo'
                  : `${row.ref} · ${row.phone_display || 'Sem telefone'}`
              "
              @update:model-value="toggle(row, $event)"
            />
          </li>
        </ul>

        <NuxtAlert
          v-if="submitError"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :description="submitError"
        />
      </div>
    </template>
    <template #footer>
      <div
        class="flex w-full min-w-0 flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end"
      >
        <p
          class="min-w-0 truncate text-xs text-muted-foreground sm:me-auto"
          :title="chosenNames"
          data-customer-group-add-chosen
        >
          {{
            chosen.size
              ? `Marcados: ${chosenNames}`
              : "Marque ao menos um cliente."
          }}
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
          icon="i-lucide-user-round-plus"
          color="primary"
          :disabled="busy || !chosen.size"
          :loading="busy"
          data-customer-group-add-confirm
          @click="confirm"
        />
      </div>
    </template>
  </NuxtModal>
</template>
