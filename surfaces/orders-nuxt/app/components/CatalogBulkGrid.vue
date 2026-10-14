<script setup lang="ts">
// Tabelão do catálogo (onda 1, fatia C): edição célula a célula de preço e das
// flags por superfície, com COLAR de planilha, DESFAZER e salvar em LOTE numa
// ida pelo POST catalog/cells/. Presentacional: o pai é dono do save.
import type {
  BulkCell,
  CatalogRowProjection,
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
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [cells: BulkCell[]];
}>();

const edit = useGridEdit<string | boolean>();

watch(
  () => props.open,
  (open) => {
    if (open) edit.clear();
  },
);

const centsToText = (q: number) => (q / 100).toFixed(2).replace(".", ",");

function cellFor(row: CatalogRowProjection, surfaceRef: string) {
  return row.cells.find((cell) => cell.surface_ref === surfaceRef);
}

function priceKey(sku: string, surfaceRef: string) {
  return editKey(sku, surfaceRef, "price");
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
    const entry: BulkCell =
      byCell.get(identity) ?? { sku, surface_ref: surfaceRef };
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
      | Record<string, unknown>
      | undefined;
    return {
      ...entry,
      base_revisions: schema?.base_revisions as
        | Record<string, string>
        | undefined,
    };
  });
  emit("save", cells);
}
</script>

<template>
  <NuxtSlideover
    :open="open"
    title="Tabelão"
    :description="
      'Edite preço e publicação por canal. Cole uma coluna de preços, desfaça e salve tudo numa ida.'
    "
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
          color="info"
          variant="subtle"
          icon="i-lucide-clipboard-paste"
          description="Toque num preço e cole a coluna da planilha. Preço vazio volta ao valor atual; nada é gravado antes de salvar."
        />
        <div class="overflow-x-auto">
          <table class="w-full text-sm" data-bulk-grid>
            <thead>
              <tr class="text-left text-muted-foreground">
                <th class="sticky left-0 bg-default p-2">Produto</th>
                <th
                  v-for="surface in surfaces"
                  :key="surface.ref"
                  class="min-w-48 p-2"
                >
                  {{ surface.short_name }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in rows"
                :key="row.sku"
                class="border-t border-default"
              >
                <th class="sticky left-0 bg-default p-2 text-left font-medium">
                  {{ row.name }}
                  <span class="block text-xs text-muted-foreground">{{
                    row.sku
                  }}</span>
                </th>
                <td
                  v-for="surface in surfaces"
                  :key="surface.ref"
                  class="p-2 align-top"
                >
                  <div class="flex flex-col gap-1">
                    <NuxtInput
                      :model-value="priceText(row, surface.ref)"
                      inputmode="decimal"
                      size="sm"
                      :aria-label="`Preço de ${row.name} em ${surface.name}`"
                      :data-cell="`${row.sku}|${surface.ref}|price`"
                      @update:model-value="
                        (value: string | number) =>
                          onPrice(row, surface.ref, String(value))
                      "
                      @blur="onPriceBlur(row, surface.ref)"
                      @paste="
                        (event: ClipboardEvent) =>
                          onPaste(row, surface.ref, event)
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
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
    <template #footer>
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs text-muted-foreground">
          <span class="tabular-nums">{{ edit.dirty.value }}</span>
          alteração{{ edit.dirty.value === 1 ? "" : "ões" }} não salva{{
            edit.dirty.value === 1 ? "" : "s"
          }}
        </p>
        <div class="flex items-center gap-1.5">
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
            :label="`Salvar ${edit.dirty.value} alteração(ões)`"
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
