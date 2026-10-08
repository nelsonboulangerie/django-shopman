<script setup lang="ts">
import type {
  CatalogBindingReviewProjection,
  CatalogReviewItem,
} from "~/generated/ordersContract";
const props = defineProps<{
  board: CatalogBindingReviewProjection;
  busy: boolean;
  stale: boolean;
  confirm: (
    item: CatalogReviewItem,
    sku: string,
    revision: string,
  ) => Promise<boolean>;
}>();
const emit = defineEmits<{ "dirty-change": [dirty: boolean] }>();
const search = ref("");
const drafts = ref<
  Record<string, { sku: string; revision: string; reviewing: boolean }>
>({});
const filtered = computed(() => {
  const query = search.value.trim().toLocaleLowerCase();
  return props.board.items.filter(
    (item) =>
      !query ||
      [
        item.name,
        item.external_code,
        item.binding?.sku,
        item.category_ref,
      ].some((value) => value?.toLocaleLowerCase().includes(query)),
  );
});
watch(drafts, (value) => emit("dirty-change", Object.keys(value).length > 0), {
  deep: true,
});
function choose(item: CatalogReviewItem, sku: string | number) {
  drafts.value[item.item_id] = {
    sku: String(sku),
    revision: item.base_revision,
    reviewing: false,
  };
}
const changed = (item: CatalogReviewItem) =>
  !!drafts.value[item.item_id] &&
  drafts.value[item.item_id]!.revision !== item.base_revision;
const statusLabel = (status: string) =>
  (
    ({ AVAILABLE: "Disponível", UNAVAILABLE: "Indisponível" }) as Record<
      string,
      string
    >
  )[status] ||
  status ||
  "Disponibilidade não informada";
const nameFor = (sku: string) =>
  props.board.products.find((product) => product.sku === sku)?.name || sku;
async function save(item: CatalogReviewItem) {
  const draft = drafts.value[item.item_id];
  if (!draft || changed(item) || props.stale || props.busy || !draft.sku)
    return;
  if (await props.confirm(item, draft.sku, draft.revision)) {
    const next = { ...drafts.value };
    Reflect.deleteProperty(next, item.item_id);
    drafts.value = next;
  }
}
function acceptCurrent(item: CatalogReviewItem) {
  const draft = drafts.value[item.item_id];
  if (draft) {
    draft.revision = item.base_revision;
    draft.reviewing = false;
  }
}
</script>

<template>
  <section class="space-y-4" aria-label="Revisão de vínculos">
    <NuxtFormField label="Buscar anúncio, código ou SKU">
      <NuxtInput v-model="search" class="w-full" type="search" />
    </NuxtFormField>
    <p class="text-sm text-muted-foreground">
      {{ board.items.length }} anúncios ·
      {{ board.items.filter((item) => item.needs_review).length }} pendentes de
      revisão
    </p>
    <NuxtEmpty
      v-if="!filtered.length"
      icon="i-lucide-package-search"
      title="Nenhum anúncio neste recorte"
      description="Isso não comprova que a loja na plataforma esteja vazia."
    />
    <NuxtCard
      v-for="item in filtered"
      :key="item.item_id"
      as="article"
      :aria-label="item.name || item.item_id"
    >
      <template #header>
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="op-micro text-muted-foreground">
              Anúncio na captura externa
            </p>
            <h2 class="break-words op-title">
              {{ item.name || "Nome não disponível na captura" }}
            </h2>
          </div>
          <NuxtBadge
            color="neutral"
            variant="subtle"
            :label="statusLabel(item.status)"
          />
        </div>
      </template>
      <div class="grid gap-4 md:grid-cols-2">
        <div class="min-w-0 space-y-2">
          <p class="whitespace-pre-wrap break-words text-sm">
            {{ item.description || "Descrição não disponível." }}
          </p>
          <p class="text-sm">
            Categoria: {{ item.category_name || "Nome não informado" }}
          </p>
          <p class="text-sm">
            Código:
            <span class="font-mono">{{
              item.external_code || "Não informado"
            }}</span>
          </p>
          <p class="text-sm">
            Preço observado (R$): {{ item.price || "Não informado" }}
          </p>
          <p
            v-if="item.image_path"
            class="break-all text-xs text-muted-foreground"
          >
            Imagem preservada: {{ item.image_path }}
          </p>
          <p v-else class="text-xs text-muted-foreground">
            Imagem não informada na captura.
          </p>
          <NuxtCollapsible>
            <NuxtButton
              label="Identificação do anúncio"
              icon="i-lucide-info"
              color="neutral"
              variant="ghost"
            />
            <template #content>
              <dl class="space-y-1 break-all">
                <dt>Item</dt>
                <dd>{{ item.item_id }}</dd>
                <dt>Produto externo</dt>
                <dd>{{ item.product_ref }}</dd>
                <dt>Categoria externa</dt>
                <dd>{{ item.category_ref }}</dd>
                <dt>Item no contexto</dt>
                <dd>{{ item.item_context_ref || "Não informado" }}</dd>
              </dl>
            </template>
          </NuxtCollapsible>
        </div>
        <div class="min-w-0 space-y-3">
          <p class="text-xs font-medium text-muted-foreground">
            Associação no nosso cadastro
          </p>
          <p v-if="item.binding" class="text-sm">
            Vinculado a <strong>{{ item.binding.name }}</strong> ({{
              item.binding.sku
            }}).
          </p>
          <p v-else class="text-sm">Ainda sem vínculo confirmado.</p>
          <p
            v-if="item.binding && item.needs_review"
            class="text-sm text-muted-foreground"
          >
            Vínculo confirmado em outra captura. Revise esta evidência antes de
            confirmar novamente.
          </p>
          <p class="text-sm text-muted-foreground">{{ item.notice }}</p>
          <p v-if="item.candidates.length" class="text-sm">
            Sugestões por código:
            {{
              item.candidates
                .map((candidate) => `${candidate.name} (${candidate.sku})`)
                .join(", ")
            }}. Escolha explicitamente abaixo.
          </p>
          <NuxtFormField label="Produto local para vincular">
            <NuxtSelect
              class="w-full"
              :model-value="drafts[item.item_id]?.sku || undefined"
              placeholder="Selecione um produto"
              :items="
                board.products.map((product) => ({
                  label: `${product.name} (${product.sku})`,
                  value: product.sku,
                }))
              "
              :disabled="busy || stale || !item.can_bind"
              @update:model-value="choose(item, $event)"
            />
          </NuxtFormField>
          <NuxtAlert
            v-if="!item.can_bind"
            color="error"
            variant="subtle"
            icon="i-lucide-lock"
            :description="item.blocked_reason"
          />
          <NuxtAlert
            v-if="changed(item)"
            color="warning"
            variant="subtle"
            title="O vínculo mudou desde sua seleção"
            description="Confira a associação atual antes de continuar."
            :actions="[
              {
                label: 'Revisar com os dados atuais',
                color: 'warning',
                variant: 'outline',
                disabled: busy || stale,
                onClick: () => acceptCurrent(item),
              },
            ]"
          />
          <NuxtButton
            v-if="drafts[item.item_id]?.sku && !drafts[item.item_id]?.reviewing"
            label="Revisar vínculo"
            :disabled="busy || stale || changed(item) || !item.can_bind"
            @click="drafts[item.item_id]!.reviewing = true"
          />
          <NuxtAlert
            v-if="drafts[item.item_id]?.reviewing"
            color="info"
            variant="subtle"
            title="Confirmar vínculo local"
            :description="`Associar ${item.name || item.item_id} a ${nameFor(drafts[item.item_id]!.sku)} (${drafts[item.item_id]!.sku}). Confirma apenas a identidade. Não copia fotos, preços ou descrições e não envia alterações à plataforma.`"
            :actions="[
              {
                label: 'Confirmar vínculo local',
                color: 'info',
                variant: 'outline',
                disabled: busy || stale || changed(item) || !item.can_bind,
                onClick: () => save(item),
              },
            ]"
          />
        </div>
      </div>
    </NuxtCard>
  </section>
</template>
