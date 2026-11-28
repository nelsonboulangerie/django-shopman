<script setup lang="ts">
import type {
  ProductComponentInput,
  ProductComponentLink,
} from "~/types/catalog";

const props = defineProps<{
  sku: string;
  unit: string;
  components: ProductComponentLink[];
  busy: boolean;
  save: (rows: ProductComponentInput[]) => Promise<boolean>;
  search: (
    query: string,
  ) => Promise<{ sku: string; name: string; unit?: string }[]>;
}>();
const emit = defineEmits<{
  "dirty-change": [value: boolean];
  "saving-change": [value: boolean];
}>();
const editing = ref(false);
const saving = ref(false);
const rows = ref<ProductComponentLink[]>([]);
const error = ref("");
const chooseOpen = ref(false);
const query = ref("");
const searching = ref(false);
const choices = ref<{ sku: string; name: string; unit?: string }[]>([]);
const undo = ref<{ rows: ProductComponentInput[]; until: number } | null>(null);
const confirm = useConfirm();
const pending = computed(() => props.busy || saving.value);
watch(editing, (value) => emit("dirty-change", value));
watch(saving, (value) => emit("saving-change", value));
// Usar os valores atuais troca a lista recebida. A atualização seletiva do
// próprio save chega enquanto saving e não descarta o rascunho de outra aba.
watch(
  () => props.components,
  () => {
    if (saving.value) return;
    editing.value = false;
    chooseOpen.value = false;
    error.value = "";
    undo.value = null;
  },
);
function edit() {
  rows.value = props.components.map((row) => ({
    ...row,
    qty: row.qty.replace(".", ","),
  }));
  error.value = "";
  undo.value = null;
  editing.value = true;
}
function cancel() {
  chooseOpen.value = false;
  editing.value = false;
  error.value = "";
}
let searchRequest = 0;
async function runSearch() {
  const request = ++searchRequest;
  searching.value = true;
  try {
    const result = await props.search(query.value);
    if (request === searchRequest)
      choices.value = result.filter(
        (row) =>
          row.sku !== props.sku &&
          !rows.value.some((item) => item.sku === row.sku),
      );
  } catch {
    if (request === searchRequest)
      error.value =
        "Não foi possível buscar os produtos. Tente buscar novamente.";
  } finally {
    if (request === searchRequest) searching.value = false;
  }
}
async function choose() {
  chooseOpen.value = true;
  error.value = "";
  query.value = "";
  choices.value = [];
  await runSearch();
}
function add(product: { sku: string; name: string; unit?: string }) {
  rows.value.push({ ...product, unit: product.unit || "un", qty: "1" });
  chooseOpen.value = false;
}
async function apply() {
  const parsed: ProductComponentInput[] = [];
  for (const row of rows.value) {
    const qty = row.qty.replace(",", ".");
    if (
      !/^\d+(?:\.\d{1,3})?$/.test(qty) ||
      Number(qty) <= 0 ||
      Number(qty) > 9999999.999
    ) {
      error.value =
        "Informe uma quantidade positiva com até três casas decimais por componente.";
      return;
    }
    parsed.push({ sku: row.sku, qty });
  }
  const removed = props.components.some(
    (row) => !parsed.some((item) => item.sku === row.sku),
  );
  if (
    removed &&
    !(await confirm({
      title: "Remover componentes do combo?",
      description:
        "Os produtos retirados deixam de compor a quantidade de estoque necessária para vender este combo.",
      tone: "danger",
      confirmLabel: "Aplicar composição",
      cancelLabel: "Continuar editando",
    }))
  )
    return;
  const previous = props.components.map(({ sku, qty }) => ({ sku, qty }));
  saving.value = true;
  error.value = "";
  try {
    if (await props.save(parsed)) {
      editing.value = false;
      undo.value = { rows: previous, until: Date.now() + 10000 };
    } else
      error.value =
        "A composição não foi aplicada. Confira a mensagem do produto e tente novamente.";
  } finally {
    saving.value = false;
  }
}
async function undoChange() {
  if (!undo.value) return;
  saving.value = true;
  try {
    if (await props.save(undo.value.rows)) undo.value = null;
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <NuxtCard variant="outline" class="mt-4" data-catalog-components>
    <div class="space-y-3">
      <div class="flex items-center justify-between gap-2">
        <h4 class="font-medium">Componentes do combo</h4>
        <NuxtButton
          v-if="!editing"
          label="Editar componentes"
          color="neutral"
          variant="ghost"
          :disabled="pending"
          @click="edit"
        />
      </div>
      <p class="text-sm text-muted">
        Alterar a composição muda o estoque necessário nas próximas vendas deste
        combo.
      </p>
      <NuxtFormField :label="`Composição para 1 ${unit} do combo`" :error="error || undefined">
        <div class="space-y-2">
          <p
            v-if="!(editing ? rows : components).length"
            class="text-sm text-muted"
          >
            Este produto não tem componentes. Inclua produtos para formar um
            combo.
          </p>
          <div
            v-for="row in editing ? rows : components"
            :key="row.sku"
            class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted p-3"
          >
            <span class="min-w-0 flex-1">{{ row.name }}</span>
            <NuxtFormField
              v-if="editing"
              :label="`Quantidade de ${row.name} (${row.unit})`"
            >
              <NuxtInput
                v-model="row.qty"
                inputmode="decimal"
                class="w-28"
                :disabled="pending"
              />
            </NuxtFormField>
            <span v-else class="text-sm tabular-nums"
              >{{ row.qty.replace(".", ",") }} {{ row.unit }}</span
            >
            <NuxtButton
              v-if="editing"
              :label="`Retirar ${row.name}`"
              color="error"
              variant="outline"
              :disabled="pending"
              @click="rows = rows.filter((item) => item.sku !== row.sku)"
            />
          </div>
        </div>
      </NuxtFormField>
      <template v-if="editing">
        <NuxtButton
          label="Incluir componente"
          color="neutral"
          variant="outline"
          :disabled="pending"
          @click="choose"
        />
        <div class="flex justify-end gap-2">
          <NuxtButton
            label="Cancelar"
            color="neutral"
            variant="ghost"
            :disabled="pending"
            @click="cancel"
          />
          <NuxtButton
            label="Aplicar"
            :loading="saving"
            :disabled="pending"
            @click="apply"
          />
        </div>
      </template>
      <OperatorTimedButton
        v-if="undo && !editing"
        label="Desfazer composição"
        color="primary"
        :until="undo.until"
        :duration="10000"
        :disabled="pending"
        @expire="undo = null"
        @click="undoChange"
      />
    </div>
    <NuxtModal
      v-model:open="chooseOpen"
      title="Escolher componente"
      description="Busque o produto pelo nome ou SKU."
    >
      <template #body>
        <div class="space-y-3">
          <NuxtFormField label="Nome ou SKU" :error="error || undefined"
            ><NuxtInput
              v-model="query"
              class="w-full"
              autofocus
              @keyup.enter="runSearch"
          /></NuxtFormField>
          <NuxtButton
            label="Buscar"
            color="neutral"
            variant="outline"
            :loading="searching"
            @click="runSearch"
          />
          <p v-if="!searching && !choices.length" class="text-sm text-muted">
            Nenhum produto encontrado. Tente outro nome ou SKU.
          </p>
          <div class="space-y-2">
            <NuxtButton
              v-for="product in choices"
              :key="product.sku"
              :label="product.name"
              color="neutral"
              variant="outline"
              @click="add(product)"
            />
          </div>
        </div>
      </template>
    </NuxtModal>
  </NuxtCard>
</template>
