<script setup lang="ts">
// O insumo aberto na Base: o que pede atenção, os selos do SKU, "Permitir revenda",
// "Quando aberto, vira" e as receitas que o consomem. Mora ao lado da tabela na mesa
// (divide a tela) e numa folha de lado abaixo do `xl`; o mesmo conteúdo nos dois.
import type { EnrichedMaterial } from "~/types/purchase";
import { formatMoney, openingView, resaleCopy, resaleSuggestionView, skuRoleBadges } from "~/presentation/purchase";
import { TONE_BADGE } from "~/presentation/purchaseUi";

const props = defineProps<{ material: EnrichedMaterial }>();

const { materials, readonlyFallback, actionPending, setSale, setOpening } = usePurchaseDesk();

// "Permitir revenda": o campo de preço só existe depois do gesto, e volta fechado
// quando outro item é aberto.
const saleOpen = ref(false);
const salePriceInput = ref("");
watch(
  () => props.material.sku,
  () => {
    saleOpen.value = false;
    salePriceInput.value = "";
  },
);

// O quadrado mostra o que vale (ou o formulário aberto): desligar uma revenda ativa é
// gesto na hora; ligar abre o campo de preço.
async function onResaleToggle(wanted: boolean | "indeterminate") {
  const material = props.material;
  if (wanted === true) {
    saleOpen.value = true;
    salePriceInput.value = resaleSuggestionView(material.saleSuggestion, material.unit)?.input ?? "";
    return;
  }
  if (saleOpen.value && !material.roles?.sellable) {
    saleOpen.value = false;
    salePriceInput.value = "";
    return;
  }
  await setSale(material.sku, false);
}

async function confirmSale() {
  if (await setSale(props.material.sku, true, salePriceInput.value)) {
    saleOpen.value = false;
    salePriceInput.value = "";
  }
}

// "Quando aberto, vira": rascunho local, reidratado a cada item.
const CREATE_OPENED = "__create__";
const openingDraft = reactive({ open: false, target: "", quantity: "", shelfLifeDays: "" });
watch(
  () => props.material.sku,
  () => {
    const material = props.material;
    openingDraft.open = false;
    openingDraft.target = material.opensInto?.sku ?? CREATE_OPENED;
    openingDraft.quantity =
      material.opensInto?.quantity.replace(".", ",") ?? openingView(material, materials.value).suggestedQuantity;
    openingDraft.shelfLifeDays = material.opensInto?.shelfLifeDays?.toString() ?? "";
  },
  { immediate: true },
);
const opening = computed(() => openingView(props.material, materials.value));
const openingTargets = computed(() => [
  { label: "Criar a partir desta embalagem (em kg)", value: CREATE_OPENED },
  ...opening.value.options.map((option) => ({ label: option.label, value: option.value })),
]);

async function saveOpening() {
  const creating = openingDraft.target === CREATE_OPENED;
  const ok = await setOpening(props.material.sku, {
    enabled: true,
    createOpened: creating,
    openedSku: creating ? "" : openingDraft.target,
    openedUnit: "kg",
    quantity: openingDraft.quantity,
    shelfLifeDays: openingDraft.shelfLifeDays,
  });
  if (ok) openingDraft.open = false;
}

async function stopOpening() {
  if (await setOpening(props.material.sku, { enabled: false })) openingDraft.open = false;
}

const resale = computed(() => resaleCopy(props.material.unit, salePriceInput.value));
const suggestion = computed(() => resaleSuggestionView(props.material.saleSuggestion, props.material.unit));
</script>

<template>
  <div class="space-y-4" data-material-panel>
    <div>
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <p class="text-xs text-muted">Insumo</p>
          <h2 class="text-base font-semibold">{{ material.name }}</h2>
          <p class="text-xs text-muted"><span class="font-mono">{{ material.sku }}</span> · {{ material.category }}</p>
        </div>
        <slot name="actions" />
      </div>
      <slot name="nav" />
    </div>

    <ul v-if="material.issues.length" class="space-y-2">
      <li v-for="issue in material.issues" :key="issue.key">
        <NuxtBadge :color="TONE_BADGE[issue.tone]" icon="i-lucide-triangle-alert" :label="issue.label" class="whitespace-normal" />
      </li>
    </ul>
    <NuxtBadge v-else color="success" icon="i-lucide-circle-check" label="Sem pontos de atenção" />

    <div class="flex flex-wrap gap-1.5">
      <NuxtBadge v-for="badge in skuRoleBadges(material.roles)" :key="badge" color="neutral" :label="badge" />
    </div>

    <!-- Permitir revenda: um gesto, que pede só o preço. O cadastro de venda nasce com o
         MESMO SKU (mesmo estoque) e entra no PDV; loja online só com foto. Desligar tira
         da venda sem apagar nada. -->
    <section class="border-t border-default pt-4" data-testid="sale-toggle">
      <p v-if="material.roles?.produced && !material.roles?.sellable" class="text-xs text-muted">
        É produzido aqui: a venda dele é do Catálogo, não do Compras.
      </p>
      <template v-else>
        <NuxtCheckbox
          :model-value="Boolean(material.roles?.sellable) || saleOpen"
          :disabled="readonlyFallback || actionPending"
          label="Permitir revenda"
          :description="
            material.roles?.sellable
              ? `${material.unit === 'kg' ? 'Vendido só no balcão, por peso' : 'À venda no PDV'}: ${formatMoney(material.salePriceQ ?? 0)} / ${material.unit}.`
              : saleOpen
                ? ''
                : 'Pede só o preço. Entra no PDV com o mesmo SKU e o mesmo estoque.'
          "
          @update:model-value="onResaleToggle"
        />
        <form v-if="!material.roles?.sellable && saleOpen" class="mt-3 space-y-2" @submit.prevent="confirmSale()">
          <NuxtFormField :label="resale.priceLabel" :hint="resale.reach">
            <div class="flex gap-2">
              <NuxtInput v-model="salePriceInput" inputmode="decimal" required placeholder="0,00" class="min-w-0 flex-1" />
              <NuxtButton
                type="submit"
                label="Colocar à venda"
                :loading="actionPending"
                :disabled="readonlyFallback || !resale.ready"
              />
            </div>
          </NuxtFormField>
          <p class="text-xs text-muted">
            {{ suggestion ? `Sugerido: ${suggestion.basis}` : "Sem custo de compra registrado: informe o preço." }}
          </p>
        </form>
      </template>
    </section>

    <!-- Quando aberto, vira: a embalagem por unidade que a produção usa em gramas. A
         produção abre sozinha no fechamento da fornada; aqui só se diz o que vem dentro. -->
    <section v-if="opening.canOpen" class="border-t border-default pt-4" data-testid="opening">
      <div class="flex items-center justify-between gap-2">
        <h3 class="text-sm font-semibold">Quando aberto, vira</h3>
        <NuxtButton
          v-if="!openingDraft.open"
          :label="material.opensInto ? 'Alterar' : 'Definir'"
          color="neutral"
          variant="ghost"
          :disabled="readonlyFallback || actionPending"
          @click="openingDraft.open = true"
        />
      </div>
      <p v-if="material.opensInto && !openingDraft.open" class="mt-1 text-sm">{{ opening.summary }}</p>
      <p v-else-if="!openingDraft.open" class="mt-1 text-xs text-muted">
        Só se a produção usa este item em peso. Ela abre uma embalagem quando precisa.
      </p>
      <form v-if="openingDraft.open" class="mt-2 space-y-3" @submit.prevent="saveOpening()">
        <NuxtFormField label="Insumo aberto">
          <NuxtSelect v-model="openingDraft.target" :items="openingTargets" value-key="value" class="w-full" />
        </NuxtFormField>
        <div class="grid grid-cols-2 gap-2">
          <NuxtFormField label="Quanto vem em uma embalagem">
            <NuxtInput v-model="openingDraft.quantity" inputmode="decimal" required placeholder="0,200" class="w-full" />
          </NuxtFormField>
          <NuxtFormField label="Validade depois de aberto (dias)">
            <NuxtInput v-model="openingDraft.shelfLifeDays" inputmode="numeric" placeholder="Sem prazo" class="w-full" />
          </NuxtFormField>
        </div>
        <div class="flex flex-wrap gap-2">
          <NuxtButton
            type="submit"
            label="Salvar"
            :loading="actionPending"
            :disabled="readonlyFallback || !openingDraft.quantity.trim()"
          />
          <NuxtButton label="Cancelar" color="neutral" variant="outline" @click="openingDraft.open = false" />
          <NuxtButton
            v-if="material.opensInto"
            label="Não abre mais"
            color="neutral"
            variant="ghost"
            :disabled="readonlyFallback || actionPending"
            @click="stopOpening()"
          />
        </div>
      </form>
    </section>

    <section class="border-t border-default pt-4">
      <h3 class="text-sm font-semibold">
        Receitas que consomem <span class="font-normal text-muted tabular-nums">{{ material.recipes.length }}</span>
      </h3>
      <div v-if="material.recipes.length" class="mt-2 flex flex-wrap gap-1.5">
        <NuxtBadge v-for="recipe in material.recipes" :key="recipe" color="neutral" :label="recipe" />
      </div>
      <p v-else class="mt-1 text-xs text-muted">Nenhuma receita usa este insumo.</p>
    </section>
  </div>
</template>
