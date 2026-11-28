<script setup lang="ts">
// Tabelão de produtos: o PRODUTO linha a linha (nome, descrição curta, preço,
// vendido por peso e classificação fiscal), com colar de planilha em bloco,
// desfazer, erro na célula antes de salvar e recibo por linha. O tabelão por
// canal (CatalogBulkGrid) segue dono do preço e da publicação em cada canal.
// Presentacional: o pai lê a planilha e é dono do save e da cópia.
import type {
  CatalogRowProjection,
  ProductSheet,
  ProductSheetReceipt,
  ProductSheetRow,
  ProductSheetRowPatch,
} from "~/types/catalog";
import {
  SHEET_COLUMNS,
  SHEET_COLUMN_LABELS,
  buildRowPatches,
  cellValue,
  confirmedKeys,
  failureText,
  pasteBlock,
  rowProblems,
  sheetKey,
  type SheetColumn,
  type SheetValue,
} from "~/presentation/productSheet";

const props = defineProps<{
  open: boolean;
  rows: CatalogRowProjection[];
  sheet: ProductSheet | null;
  busy?: boolean;
  duplicateBusy?: boolean;
  error?: string;
  receipt?: ProductSheetReceipt | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [rows: ProductSheetRowPatch[]];
  duplicate: [skus: string[]];
}>();

const confirmDuplicate = useConfirm();
const edit = useGridEdit<SheetValue>();
const rowSelection = ref<Record<string, boolean>>({});
const blocked = ref<string[]>([]);

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    edit.clear();
    rowSelection.value = {};
    blocked.value = [];
  },
);

// As linhas seguem a página do catálogo (mesmo recorte, mesma ordem); os valores
// vêm da planilha do servidor, que traz a revisão de cada campo.
const sheetRows = computed<ProductSheetRow[]>(() => {
  const bySku = new Map((props.sheet?.rows ?? []).map((row) => [row.sku, row]));
  return props.rows.flatMap((row) => {
    const found = bySku.get(row.sku);
    return found ? [found] : [];
  });
});
const skus = computed(() => sheetRows.value.map((row) => row.sku));
const profiles = computed(() => props.sheet?.fiscal_profiles ?? []);
const origins = computed(() => props.sheet?.fiscal_origins ?? []);
const profileItems = computed(() =>
  profiles.value.map((profile) => ({ value: profile.key, label: profile.name })),
);
const originItems = computed(() =>
  origins.value.map((origin) => ({
    value: origin.key,
    label: `${origin.key}: ${origin.name}`,
  })),
);
const selectedSkus = computed(() =>
  skus.value.filter((sku) => rowSelection.value[sku]),
);

const tableColumns = computed(() => [
  { id: "product", header: "Produto", enableHiding: false },
  ...SHEET_COLUMNS.map((column) => ({
    id: column,
    header: SHEET_COLUMN_LABELS[column],
  })),
]);

watch(
  () => props.receipt,
  (receipt) => {
    if (!receipt) return;
    edit.clear(receipt.applied.flatMap((row) => confirmedKeys(row.sku)));
  },
);

const rowFailures = computed(() => {
  const failures = new Map<string, string>();
  for (const failure of [
    ...(props.receipt?.conflicts ?? []),
    ...(props.receipt?.errors ?? []),
  ]) {
    const fields = (failure as { conflicting_fields?: string[] })
      .conflicting_fields;
    failures.set(failure.sku, failureText(failure.detail, fields));
  }
  for (const sku of blocked.value) {
    if (!failures.has(sku))
      failures.set(sku, "Corrija as células marcadas desta linha.");
  }
  return failures;
});

const problemsBySku = computed(() => {
  const map = new Map<string, Partial<Record<SheetColumn, string>>>();
  for (const row of sheetRows.value) {
    const touched = SHEET_COLUMNS.some(
      (column) => sheetKey(row.sku, column) in edit.draft.value,
    );
    if (touched) map.set(row.sku, rowProblems(row, edit.draft.value, profiles.value));
  }
  return map;
});

function problem(row: ProductSheetRow, column: SheetColumn): string {
  return problemsBySku.value.get(row.sku)?.[column] ?? "";
}

function value(row: ProductSheetRow, column: SheetColumn) {
  return cellValue(row, column, edit.draft.value);
}

function setValue(row: ProductSheetRow, column: SheetColumn, next: SheetValue) {
  edit.set(sheetKey(row.sku, column), next);
}

function onPaste(row: ProductSheetRow, column: SheetColumn, event: ClipboardEvent) {
  const text = event.clipboardData?.getData("text/plain") ?? "";
  // Um valor só, sem quebra nem tabulação, é digitação: o campo cola sozinho.
  if (!/[\t\n]/.test(text.trim()) && column !== "by_weight") return;
  const edits = pasteBlock(
    text,
    { skus: skus.value, sku: row.sku, column },
    { profiles: profiles.value, origins: origins.value },
  );
  if (!edits.length) return;
  event.preventDefault();
  for (const change of edits) edit.set(change.key, change.value);
}

function save() {
  const result = buildRowPatches(sheetRows.value, edit.draft.value, profiles.value);
  blocked.value = result.blocked;
  if (result.patches.length) emit("save", result.patches);
}

async function duplicateSelected() {
  const count = selectedSkus.value.length;
  if (!count) return;
  if (
    !(await confirmDuplicate({
      tone: "primary",
      title: `Duplicar ${count} produto${count === 1 ? "" : "s"}?`,
      description:
        "Cada cópia nasce oculta e fora de venda, com o SKU terminado em -COPIA e o nome com (cópia). Sem GTIN, coleção nem canal: revise e publique quando estiver pronta.",
      confirmLabel: count === 1 ? "Duplicar produto" : "Duplicar produtos",
      cancelLabel: "Voltar",
    }))
  )
    return;
  emit("duplicate", selectedSkus.value);
  rowSelection.value = {};
}

const TEXT_INPUT: Partial<Record<SheetColumn, { inputmode?: "decimal" | "numeric"; maxlength?: number; width: string }>> = {
  name: { maxlength: 200, width: "min-w-64" },
  short_description: { width: "min-w-56" },
  price: { inputmode: "decimal", width: "w-24" },
  ncm: { inputmode: "numeric", maxlength: 8, width: "w-28" },
  cest: { inputmode: "numeric", maxlength: 7, width: "w-24" },
};
</script>

<template>
  <NuxtSlideover
    :open="open"
    title="Tabelão de produtos"
    description="Edite nome, descrição, preço, peso e dados fiscais de vários produtos. Cole um bloco da planilha, desfaça e salve tudo numa ida."
    side="right"
    class="sm:max-w-6xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <template #body>
      <div class="flex flex-col gap-3">
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
          icon="i-lucide-clipboard-paste"
          description="Toque numa célula e cole linhas e colunas da planilha, na ordem do tabelão. CFOP e CSOSN saem do perfil fiscal; outra unidade de venda se edita no produto."
        />
        <div
          v-if="!sheet"
          class="py-8 text-center text-sm text-muted-foreground"
          data-sheet-loading
        >
          Carregando os produtos…
        </div>
        <OperatorTable
          v-else
          v-model:row-selection="rowSelection"
          :data="sheetRows"
          :columns="tableColumns"
          :row-key="(row: ProductSheetRow) => row.sku"
          caption="Tabelão de produtos"
          pinned="product"
          selectable
          :row-label="(row: ProductSheetRow) => row.name"
          data-product-sheet
        >
          <template #product-cell="{ row: tableRow }">
            <template v-for="row in [tableRow.original]" :key="row.sku">
              <!-- No desktop o nome está na coluna ao lado; no celular a coluna
                   fixa é a única que fica à vista, então leva o nome também. -->
              <div class="flex w-32 flex-col gap-1 sm:w-36">
                <span class="text-sm font-medium sm:hidden">{{ row.name }}</span>
                <span class="font-mono text-xs text-muted-foreground break-all">{{
                  row.sku
                }}</span>
                <span
                  v-if="!row.is_active"
                  class="text-xs text-muted-foreground"
                  >Arquivado</span
                >
                <NuxtAlert
                  v-if="rowFailures.get(row.sku)"
                  color="error"
                  variant="subtle"
                  icon="i-lucide-circle-alert"
                  :description="rowFailures.get(row.sku)"
                  :data-row-error="row.sku"
                />
                <p
                  v-else-if="row.fiscal_warnings.length"
                  class="text-xs text-warning"
                >
                  {{ row.fiscal_warnings.join(" ") }}
                </p>
              </div>
            </template>
          </template>
          <template
            v-for="column in SHEET_COLUMNS"
            :key="`sheet-${column}`"
            #[`${column}-cell`]="{ row: tableRow }"
          >
            <template v-for="row in [tableRow.original]" :key="row.sku">
              <div
                class="flex flex-col gap-1"
                :data-sheet-cell="`${row.sku}|${column}`"
                @paste="(event: ClipboardEvent) => onPaste(row, column, event)"
              >
                <NuxtCheckbox
                  v-if="column === 'by_weight'"
                  :model-value="value(row, column) === true"
                  :aria-label="`${row.name} vendido por peso`"
                  @update:model-value="
                    (next: boolean | 'indeterminate') =>
                      setValue(row, column, next === true)
                  "
                />
                <NuxtSelect
                  v-else-if="column === 'profile' || column === 'origin'"
                  :model-value="String(value(row, column)) || undefined"
                  :items="column === 'profile' ? profileItems : originItems"
                  :placeholder="column === 'profile' ? 'Sem perfil' : 'Origem'"
                  :aria-label="`${SHEET_COLUMN_LABELS[column]} de ${row.name}`"
                  :aria-invalid="Boolean(problem(row, column))"
                  class="w-44"
                  @update:model-value="
                    (next: string) => setValue(row, column, String(next ?? ''))
                  "
                />
                <NuxtInput
                  v-else
                  :model-value="String(value(row, column))"
                  :inputmode="TEXT_INPUT[column]?.inputmode"
                  :maxlength="TEXT_INPUT[column]?.maxlength"
                  :class="TEXT_INPUT[column]?.width"
                  :aria-label="`${SHEET_COLUMN_LABELS[column]} de ${row.name}`"
                  :aria-invalid="Boolean(problem(row, column))"
                  @update:model-value="
                    (next: string | number) => setValue(row, column, String(next))
                  "
                />
                <span
                  v-if="problem(row, column)"
                  class="text-xs text-error"
                  :data-cell-problem="`${row.sku}|${column}`"
                  >{{ problem(row, column) }}</span
                >
              </div>
            </template>
          </template>
        </OperatorTable>
      </div>
    </template>
    <template #footer>
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-xs text-muted-foreground">
          <template v-if="selectedSkus.length">
            {{ selectedSkus.length }} selecionado{{
              selectedSkus.length === 1 ? "" : "s"
            }}
            ·
          </template>
          <span class="tabular-nums">{{ edit.dirty.value }}</span>
          {{
            edit.dirty.value === 1
              ? "alteração não salva"
              : "alterações não salvas"
          }}
        </p>
        <div class="flex flex-wrap items-center gap-1.5">
          <NuxtButton
            v-if="selectedSkus.length"
            color="neutral"
            variant="outline"
            :label="`Duplicar ${selectedSkus.length}`"
            icon="i-lucide-copy"
            :loading="duplicateBusy"
            data-sheet-duplicate
            @click="duplicateSelected"
          />
          <NuxtButton
            color="neutral"
            variant="ghost"
            label="Desfazer"
            icon="i-lucide-undo-2"
            :disabled="!edit.canUndo.value"
            data-sheet-undo
            @click="edit.undo()"
          />
          <NuxtButton
            color="neutral"
            variant="outline"
            label="Descartar"
            :disabled="!edit.dirty.value"
            @click="
              edit.clear();
              blocked = [];
            "
          />
          <NuxtButton
            :label="`Salvar ${edit.dirty.value} ${edit.dirty.value === 1 ? 'alteração' : 'alterações'}`"
            :loading="busy"
            :disabled="!edit.dirty.value"
            data-sheet-save
            @click="save"
          />
        </div>
      </div>
    </template>
  </NuxtSlideover>
</template>
