<script setup lang="ts">
// Import CSV pt-BR do catálogo (onda 1, fatia C3). A prévia NÃO grava: mostra o
// que muda e o erro por linha; a confirmação leva a revisão da prévia.
import type { ImportPreview } from "~/types/catalog";

const props = defineProps<{
  open: boolean;
  preview: ImportPreview | null;
  previewBusy?: boolean;
  busy?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  preview: [csv: string];
  apply: [];
  reset: [];
}>();

const csv = ref("");
const fileName = ref("");

function reset() {
  csv.value = "";
  fileName.value = "";
  emit("reset");
}

function onFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  fileName.value = file.name;
  const reader = new FileReader();
  reader.onload = () => {
    csv.value = String(reader.result ?? "");
    emit("preview", csv.value);
  };
  reader.readAsText(file, "utf-8");
}

const totalLine = computed(() => {
  if (!props.preview) return "";
  const totals = props.preview.totals ?? {};
  const newCount = totals.new ?? 0;
  const updateCount = totals.update ?? 0;
  const skipped = totals.skip ?? 0;
  return `${newCount} novo(s) · ${updateCount} atualizado(s) · ${skipped} sem mudança`;
});

const errorCount = computed(() => props.preview?.errors.length ?? 0);

const money = (q: number) =>
  (q / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

const previewRows = computed(() =>
  (props.preview?.changes ?? []).map((change) => ({
    sku: change.sku,
    action: change.action === "new" ? "Novo" : "Atualiza",
    name: change.name,
    before: change.before ? money(change.before.base_price_q) : "",
  })),
);
const previewColumns = [
  { id: "sku", header: "SKU", accessorKey: "sku" },
  { id: "action", header: "Ação", accessorKey: "action" },
  { id: "name", header: "Nome", accessorKey: "name" },
  { id: "before", header: "Preço atual", accessorKey: "before" },
];
</script>

<template>
  <NuxtSlideover
    :open="open"
    title="Importar CSV"
    description="O arquivo tem as colunas do export (sku, name, base_price_q...). Use ponto e vírgula e vírgula decimal."
    side="right"
    class="sm:max-w-2xl"
    @update:open="
      (value: boolean) => {
        if (!value) reset();
        emit('update:open', value);
      }
    "
  >
    <template #body>
      <div class="flex flex-col gap-4">
        <NuxtAlert
          v-if="error"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-alert"
          :description="error"
        />
        <NuxtFormField
          label="Arquivo CSV"
          hint="Separador ponto e vírgula; vírgula decimal."
        >
          <NuxtInput
            type="file"
            accept=".csv,text/csv"
            :disabled="previewBusy"
            data-import-pick
            @change="onFile"
          />
        </NuxtFormField>
        <p v-if="fileName" class="text-sm text-muted-foreground">
          {{ fileName }}
        </p>

        <NuxtCard v-if="preview" variant="outline">
          <div class="flex flex-col gap-3">
            <div>
              <p class="text-sm font-medium">Prévia</p>
              <p class="text-xs text-muted-foreground">
                {{ totalLine }} · {{ preview.rows }} linha(s) lida(s)
              </p>
            </div>
            <NuxtAlert
              v-if="errorCount"
              color="warning"
              variant="subtle"
              icon="i-lucide-triangle-alert"
              :title="`${errorCount} linha(s) com erro`"
              description="Corrija o arquivo e leia de novo. Nada foi gravado."
            />
            <ul v-if="errorCount" class="ml-4 list-disc text-xs text-muted-foreground">
              <li v-for="item in preview.errors.slice(0, 20)" :key="item.row">
                Linha {{ item.row }}: {{ item.detail }}
              </li>
            </ul>
            <OperatorTable
              :data="previewRows"
              :columns="previewColumns"
              :row-key="(row) => row.sku"
              caption="Mudanças da importação"
              in-card
              data-import-preview
            />
          </div>
        </NuxtCard>
      </div>
    </template>
    <template #footer>
      <div class="flex items-center justify-end gap-1.5">
        <NuxtButton
          color="neutral"
          variant="ghost"
          label="Cancelar"
          @click="
            () => {
              reset();
              emit('update:open', false);
            }
          "
        />
        <NuxtButton
          label="Aplicar importação"
          :loading="busy"
          :disabled="!preview || errorCount > 0"
          data-import-apply
          @click="emit('apply')"
        />
      </div>
    </template>
  </NuxtSlideover>
</template>
