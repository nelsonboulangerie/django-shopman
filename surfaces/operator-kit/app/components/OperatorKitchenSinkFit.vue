<script setup lang="ts">
// O "Rótulo que cabe" no catálogo vivo (dono, 10/10/2026): a mesma barra de ações em
// contêineres de larguras diferentes, cada uma num degrau (completo, curto, só ícone),
// e o nome que não é ação em cartão de tamanho fixo, com uma, duas e três linhas e a
// MESMA altura. A matriz visual do kit (`tests/catalog/operator-kit-catalog.spec.ts`)
// passa o scanner de geometria aqui em todos os viewports e confere os degraus.
const send = { label: "Enviar à cozinha", shortLabel: "Cozinha", icon: "i-lucide-chef-hat" };
const save = { label: "Salvar comanda", shortLabel: "Salvar", icon: "i-lucide-save" };
const actions = [send, save];

// Larguras do contêiner (rem): os três degraus e a ação sem ícone que quebra linha.
const widths = [
  { rem: 24, expect: "full" },
  { rem: 16, expect: "short" },
  { rem: 6, expect: "icon" },
];

const names = [
  "Baguete",
  "Pão de fermentação natural com nozes",
  "Croissant de manteiga francesa recheado com amêndoas tostadas e açúcar de confeiteiro",
];
</script>

<template>
  <section id="fit" class="space-y-4" data-operator-audit-id="catalog-fit">
    <div>
      <p class="op-eyebrow">Rótulo que cabe</p>
      <h2 class="op-title">A ação encolhe por degraus; o nome reserva duas linhas</h2>
    </div>
    <div class="space-y-3">
      <div
        v-for="width in widths"
        :key="width.rem"
        class="max-w-full rounded-md border border-dashed border-default p-2"
        :style="{ width: `${width.rem}rem` }"
        :data-fit-demo="width.expect"
      >
        <OperatorFitGroup :actions="actions" class="flex items-center gap-2">
          <OperatorButton v-bind="send" />
          <OperatorButton v-bind="save" color="neutral" variant="outline" />
        </OperatorFitGroup>
      </div>
      <div
        class="max-w-full rounded-md border border-dashed border-default p-2"
        :style="{ width: '7rem' }"
        data-fit-demo="wrap"
      >
        <div class="op-fit-scope">
          <OperatorButton label="Registrar sangria" color="neutral" variant="outline" />
        </div>
      </div>
    </div>
    <div class="grid max-w-xl grid-cols-3 gap-3" data-fixed-demo>
      <NuxtCard v-for="name in names" :key="name" data-fixed-demo-card>
        <p class="op-fixed-lines op-label" :title="name" data-operator-fixed-text>{{ name }}</p>
        <p class="op-micro text-muted">R$ 12,00</p>
      </NuxtCard>
    </div>
  </section>
</template>
