<script setup lang="ts">
// Proposta 5 (rail da suíte): o rail montado SÓ com peças do Nuxt UI
// (DashboardGroup, DashboardSidebar, NavigationMenu,
// DashboardSidebarToggle), sem :ui por instância, para o dono decidir.
//
// Os três estados:
//   aberto    = DashboardSidebar `collapsed=false` (ícone + nome);
//   compacto  = `collapsed=true` (só ícone; o NavigationMenu recolhido esconde nome e
//               selo e mostra o nome em tooltip);
//   oculto    = no desktop, o sidebar não é montado (estado do kit, um cookie); abaixo
//               de lg o Nuxt UI já esconde o rail e o abre como slideover pelo
//               DashboardSidebarToggle da barra.
//
// O tema dourado: o bloco `railTheme` abaixo é EXATAMENTE o que iria para o
// `app.config.ts` do kit (`ui.dashboardSidebar`). Aqui ele entra pela API oficial
// `updateAppConfig`, só nesta rota, porque a home do catálogo também usa
// DashboardSidebar (OperatorOfficeShell) e não deve mudar antes da decisão.
import { useMediaQuery } from "@vueuse/core";

useHead({ title: "Proposta: rail da suíte" });

type RailState = "open" | "compact" | "hidden";

const route = useRoute();
const palette = route.query.palette === "neutral" ? "neutral" : "gold";

// Tokens do Nuxt UI redefinidos SÓ dentro do rail: os componentes canônicos que
// moram nele (NavigationMenu, Button, Chip) leem o dourado sem nenhuma classe nova.
const goldScope = [
  "bg-rail text-rail-foreground border-e-0",
  "[--ui-text:var(--rail-foreground)]",
  "[--ui-text-muted:var(--rail-foreground)]",
  "[--ui-text-dimmed:var(--rail-foreground)]",
  "[--ui-text-toned:var(--rail-foreground)]",
  "[--ui-text-highlighted:var(--rail-foreground)]",
  "[--primary:var(--rail-foreground)]",
  "[--ui-primary:var(--rail-foreground)]",
  "[--ui-bg-elevated:rgb(0_0_0/0.4)]",
  "[--ui-border:color-mix(in_srgb,var(--rail-foreground)_25%,transparent)]",
].join(" ");

const railTheme = {
  slots: {
    root: goldScope,
    content: goldScope,
  },
};

if (palette === "gold") updateAppConfig({ ui: { dashboardSidebar: railTheme } });

const isDesktop = useMediaQuery("(min-width: 1024px)", { ssrWidth: 1440 });

// Aberto e compacto: estado do próprio DashboardSidebar, gravado pelo
// DashboardGroup no cookie `<storage-key>-sidebar-<id>` ({ size, collapsed }).
const collapsed = ref(false);
// Oculto (só desktop): o Nuxt UI não tem esse terceiro estado; o kit guarda num cookie.
const hidden = useCookie<boolean>("kitchensink-rail-hidden", { default: () => false });

const initial = route.query.state as RailState | undefined;
if (initial === "open" || initial === "compact" || initial === "hidden") {
  hidden.value = initial === "hidden";
  collapsed.value = initial === "compact";
}

const state = computed<RailState>({
  get: () => (hidden.value ? "hidden" : collapsed.value ? "compact" : "open"),
  set: (value) => {
    hidden.value = value === "hidden";
    if (value !== "hidden") collapsed.value = value === "compact";
  },
});

const stateItems = [
  { label: "Aberto", value: "open", icon: "i-lucide-panel-left" },
  { label: "Compacto", value: "compact", icon: "i-lucide-panel-left-dashed" },
  { label: "Oculto", value: "hidden", icon: "i-lucide-panel-left-close" },
];

// Atalho: a doc do DashboardSidebar mostra `defineShortcuts` com a tecla C para
// recolher. Aqui o mesmo gesto percorre os três estados.
// Um botão só na barra faz o mesmo percurso; o ícone e o nome dizem o PRÓXIMO estado.
const order: RailState[] = ["open", "compact", "hidden"];
async function cycle() {
  const target = order[(order.indexOf(state.value) + 1) % order.length]!;
  state.value = target;
  // Ao voltar do oculto, o DashboardSidebar remonta e relê o cookie (compacto);
  // o aberto é reafirmado depois da montagem.
  if (target === "open") {
    await nextTick();
    collapsed.value = false;
  }
}
const nextLabel: Record<RailState, { label: string; icon: string }> = {
  open: { label: "Compactar o rail", icon: "i-lucide-panel-left-dashed" },
  compact: { label: "Ocultar o rail", icon: "i-lucide-panel-left-close" },
  hidden: { label: "Mostrar o rail", icon: "i-lucide-panel-left-open" },
};
const next = computed(() => nextLabel[state.value]);
defineShortcuts({ c: cycle });

const badgeCount = "3";
const suite = computed(() => [
  [
    { label: "Central", icon: "i-lucide-layout-grid" },
    { label: "PDV", icon: "i-lucide-shopping-cart" },
    {
      label: "Cozinha",
      icon: "i-lucide-chef-hat",
      // Aberto: o selo ao lado do nome. Compacto: o NavigationMenu esconde o selo,
      // então o ponto (Chip) no ícone avisa e o tooltip diz o número.
      badge: { label: badgeCount, color: "neutral" as const, variant: "solid" as const },
      chip: collapsed.value ? { color: "warning" as const } : undefined,
      tooltip: { text: `Cozinha, ${badgeCount} pedidos esperando` },
    },
    { label: "Gestor", icon: "i-lucide-clipboard-list", active: true },
    { label: "Produção", icon: "i-lucide-croissant" },
    { label: "Marketing", icon: "i-lucide-megaphone" },
    { label: "Compras", icon: "i-lucide-truck" },
    { label: "B.I.", icon: "i-lucide-chart-line" },
  ],
]);
const foot = [
  { label: "Atalhos", icon: "i-lucide-keyboard" },
  { label: "Bloquear", icon: "i-lucide-lock" },
];
</script>

<template>
  <NuxtDashboardGroup
    storage-key="kitchensink-rail"
    unit="rem"
    data-operator-catalog="proposal-rail"
    :data-rail-state="state"
    :data-rail-palette="palette"
  >
    <NuxtDashboardSidebar
      v-if="!(hidden && isDesktop)"
      id="suite"
      v-model:collapsed="collapsed"
      collapsible
      :collapsed-size="4"
      :default-size="14"
      :min-size="14"
      :max-size="14"
      aria-label="Apps da suíte"
    >
      <template #header="{ collapsed: isCollapsed }">
        <Icon name="lucide:croissant" class="size-6 shrink-0" :class="isCollapsed ? 'mx-auto' : ''" aria-hidden="true" />
        <span v-if="!isCollapsed" class="font-semibold">Nelson Boulangerie</span>
      </template>

      <template #default="{ collapsed: isCollapsed }">
        <NuxtNavigationMenu
          :collapsed="isCollapsed"
          :items="suite"
          orientation="vertical"
          tooltip
          popover
          data-rail-menu
        />
        <NuxtNavigationMenu
          :collapsed="isCollapsed"
          :items="foot"
          orientation="vertical"
          tooltip
          class="mt-auto"
        />
      </template>
    </NuxtDashboardSidebar>

    <NuxtDashboardPanel id="proposal-rail-content">
      <template #header>
        <NuxtDashboardNavbar title="5. Rail da suíte">
          <template #leading>
            <NuxtButton
              class="hidden lg:inline-flex"
              :icon="next.icon"
              color="neutral"
              variant="ghost"
              :aria-label="next.label"
              :title="next.label"
              data-rail-cycle
              @click="cycle"
            />
          </template>
        </NuxtDashboardNavbar>
      </template>
      <template #body>
        <div class="max-w-3xl space-y-4">
          <NuxtCard title="Três estados, peças oficiais">
            <div class="space-y-3 text-sm">
              <p>
                Aberto e compacto são o <code>collapsed</code> do DashboardSidebar. Um botão só na barra
                percorre os três estados; o ícone e o nome dizem o próximo. Oculto não existe no Nuxt UI para o desktop: aqui é
                o sidebar não montado, guardado num cookie do kit. No celular o rail sempre começa
                oculto e abre como slideover pelo botão de menu da barra.
              </p>
              <p>
                Tecla <NuxtKbd value="C" /> percorre aberto, compacto e oculto.
              </p>
              <div class="hidden lg:flex flex-wrap gap-2" role="group" aria-label="Estado do rail">
                <NuxtButton
                  v-for="item in stateItems"
                  :key="item.value"
                  :label="item.label"
                  :icon="item.icon"
                  color="neutral"
                  :variant="state === item.value ? 'solid' : 'outline'"
                  :aria-pressed="state === item.value"
                  @click="state = item.value as RailState"
                />
              </div>
            </div>
          </NuxtCard>
          <NuxtCard title="O tema dourado">
            <p class="text-sm">
              O fundo e as cores do rail saem de um bloco <code>ui.dashboardSidebar.slots</code>
              (<code>root</code> e <code>content</code>) que redefine os tokens do Nuxt UI só dentro do
              rail. Nesta página ele entra por <code>updateAppConfig</code>, só nesta rota, para não
              mudar a home do catálogo antes da decisão. Na suíte ele mora no
              <code>app.config.ts</code> do kit, uma vez, e nenhuma tela passa <code>:ui</code>.
            </p>
          </NuxtCard>
        </div>
      </template>
    </NuxtDashboardPanel>
  </NuxtDashboardGroup>
</template>
