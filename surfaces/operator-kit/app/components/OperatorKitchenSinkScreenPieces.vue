<script setup lang="ts">
// As peças de tela da fase 2 (WP-FASE2-UX-OPERADOR), com dados fixos: a vitrine de
// quem vai migrar um app. Cada peça entra aqui no mesmo PR em que nasce no kit.
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
  </section>
</template>
