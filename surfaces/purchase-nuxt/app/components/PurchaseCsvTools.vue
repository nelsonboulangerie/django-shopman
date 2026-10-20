<script setup lang="ts">
import { computed, ref } from "vue";
import type { CsvTable } from "../../../operator-kit/app/presentation/csv";

const props = defineProps<{ entity: "materials" | "suppliers" }>();
const emit = defineEmits<{ applied: [] }>();
interface Preview {
  rows: number;
  totals: Record<string, number>;
  errors: { row: number; detail: string }[];
  changes: Record<string, unknown>[];
  base_revision: string;
}
const importOpen = ref(false);
const exportOpen = ref(false);
const previewBusy = ref(false);
const busy = ref(false);
const error = ref("");
const source = ref("");
const preview = ref<Preview | null>(null);
const table = ref<CsvTable | null>(null);
const intention = ref("");
const label = computed(() =>
  props.entity === "materials" ? "insumos" : "fornecedores",
);
const endpoint = computed(
  () => `/api/v1/backstage/purchase/${props.entity}/csv/`,
);
const columns = [
  {
    accessorKey: "ref",
    header: props.entity === "materials" ? "SKU" : "Referência",
  },
  { accessorKey: "name", header: "Nome" },
  { accessorKey: "action", header: "Alteração" },
];
function reset() {
  preview.value = null;
  source.value = "";
  error.value = "";
  intention.value = "";
}
function openImport() {
  reset();
  importOpen.value = true;
}
function message(exc: unknown) {
  return (
    (exc as { data?: { detail?: string } }).data?.detail ||
    "Não foi possível confirmar a alteração. Tente de novo."
  );
}
async function loadPreview(csv: string) {
  source.value = csv;
  preview.value = null;
  error.value = "";
  previewBusy.value = true;
  intention.value = "";
  try {
    const result = await $fetch<{ preview: Preview }>(endpoint.value, {
      method: "POST",
      credentials: "include",
      body: { csv, preview: true },
    });
    preview.value = result.preview;
    intention.value = crypto.randomUUID();
  } catch (exc) {
    error.value = message(exc);
  } finally {
    previewBusy.value = false;
  }
}
async function apply() {
  if (!preview.value || preview.value.errors.length || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await $fetch<{ ok?: boolean; outcome?: string }>(
      endpoint.value,
      {
        method: "POST",
        credentials: "include",
        headers: { "Idempotency-Key": intention.value },
        body: { csv: source.value, base_revision: preview.value.base_revision },
      },
    );
    if (result.outcome !== "applied" || !result.ok) {
      error.value = "A importação ainda não foi confirmada. Tente de novo.";
      return;
    }
    importOpen.value = false;
    reset();
    emit("applied");
  } catch (exc) {
    error.value = message(exc);
  } finally {
    busy.value = false;
  }
}
async function openExport() {
  exportOpen.value = true;
  table.value = null;
  error.value = "";
  previewBusy.value = true;
  try {
    table.value = (
      await $fetch<{ table: CsvTable }>(endpoint.value, {
        credentials: "include",
      })
    ).table;
  } catch (exc) {
    error.value = message(exc);
  } finally {
    previewBusy.value = false;
  }
}
defineExpose({ openImport, openExport });
</script>
<template>
  <OperatorCsvImport
    :open="importOpen"
    :preview="preview"
    :columns="columns"
    :row-key="(row: Record<string, unknown>) => String(row.ref)"
    :title="`Importar ${label}`"
    description="Use o CSV exportado como modelo. Confira até 1.000 cadastros na prévia antes de salvar. Quantidades com vírgula decimal."
    :total-labels="{
      new: preview?.totals.new === 1 ? 'novo' : 'novos',
      update: preview?.totals.update === 1 ? 'atualizado' : 'atualizados',
    }"
    :preview-busy="previewBusy || busy"
    :busy="busy"
    :error="error"
    @update:open="importOpen = $event"
    @preview="loadPreview"
    @apply="apply"
    @reset="reset"
  />
  <NuxtModal
    :open="exportOpen"
    :title="`Exportar ${label}`"
    description="O arquivo inclui todos os cadastros da Base, em uso e arquivados, sem limitar à página atual. Colunas em português e vírgula decimal."
    @update:open="exportOpen = $event"
  >
    <template #body>
      <p v-if="previewBusy" role="status">Preparando o arquivo…</p>
      <NuxtAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="O arquivo não ficou pronto"
        :description="error"
        close
        @update:open="error = ''"
      />
      <div v-if="table" class="flex flex-col items-start gap-3">
        <p class="text-sm text-muted">
          {{ table.rows.length }}
          {{
            table.rows.length === 1
              ? entity === "materials"
                ? "insumo"
                : "fornecedor"
              : label
          }}
          no arquivo.
        </p>
        <OperatorCsvExportButton
          :table="table"
          :file-name="`${entity}-${new Date().toISOString().slice(0, 10)}.csv`"
          label="Baixar CSV"
        />
      </div>
    </template>
  </NuxtModal>
</template>
