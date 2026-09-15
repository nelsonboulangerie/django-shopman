<script setup lang="ts">
import type { CatalogBindingReviewProjection, CatalogReviewItem } from "~/generated/ordersContract";
const props = defineProps<{
  board: CatalogBindingReviewProjection;
  busy: boolean;
  stale: boolean;
  confirm: (item: CatalogReviewItem, sku: string, revision: string) => Promise<boolean>;
}>();
const emit = defineEmits<{ "dirty-change": [dirty: boolean] }>();
const search = ref("");
const drafts = ref<Record<string, { sku: string; revision: string; reviewing: boolean }>>({});
const filtered = computed(() => {
  const query = search.value.trim().toLocaleLowerCase();
  return props.board.items.filter((item) => !query || [item.name, item.external_code, item.binding?.sku, item.category_ref]
    .some((value) => value?.toLocaleLowerCase().includes(query)));
});
watch(drafts, (value) => emit("dirty-change", Object.keys(value).length > 0), { deep: true });
function choose(item: CatalogReviewItem, event: Event) {
  drafts.value[item.item_id] = { sku: (event.target as HTMLSelectElement).value, revision: item.base_revision, reviewing: false };
}
const changed = (item: CatalogReviewItem) => !!drafts.value[item.item_id] && drafts.value[item.item_id]!.revision !== item.base_revision;
const statusLabel = (status: string) => ({ AVAILABLE: "Disponível", UNAVAILABLE: "Indisponível" } as Record<string, string>)[status] || status || "Disponibilidade não informada";
const nameFor = (sku: string) => props.board.products.find((product) => product.sku === sku)?.name || sku;
async function save(item: CatalogReviewItem) {
  const draft = drafts.value[item.item_id];
  if (!draft || changed(item) || props.stale || props.busy || !draft.sku) return;
  if (await props.confirm(item, draft.sku, draft.revision)) {
    const next = { ...drafts.value }; Reflect.deleteProperty(next, item.item_id); drafts.value = next;
  }
}
function acceptCurrent(item: CatalogReviewItem) {
  const draft = drafts.value[item.item_id];
  if (draft) { draft.revision = item.base_revision; draft.reviewing = false; }
}
</script>

<template>
  <section class="space-y-4" aria-label="Revisão de vínculos">
    <label class="block max-w-lg text-sm">
      <span class="mb-1 block font-medium">Buscar anúncio, código ou SKU</span>
      <input v-model="search" type="search" class="min-h-11 w-full rounded-md border bg-background px-3" />
    </label>
    <p class="text-sm text-muted-foreground">{{ board.items.length }} anúncios · {{ board.items.filter(item => item.needs_review).length }} pendentes de revisão</p>
    <p v-if="!filtered.length" class="rounded-lg border p-4 text-sm">Nenhum anúncio neste recorte. Isso não comprova que a loja na plataforma esteja vazia.</p>
    <article v-for="item in filtered" :key="item.item_id" class="space-y-3 rounded-xl border bg-card p-4" :aria-label="item.name || item.item_id">
      <div class="grid gap-4 md:grid-cols-2">
        <div class="min-w-0 space-y-2">
          <p class="text-xs font-medium text-muted-foreground">Anúncio na captura externa</p>
          <h2 class="break-words font-semibold">{{ item.name || "Nome não disponível na captura" }}</h2>
          <p class="whitespace-pre-wrap break-words text-sm">{{ item.description || "Descrição não disponível." }}</p>
          <p class="text-sm">Categoria: {{ item.category_name || "Nome não informado" }}</p>
          <p class="text-sm">Código: <span class="font-mono">{{ item.external_code || "Não informado" }}</span></p>
          <p class="text-sm">Preço observado (R$): {{ item.price || "Não informado" }} · {{ statusLabel(item.status) }}</p>
          <p v-if="item.image_path" class="break-all text-xs text-muted-foreground">Imagem preservada: {{ item.image_path }}</p>
          <p v-else class="text-xs text-muted-foreground">Imagem não informada na captura.</p>
          <details class="text-xs text-muted-foreground">
            <summary class="min-h-11 cursor-pointer py-3">Identificação do anúncio</summary>
            <dl class="space-y-1 break-all"><dt>Item</dt><dd>{{ item.item_id }}</dd><dt>Produto externo</dt><dd>{{ item.product_ref }}</dd><dt>Categoria externa</dt><dd>{{ item.category_ref }}</dd><dt>Item no contexto</dt><dd>{{ item.item_context_ref || "Não informado" }}</dd></dl>
          </details>
        </div>
        <div class="min-w-0 space-y-3">
          <p class="text-xs font-medium text-muted-foreground">Associação no nosso cadastro</p>
          <p v-if="item.binding" class="text-sm">Vinculado a <strong>{{ item.binding.name }}</strong> ({{ item.binding.sku }}).</p>
          <p v-else class="text-sm">Ainda sem vínculo confirmado.</p>
          <p v-if="item.binding && item.needs_review" class="text-sm text-muted-foreground">Vínculo confirmado em outra captura. Revise esta evidência antes de confirmar novamente.</p>
          <p class="text-sm text-muted-foreground">{{ item.notice }}</p>
          <p v-if="item.candidates.length" class="text-sm">Sugestões por código: {{ item.candidates.map(candidate => `${candidate.name} (${candidate.sku})`).join(", ") }}. Escolha explicitamente abaixo.</p>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Produto local para vincular</span>
            <select :value="drafts[item.item_id]?.sku || ''" :disabled="busy || stale || !item.can_bind" class="min-h-11 w-full rounded-md border bg-background px-2" @change="choose(item, $event)">
              <option value="">Selecione um produto</option>
              <option v-for="product in board.products" :key="product.sku" :value="product.sku">{{ product.name }} ({{ product.sku }})</option>
            </select>
          </label>
          <p v-if="!item.can_bind" class="text-sm text-destructive">{{ item.blocked_reason }}</p>
          <div v-if="changed(item)" role="alert" class="rounded-md border p-3 text-sm">
            O vínculo mudou desde sua seleção. Confira a associação atual antes de continuar.
            <button class="mt-2 block min-h-11 underline" :disabled="busy || stale" @click="acceptCurrent(item)">Revisar com os dados atuais</button>
          </div>
          <button v-if="drafts[item.item_id]?.sku && !drafts[item.item_id]?.reviewing" class="min-h-11 rounded-md border px-3 text-sm font-medium" :disabled="busy || stale || changed(item) || !item.can_bind" @click="drafts[item.item_id]!.reviewing = true">Revisar vínculo</button>
          <div v-if="drafts[item.item_id]?.reviewing" class="space-y-2 rounded-lg border bg-muted/30 p-3 text-sm">
            <p>Associar <strong>{{ item.name || item.item_id }}</strong> a <strong>{{ nameFor(drafts[item.item_id]!.sku) }}</strong> ({{ drafts[item.item_id]!.sku }}).</p>
            <p>Confirma apenas a identidade. Não copia fotos, preços ou descrições e não envia alterações à plataforma.</p>
            <button class="min-h-11 rounded-md bg-primary px-3 font-medium text-primary-foreground disabled:opacity-50" :disabled="busy || stale || changed(item) || !item.can_bind" @click="save(item)">Confirmar vínculo local</button>
          </div>
        </div>
      </div>
    </article>
  </section>
</template>
