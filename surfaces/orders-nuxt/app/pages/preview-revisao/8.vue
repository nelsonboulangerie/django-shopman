<script setup lang="ts">
// Prévia 8 da revisão das Entregas: o cartão da Saída, forma E (dono, 16/11).
// Dados fictícios, sem backend.
import type { SaidaItem } from "~/components/PreviewSaidaCard.vue";

const toCollect: SaidaItem[] = [
  {
    key: "rA", ride: 1, icon: "i-lucide-bike", moment: "Diego vem buscar", momentTone: "info", hint: "Chega uns 14:32 · Moto prata · ABC1D23",
    stops: [{ code: "A51", place: "Gleba Palhano", bags: 2 }, { code: "C07", place: "Bela Suíça", bags: 1 }],
  },
  {
    key: "rC", ride: 3, icon: "i-lucide-search", moment: "A TaOn procura entregador", hint: "Chamada às 14:26", pulse: true,
    stops: [{ code: "A47", place: "Gleba Palhano", bags: 2 }],
  },
  {
    key: "rD", ride: 4, icon: "i-lucide-store", moment: "Léo espera na loja há 3 min", momentTone: "warning", hint: "Confira a placa: DEF4G56",
    stops: [
      { code: "B12", place: "Centro", bags: 1 },
      { code: "D14", place: "Centro", bags: 2, note: "Troco R$ 30,00" },
      { code: "E02", place: "Jardim Higienópolis", bags: 1 },
      { code: "F20", place: "Jardim Higienópolis", bags: 1 },
    ],
    action: { label: "Entreguei as 5 sacolas", icon: "i-lucide-package-check" },
  },
  {
    key: "C03", icon: "i-lucide-circle-check", moment: "Pronto há 4 min", momentTone: "success",
    stops: [{ code: "C03", place: "Bela Suíça", note: "Pago no Pix" }],
    action: { label: "Chamar entregador", icon: "i-lucide-bike" },
  },
  {
    key: "B08", icon: "i-lucide-circle-check", moment: "Pronto há 3 min", momentTone: "success",
    stops: [{ code: "B08", place: "Retira na loja", note: "Carla" }],
    action: { label: "Entregue ao cliente", icon: "i-lucide-hand-helping" },
  },
];
const onRoad: SaidaItem[] = [
  {
    key: "rB", ride: 2, icon: "i-lucide-navigation", moment: "Léo na rua", momentTone: "info", hint: "1 de 3 entregues · Próxima: A44",
    stops: [{ code: "D04", place: "Centro", done: true }, { code: "A44", place: "Gleba Palhano" }, { code: "E18", place: "Jardim Higienópolis" }],
  },
  {
    key: "rE", ride: 5, icon: "i-lucide-navigation", moment: "Rui na rua", momentTone: "info", hint: "Chega uns 14:40",
    stops: [{ code: "F11", place: "Bela Suíça" }],
  },
  {
    key: "H58", icon: "i-lucide-navigation", moment: "Saiu há 9 min", hint: "Entregador do iFood",
    stops: [{ code: "H58", place: "Centro" }],
  },
];
const parts = [
  { label: "A coletar", items: toCollect },
  { label: "Saiu para entrega", items: onRoad },
];
</script>

<template>
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default pb-32" data-preview-overlay>
        <main class="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-8 py-8">
          <header class="flex flex-col gap-1">
            <PreviewNav :current="8" />
            <h1 class="op-title font-semibold text-highlighted">Prévia 8 · O cartão da Saída (forma E)</h1>
            <p class="op-body text-toned">
              Pedido solto, corrida de um pedido e corrida de vários usam a mesma estrutura: identidade, momento, destino e gesto. A corrida
              ganha o trilho da cor e a letra no canto superior direito, com a quantidade de pedidos à esquerda. A de vários pedidos ganha o
              empilhamento por trás e separa os códigos com ∙. Os códigos só recolhem em "+N" quando falta espaço: compare a corrida D no
              computador (cabem todos) e no celular (recolhe).
            </p>
          </header>

          <div class="flex items-start gap-8">
            <div class="flex min-w-0 flex-1 flex-col gap-2">
              <p class="op-micro font-semibold text-muted">Computador · coluna Saída</p>
              <div class="flex flex-col gap-2 rounded-xl bg-elevated/60 p-2">
                <template v-for="part in parts" :key="part.label">
                  <p class="px-1 pt-1 op-micro font-semibold text-muted">{{ part.label }}</p>
                  <div class="grid grid-cols-2 items-start gap-2">
                    <PreviewSaidaCard v-for="item in part.items" :key="item.key" :item="item" />
                  </div>
                </template>
              </div>
            </div>

            <div class="flex w-[375px] shrink-0 flex-col gap-2">
              <p class="op-micro font-semibold text-muted">Celular · 375 px</p>
              <div class="flex flex-col gap-2 rounded-[2rem] border-8 border-black/80 bg-elevated/60 p-2">
                <template v-for="part in parts" :key="part.label">
                  <p class="px-1 pt-1 op-micro font-semibold text-muted">{{ part.label }}</p>
                  <div class="flex flex-col gap-2">
                    <PreviewSaidaCard v-for="item in part.items" :key="item.key" :item="item" />
                  </div>
                </template>
              </div>
            </div>
          </div>

          <div class="flex flex-col gap-2">
            <p class="op-micro font-semibold text-muted">Recolhendo de verdade: a mesma corrida D em larguras menores</p>
            <div class="flex items-start gap-4">
              <div v-for="w in [320, 260, 220]" :key="w" class="flex flex-col gap-1" :style="{ width: `${w}px` }">
                <span class="op-micro text-muted">{{ w }} px</span>
                <PreviewSaidaCard :item="toCollect[2]!" />
              </div>
            </div>
          </div>
        </main>
      </div>
    </Teleport>
  </div>
</template>
