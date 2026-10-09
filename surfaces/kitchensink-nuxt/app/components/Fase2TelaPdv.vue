<script setup lang="ts">
// Tela composta 4: o Balcão do PDV, a carta branca (WP §7) sobre as mesmas regras.
// O que o PDV muda, e por quê:
//   - a toolbar vira a BARRA DA VENDA (cliente, recebimento, quando, desconto, F6 a F8)
//     enquanto a comanda está aberta: o recorte de uma venda é a própria venda;
//   - a busca é um CAMPO de produto sempre visível (tecla "/"), não a lupa: no balcão a
//     busca é o gesto principal, não um desvio; a busca da suíte fica no ⋯;
//   - na mesa a comanda é uma coluna fixa à direita, com "Receber" grande e F2; no
//     celular ela vira a ação flutuante (total + Receber) e abre como folha de baixo.
import { computed, ref } from "vue";

import { PRODUCTS, brl } from "../data/fase2";

const props = defineProps<{ estado: string }>();

const sections = [
  { key: "counter", label: "Balcão", icon: "i-lucide-store" },
  { key: "preorders", label: "Encomendas", icon: "i-lucide-calendar-clock", badge: "2" },
  { key: "tabs", label: "Comandas", icon: "i-lucide-receipt" },
  { key: "closing", label: "Fim do dia", icon: "i-lucide-moon" },
  { key: "settings", label: "Ajustes", icon: "i-lucide-settings", foot: true },
];

const lines = ref(
  props.estado === "vazio"
    ? []
    : [
        { sku: "CROI", name: "Croissant", qty: 2, price_q: 1150 },
        { sku: "PAC", name: "Pain au chocolat", qty: 1, price_q: 1290 },
        { sku: "CAFE", name: "Café coado", qty: 2, price_q: 690 },
      ],
);
const count = computed(() => lines.value.reduce((sum, line) => sum + line.qty, 0));
const total = computed(() => lines.value.reduce((sum, line) => sum + line.qty * line.price_q, 0));
function add(sku: string) {
  const product = PRODUCTS.find((item) => item.sku === sku)!;
  const line = lines.value.find((item) => item.sku === sku);
  if (line) line.qty += 1;
  else lines.value.push({ sku, name: product.name, qty: 1, price_q: product.price_q });
}

const query = ref("");
const products = computed(() =>
  PRODUCTS.filter((item) => item.name.toLowerCase().includes(query.value.trim().toLowerCase())),
);
const sheetOpen = ref(props.estado === "comanda");

const actions = [
  [{ label: "Buscar na suíte", icon: "i-lucide-search", kbds: ["meta", "K"] }],
  [
    { label: "Abrir a gaveta", icon: "i-lucide-archive" },
    { label: "Reimprimir o último recibo", icon: "i-lucide-printer" },
  ],
];
</script>

<template>
  <Fase2Screen storage-key="fase2-pdv" :sections="sections" label="Seções do PDV" current="counter">
    <template #header>
      <Fase2Header title="Balcão" :live="{ label: 'Caixa 1 aberto · 07:02', color: 'success' }" :actions="actions" :inbox="1" />
    </template>

    <template #toolbar>
      <!-- A barra da venda (carta branca): o lugar da toolbar, enquanto houver comanda. -->
      <div class="flex min-h-12 items-center gap-2 overflow-x-auto px-2 py-1.5 sm:px-3" data-fase2-sale-bar>
        <NuxtButton label="Ana Souza" icon="i-lucide-user" color="neutral" variant="outline" class="shrink-0" />
        <NuxtButton label="Retirada" icon="i-lucide-shopping-bag" color="neutral" variant="outline" class="shrink-0">
          <template #trailing><NuxtKbd value="F6" class="max-sm:hidden" /></template>
        </NuxtButton>
        <NuxtButton label="Agora" icon="i-lucide-clock" color="neutral" variant="outline" class="shrink-0">
          <template #trailing><NuxtKbd value="F7" class="max-sm:hidden" /></template>
        </NuxtButton>
        <NuxtButton label="Desconto" icon="i-lucide-percent" color="neutral" variant="ghost" class="shrink-0">
          <template #trailing><NuxtKbd value="F8" class="max-sm:hidden" /></template>
        </NuxtButton>
      </div>
      <div class="border-t border-default px-2 py-1.5 sm:px-3">
        <NuxtInput
          v-model="query"
          icon="i-lucide-search"
          placeholder="Produto ou código"
          aria-label="Buscar produto"
          class="w-full lg:w-96"
          data-fase2-product-search
        >
          <template #trailing><NuxtKbd value="/" /></template>
        </NuxtInput>
      </div>
    </template>

    <div class="flex min-h-full gap-3 p-2 sm:p-3">
      <ul class="grid min-w-0 flex-1 auto-rows-min grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4" aria-label="Produtos">
        <li v-for="product in products" :key="product.sku">
          <NuxtButton
            color="neutral"
            variant="outline"
            size="xl"
            block
            class="h-full flex-col items-start text-start"
            :disabled="product.stock === 'Indisponível'"
            :aria-label="`Pôr ${product.name} na comanda`"
            @click="add(product.sku)"
          >
            <span class="text-pretty text-highlighted">{{ product.name }}</span>
            <span class="flex w-full justify-between gap-2 text-sm font-normal text-muted">
              <span class="tabular-nums">{{ brl(product.price_q) }}</span>
              <span v-if="product.stock">{{ product.stock }}</span>
            </span>
          </NuxtButton>
        </li>
      </ul>

      <!-- Mesa: a comanda fixa à direita. A ação mora nela, não na barra do topo. -->
      <aside class="sticky top-0 hidden w-88 shrink-0 self-start lg:block" aria-label="Comanda" data-fase2-tab>
        <NuxtCard :ui="{ body: 'p-3 sm:p-3 space-y-3' }">
          <div class="flex items-baseline justify-between">
            <h2 class="font-semibold text-highlighted">Comanda</h2>
            <span class="text-sm tabular-nums text-muted">{{ count }} itens</span>
          </div>
          <ul class="divide-y divide-default text-sm">
            <li v-for="line in lines" :key="line.sku" class="flex justify-between gap-2 py-1.5">
              <span>{{ line.qty }} {{ line.name }}</span>
              <span class="tabular-nums">{{ brl(line.qty * line.price_q) }}</span>
            </li>
          </ul>
          <p class="flex justify-between text-base font-semibold">
            <span>Total</span><span class="tabular-nums">{{ brl(total) }}</span>
          </p>
          <NuxtButton :label="`Receber ${brl(total)}`" size="xl" block :disabled="!count">
            <template #trailing><NuxtKbd value="F2" /></template>
          </NuxtButton>
        </NuxtCard>
      </aside>
    </div>

    <template v-if="count" #base>
      <Fase2ActionBar
        :context-label="`Comanda · ${count} itens`"
        :context-value="brl(total)"
        action="Receber"
        icon="i-lucide-banknote"
        secondary="Ver comanda"
        @secondary="sheetOpen = true"
      />
    </template>
  </Fase2Screen>

  <NuxtDrawer v-model:open="sheetOpen" title="Comanda" :description="`${count} itens · ${brl(total)}`">
    <template #body>
      <ul class="divide-y divide-default text-sm" data-fase2-tab-sheet>
        <li v-for="line in lines" :key="line.sku" class="flex justify-between gap-2 py-2">
          <span>{{ line.qty }} {{ line.name }}</span>
          <span class="tabular-nums">{{ brl(line.qty * line.price_q) }}</span>
        </li>
      </ul>
    </template>
    <template #footer>
      <NuxtButton :label="`Receber ${brl(total)}`" size="xl" block @click="sheetOpen = false" />
    </template>
  </NuxtDrawer>
</template>
