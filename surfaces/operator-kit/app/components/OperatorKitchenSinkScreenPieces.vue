<script setup lang="ts">
// As peças de tela da fase 2 (WP-FASE2-UX-OPERADOR), com dados fixos: a vitrine de
// quem vai migrar um app. Cada peça entra aqui no mesmo PR em que nasce no kit.
import { computed, onMounted, ref } from "vue";

import { useRecordTrail } from "../composables/useRecordTrail";
import type { OperatorMoreMenuItems } from "../presentation/moreMenu";

const toast = useToast();
function said(label: string) {
  toast.add({ title: label, color: "success" });
}

// O ⋯ de um pedido: grupos, ícone, a destrutiva em `error` e uma ação que não pode,
// com o motivo escrito.
const orderMenu: OperatorMoreMenuItems = [
  [
    { label: "Atender este pedido", icon: "i-lucide-user-plus", onSelect: () => said("Atender este pedido") },
    { label: "Declarar volumes", icon: "i-lucide-package", onSelect: () => said("Declarar volumes") },
    {
      label: "Voltar para a Cozinha",
      icon: "i-lucide-rotate-ccw",
      disabled: true,
      reason: "A Cozinha já fechou o pedido 1048.",
    },
  ],
  [
    { type: "label", label: "Leitura" },
    { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => said("Atualizar") },
    { label: "Exportar CSV", icon: "i-lucide-download", onSelect: () => said("Exportar CSV") },
  ],
  [
    { label: "Cancelar pedido", icon: "i-lucide-x", color: "error", onSelect: () => said("Cancelar pedido") },
  ],
];

const rowMenu: OperatorMoreMenuItems = [
  { label: "Editar o produto", icon: "i-lucide-pencil", onSelect: () => said("Editar o produto") },
  { label: "Pausar em todos os canais", icon: "i-lucide-pause", onSelect: () => said("Pausar") },
];

// Anterior e próximo: a lista (aqui, quatro pedidos com o recorte "Retirada") grava a
// ordem que mostra; o "detalhe" lê a trilha. O registro aberto mora na URL (`?record=`).
const route = useRoute();
const trailOrders = [
  { ref: "1046", customer: "Bruno Lima" },
  { ref: "1048", customer: "Ana Souza" },
  { ref: "1051", customer: "Carla Dias" },
  { ref: "1053", customer: "Davi Rocha" },
];
const { remember } = useRecordTrail("kitchen-sink-orders");
onMounted(() =>
  remember(
    trailOrders.map((order) => order.ref),
    { from: route.fullPath, label: "Pedidos para retirar" },
  ),
);
const openRecord = computed(() =>
  typeof route.query.record === "string" ? route.query.record : "1048",
);
const openOrder = computed(() => trailOrders.find((order) => order.ref === openRecord.value));
function recordLocation(id: string) {
  return { path: route.path, query: { ...route.query, record: id } };
}

// A ação na base: o que ela mexe, uma ação larga e o motivo quando não pode.
const acting = ref(false);
function act() {
  acting.value = true;
  setTimeout(() => {
    acting.value = false;
    said("Pronto para retirar");
  }, 800);
}
const readyAction = computed(() => ({
  label: "Pronto para retirar",
  icon: "i-lucide-check",
  loading: acting.value,
  onSelect: act,
}));
const blockedAction = {
  label: "Iniciar preparo",
  icon: "i-lucide-lock",
  disabled: true,
  reason: "O Pix ainda não caiu. O pedido libera sozinho quando cair.",
};

// Ação com prazo: o Desfazer com o tempo dentro do botão. "Recomeçar" abre janelas
// novas de 5 s em todos os exemplos de uma vez.
const timedUntil = ref(0);
const timedDone = ref<string[]>([]);
const timedExpired = ref<string[]>([]);
function restartTimed() {
  timedDone.value = [];
  timedExpired.value = [];
  timedUntil.value = Date.now() + 5000;
}
onMounted(restartTimed);
function timedUndo(id: string) {
  timedDone.value = [...timedDone.value, id];
  said("Desfeito");
}
const timedRows = [
  { id: "outline", title: "Contornado", variant: "outline" as const, color: "neutral" as const, reduced: false },
  { id: "solid", title: "Sólido", variant: "solid" as const, color: "primary" as const, reduced: false },
  { id: "reduced", title: "Sem movimento", variant: "outline" as const, color: "neutral" as const, reduced: true },
];

const rows = [
  { sku: "PAO-FRANCES", name: "Pão francês" },
  { sku: "CROISSANT-MANTEIGA", name: "Croissant de manteiga com fermentação natural de 36 horas" },
];
</script>

<template>
  <section
    id="screen-pieces"
    class="space-y-4"
    aria-labelledby="screen-pieces-title"
    data-operator-audit-id="catalog-screen-pieces"
  >
    <div>
      <h2 id="screen-pieces-title" class="op-title">Peças de tela</h2>
      <p class="op-body text-muted">
        As atividades comuns do operador, uma peça para cada uma. Dados fixos.
      </p>
    </div>

    <NuxtCard
      title="Mais ações"
      description="OperatorMoreMenu: as ações como dados, o mesmo ⋯ no cabeçalho, no cartão e na linha, no celular e na mesa. A ação que não pode diz por quê."
      data-catalog-more-menu
    >
      <div class="grid gap-4 md:grid-cols-2">
        <NuxtCard variant="soft">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="text-base font-semibold">Pedido 1048</p>
              <p class="text-sm text-muted">Ana Souza · Retirada às 10:30</p>
            </div>
            <OperatorMoreMenu
              :items="orderMenu"
              label="Mais ações do pedido 1048"
              data-catalog-more-menu-order
            />
          </div>
        </NuxtCard>
        <NuxtCard variant="soft">
          <ul class="divide-y divide-default">
            <li
              v-for="row in rows"
              :key="row.sku"
              class="flex items-center justify-between gap-2 py-2"
            >
              <span class="min-w-0 text-sm">{{ row.name }}</span>
              <OperatorMoreMenu :items="rowMenu" :label="`Mais ações de ${row.name}`" />
            </li>
          </ul>
        </NuxtCard>
      </div>
    </NuxtCard>

    <NuxtCard
      title="Anterior e próximo"
      description="OperatorRecordNav: ‹ 3 de 18 › dentro da lista de onde a pessoa veio, com o recorte dela. Teclas J e K, ou as setas. Aberto por link, sem a lista, o par não aparece."
      data-catalog-record-nav
    >
      <div class="space-y-3">
        <NuxtCard variant="soft">
          <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
            <p class="text-base font-semibold">Pedido {{ openRecord }}</p>
            <NuxtBadge color="info" label="Retirada" />
            <OperatorRecordNav
              class="ms-auto"
              trail="kitchen-sink-orders"
              :current="openRecord"
              :to="recordLocation"
              previous-label="Pedido anterior"
              next-label="Próximo pedido"
            />
          </div>
          <p class="text-sm text-muted">{{ openOrder?.customer }} · Retirada às 10:30</p>
        </NuxtCard>
        <p class="op-micro text-muted">
          A lista de origem: {{ trailOrders.map((order) => order.ref).join(", ") }}.
        </p>
      </div>
    </NuxtCard>

    <NuxtCard
      title="Ação na base"
      description="OperatorActionBar: no celular e no tablet, a ação do momento fica na base, em fluxo, entre o conteúdo e a barra inferior. Na mesa (1024 px ou mais) ela não aparece: a ação sobe para a barra do topo."
      data-catalog-action-bar
    >
      <div class="grid gap-4 md:grid-cols-2">
        <div class="flex flex-col overflow-hidden rounded-lg border border-default">
          <p class="flex-1 p-3 text-sm text-muted">Itens e cliente do pedido 1048.</p>
          <OperatorActionBar
            :action="readyAction"
            context-label="Pedido 1048 · Ana Souza"
            context-value="R$ 48,70"
          />
        </div>
        <div class="flex flex-col overflow-hidden rounded-lg border border-default">
          <p class="flex-1 p-3 text-sm text-muted">Itens e cliente do pedido 1049.</p>
          <OperatorActionBar
            :action="blockedAction"
            :secondary="{ label: 'Recusar', onSelect: () => said('Recusar') }"
            context-label="Pedido 1049 · Pix"
            context-value="R$ 93,20"
          />
        </div>
      </div>
    </NuxtCard>

    <NuxtCard
      title="Ação com prazo"
      description="OperatorTimedButton: a ação que só vale até um prazo, com o tempo dentro do botão. O fundo esvazia até a janela fechar; ao fim, o botão some ou fica desabilitado. Com movimento reduzido no dispositivo, nada anima e o botão mostra só os segundos. O leitor de tela ouve o rótulo, e o prazo numa descrição fixa (Disponível até 10:42:15), anunciada só ao abrir e ao fechar."
      data-catalog-timed-button
    >
      <div class="space-y-3">
        <div class="flex flex-col divide-y divide-default">
          <div
            v-for="row in timedRows"
            :key="row.id"
            class="flex flex-wrap items-center gap-3 py-3"
          >
            <p class="w-32 text-sm font-medium">{{ row.title }}</p>
            <div v-for="size in ['md', 'xl'] as const" :key="size" class="min-w-36">
              <OperatorTimedButton
                v-if="timedUntil && !timedDone.includes(`${row.id}-${size}`) && !timedExpired.includes(`${row.id}-${size}`)"
                :until="timedUntil"
                :duration="5000"
                label="Desfazer"
                icon="i-lucide-undo-2"
                :size="size"
                :variant="row.variant"
                :color="row.color"
                :reduced-motion="row.reduced"
                @click="timedUndo(`${row.id}-${size}`)"
                @expire="timedExpired = [...timedExpired, `${row.id}-${size}`]"
              />
              <p v-else-if="timedDone.includes(`${row.id}-${size}`)" class="text-sm text-muted">Desfeito.</p>
              <p v-else class="text-sm text-muted">O prazo acabou.</p>
            </div>
          </div>
        </div>
        <NuxtButton
          icon="i-lucide-rotate-ccw"
          color="neutral"
          variant="outline"
          label="Recomeçar"
          @click="restartTimed"
        />
      </div>
    </NuxtCard>

    <NuxtCard
      title="Estado da tela"
      description="OperatorScreenState: carregando, vazio, erro e sem conexão, uma frase por estado. O erro traz Tentar de novo na cor do aviso. O aviso que vale para a tela inteira mora no cabeçalho (alerts do OperatorPageHeader): um inteiro, o resto em e mais N."
      data-catalog-screen-state
    >
      <div class="grid gap-4 md:grid-cols-2">
        <NuxtCard variant="soft">
          <OperatorScreenState state="loading" what="a fila" in-card />
        </NuxtCard>
        <NuxtCard variant="soft">
          <OperatorScreenState
            state="empty"
            icon="i-lucide-inbox"
            title="Nenhum pedido precisa de você agora."
            in-card
          />
        </NuxtCard>
        <OperatorScreenState state="error" what="a fila" @retry="said('Tentar de novo')" />
        <OperatorScreenState state="offline" since="10:42" />
      </div>
    </NuxtCard>
  </section>
</template>
