<script setup lang="ts">
// Tabelão do catálogo (onda 1, fatia C): edição célula a célula de preço e das
// flags por superfície, com COLAR de planilha, DESFAZER e salvar em LOTE numa
// ida pelo POST catalog/cells/. Presentacional: o pai é dono do save.
import type {
  BulkCell,
  BulkCellsResponse,
  CatalogRowProjection,
  ProductArchiveReceipt,
  SurfaceProjection,
} from "~/types/catalog";
import {
  editKey,
  parseGrid,
  parseMoneyCell,
  splitEditKey,
} from "../../../operator-kit/app/presentation/gridEdit";

const props = defineProps<{
  open: boolean;
  rows: CatalogRowProjection[];
  surfaces: SurfaceProjection[];
  busy?: boolean;
  error?: string;
  receipt?: BulkCellsResponse | null;
  archiveBusy?: boolean;
  archiveReceipt?: ProductArchiveReceipt | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [cells: BulkCell[]];
  archive: [
    products: { sku: string; base_is_active: boolean }[],
    active: boolean,
  ];
}>();

const confirmArchive = useConfirm();

const edit = useGridEdit<string | boolean>();
const pendingCells = ref<BulkCell[]>([]);
const rowSelection = ref<Record<string, boolean>>({});
const selectedRows = computed(() =>
  props.rows.filter((row) => rowSelection.value[row.sku]),
);
const selectedState = computed(() => {
  const states = new Set(selectedRows.value.map((row) => row.is_active));
  return states.size === 1 ? selectedRows.value[0]?.is_active : undefined;
});
const archiveReceiptDescription = computed(() => {
  const receipt = props.archiveReceipt;
  if (!receipt) return "";
  const lines = receipt.applied.map(
    (row) => `${row.name}: ${row.is_active ? "desarquivado" : "arquivado"}`,
  );
  lines.push(...receipt.conflicts.map((row) => `${row.sku}: ${row.detail}`));
  lines.push(...receipt.errors.map((row) => `${row.sku}: ${row.detail}`));
  return lines.join(" · ");
});

watch(
  () => props.open,
  (open) => {
    if (open) edit.clear();
    if (open) rowSelection.value = {};
  },
);

const centsToText = (q: number) => (q / 100).toFixed(2).replace(".", ",");

const columnId = (ref: string) =>
  `surface_${ref.replace(/[^a-zA-Z0-9_]/g, "_")}`;
const bulkColumns = computed(() => [
  { id: "product", header: "Produto", enableHiding: false },
  ...props.surfaces.map((surface) => ({
    id: columnId(surface.ref),
    header: surface.short_name,
  })),
]);

function cellFor(row: CatalogRowProjection, surfaceRef: string) {
  return row.cells.find((cell) => cell.surface_ref === surfaceRef);
}

function priceKey(sku: string, surfaceRef: string) {
  return editKey(sku, surfaceRef, "price");
}

watch(
  () => props.receipt,
  (receipt) => {
    if (!receipt) return;
    const confirmed: string[] = [];
    for (const applied of receipt.applied) {
      const submitted = pendingCells.value[applied.index];
      if (
        !submitted ||
        submitted.sku !== applied.sku ||
        submitted.surface_ref !== applied.surface_ref
      )
        continue;
      if ("price_q" in submitted)
        confirmed.push(priceKey(submitted.sku, submitted.surface_ref));
      if ("is_published" in submitted)
        confirmed.push(
          editKey(submitted.sku, submitted.surface_ref, "published"),
        );
      if ("is_sellable" in submitted)
        confirmed.push(
          editKey(submitted.sku, submitted.surface_ref, "sellable"),
        );
    }
    edit.clear(confirmed);
  },
);

const cellFailures = computed(() => {
  const failures = new Map<string, string>();
  if (!props.receipt) return failures;
  for (const failure of [
    ...props.receipt.conflicts,
    ...props.receipt.errors,
  ]) {
    const conflictingFields = (
      failure as { conflicting_fields?: string[] }
    ).conflicting_fields;
    const fields =
      conflictingFields?.length
        ? `${conflictingFields
            .map((field) =>
              field === "price_q"
                ? "Preço"
                : field === "is_published"
                  ? "Exibido"
                  : field === "is_sellable"
                    ? "Vendável"
                    : field,
            )
            .join(", ")}: `
        : "";
    failures.set(
      editKey(failure.sku, failure.surface_ref, "cell"),
      `${fields}${failure.detail}`,
    );
  }
  return failures;
});

function cellFailure(sku: string, surfaceRef: string): string {
  return cellFailures.value.get(editKey(sku, surfaceRef, "cell")) ?? "";
}

function priceText(row: CatalogRowProjection, surfaceRef: string): string {
  const draft = edit.draft.value[priceKey(row.sku, surfaceRef)];
  if (typeof draft === "string") return draft;
  const cell = cellFor(row, surfaceRef);
  return cell?.price_q != null ? centsToText(cell.price_q) : "";
}

function onPrice(row: CatalogRowProjection, surfaceRef: string, value: string) {
  edit.set(priceKey(row.sku, surfaceRef), value);
}

// Célula vazia ou ilegível volta ao valor do SERVIDOR: preço não vira zero sozinho.
function onPriceBlur(row: CatalogRowProjection, surfaceRef: string) {
  const key = priceKey(row.sku, surfaceRef);
  const text = edit.draft.value[key];
  if (typeof text !== "string") return;
  if (parseMoneyCell(text) === null) edit.remove(key);
}

function flagValue(
  row: CatalogRowProjection,
  surfaceRef: string,
  field: "published" | "sellable",
): boolean {
  const draft = edit.draft.value[editKey(row.sku, surfaceRef, field)];
  if (typeof draft === "boolean") return draft;
  const cell = cellFor(row, surfaceRef);
  if (!cell) return false;
  return field === "published" ? cell.is_published : cell.is_sellable;
}

function setFlag(
  row: CatalogRowProjection,
  surfaceRef: string,
  field: "published" | "sellable",
  value: boolean,
) {
  edit.set(editKey(row.sku, surfaceRef, field), value);
}

// Colar uma coluna de preços (TSV/CSV) desce pela MESMA superfície, a partir da
// linha focada. É o gesto de planilha: coluna no clipboard, coluna no tabelão.
function onPaste(
  row: CatalogRowProjection,
  surfaceRef: string,
  event: ClipboardEvent,
) {
  const text = event.clipboardData?.getData("text/plain") ?? "";
  const grid = parseGrid(text);
  if (!grid.length) return;
  event.preventDefault();
  const start = props.rows.findIndex((item) => item.sku === row.sku);
  if (start < 0) return;
  grid.forEach((line, offset) => {
    const target = props.rows[start + offset];
    if (!target) return;
    const raw = line[0];
    if (raw === undefined || raw === "") return;
    edit.set(priceKey(target.sku, surfaceRef), raw);
  });
}

function save() {
  const byCell = new Map<string, BulkCell>();
  for (const { key, value } of edit.changes.value) {
    const [sku, surfaceRef, field] = splitEditKey(key);
    const identity = [sku, surfaceRef].join("|");
    const entry: BulkCell = byCell.get(identity) ?? {
      sku,
      surface_ref: surfaceRef,
    };
    if (field === "price") {
      const cents = parseMoneyCell(String(value));
      if (cents === null) {
        byCell.delete(identity);
        continue;
      }
      entry.price_q = cents;
    } else if (field === "published") {
      entry.is_published = Boolean(value);
    } else if (field === "sellable") {
      entry.is_sellable = Boolean(value);
    }
    byCell.set(identity, entry);
  }
  const cells = [...byCell.values()].map((entry) => {
    const row = props.rows.find((item) => item.sku === entry.sku);
    const cell = row?.cells.find(
      (item) => item.surface_ref === entry.surface_ref,
    );
    const schema = cell?.action?.payload_schema as
      Record<string, unknown> | undefined;
    return {
      ...entry,
      base_revisions: schema?.base_revisions as
        Record<string, string> | undefined,
    };
  });
  pendingCells.value = cells;
  emit("save", cells);
}

async function setSelectedActive(active: boolean) {
  if (!selectedRows.value.length || selectedState.value === undefined) return;
  if (
    !(await confirmArchive({
      ...(active
        ? {
            tone: "primary" as const,
            confirmLabel: "Desarquivar produtos",
            cancelLabel: "Manter arquivados",
          }
        : {
            tone: "danger" as const,
            confirmLabel: "Arquivar produtos",
            cancelLabel: "Manter produtos",
          }),
      title: `${active ? "Desarquivar" : "Arquivar"} ${selectedRows.value.length} produto${selectedRows.value.length === 1 ? "" : "s"}?`,
      description: active
        ? "Os produtos voltam às listas e aos canais conforme os estados publicado e vendável que já tinham."
        : "Os produtos saem do cardápio, dos canais e das listas. O histórico e os vínculos ficam guardados.",
    }))
  )
    return;
  emit(
    "archive",
    selectedRows.value.map((row) => ({
      sku: row.sku,
      base_is_active: row.is_active,
    })),
    active,
  );
}

function undoArchive() {
  const receipt = props.archiveReceipt;
  if (!receipt?.applied.length) return;
  emit(
    "archive",
    receipt.applied.map((row) => ({
      sku: row.sku,
      base_is_active: row.is_active,
    })),
    receipt.applied[0]?.before_is_active ?? true,
  );
}
</script>

<template>
  <NuxtSlideover
    :open="open"
    title="Tabelão"
    :description="'Edite preço e publicação por canal. Cole uma coluna de preços, desfaça e salve tudo numa ida.'"
    side="right"
    class="sm:max-w-4xl"
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
          v-if="archiveReceiptDescription"
          :color="
            archiveReceipt?.conflicts.length || archiveReceipt?.errors.length
              ? 'warning'
              : 'success'
          "
          variant="subtle"
          title="Recibo do arquivamento"
          :description="archiveReceiptDescription"
          data-archive-receipt
        />
        <NuxtAlert
          color="info"
          variant="subtle"
          icon="i-lucide-clipboard-paste"
          description="Toque num preço e cole a coluna da planilha. Preço vazio volta ao valor atual; nada é gravado antes de salvar."
        />
        <OperatorTable
          v-model:row-selection="rowSelection"
          :data="rows"
          :columns="bulkColumns"
          :row-key="(row: CatalogRowProjection) => row.sku"
          caption="Tabelão de preços e publicação por canal"
          selectable
          :row-label="(row: CatalogRowProjection) => row.name"
          data-bulk-grid
        >
          <template #product-cell="{ row: tableRow }">
            <template v-for="row in [tableRow.original]" :key="row.sku">
              <div class="font-medium">
                {{ row.name }}
                <span class="block text-xs text-muted-foreground">{{
                  row.sku
                }}</span>
              </div>
            </template>
          </template>
          <template
            v-for="surface in surfaces"
            :key="`cell-${surface.ref}`"
            #[`${columnId(surface.ref)}-cell`]="{ row: tableRow }"
          >
            <template v-for="row in [tableRow.original]" :key="row.sku">
              <div class="flex flex-col gap-1">
                <NuxtInput
                  :model-value="priceText(row, surface.ref)"
                  inputmode="decimal"
                  :aria-label="`Preço de ${row.name} em ${surface.name}`"
                  :aria-invalid="Boolean(cellFailure(row.sku, surface.ref))"
                  :data-cell="`${row.sku}|${surface.ref}|price`"
                  @update:model-value="
                    (value: string | number) =>
                      onPrice(row, surface.ref, String(value))
                  "
                  @blur="onPriceBlur(row, surface.ref)"
                  @paste="
                    (event: ClipboardEvent) => onPaste(row, surface.ref, event)
                  "
                />
                <div class="flex items-center gap-2">
                  <NuxtCheckbox
                    :model-value="flagValue(row, surface.ref, 'published')"
                    label="Exibido"
                    @update:model-value="
                      (value: boolean | 'indeterminate') =>
                        setFlag(row, surface.ref, 'published', value === true)
                    "
                  />
                  <NuxtCheckbox
                    :model-value="flagValue(row, surface.ref, 'sellable')"
                    label="Vendável"
                    @update:model-value="
                      (value: boolean | 'indeterminate') =>
                        setFlag(row, surface.ref, 'sellable', value === true)
                    "
                  />
                </div>
                <NuxtAlert
                  v-if="cellFailure(row.sku, surface.ref)"
                  color="error"
                  variant="subtle"
                  icon="i-lucide-circle-alert"
                  :description="cellFailure(row.sku, surface.ref)"
                  :data-cell-error="`${row.sku}|${surface.ref}`"
                />
              </div>
            </template>
          </template>
        </OperatorTable>
      </div>
    </template>
    <template #footer>
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs text-muted-foreground">
          <template v-if="selectedRows.length">
            {{ selectedRows.length }} selecionado{{
              selectedRows.length === 1 ? "" : "s"
            }}
            ·
          </template>
          <span class="tabular-nums">{{ edit.dirty.value }}</span>
          {{ edit.dirty.value === 1 ? "alteração não salva" : "alterações não salvas" }}
        </p>
        <div class="flex items-center gap-1.5">
          <OperatorTimedButton
            v-if="archiveReceipt?.applied.length"
            label="Desfazer"
            short-label="Desfazer"
            icon="i-lucide-undo-2"
            color="error"
            :until="archiveReceipt.undo_until"
            :server-now="archiveReceipt.server_now"
            :loading="archiveBusy"
            data-bulk-archive-undo
            @click="undoArchive"
          />
          <NuxtButton
            v-else-if="selectedRows.length"
            :label="selectedState === false ? 'Desarquivar' : 'Arquivar'"
            :icon="
              selectedState === false
                ? 'i-lucide-archive-restore'
                : 'i-lucide-archive'
            "
            :color="selectedState === false ? 'primary' : 'error'"
            :disabled="selectedState === undefined"
            :loading="archiveBusy"
            data-bulk-archive
            @click="setSelectedActive(selectedState === false)"
          />
          <NuxtButton
            color="neutral"
            variant="ghost"
            label="Desfazer"
            icon="i-lucide-undo-2"
            :disabled="!edit.canUndo.value"
            data-bulk-undo
            @click="edit.undo()"
          />
          <NuxtButton
            color="neutral"
            variant="outline"
            label="Descartar"
            :disabled="!edit.dirty.value"
            @click="edit.clear()"
          />
          <NuxtButton
            :label="`Salvar ${edit.dirty.value} ${edit.dirty.value === 1 ? 'alteração' : 'alterações'}`"
            :loading="busy"
            :disabled="!edit.dirty.value"
            data-bulk-save
            @click="save"
          />
        </div>
      </div>
    </template>
  </NuxtSlideover>
</template>
