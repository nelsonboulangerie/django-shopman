<script setup lang="ts">
// Cabeçalho de seção do Marketing: mora no topo do CONTEÚDO (não é o rail).
//
// Decisão do dono (03/10/2026, SUITE-UX §6): o andar de OPERAÇÃO tem quatro
// seções, Decisões, Agendados, Enviados e Ajustes, e o andar de AJUSTES entra por
// um item só, com as próprias seções numa segunda linha (Campanhas, Modelos,
// Ofertas e cupons, Plataformas). No celular as quatro vão para uma barra no pé
// da tela, ao alcance do polegar; a barra do topo fica com o sino.
//
// Nenhuma rota foi removida: `/v2?area=…`, `/campaigns`, `/templates`, `/platforms` e
// `/history` continuam onde estavam. Só mudou por onde se chega a elas.
// As funções comuns (Shopman Apps, operador, tema) vivem no OperatorRail à esquerda.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

const route = useRoute();
const { decisionCount } = useMarketingDecisions();

type SectionKey = "decisions" | "scheduled" | "sent" | "settings";
type SettingsKey = "campaigns" | "templates" | "offers" | "platforms";

const activeSection = computed<SectionKey>(() => {
  const path = route.path;
  if (path === "/" || path.startsWith("/announcements")) return "decisions";
  if (path === "/scheduled") return "scheduled";
  if (path === "/history") return "sent";
  // O panorama antigo (`/v2` sem área, ou Hoje) continua acessível pela URL e
  // pertence ao andar de operação, não aos ajustes.
  if (path === "/v2") {
    const area = String(route.query.area || "today");
    return area === "today" ? "decisions" : "settings";
  }
  return "settings";
});

const activeSettings = computed<SettingsKey>(() => {
  if (route.path === "/templates") return "templates";
  if (route.path === "/platforms") return "platforms";
  if (route.path === "/campaigns") return "campaigns";
  const area = String(route.query.area || "");
  if (area === "offers" || area === "platforms") return area;
  return "campaigns";
});

const sections = computed<OperatorSection[]>(() => [
  {
    key: "decisions",
    label: "Decisões",
    icon: "lucide:inbox",
    to: "/",
    attention: decisionCount.value ? String(decisionCount.value) : undefined,
  },
  {
    key: "scheduled",
    label: "Agendados",
    icon: "lucide:calendar-clock",
    to: "/scheduled",
  },
  {
    key: "sent",
    label: "Enviados",
    icon: "lucide:send",
    to: "/history",
  },
  {
    key: "settings",
    label: "Ajustes",
    icon: "lucide:sliders-horizontal",
    to: "/v2?area=campaigns",
    match: ["/campaigns", "/templates", "/platforms"],
  },
]);

const settingsSections: ReadonlyArray<{
  key: SettingsKey;
  label: string;
  to: string;
}> = [
  { key: "campaigns", label: "Campanhas", to: "/v2?area=campaigns" },
  { key: "templates", label: "Modelos", to: "/templates" },
  { key: "offers", label: "Ofertas e cupons", to: "/v2?area=offers" },
  { key: "platforms", label: "Plataformas", to: "/v2?area=platforms" },
];
</script>

<template>
  <!-- No celular a navegação mora na barra do pé; a do topo fica só com o sino. -->
  <div
    class="max-sm:[&_[data-operator-app-bar]_nav]:hidden"
    data-marketing-top-bar
  >
    <OperatorAppBar
      :sections="sections"
      :current="activeSection"
      label="Seções do Marketing"
    >
      <template #end>
        <MarketingNotificationsBell />
      </template>
    </OperatorAppBar>

    <nav
      v-if="activeSection === 'settings'"
      class="flex gap-1 overflow-x-auto border-b border-border bg-card px-4 py-2"
      aria-label="Seções de Ajustes"
      data-marketing-settings-nav
    >
      <NuxtLink
        v-for="section in settingsSections"
        :key="section.key"
        :to="section.to"
        :aria-current="activeSettings === section.key ? 'page' : undefined"
        class="inline-flex min-h-11 shrink-0 items-center rounded-md px-3 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        :class="
          activeSettings === section.key
            ? 'bg-muted font-semibold text-foreground'
            : 'text-muted-foreground hover:bg-muted hover:text-foreground'
        "
      >
        {{ section.label }}
      </NuxtLink>
    </nav>

    <!-- A barra do polegar: só no celular. As mesmas quatro seções da barra do topo. -->
    <nav
      class="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-border bg-card pb-[env(safe-area-inset-bottom)] sm:hidden print:hidden"
      aria-label="Seções do Marketing no celular"
      data-marketing-bottom-bar
    >
      <NuxtLink
        v-for="section in sections"
        :key="section.key"
        :to="section.to"
        :aria-current="activeSection === section.key ? 'page' : undefined"
        :data-section="section.key"
        class="flex min-h-16 flex-col items-center justify-center gap-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        :class="
          activeSection === section.key
            ? 'font-semibold text-foreground'
            : 'text-muted-foreground'
        "
      >
        <span
          class="relative grid h-8 w-14 place-items-center rounded-full"
          :class="activeSection === section.key ? 'bg-primary/15' : ''"
        >
          <Icon :name="section.icon" class="size-5" aria-hidden="true" />
          <span
            v-if="section.attention"
            class="absolute -right-0.5 -top-1 grid min-w-5 place-items-center rounded-full bg-destructive px-1 text-[11px] font-bold tabular-nums text-white"
            aria-hidden="true"
            >{{ section.attention }}</span
          >
        </span>
        <span>{{ section.label }}</span>
        <span v-if="section.attention" class="sr-only"
          >, {{ section.attention }} esperando você</span
        >
      </NuxtLink>
    </nav>
  </div>
</template>

