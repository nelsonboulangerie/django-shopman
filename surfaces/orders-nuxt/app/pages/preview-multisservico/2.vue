<script setup lang="ts">
// Prévia M2 (DEV-2026-030): a corrida do entregador da casa no cartão da Saída, forma E
// (decisão do dono, prévia 8 da revisão), ao lado das corridas da TaOn. Dados fictícios.
import type { SaidaItem } from "~/components/MsSaidaCard.vue";

const crew = [
  { name: "Diego", state: "Na corrida A", tone: "info" },
  { name: "Rui", state: "Na rua · corrida C", tone: "info" },
  { name: "Ana", state: "Livre", tone: "success" },
  { name: "Bruno", state: "Fora da escala", tone: "off" },
];

const toCollect: SaidaItem[] = [
  {
    key: "rA", ride: 1, icon: "i-lucide-user-round", moment: "Diego leva", momentTone: "info",
    hint: "Entregador da casa · R$ 15,00 · Abriu o link às 12h31",
    stops: [
      { code: "A47", place: "Gleba Palhano", bags: 2, note: "Troco R$ 50,00" },
      { code: "C03", place: "Gleba Palhano", bags: 1, note: "Troco R$ 20,00" },
    ],
    action: { label: "Saiu", icon: "i-lucide-navigation" },
    secondaryAction: { label: "Reenviar o link", icon: "i-lucide-send" },
  },
  {
    key: "rB", ride: 2, icon: "i-lucide-search", moment: "A TaOn procura entregador", hint: "Chamada às 12h26", pulse: true,
    stops: [{ code: "B12", place: "Centro", bags: 1 }],
  },
  {
    key: "D15", icon: "i-lucide-circle-check", moment: "Pronto há 4 min", momentTone: "success",
    stops: [{ code: "D15", place: "Bela Suíça", note: "Pago no Pix" }],
    action: { label: "Chamar entregador", icon: "i-lucide-bike" },
  },
];
const onRoad: SaidaItem[] = [
  {
    key: "rC", ride: 3, icon: "i-lucide-navigation", moment: "Rui na rua", momentTone: "info",
    hint: "Entregador da casa · 1 de 2 entregues · Próxima: E18",
    stops: [{ code: "D04", place: "Centro", done: true }, { code: "E18", place: "Jardim Higienópolis", note: "Cobrar R$ 42,00 no cartão" }],
    action: { label: "E18 entregue", icon: "i-lucide-package-check" },
    secondaryAction: { label: "Ligar para Rui", icon: "i-lucide-phone" },
  },
  {
    key: "rD", ride: 4, icon: "i-lucide-store", moment: "Ana voltou à loja", momentTone: "warning",
    hint: "Entregador da casa · Confira a maquininha verde e o troco",
    stops: [{ code: "F11", place: "Bela Suíça", done: true }],
    action: { label: "Entregador voltou", icon: "i-lucide-undo-2" },
  },
  {
    key: "rE", ride: 5, icon: "i-lucide-navigation", moment: "Léo na rua", momentTone: "info", hint: "TaOn · Chega por volta de 12h40",
    stops: [{ code: "G20", place: "Centro" }],
  },
];
const parts = [
  { label: "A coletar", items: toCollect },
  { label: "Saiu para entrega", items: onRoad },
];
const toneClass: Record<string, string> = {
  info: "bg-info/10 text-info ring-info/30",
  success: "bg-success/10 text-success ring-success/30",
  off: "bg-elevated text-dimmed ring-default line-through",
};
</script>

<template>
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default pb-32" data-preview-overlay>
        <main class="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-8 py-8">
          <header class="flex flex-col gap-1">
            <MsPreviewNav :current="2" />
            <h1 class="op-title font-semibold text-highlighted">Prévia M2 · A corrida da casa na Saída</h1>
            <p class="op-body text-toned">
              A corrida de um entregador da casa usa o mesmo cartão da forma E, com a letra e a cor. O que muda é o momento (o nome de quem
              leva, desde a chamada, porque a casa já escolheu a pessoa) e os gestos: sem API, quem avança é o entregador pelo link ou o
              operador aqui ("Saiu", "E18 entregue", "Entregador voltou"). A corrida da TaOn segue sem gesto até a coleta, como decidido.
            </p>
          </header>

          <!-- quem está hoje -->
          <section class="flex flex-col gap-2">
            <p class="op-micro font-semibold text-muted">Topo da seção Entregas · Entregadores de hoje (um toque liga e desliga a escala)</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="c in crew"
                :key="c.name"
                type="button"
                class="flex items-center gap-2 rounded-full px-3 py-1.5 op-micro ring-1"
                :class="toneClass[c.tone]"
              >
                <NuxtIcon name="i-lucide-user-round" class="size-4" />
                <span class="font-semibold">{{ c.name }}</span>
                <span>{{ c.state }}</span>
              </button>
              <NuxtButton size="sm" color="neutral" variant="ghost" icon="i-lucide-plus" label="Entregador" />
            </div>
          </section>

          <div class="flex items-start gap-8">
            <div class="flex min-w-0 flex-1 flex-col gap-2">
              <p class="op-micro font-semibold text-muted">Computador · coluna Saída</p>
              <div class="flex flex-col gap-2 rounded-xl bg-elevated/60 p-2">
                <template v-for="part in parts" :key="part.label">
                  <p class="px-1 pt-1 op-micro font-semibold text-muted">{{ part.label }}</p>
                  <div class="grid grid-cols-2 items-start gap-2">
                    <MsSaidaCard v-for="item in part.items" :key="item.key" :item="item" />
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
                    <MsSaidaCard v-for="item in part.items" :key="item.key" :item="item" />
                  </div>
                </template>
              </div>
            </div>
          </div>

          <section class="flex flex-col gap-1 rounded-xl border border-dashed border-accented p-4 op-micro text-toned">
            <p class="font-semibold text-highlighted">O que cada gesto faz</p>
            <p>"Saiu": os pedidos da corrida saem para entrega e o cliente recebe o aviso de saída (igual ao E da TaOn). O link de Diego passa a mostrar as paradas.</p>
            <p>"E18 entregue": só aquele pedido fica entregue, e o aviso vai só àquele cliente. O mesmo toque existe no link do entregador.</p>
            <p>"Entregador voltou": o mesmo conferir de troco e maquininha de hoje. Nada novo no livro do caixa.</p>
            <p>"Reenviar o link": abre o WhatsApp de novo com o link, para quando o entregador perdeu a mensagem.</p>
          </section>
        </main>
      </div>
    </Teleport>
  </div>
</template>
