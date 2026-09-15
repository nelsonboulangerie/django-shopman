<script setup lang="ts">
definePageMeta({ key: route => route.path });
const route = useRoute();
const channel = String(route.params.ref);
const { board, pending, error, stale, refresh, readMetadata, realtime, selected, busy, message, importSnapshot, bind } = useCatalogBindings(channel);
const fileName = ref("");
const rawJson = ref("");
const fileError = ref("");
const reading = ref(false);
const dirty = ref(false);
let disposed = false;
function protectDraft(event: BeforeUnloadEvent) {
  if (!dirty.value && !rawJson.value) return;
  event.preventDefault(); event.returnValue = "";
}
onMounted(() => window.addEventListener("beforeunload", protectDraft));
onBeforeUnmount(() => { disposed = true; window.removeEventListener("beforeunload", protectDraft); });
async function readFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file || reading.value) return;
  fileError.value = "";
  rawJson.value = "";
  fileName.value = file.name;
  if (file.size > 20 * 1024 * 1024) { fileError.value = "O arquivo excede o limite de 20 MiB."; return; }
  reading.value = true;
  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
    if (!disposed) rawJson.value = text;
  } catch { if (!disposed) fileError.value = "Não foi possível ler o arquivo como UTF-8."; }
  finally { if (!disposed) reading.value = false; }
}
async function storeSnapshot() {
  if (!rawJson.value || busy.value || error.value) return;
  if (dirty.value && !window.confirm("Guardar outra captura descarta a seleção de vínculo atual. Continuar?")) return;
  if (await importSnapshot(rawJson.value)) { rawJson.value = ""; fileName.value = ""; dirty.value = false; }
}
function selectSnapshot(event: Event) {
  const element = event.target as HTMLSelectElement;
  if (dirty.value && !window.confirm("Há uma seleção de vínculo não confirmada. Trocar de inventário e descartar a seleção?")) {
    element.value = String(board.value?.selected_snapshot?.id ?? ""); return;
  }
  dirty.value = false;
  selected.value = element.value;
}
onBeforeRouteLeave(() => !(dirty.value || rawJson.value) || window.confirm("Há uma revisão local não concluída. Sair e descartar a seleção?"));
useHead({ title: "Revisão de vínculos · Gestor" });
</script>

<template>
  <main class="min-w-0 flex-1 space-y-4 p-4">
    <div class="flex flex-wrap items-center gap-3">
      <NuxtLink to="/feeds" class="inline-flex min-h-11 items-center gap-1 rounded-md border px-3 text-sm"><Icon name="lucide:arrow-left" />Canais</NuxtLink>
      <h1 class="text-lg font-semibold">{{ board?.channel_name || channel }} · Revisão de vínculos</h1>
      <UiIconButton icon="lucide:refresh-cw" label="Atualizar revisão" :spinning="pending" @click="refresh()" />
    </div>
    <ReadFreshness :metadata="readMetadata" :failed="Boolean(error)" :realtime="realtime" />
    <p class="max-w-4xl text-sm text-muted-foreground">Confira a identidade dos anúncios antes de associá-los ao cadastro. Os dados locais ainda precisam de revisão. Este fluxo não envia alterações à plataforma.</p>
    <p v-if="message" role="status" class="rounded-lg border p-3 text-sm">{{ message }}</p>
    <div v-if="error" role="alert" class="rounded-lg border border-destructive p-3 text-sm">
      Não foi possível atualizar a revisão. {{ board ? "Exibindo a última leitura disponível; a gravação está bloqueada." : "Tente novamente para consultar os inventários." }}
      <button class="ml-2 min-h-11 underline" @click="refresh()">Tentar novamente</button>
    </div>
    <p v-if="pending && !board" class="text-sm text-muted-foreground">Carregando inventários…</p>
    <template v-if="board">
      <details class="rounded-xl border bg-card p-4">
        <summary class="min-h-11 cursor-pointer py-2 text-sm font-medium">Carregar inventário para revisão</summary>
        <div class="max-w-2xl space-y-3 pt-2">
          <p class="text-sm text-muted-foreground">Selecione a captura completa gerada pelo coletor iFood. O arquivo será guardado no sistema; nenhum produto será alterado ou vinculado automaticamente.</p>
          <label class="block text-sm"><span class="mb-1 block">Arquivo JSON da captura</span><input type="file" accept=".json,application/json" :disabled="busy || reading || Boolean(error)" class="min-h-11 max-w-full" @change="readFile" /></label>
          <p v-if="fileName" class="break-all text-sm">{{ fileName }}</p>
          <p v-if="fileError" role="alert" class="text-sm text-destructive">{{ fileError }}</p>
          <button class="min-h-11 rounded-md border px-3 text-sm font-medium disabled:opacity-50" :disabled="!rawJson || busy || reading || Boolean(error) || !board.import_action?.enabled" @click="storeSnapshot">Guardar inventário para revisão</button>
        </div>
      </details>
      <p v-if="!board.snapshots.length && !error" class="rounded-lg border border-dashed p-5 text-sm">Nenhum inventário guardado para este canal. Carregue uma captura para começar a revisão.</p>
      <label v-if="board.snapshots.length" class="block max-w-xl text-sm">
        <span class="mb-1 block font-medium">Inventário em revisão</span>
        <select :value="board.selected_snapshot?.id || ''" :disabled="busy || Boolean(error)" class="min-h-11 w-full rounded-md border bg-background px-2" @change="selectSnapshot">
          <option v-for="snapshot in board.snapshots" :key="snapshot.id" :value="snapshot.id">{{ snapshot.captured_at }} · {{ snapshot.context }} · {{ snapshot.item_count }} anúncios</option>
        </select>
      </label>
      <details v-if="board.selected_snapshot" class="rounded-lg border p-3 text-sm">
        <summary class="min-h-11 cursor-pointer py-2">Origem e identificação da captura</summary>
        <dl class="space-y-1 break-all text-xs text-muted-foreground">
          <dt>Loja externa declarada</dt><dd>{{ board.selected_snapshot.account_ref }}</dd>
          <dt>Catálogo e contexto</dt><dd>{{ board.selected_snapshot.catalog_ref }} · {{ board.selected_snapshot.context }}</dd>
          <dt>SHA-256 do arquivo</dt><dd>{{ board.selected_snapshot.sha256 }}</dd>
        </dl>
        <p class="mt-3 text-xs text-muted-foreground">{{ board.notice }}</p>
      </details>
      <CatalogBindingReview v-if="board.selected_snapshot" :key="board.selected_snapshot.id" :board="board" :busy="busy" :stale="stale" :confirm="bind" @dirty-change="dirty = $event" />
    </template>
  </main>
</template>
