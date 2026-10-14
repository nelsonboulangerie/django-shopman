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
const fileInput = ref<HTMLInputElement | null>(null);

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
        <div class="flex items-center gap-2">
          <NuxtButton
            color="neutral"
            variant="outline"
            icon="i-lucide-file-up"
            label="Escolher arquivo CSV"
            :loading="previewBusy"
            data-import-pick
            @click="fileInput?.click()"
          />
          <span class="text-sm text-muted-foreground">{{ fileName }}</span>
          <input
            ref="fileInput"
            type="file"
            accept=".csv,text/csv"
            class="hidden"
            @change="onFile"
          />
        </div>

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
            <div class="max-h-72 overflow-y-auto">
              <table class="w-full text-xs">
                <thead class="text-left text-muted-foreground">
                  <tr>
                    <th class="p-1">SKU</th>
                    <th class="p-1">Ação</th>
                    <th class="p-1">Nome</th>
                    <th class="p-1">Preço atual</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="change in preview.changes"
                    :key="change.sku"
                    class="border-t border-default"
                  >
                    <td class="p-1">{{ change.sku }}</td>
                    <td class="p-1">
                      {{ change.action === "new" ? "Novo" : "Atualiza" }}
                    </td>
                    <td class="p-1">{{ change.name }}</td>
                    <td class="p-1 tabular-nums">
                      {{ change.before ? money(change.before.base_price_q) : "" }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
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
