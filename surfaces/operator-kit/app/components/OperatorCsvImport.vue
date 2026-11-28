<script setup lang="ts">
import type { TableColumn } from "@nuxt/ui";

interface ImportError {
  row: number;
  detail: string;
}

interface ImportPreview {
  rows: number;
  totals: Record<string, number>;
  errors: ImportError[];
  changes: Record<string, unknown>[];
  base_revision: string;
}

const props = withDefaults(
  defineProps<{
    open: boolean;
    preview: ImportPreview | null;
    columns: TableColumn<Record<string, unknown>>[];
    rowKey: (row: Record<string, unknown>) => string;
    totalLabels?: Record<string, string>;
    title?: string;
    description?: string;
    previewBusy?: boolean;
    busy?: boolean;
    error?: string;
  }>(),
  {
    title: "Importar CSV",
    description:
      "Escolha um arquivo com cabeçalho em português, ponto e vírgula entre campos e vírgula decimal.",
    totalLabels: () => ({}),
    previewBusy: false,
    busy: false,
    error: "",
  },
);

const emit = defineEmits<{
  "update:open": [value: boolean];
  preview: [csv: string];
  apply: [revision: string];
  reset: [];
}>();

const selectedFile = ref<File | null>(null);
const fileName = computed(() => selectedFile.value?.name ?? "");

const fileActionLabel = computed(() => {
  if (props.previewBusy) return "Lendo arquivo CSV";
  return fileName.value ? "Trocar arquivo CSV" : "Escolher arquivo CSV";
});

const fileDescription = computed(() => {
  if (props.previewBusy) return "Aguarde enquanto a prévia é preparada.";
  if (fileName.value) return "Solte outro arquivo aqui ou escolha no dispositivo.";
  return "Solte o arquivo aqui ou escolha no dispositivo.";
});

const fileState = computed(() =>
  fileName.value ? `Arquivo selecionado: ${fileName.value}` : "Nenhum arquivo selecionado.",
);

function reset() {
  selectedFile.value = null;
  emit("reset");
}

function onFile(file: File | null | undefined) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => emit("preview", String(reader.result ?? ""));
  reader.readAsText(file, "utf-8");
}

const totalLine = computed(() =>
  Object.entries(props.preview?.totals ?? {})
    .map(([key, value]) => `${value} ${props.totalLabels[key] ?? key}`)
    .join(" · "),
);

const rowsRead = computed(() =>
  props.preview?.rows === 1 ? "1 linha lida" : `${props.preview?.rows ?? 0} linhas lidas`,
);

const rowsWithError = computed(() => {
  const count = props.preview?.errors.length ?? 0;
  return count === 1 ? "1 linha com erro" : `${count} linhas com erro`;
});
</script>

<template>
  <NuxtSlideover
    :open="open"
    :title="title"
    :description="description"
    side="right"
    class="sm:max-w-2xl"
    @update:open="(value: boolean) => { if (!value) reset(); emit('update:open', value); }"
  >
    <template #body>
      <div class="flex flex-col gap-4">
        <NuxtAlert v-if="error" color="error" variant="subtle" icon="i-lucide-circle-alert" :description="error" />
        <NuxtFormField label="Arquivo CSV" hint="Separador ponto e vírgula; vírgula decimal.">
          <div data-import-picker>
            <NuxtFileUpload
              v-model="selectedFile"
              :label="fileActionLabel"
              :description="fileDescription"
              accept=".csv,text/csv"
              layout="list"
              position="outside"
              reset
              :file-image="false"
              :disabled="previewBusy"
              :highlight="Boolean(error)"
              :color="error ? 'error' : 'primary'"
              class="w-full"
              @update:model-value="onFile"
            />
            <p
              class="sr-only"
              aria-live="polite"
              data-import-file-state
            >
              {{ fileState }}
            </p>
          </div>
        </NuxtFormField>

        <NuxtCard v-if="preview" variant="outline">
          <div class="flex flex-col gap-3">
            <div>
              <p class="text-sm font-medium">Prévia</p>
              <p class="text-xs text-muted-foreground">{{ totalLine }} · {{ rowsRead }}</p>
            </div>
            <NuxtAlert
              v-if="preview.errors.length"
              color="warning"
              variant="subtle"
              icon="i-lucide-triangle-alert"
              :title="rowsWithError"
              description="Corrija o arquivo e leia de novo. Nada foi gravado."
            />
            <ul v-if="preview.errors.length" class="ml-4 list-disc text-xs text-muted-foreground">
              <li v-for="item in preview.errors.slice(0, 20)" :key="item.row">Linha {{ item.row }}: {{ item.detail }}</li>
            </ul>
            <OperatorTable
              :data="preview.changes"
              :columns="columns"
              :row-key="rowKey"
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
        <NuxtButton color="neutral" variant="ghost" label="Cancelar" @click="() => { reset(); emit('update:open', false); }" />
        <NuxtButton
          label="Aplicar importação"
          :loading="busy"
          :disabled="!preview || preview.errors.length > 0"
          data-import-apply
          @click="preview && emit('apply', preview.base_revision)"
        />
      </div>
    </template>
  </NuxtSlideover>
</template>
