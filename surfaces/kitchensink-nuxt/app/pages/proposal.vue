<script setup lang="ts">
// Proposta para decisão do dono (WP-BI-CANON-LAUDO, seção F): o que está em uso hoje
// ao lado do conjunto mínimo proposto, com os componentes reais e o tema do kit.
// A página não muda o kit nem o tema: só passa props explícitas para mostrar o
// conjunto proposto. Nada aqui é contrato; é material de decisão.
import { onMounted, ref } from "vue";

useHead({ title: "Proposta: conjunto mínimo" });

const hydrated = ref(false);
onMounted(() => {
  hydrated.value = true;
});

type ButtonSize = "md" | "xl";
type ButtonVariant = "solid" | "outline" | "ghost";
type ButtonColor = "primary" | "neutral" | "error";

const proposedSizes: ButtonSize[] = ["md", "xl"];
const proposedVariants: ButtonVariant[] = ["solid", "outline", "ghost"];
const proposedColors: ButtonColor[] = ["primary", "neutral", "error"];
const colorLabel: Record<ButtonColor, string> = {
  primary: "Principal",
  neutral: "Neutro",
  error: "Perigo",
};

const badgeColors = ["neutral", "primary", "success", "warning", "error"] as const;
const badgeLabel: Record<(typeof badgeColors)[number], string> = {
  neutral: "Retirada",
  primary: "Encomenda",
  success: "Pronto",
  warning: "Atrasado",
  error: "Recusado",
};

const alertColors = [
  { color: "info", title: "Cardápio atualizado", icon: "i-lucide-info" },
  { color: "success", title: "Pedido entregue", icon: "i-lucide-circle-check" },
  { color: "warning", title: "Estoque baixo de croissant", icon: "i-lucide-triangle-alert" },
  { color: "error", title: "Pagamento recusado", icon: "i-lucide-circle-x" },
] as const;

const textToday = [
  { cls: "text-[9px]", label: "9 px" },
  { cls: "text-[9.5px]", label: "9,5 px" },
  { cls: "text-[0.625rem]", label: "0,625 rem" },
  { cls: "text-[10px]", label: "10 px" },
  { cls: "text-[11px]", label: "11 px" },
  { cls: "text-xs", label: "text-xs, 12 px" },
  { cls: "text-[12px]", label: "12 px arbitrário" },
  { cls: "text-[13px]", label: "13 px (op-label)" },
  { cls: "text-sm", label: "text-sm, 14 px" },
  { cls: "text-[15px]", label: "15 px (op-body)" },
  { cls: "text-base", label: "text-base, 16 px" },
  { cls: "text-[16px]", label: "16 px arbitrário" },
  { cls: "text-lg", label: "text-lg, 18 px" },
  { cls: "text-xl", label: "text-xl, 20 px" },
  { cls: "text-2xl", label: "text-2xl, 24 px" },
];

const textProposed = [
  { cls: "text-xs", label: "text-xs, 12 px", use: "rótulo e meta" },
  { cls: "text-sm", label: "text-sm, 14 px", use: "texto corrido e controles" },
  { cls: "text-base", label: "text-base, 16 px", use: "título de cartão" },
  { cls: "text-xl", label: "text-xl, 20 px", use: "título de tela" },
  { cls: "text-2xl", label: "text-2xl, 24 px", use: "figura" },
];

const radiusToday = [
  "rounded-none",
  "rounded-sm",
  "rounded",
  "rounded-md",
  "rounded-[10px]",
  "rounded-lg",
  "rounded-xl",
  "rounded-[14px]",
  "rounded-2xl",
  "rounded-3xl",
  "rounded-full",
];

const stations = ["Balcão", "Forno", "Confeitaria", "Expedição"];
const station = ref("Forno");
const stationNative = ref("Forno");
const stationMenu = ref("Forno");

const products = [
  "Baguete tradicional",
  "Baguete de fermentação natural",
  "Pão de campanha",
  "Pão de centeio",
  "Pão integral de nozes",
  "Pão de azeitona",
  "Fougasse de alecrim",
  "Ciabatta",
  "Focaccia de tomate",
  "Brioche",
  "Brioche de chocolate",
  "Croissant",
  "Croissant de amêndoas",
  "Pain au chocolat",
  "Pain aux raisins",
  "Chausson aux pommes",
  "Kouign-amann",
  "Madeleine",
  "Financier de pistache",
  "Canelé",
  "Éclair de café",
  "Éclair de chocolate",
  "Paris-Brest",
  "Tarte au citron",
  "Tarte aux fraises",
  "Tarte Tatin",
  "Mille-feuille",
  "Opéra",
  "Macaron de framboesa",
  "Macaron de baunilha",
  "Quiche lorraine",
  "Quiche de alho-poró",
  "Croque-monsieur",
  "Sanduíche de presunto e brie",
  "Sanduíche de frango",
  "Salada niçoise",
  "Sopa de cebola",
  "Café coado",
  "Chocolate quente",
  "Suco de laranja",
];
const product = ref("Croissant");
const productNative = ref("Croissant");
const productMenu = ref("Croissant");
</script>

<template>
  <div
    data-operator-catalog="proposal"
    data-proposal-page
    :data-hydrated="hydrated ? 'true' : 'false'"
  >
    <OperatorPage
      title="Proposta: conjunto mínimo"
      description="Hoje ao lado da proposta, com os componentes reais e o tema do kit. Nada foi mudado na suíte: esta página serve para decidir."
    >
      <!-- 1. Botões -->
      <section id="botoes" data-proposal-section="1-botoes" aria-labelledby="botoes-title" class="space-y-4">
        <h2 id="botoes-title" class="text-xl font-semibold">1. Botões</h2>
        <div class="grid gap-4 lg:grid-cols-2">
          <NuxtCard title="Hoje" description="Duas famílias (NuxtButton e UiButton), 5 tamanhos e 6 cores. Amostra de combinações reais, com a origem.">
            <ul class="grid gap-3">
              <li class="flex flex-wrap items-center justify-between gap-2">
                <NuxtButton label="Mais ações da fila" color="neutral" variant="outline" />
                <span class="text-xs text-muted">NuxtButton neutral outline · Gestor, BoardMenu</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <NuxtButton label="Desfazer" color="neutral" variant="link" />
                <span class="text-xs text-muted">NuxtButton neutral link · Gestor, QueueView</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <NuxtButton label="Manter sem GTIN na nota" color="warning" variant="outline" />
                <span class="text-xs text-muted">NuxtButton warning outline · Gestor, Catálogo</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <NuxtButton label="Desfazer 5 s" color="success" variant="outline" />
                <span class="text-xs text-muted">NuxtButton success outline · Gestor, OrderCard</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <NuxtButton label="Copiar endereço" size="xs" color="info" variant="outline" />
                <span class="text-xs text-muted">NuxtButton xs info outline · Gestor, Canais</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <NuxtButton label="2" size="xs" color="error" variant="soft" />
                <span class="text-xs text-muted">NuxtButton xs error soft · Gestor, Catálogo</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <NuxtButton label="Produto: Croissant" color="primary" variant="soft" />
                <span class="text-xs text-muted">NuxtButton primary soft · Gestor, Histórico</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <NuxtButton label="7" size="xl" color="neutral" variant="outline" />
                <span class="text-xs text-muted">NuxtButton xl neutral outline · kit, teclado do PIN</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <UiButton size="lg" class="h-14 gap-2 text-base">Nova venda</UiButton>
                <span class="text-xs text-muted">UiButton lg (h-14) · PDV, fim da venda</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <UiButton variant="destructive">Remover item</UiButton>
                <span class="text-xs text-muted">UiButton destructive · PDV, carrinho</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <UiButton variant="secondary" class="min-h-12">Confirmar cliente</UiButton>
                <span class="text-xs text-muted">UiButton secondary · PDV, cliente</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <UiButton variant="outline" size="xs">Repetir último pedido</UiButton>
                <span class="text-xs text-muted">UiButton outline xs · PDV, cliente</span>
              </li>
            </ul>
          </NuxtCard>

          <NuxtCard title="Proposta" description="Uma família só: tamanhos md e xl, variantes solid, outline e ghost, cores primary, neutral e error.">
            <div class="space-y-5">
              <div v-for="size in proposedSizes" :key="size" class="space-y-2">
                <h3 class="text-sm font-semibold">
                  {{ size === "md" ? "md: todo lugar" : "xl: toque crítico (PDV, KDS, quiosque)" }}
                </h3>
                <div class="overflow-x-auto">
                  <table class="w-full text-sm">
                    <thead>
                      <tr>
                        <th scope="col" class="p-1 text-left text-xs font-medium text-muted">Cor</th>
                        <th v-for="variant in proposedVariants" :key="variant" scope="col" class="p-1 text-left text-xs font-medium text-muted">
                          {{ variant }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="color in proposedColors" :key="color">
                        <th scope="row" class="p-1 text-left text-xs font-medium text-muted">{{ color }}</th>
                        <td v-for="variant in proposedVariants" :key="variant" class="p-1">
                          <NuxtButton :size="size" :color="color" :variant="variant" :label="colorLabel[color]" />
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div class="space-y-2">
                <h3 class="text-sm font-semibold">Barra de trabalho só com o conjunto</h3>
                <div class="overflow-hidden rounded-md border border-default">
                  <OperatorToolbar>
                    <template #left>
                      <NuxtButton icon="i-lucide-sliders-horizontal" color="neutral" variant="ghost" square aria-label="Filtros" />
                      <NuxtButton label="Hoje" color="neutral" variant="outline" active active-variant="solid" />
                      <NuxtButton label="Semana" color="neutral" variant="outline" />
                    </template>
                    <template #right>
                      <NuxtButton label="Exportar" icon="i-lucide-download" color="neutral" variant="outline" />
                      <NuxtButton label="Novo pedido" icon="i-lucide-plus" color="primary" variant="solid" />
                    </template>
                  </OperatorToolbar>
                </div>
              </div>

              <div class="space-y-2">
                <h3 class="text-sm font-semibold">Rodapé de diálogo só com o conjunto</h3>
                <NuxtCard>
                  <p class="text-base font-semibold">Recusar o pedido NB-1048?</p>
                  <p class="mt-1 text-sm text-muted">O cliente recebe o aviso e o valor volta pelo mesmo meio de pagamento.</p>
                  <template #footer>
                    <div class="flex flex-wrap justify-end gap-2">
                      <NuxtButton label="Voltar" color="neutral" variant="outline" />
                      <NuxtButton label="Recusar pedido" color="error" variant="solid" />
                    </div>
                  </template>
                </NuxtCard>
              </div>
            </div>
          </NuxtCard>
        </div>
      </section>

      <!-- 2. Badge, Card, Alert, Texto, Raio -->
      <section id="pecas" data-proposal-section="2-pecas" aria-labelledby="pecas-title" class="space-y-4">
        <h2 id="pecas-title" class="text-xl font-semibold">2. Selo, cartão, aviso, texto e raio</h2>

        <h3 class="text-base font-semibold">Selo (Badge)</h3>
        <div class="grid gap-4 lg:grid-cols-2">
          <NuxtCard title="Hoje" description="4 variantes × 6 cores. O mesmo neutro aparece como soft e como subtle, às vezes no mesmo componente.">
            <div class="space-y-3">
              <div class="flex flex-wrap items-center gap-2">
                <NuxtBadge color="neutral" variant="soft" label="Retirada" />
                <NuxtBadge color="neutral" variant="subtle" label="Retirada" />
                <span class="text-xs text-muted">neutro soft e subtle · Gestor, QueueView</span>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <NuxtBadge color="error" variant="soft" label="Bloqueado" />
                <NuxtBadge color="warning" variant="outline" label="Atrasado" />
                <NuxtBadge color="success" variant="solid" label="Pronto" />
                <NuxtBadge color="info" variant="subtle" label="Encomenda" />
                <NuxtBadge color="primary" variant="soft" label="Destaque" />
              </div>
            </div>
          </NuxtCard>
          <NuxtCard title="Proposta" description="Uma variante (subtle, com borda) × 5 cores. info vira neutral.">
            <div class="flex flex-wrap gap-2">
              <NuxtBadge v-for="color in badgeColors" :key="color" :color="color" variant="subtle" :label="badgeLabel[color]" />
            </div>
          </NuxtCard>
        </div>

        <h3 class="text-base font-semibold">Cartão (Card)</h3>
        <div class="grid gap-4 lg:grid-cols-2">
          <NuxtCard title="Hoje" description="3 estilos: outline (padrão), soft e subtle, usados como caixa dentro do painel.">
            <div class="grid gap-3 sm:grid-cols-3">
              <NuxtCard variant="outline"><p class="text-sm font-medium">outline</p><p class="text-xs text-muted">75 usos</p></NuxtCard>
              <NuxtCard variant="soft"><p class="text-sm font-medium">soft</p><p class="text-xs text-muted">9 usos</p></NuxtCard>
              <NuxtCard variant="subtle"><p class="text-sm font-medium">subtle</p><p class="text-xs text-muted">3 usos</p></NuxtCard>
            </div>
          </NuxtCard>
          <NuxtCard title="Proposta" description="Só outline. Destaque navegável é o PageCard com highlight.">
            <div class="grid gap-3 sm:grid-cols-2">
              <NuxtCard variant="outline"><p class="text-sm font-medium">Lote das 7h</p><p class="text-xs text-muted">48 croissants, forno 1</p></NuxtCard>
              <NuxtPageCard
                title="Dois pedidos para revisar"
                description="Abra a fila para decidir"
                icon="i-lucide-triangle-alert"
                highlight
                highlight-color="warning"
                variant="outline"
                to="#pecas"
              />
            </div>
          </NuxtCard>
        </div>

        <h3 class="text-base font-semibold">Aviso (Alert)</h3>
        <div class="grid gap-4 lg:grid-cols-2">
          <NuxtCard title="Hoje" description="3 variantes × 6 cores (subtle em 95% dos usos).">
            <div class="space-y-2">
              <NuxtAlert color="error" variant="soft" icon="i-lucide-lock" title="Expirou às 15:40" />
              <NuxtAlert color="warning" variant="solid" icon="i-lucide-triangle-alert" title="Forno 2 parado" />
              <NuxtAlert color="neutral" variant="subtle" icon="i-lucide-info" title="Sem pedidos novos" />
              <NuxtAlert color="primary" variant="subtle" icon="i-lucide-sparkles" title="Campanha ativa" />
            </div>
          </NuxtCard>
          <NuxtCard title="Proposta" description="Uma variante (subtle) × 4 cores: info, success, warning, error.">
            <div class="space-y-2">
              <NuxtAlert v-for="alert in alertColors" :key="alert.color" :color="alert.color" variant="subtle" :icon="alert.icon" :title="alert.title" />
            </div>
          </NuxtCard>
        </div>

        <h3 class="text-base font-semibold">Texto</h3>
        <div class="grid gap-4 lg:grid-cols-2">
          <NuxtCard title="Hoje" description="15 tamanhos nas telas migradas, 9 deles arbitrários. 4 pesos.">
            <ul class="space-y-1">
              <li v-for="item in textToday" :key="item.cls" class="flex items-baseline justify-between gap-3">
                <span :class="item.cls">Croissant de amêndoas</span>
                <span class="shrink-0 text-xs text-muted">{{ item.label }}</span>
              </li>
            </ul>
          </NuxtCard>
          <NuxtCard title="Proposta" description="5 tamanhos × 2 pesos (medium e semibold). Zero arbitrários.">
            <div class="space-y-4">
              <ul class="space-y-1">
                <li v-for="item in textProposed" :key="item.cls" class="flex items-baseline justify-between gap-3">
                  <span :class="item.cls"><span class="font-medium">Croissant</span> <span class="font-semibold">Croissant</span></span>
                  <span class="shrink-0 text-xs text-muted">{{ item.label }}, {{ item.use }}</span>
                </li>
              </ul>
              <div class="space-y-2">
                <p class="text-xl font-semibold">Pedidos de hoje</p>
                <NuxtCard>
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <p class="text-base font-semibold">NB-1048 · Maria Santos</p>
                      <p class="text-sm text-muted">Retirada às 10:30, loja online</p>
                    </div>
                    <NuxtBadge color="warning" variant="subtle" label="Atrasado" />
                  </div>
                  <p class="mt-3 text-sm">2× Croissant, 1× Pain au chocolat, 1× Café coado</p>
                  <div class="mt-3 flex items-end justify-between gap-3">
                    <p class="text-xs font-medium text-muted">Total pago no Pix</p>
                    <p class="text-2xl font-semibold tabular-nums">R$ 38,50</p>
                  </div>
                </NuxtCard>
              </div>
            </div>
          </NuxtCard>
        </div>

        <h3 class="text-base font-semibold">Raio</h3>
        <div class="grid gap-4 lg:grid-cols-2">
          <NuxtCard title="Hoje" description="Dois sistemas de raio (o do kit e o do Nuxt UI), 9 valores nas telas migradas e 16 nas legadas.">
            <div class="flex flex-wrap gap-3">
              <div v-for="radius in radiusToday" :key="radius" class="flex flex-col items-center gap-1">
                <div :class="radius" class="size-12 border border-default bg-elevated" />
                <span class="text-xs text-muted">{{ radius.replace("rounded-", "").replace("rounded", "padrão") }}</span>
              </div>
            </div>
          </NuxtCard>
          <NuxtCard title="Proposta" description="Um token (--ui-radius) e 3 usos: o do componente, redondo e reto.">
            <div class="flex flex-wrap items-center gap-4">
              <div class="flex flex-col items-center gap-1">
                <NuxtButton label="Componente" color="neutral" variant="outline" />
                <span class="text-xs text-muted">o do tema</span>
              </div>
              <div class="flex flex-col items-center gap-1">
                <div class="size-10 rounded-full bg-elevated border border-default" />
                <span class="text-xs text-muted">full: avatar, ponto</span>
              </div>
              <div class="flex flex-col items-center gap-1">
                <div class="size-10 rounded-none bg-elevated border border-default" />
                <span class="text-xs text-muted">none</span>
              </div>
            </div>
          </NuxtCard>
        </div>
      </section>

      <!-- 3. Lista curta -->
      <section id="lista" data-proposal-section="3-lista" aria-labelledby="lista-title" class="space-y-4">
        <h2 id="lista-title" class="text-xl font-semibold">3. Escolha numa lista</h2>
        <p class="text-sm text-muted">
          O mesmo campo nas três peças, no tamanho de toque. Proposta: NuxtSelect para lista curta e fixa,
          NuxtSelectMenu para lista longa (sem abrir o teclado no toque). O seletor nativo se aposenta.
        </p>
        <div class="grid gap-4 lg:grid-cols-3">
          <NuxtCard title="Hoje: UiNativeSelect" description="A lista abre na roda do sistema, fora do tema. Depois do carregamento o campo mostra o primeiro item, não o valor escolhido (Forno, Croissant).">
            <div class="space-y-4" data-proposal-select="native">
              <NuxtFormField label="Estação" name="station-native">
                <UiNativeSelect v-model="stationNative" class="w-full" aria-label="Estação">
                  <option v-for="item in stations" :key="item" :value="item">{{ item }}</option>
                </UiNativeSelect>
              </NuxtFormField>
              <NuxtFormField label="Produto" name="product-native">
                <UiNativeSelect v-model="productNative" class="w-full" aria-label="Produto">
                  <option v-for="item in products" :key="item" :value="item">{{ item }}</option>
                </UiNativeSelect>
              </NuxtFormField>
            </div>
          </NuxtCard>
          <NuxtCard title="Proposta: NuxtSelect" description="Lista curta e fixa.">
            <div class="space-y-4" data-proposal-select="select">
              <NuxtFormField label="Estação" name="station-select">
                <NuxtSelect v-model="station" :items="stations" class="w-full" data-proposal-open="select-station" />
              </NuxtFormField>
              <NuxtFormField label="Produto" name="product-select">
                <NuxtSelect v-model="product" :items="products" class="w-full" data-proposal-open="select-product" />
              </NuxtFormField>
            </div>
          </NuxtCard>
          <NuxtCard title="Proposta: NuxtSelectMenu" description="Lista longa ou buscável, sem teclado automático.">
            <div class="space-y-4" data-proposal-select="select-menu">
              <NuxtFormField label="Estação" name="station-menu">
                <NuxtSelectMenu
                  v-model="stationMenu"
                  :items="stations"
                  :search-input="{ autofocus: false, placeholder: 'Buscar estação' }"
                  class="w-full"
                  data-proposal-open="menu-station"
                />
              </NuxtFormField>
              <NuxtFormField label="Produto" name="product-menu">
                <NuxtSelectMenu
                  v-model="productMenu"
                  :items="products"
                  :search-input="{ autofocus: false, placeholder: 'Buscar produto' }"
                  class="w-full"
                  data-proposal-open="menu-product"
                />
              </NuxtFormField>
            </div>
          </NuxtCard>
        </div>
      </section>

      <!-- 4. Selo ao vivo -->
      <section id="ao-vivo" data-proposal-section="4-ao-vivo" aria-labelledby="ao-vivo-title" class="space-y-4">
        <h2 id="ao-vivo-title" class="text-xl font-semibold">4. Selo ao vivo</h2>
        <div class="grid gap-4 lg:grid-cols-2">
          <NuxtCard title="Hoje: OperatorLiveStatus" description="Mostra On ou Off. Leitura calma e atrasada parecem ao vivo.">
            <ul class="space-y-3">
              <li class="flex flex-wrap items-center justify-between gap-2">
                <OperatorLiveStatus tone="live" time="10:12" label="Ao vivo" />
                <span class="text-xs text-muted">ao vivo</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <OperatorLiveStatus tone="calm" time="10:12" label="Atualiza a cada 60 s" />
                <span class="text-xs text-muted">leitura calma</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <OperatorLiveStatus tone="late" time="10:04" label="Atrasado" />
                <span class="text-xs text-muted">atrasado</span>
              </li>
              <li class="flex flex-wrap items-center justify-between gap-2">
                <OperatorLiveStatus tone="off" label="Sem conexão" />
                <span class="text-xs text-muted">sem conexão</span>
              </li>
            </ul>
          </NuxtCard>
          <NuxtCard title="Proposta: o contrato do README do kit" description="O ponto com a hora quando é ao vivo; fora dele, o estado por extenso.">
            <div class="space-y-3">
              <div
                v-for="state in [
                  { key: 'live', title: 'Fila de pedidos', color: 'success', label: '10:12', dot: true, aria: 'Ao vivo, última leitura 10:12' },
                  { key: 'calm', title: 'Quanto vendemos?', color: 'neutral', label: 'Atualiza a cada 60 s', dot: false, aria: 'Atualiza a cada 60 s, última leitura 10:12' },
                  { key: 'late', title: 'Cozinha', color: 'warning', label: 'Última leitura às 10:04', dot: true, aria: 'Atrasado, última leitura 10:04' },
                  { key: 'off', title: 'Saída', color: 'error', label: 'Sem conexão', dot: false, aria: 'Sem conexão' },
                ] as const"
                :key="state.key"
                class="flex flex-wrap items-center justify-between gap-3 rounded-md border border-default bg-default px-3 py-2"
                :data-proposal-live="state.key"
              >
                <div class="flex min-w-0 flex-wrap items-center gap-2">
                  <p class="text-xl font-semibold">{{ state.title }}</p>
                  <NuxtBadge :color="state.color" variant="subtle" :label="state.label" role="status" :aria-label="state.aria" :title="state.aria">
                    <template v-if="state.dot" #leading>
                      <NuxtChip as="span" :color="state.color" size="md" inset standalone />
                    </template>
                  </NuxtBadge>
                </div>
                <NuxtButton label="Atualizar" icon="i-lucide-refresh-cw" color="neutral" variant="ghost" />
              </div>
            </div>
          </NuxtCard>
        </div>
      </section>
    </OperatorPage>
  </div>
</template>
