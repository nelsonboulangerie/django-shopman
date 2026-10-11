<script setup lang="ts">
// Catálogo: o conjunto mínimo da suíte (dono, 08/10/2026; WP-BI-CANON-LAUDO, seção F,
// e a proposta aprovada do PR #1539). Tudo aqui é o tema do kit em ação: onde a peça
// não recebe cor nem variante, é o padrão do `app.config.ts` que aparece. O contrato
// por extenso está no README do kit, seção "Conjunto mínimo".
import { ref } from "vue";

const buttonSizes = [
  { size: "md", title: "md: todo lugar" },
  { size: "xl", title: "xl: toque crítico (PDV, Cozinha, quiosque)" },
] as const;
const buttonVariants = ["solid", "outline", "ghost"] as const;
const buttonColors = [
  { color: "primary", label: "Principal" },
  { color: "neutral", label: "Neutro" },
  { color: "error", label: "Perigo" },
] as const;

const badges = [
  { color: "neutral", label: "Retirada" },
  { color: "primary", label: "Encomenda" },
  { color: "success", label: "Pronto" },
  { color: "warning", label: "Atrasado" },
  { color: "error", label: "Recusado" },
] as const;

const alerts = [
  { color: "info", title: "Cardápio atualizado", icon: "i-lucide-info" },
  { color: "success", title: "Pedido entregue", icon: "i-lucide-circle-check" },
  { color: "warning", title: "Estoque baixo de croissant", icon: "i-lucide-triangle-alert" },
  { color: "error", title: "Pagamento recusado", icon: "i-lucide-circle-x" },
] as const;

const textScale = [
  { cls: "text-xs", label: "text-xs, 12 px", use: "rótulo e meta" },
  { cls: "text-sm", label: "text-sm, 14 px", use: "texto corrido e controles" },
  { cls: "text-base", label: "text-base, 16 px", use: "título de cartão" },
  { cls: "text-xl", label: "text-xl, 20 px", use: "título de tela" },
  { cls: "text-2xl", label: "text-2xl, 24 px", use: "figura" },
] as const;

const liveTones = [
  { tone: "live", time: "10:12", label: "Ao vivo", use: "ao vivo: o ponto e a hora" },
  { tone: "calm", time: "10:12", label: "Atualiza a cada 60 s", use: "leitura calma: a cadência" },
  { tone: "late", time: "10:04", label: "Sem atualizar", use: "atrasado: a hora da última leitura" },
  { tone: "off", time: "", label: "Sem conexão", use: "sem conexão" },
] as const;

const stations = ["Balcão", "Forno", "Confeitaria", "Expedição"];
const products = [
  "Baguete tradicional",
  "Pão de campanha",
  "Pão de centeio",
  "Ciabatta",
  "Brioche",
  "Croissant",
  "Croissant de amêndoas",
  "Pain au chocolat",
  "Pain aux raisins",
  "Madeleine",
  "Canelé",
  "Éclair de café",
  "Paris-Brest",
  "Tarte au citron",
  "Quiche lorraine",
  "Café coado",
];
const station = ref("Forno");
const product = ref("Croissant");

const retired = [
  {
    name: "UiButton",
    replacement: "NuxtButton no conjunto: default vira primary solid, destructive vira error, outline e secondary viram neutral outline, ghost fica neutral ghost, link vira primary ghost; lg vira xl, icon vira square.",
  },
  {
    name: "UiIconButton",
    replacement: "NuxtButton square, neutral ghost, com aria-label.",
  },
  {
    name: "UiNativeSelect",
    replacement: "NuxtSelect para lista curta e fixa; NuxtSelectMenu para lista longa ou buscável, sem abrir o teclado no toque. Com v-model, perde o valor inicial depois do SSR.",
  },
] as const;
</script>

<template>
  <section
    id="minimal-set"
    class="space-y-4"
    data-operator-audit-id="catalog-minimal-set"
    aria-labelledby="minimal-set-title"
  >
    <div>
      <p class="op-eyebrow">Conjunto mínimo</p>
      <h2 id="minimal-set-title" class="op-title">
        O que a suíte usa, fixado uma vez no tema
      </h2>
      <p class="op-body mt-1 text-muted">
        Peça sem cor nem variante já sai no padrão do tema. O que passa disso é
        uso antigo, que cada app troca na própria migração.
      </p>
    </div>

    <NuxtCard
      title="Botão"
      description="Dois tamanhos, três variantes, três cores. Sem prop, é o gesto principal: primary solid md."
    >
      <div class="space-y-5">
        <div
          v-for="row in buttonSizes"
          :key="row.size"
          class="space-y-2"
          :data-minimal-button-size="row.size"
        >
          <h3 class="text-sm font-semibold">{{ row.title }}</h3>
          <div class="grid gap-2">
            <div
              v-for="color in buttonColors"
              :key="color.color"
              class="flex flex-wrap items-center gap-2"
            >
              <span class="w-20 shrink-0 text-xs font-medium text-muted">{{ color.color }}</span>
              <NuxtButton
                v-for="variant in buttonVariants"
                :key="variant"
                :size="row.size"
                :color="color.color"
                :variant="variant"
                :label="`${color.label} ${variant}`"
              />
            </div>
          </div>
        </div>
      </div>
    </NuxtCard>

    <div class="grid gap-4 lg:grid-cols-2">
      <NuxtCard
        title="Selo"
        description="Uma variante só (subtle, com borda), cinco cores. Sem prop: neutral."
      >
        <div class="flex flex-wrap gap-2" data-minimal-badges>
          <NuxtBadge
            v-for="badge in badges"
            :key="badge.color"
            :color="badge.color"
            :label="badge.label"
          />
        </div>
      </NuxtCard>

      <NuxtCard
        title="Aviso"
        description="Uma variante só (subtle), quatro cores. Sem prop: info."
      >
        <div class="space-y-2" data-minimal-alerts>
          <NuxtAlert
            v-for="alert in alerts"
            :key="alert.color"
            :color="alert.color"
            :icon="alert.icon"
            :title="alert.title"
          />
        </div>
      </NuxtCard>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <NuxtCard
        title="Cartão"
        description="Outline no nível da página. Soft só para o cartão dentro de outro."
      >
        <NuxtCard variant="soft" data-minimal-nested-card>
          <p class="text-sm font-medium">Lote das 7h</p>
          <p class="text-xs text-muted">48 croissants, forno 1</p>
        </NuxtCard>
      </NuxtCard>
      <NuxtPageCard
        title="Dois pedidos para revisar"
        description="Destaque é PageCard com highlight: o item que pede o próximo gesto."
        icon="i-lucide-triangle-alert"
        highlight
        highlight-color="warning"
        variant="outline"
      />
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <NuxtCard
        title="Texto"
        description="Cinco tamanhos, dois pesos de destaque (medium e semibold). Zero arbitrários."
      >
        <ul class="space-y-1">
          <li
            v-for="item in textScale"
            :key="item.cls"
            class="flex flex-wrap items-baseline justify-between gap-x-3"
          >
            <span :class="item.cls"
              ><span class="font-medium">Croissant</span>
              <span class="font-semibold">Croissant</span></span
            >
            <span class="text-xs text-muted">{{ item.label }}, {{ item.use }}</span>
          </li>
        </ul>
      </NuxtCard>
      <NuxtCard
        title="Raio"
        description="Um token (--ui-radius) e três usos: o do componente, redondo e reto."
      >
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex flex-col items-center gap-1">
            <NuxtButton label="Componente" color="neutral" variant="outline" />
            <span class="text-xs text-muted">o do tema</span>
          </div>
          <div class="flex flex-col items-center gap-1">
            <div class="size-10 rounded-full border border-default bg-elevated" />
            <span class="text-xs text-muted">redondo: avatar, ponto</span>
          </div>
          <div class="flex flex-col items-center gap-1">
            <div class="size-10 rounded-none border border-default bg-elevated" />
            <span class="text-xs text-muted">reto</span>
          </div>
        </div>
      </NuxtCard>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <NuxtCard
        title="Selo ao vivo"
        description="OperatorLiveStatus: o ponto e a hora quando é ao vivo; fora dele, o estado por extenso."
      >
        <ul class="space-y-3" data-minimal-live>
          <li
            v-for="state in liveTones"
            :key="state.tone"
            class="flex flex-wrap items-center justify-between gap-2"
          >
            <OperatorLiveStatus
              :tone="state.tone"
              :time="state.time"
              :label="state.label"
            />
            <span class="text-xs text-muted">{{ state.use }}</span>
          </li>
        </ul>
      </NuxtCard>
      <NuxtCard
        title="Escolha numa lista"
        description="NuxtSelect para lista curta e fixa. NuxtSelectMenu para lista longa ou buscável, sem teclado automático no toque."
      >
        <div class="grid gap-4 sm:grid-cols-2">
          <NuxtFormField label="Estação" name="minimal-station">
            <NuxtSelect v-model="station" :items="stations" class="w-full" />
          </NuxtFormField>
          <NuxtFormField label="Produto" name="minimal-product">
            <NuxtSelectMenu
              v-model="product"
              :items="products"
              :search-input="{ autofocus: false, placeholder: 'Buscar produto' }"
              class="w-full"
            />
          </NuxtFormField>
        </div>
      </NuxtCard>
    </div>

    <NuxtCard
      title="Aposentados"
      description="Nenhum uso novo. Os que existem saem quando cada app migra; a trava do kit tem o teto por app."
    >
      <ul class="space-y-3" data-minimal-retired>
        <li
          v-for="item in retired"
          :key="item.name"
          class="flex flex-wrap items-start gap-2"
          :data-retired="item.name"
        >
          <NuxtBadge color="warning" label="Aposentado" />
          <div class="min-w-0 flex-1">
            <p class="text-sm font-semibold">{{ item.name }}</p>
            <p class="text-sm text-muted">{{ item.replacement }}</p>
          </div>
        </li>
      </ul>
    </NuxtCard>
  </section>
</template>
