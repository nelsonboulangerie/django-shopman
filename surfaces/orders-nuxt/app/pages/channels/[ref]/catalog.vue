<script setup lang="ts">
import { realtimeIndicator } from "~/presentation/board";

definePageMeta({ key: (route) => route.path });
const route = useRoute();
const channel = String(route.params.ref);
const {
  board,
  pending,
  error,
  stale,
  refresh,
  readMetadata,
  realtime,
  selected,
  busy,
  message,
  importSnapshot,
  bind,
} = useCatalogBindings(channel);
const fileName = ref("");
const rawJson = ref("");
const fileError = ref("");
const reading = ref(false);
const dirty = ref(false);
let disposed = false;
function protectDraft(event: BeforeUnloadEvent) {
  if (!dirty.value && !rawJson.value) return;
  event.preventDefault();
  event.returnValue = "";
}
onMounted(() => window.addEventListener("beforeunload", protectDraft));
onBeforeUnmount(() => {
  disposed = true;
  window.removeEventListener("beforeunload", protectDraft);
});
async function readFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file || reading.value) return;
  fileError.value = "";
  rawJson.value = "";
  fileName.value = file.name;
  if (file.size > 20 * 1024 * 1024) {
    fileError.value = "O arquivo excede o limite de 20 MiB.";
    return;
  }
  reading.value = true;
  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(
      await file.arrayBuffer(),
    );
    if (!disposed) rawJson.value = text;
  } catch {
    if (!disposed)
      fileError.value = "Não foi possível ler o arquivo como UTF-8.";
  } finally {
    if (!disposed) reading.value = false;
  }
}
const confirmDiscard = useConfirm();
async function storeSnapshot() {
  if (!rawJson.value || busy.value || error.value) return;
  if (
    dirty.value &&
    !(await confirmDiscard({
      title: "Guardar o novo inventário e descartar a seleção?",
      description:
        "Os vínculos que você marcou e ainda não confirmou se perdem.",
      confirmLabel: "Descartar e guardar",
      cancelLabel: "Continuar revisando",
    }))
  )
    return;
  if (await importSnapshot(rawJson.value)) {
    rawJson.value = "";
    fileName.value = "";
    dirty.value = false;
  }
}
async function selectSnapshot(value: string | number) {
  if (
    dirty.value &&
    !(await confirmDiscard({
      title: "Trocar de inventário e descartar a seleção?",
      description:
        "Os vínculos que você marcou e ainda não confirmou se perdem.",
      confirmLabel: "Descartar e trocar",
      cancelLabel: "Continuar revisando",
    }))
  ) {
    return;
  }
  dirty.value = false;
  selected.value = String(value);
}
onBeforeRouteLeave(
  () =>
    !(dirty.value || rawJson.value) ||
    confirmDiscard({
      title: "Sair sem concluir a revisão de vínculos?",
      description:
        "O que ainda não foi confirmado nesta revisão se perde: os vínculos marcados e o arquivo lido que não foi guardado.",
      confirmLabel: "Descartar e sair",
      cancelLabel: "Continuar revisando",
    }),
);
useHead({ title: "Revisão de vínculos" });
// Celular (abaixo de `sm`, README do kit "Barra do topo no celular" e "Toolbar no
// celular"): as ações da toolbar vão para o ⋯ da barra do topo e a leitura (frescor)
// desce para a faixa de texto abaixo da linha. Do `sm` para cima, tudo como está.
const { belowSm: isNarrow } = useScreen();
const phoneHeaderActions = computed(() =>
  isNarrow.value
    ? [
        { label: "Atualizar revisão", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() },
      ]
    : undefined,
);
</script>

<template>
  <main class="flex min-h-0 min-w-0 flex-1 flex-col">
    <OperatorPageHeader
      :title="`${board?.channel_name || channel} · Revisão de vínculos`"
      :filters-wrap="false"
      :actions="phoneHeaderActions"
    >
      <template #lead>
        <NuxtButton
          to="/feeds"
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="ghost"
          square
          aria-label="Voltar para Canais"
        />
      </template>
      <template v-if="!isNarrow" #filters>
        <NuxtButton
          icon="i-lucide-refresh-cw"
          label="Atualizar revisão"
          color="neutral"
          variant="outline"
          :loading="pending"
          @click="refresh()"
        />
      </template>
      <template #filters-end>
        <ReadFreshness
          inline
          :metadata="readMetadata"
          :failed="Boolean(error)"
          :realtime-label="realtimeIndicator(realtime).label"
        />
      </template>
    </OperatorPageHeader>
    <div class="min-h-0 min-w-0 flex-1 space-y-4 overflow-auto p-4 sm:p-6">
      <p class="max-w-4xl text-sm text-muted-foreground">
        Confira a identidade dos anúncios antes de associá-los ao cadastro. Os
        dados locais ainda precisam de revisão. Este fluxo não envia alterações
        à plataforma.
      </p>
      <NuxtAlert
        v-if="message"
        color="info"
        variant="subtle"
        icon="i-lucide-info"
        :description="message"
      />
      <NuxtAlert
        v-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Não foi possível atualizar a revisão"
        :description="
          board
            ? 'Exibindo a última leitura disponível; a gravação está bloqueada.'
            : 'Tente novamente para consultar os inventários.'
        "
        :actions="[
          {
            label: 'Tentar de novo',
            color: 'error',
            variant: 'outline',
            onClick: () => refresh(),
          },
        ]"
      />
      <NuxtSkeleton
        v-if="pending && !board"
        class="h-48 w-full"
        aria-label="Carregando inventários"
      />
      <template v-if="board">
        <NuxtCollapsible>
          <NuxtButton
            icon="i-lucide-upload"
            label="Carregar inventário para revisão"
            color="neutral"
            variant="outline"
          />
          <template #content>
            <NuxtCard variant="soft" class="mt-2">
              <div class="max-w-2xl space-y-3">
                <p class="text-sm text-muted-foreground">
                  Selecione a captura completa gerada pelo coletor iFood. O
                  arquivo será guardado no sistema; nenhum produto será alterado
                  ou vinculado automaticamente.
                </p>
                <NuxtFormField label="Arquivo JSON da captura">
                  <NuxtInput
                    class="w-full"
                    type="file"
                    accept=".json,application/json"
                    :disabled="busy || reading || Boolean(error)"
                    @change="readFile"
                  />
                </NuxtFormField>
                <p v-if="fileName" class="break-all text-sm">{{ fileName }}</p>
                <NuxtAlert
                  v-if="fileError"
                  color="error"
                  variant="subtle"
                  icon="i-lucide-circle-alert"
                  :description="fileError"
                />
                <NuxtButton
                  label="Guardar inventário para revisão"
                  :disabled="
                    !rawJson ||
                    busy ||
                    reading ||
                    Boolean(error) ||
                    !board.import_action?.enabled
                  "
                  @click="storeSnapshot"
                />
              </div>
            </NuxtCard>
          </template>
        </NuxtCollapsible>
        <NuxtEmpty
          v-if="!board.snapshots.length && !error"
          icon="i-lucide-package-search"
          title="Nenhum inventário guardado"
          description="Carregue uma captura para começar a revisão."
        />
        <NuxtFormField
          v-if="board.snapshots.length"
          label="Inventário em revisão"
        >
          <NuxtSelect
            :model-value="board.selected_snapshot?.id"
            :items="
              board.snapshots.map((snapshot) => ({
                value: snapshot.id,
                label: `Captura #${snapshot.id} · ${snapshot.captured_at} · ${snapshot.context} · ${snapshot.item_count} anúncios`,
              }))
            "
            :disabled="busy || Boolean(error)"
            class="w-full"
            @update:model-value="(value) => selectSnapshot(Number(value))"
          />
        </NuxtFormField>
        <NuxtCollapsible v-if="board.selected_snapshot">
          <NuxtButton
            icon="i-lucide-info"
            label="Origem e identificação da captura"
            color="neutral"
            variant="ghost"
          />
          <template #content>
            <NuxtCard variant="soft" class="mt-2">
              <dl class="space-y-1 break-all text-xs text-muted-foreground">
                <dt>Loja externa declarada</dt>
                <dd>{{ board.selected_snapshot.account_ref }}</dd>
                <dt>Catálogo e contexto</dt>
                <dd>
                  {{ board.selected_snapshot.catalog_ref }} ·
                  {{ board.selected_snapshot.context }}
                </dd>
                <dt>Identificação única do arquivo</dt>
                <dd>{{ board.selected_snapshot.sha256 }}</dd>
              </dl>
              <p class="mt-3 text-xs text-muted-foreground">
                {{ board.notice }}
              </p>
            </NuxtCard>
          </template>
        </NuxtCollapsible>
        <CatalogBindingReview
          v-if="board.selected_snapshot"
          :key="board.selected_snapshot.id"
          :board="board"
          :busy="busy"
          :stale="stale"
          :confirm="bind"
          @dirty-change="dirty = $event"
        />
      </template>
    </div>
  </main>
</template>
