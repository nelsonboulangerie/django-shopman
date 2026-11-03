<script setup lang="ts">
// O shell da suíte (Gestor): o rail dourado em três estados, montado SÓ com peças do
// Nuxt UI (dono, 08/10/2026, PR #1539; referência `pages/proposal/rail.vue` do Kitchen
// Sink): `NuxtDashboardGroup`, `NuxtDashboardSidebar` e `NuxtNavigationMenu`
// vertical. Nenhum `:ui` por instância: o dourado mora no `ui.dashboardSidebar` do
// `app.config` do kit.
//
// Os três estados no desktop:
//   aberto   = `collapsed=false` (ícone e nome; redimensionável de 12 a 20 rem, a
//              largura gravada pelo DashboardGroup);
//   compacto = `collapsed=true` (só ícone; o nome vira tooltip);
//   oculto   = o sidebar não é montado (um cookie do kit, `<storage-key>-rail-hidden`).
// UM botão na barra do topo (`OperatorPageHeader`, via `useSuiteRail`) e a tecla C
// percorrem aberto → compacto → oculto → aberto; o ícone e o nome dizem o PRÓXIMO
// estado. Arrastar alterna aberto e compacto (canônico); ocultar não é por arrasto.
// Abaixo de `lg`, o comportamento oficial: a barra lateral abre como slideover (a
// gaveta, o menu COMPLETO) pelo ☰ da barra do topo, e a barra inferior
// (`OperatorQuickBar`) é o menu RÁPIDO, de 3 a 5 vagas, com "Mais" só quando sobra
// seção (dono, 08/10/2026, PR #1544).
//
// Sinais: o ponto de estado ou o número de cada seção (`sectionRailSignal`). Compacto,
// o chip vai no canto do ícone (`chip` do item); aberto, o MESMO chip vai na ponta
// direita da linha (slot `item-trailing`). Tooltip e nome acessível: "Seção · estado"
// ou "Seção · N pendências" (`sectionDescription`, a mesma da barra inferior). Na tela
// a peça se chama "barra lateral"; `rail` é só o nome no código.
import type { ChipProps } from "@nuxt/ui";
import { useScreen } from "../composables/useScreen";

import { activeSectionKey, type OperatorSection } from "../presentation/appBar";
import {
  SUITE_RAIL_NEXT,
  nextSuiteRailState,
  railSignalChip,
  sectionDescription,
  sectionRailSignal,
  withSectionShortcuts,
  type RailSignal,
  type SuiteRailState,
} from "../presentation/suiteChrome";
import {
  SUITE_HELP_SHORTCUT,
  SUITE_RAIL_SHORTCUT,
  SUITE_SECTION_SHORTCUTS,
} from "../shortcuts/suiteShortcuts";

interface SuiteShellIdentity { label?: string }

const props = defineProps<{
  storageKey: string;
  sections: readonly OperatorSection[];
  label: string;
  current?: string;
  operatorName?: string;
  /**
   * Variante "início": o shell da própria Central. O selo do topo da barra lateral (e
   * da gaveta) é só identidade, sem "voltar à Central" apontando para ela mesma.
   */
  home?: boolean;
  /**
   * Liga o trocador (modelo de navegação, 31/10/2026): todas as seções do app, com a
   * forma de cada uma. Sem ele, o shell segue com ☰ e a barra de baixo de sempre.
   */
  switcherSections?: readonly OperatorSection[];
  /** A forma de uma tela que não é seção (o item aberto). Só com o trocador. */
  defaultForm?: "floor" | "office" | "wall";
}>();

const emit = defineEmits<{ lock: []; select: [key: string] }>();
const route = useRoute();
const active = computed(
  () => props.current ?? activeSectionKey(route.path, props.sections),
);
const topSections = computed(() =>
  withSectionShortcuts(
    props.sections.filter(
      (section) => section.where !== "bar" && !section.foot,
    ),
  ),
);
const footSections = computed(() =>
  props.sections.filter((section) => section.where !== "bar" && section.foot),
);
// A barra inferior do celular: a regra única do kit (`quickBarLayout`), sobre as
// seções que não são só da barra lateral.
const quickSections = computed(() =>
  props.sections.filter((section) => section.where !== "rail"),
);
// Com o trocador, a forma da tela decide a barra de baixo. Chão: nenhuma (o posto define o
// lugar; trocar é pelo selo). Escritório: as seções do escritório, "Mais" abre o trocador.
// Escrito já no setup (o servidor não roda `watchEffect`): o cabeçalho, filho do shell,
// tem de desenhar o mesmo selo no servidor e na hidratação.
const switcherEnabled = useState<boolean>("suite-switcher-enabled", () => false);
const wantsSwitcher = () => Boolean(props.switcherSections) && !props.home;
switcherEnabled.value = wantsSwitcher();
watch(wantsSwitcher, (enabled) => {
  switcherEnabled.value = enabled;
});
const pool = computed(() => props.switcherSections ?? props.sections);
function exactKey(path: string): string | undefined {
  const clean = (path || "/").split("?")[0]!.replace(/(.)\/$/, "$1");
  let best: { key: string; len: number } | undefined;
  for (const section of pool.value) {
    for (const cand of [section.to, ...(section.match || [])]) {
      if (!cand) continue;
      const c = cand.split("?")[0]!.replace(/(.)\/$/, "$1");
      const hit = c === "/" ? clean === "/" : clean === c || clean.startsWith(c + "/");
      if (hit && (!best || c.length > best.len)) best = { key: section.key, len: c.length };
    }
  }
  return best?.key;
}
const switcherCurrent = computed(() => props.current ?? exactKey(route.path));
const form = computed(
  () => pool.value.find((s) => s.key === switcherCurrent.value)?.form ?? props.defaultForm ?? "office",
);
const switcherOpen = useState<boolean>("suite-switcher-open", () => false);
const officeQuick = computed(() =>
  (props.switcherSections ?? [])
    .filter((s) => (s.form ?? "office") === "office")
    .map((s) => ({ ...s, quick: undefined })),
);
// A gaveta (abaixo de lg, o DashboardSidebar abre como slideover): o ☰ da barra do
// topo e o "Mais" da barra inferior a abrem.
const drawerOpen = ref(false);
const shortcuts = useOperatorShortcuts();
const appLabel = (
  useRuntimeConfig().public?.operatorPwa as
    | { identity?: SuiteShellIdentity }
    | undefined
)?.identity?.label;

// O rail de três estados. Aberto e compacto são do DashboardSidebar (cookie do
// DashboardGroup, `{ size, collapsed }`); oculto não existe no Nuxt UI para o desktop:
// é o sidebar não montado, guardado num cookie do kit.
// A régua da suíte (`useScreen`): mesa até a hidratação terminar, a largura real depois.
const screen = useScreen();
const isDesktop = computed(() => !screen.belowLg.value);
const collapsed = ref(false);
const hidden = useCookie<boolean>(`${props.storageKey}-rail-hidden`, {
  default: () => false,
  sameSite: "lax",
  maxAge: 60 * 60 * 24 * 365,
  path: "/",
});
const railState = computed<SuiteRailState>(() =>
  hidden.value ? "hidden" : collapsed.value ? "compact" : "open",
);
function setRail(target: SuiteRailState) {
  hidden.value = target === "hidden";
  if (target !== "hidden") collapsed.value = target === "compact";
}
async function cycleRail() {
  const target = nextSuiteRailState(railState.value);
  setRail(target);
  // Ao voltar do oculto, o DashboardSidebar remonta e relê o cookie (compacto): o
  // aberto é reafirmado depois da montagem.
  if (target === "open") {
    await nextTick();
    collapsed.value = false;
  }
}
provideSuiteRail({
  state: railState,
  visible: computed(() => isDesktop.value && !hidden.value),
  next: computed(() => SUITE_RAIL_NEXT[railState.value]),
  cycle: cycleRail,
});

function go(section: OperatorSection) {
  if (section.to) void navigateTo(section.to);
  else emit("select", section.key);
}

useOperatorShortcutMap(
  [...SUITE_SECTION_SHORTCUTS, ...SUITE_HELP_SHORTCUT, ...SUITE_RAIL_SHORTCUT],
  Object.fromEntries([
    ...SUITE_SECTION_SHORTCUTS.map((command, index) => [
      command.id,
      () => {
        const section = topSections.value[index];
        if (section) go(section);
      },
    ]),
    [
      "suite.shortcuts-help",
      () => {
        shortcuts.open.value = true;
      },
    ],
    [
      "suite.rail.cycle",
      () => {
        // Os três estados são do desktop; abaixo de lg o rail é o slideover oficial.
        if (isDesktop.value) void cycleRail();
      },
    ],
  ]),
  computed<ReadonlySet<string>>(() => new Set(["ready"])),
);

/** Uma seção no rail: item do NavigationMenu com o sinal dela. Compacto, o chip vai no
 *  canto do ícone; aberto, o slot `item-trailing` desenha o mesmo chip no fim da linha. */
function railItemFor(section: OperatorSection, isCollapsed: boolean) {
  const signal = sectionRailSignal(section);
  const description = sectionDescription(section);
  return {
    label: section.label,
    icon: section.icon,
    to: section.to,
    active: active.value === section.key,
    signal,
    chip: isCollapsed && signal ? railSignalChip(signal) : undefined,
    tooltip: { text: description },
    "aria-label": description,
    "data-section": section.key,
    onSelect: section.to ? undefined : () => emit("select", section.key),
  };
}

function railItems(isCollapsed: boolean) {
  return topSections.value.map((section) => railItemFor(section, isCollapsed));
}

/** O pé: as seções do pé do app, Atalhos (só com ponteiro fino) e Bloquear. */
function footItems(isCollapsed: boolean) {
  return [
    ...footSections.value.map((section) => railItemFor(section, isCollapsed)),
    {
      label: "Atalhos",
      icon: "i-lucide-keyboard",
      class: "hidden pointer-fine:flex",
      tooltip: { text: "Atalhos do teclado" },
      "aria-label": "Atalhos do teclado",
      "data-rail-shortcuts": "",
      onSelect: () => {
        shortcuts.open.value = true;
      },
    },
    ...(props.operatorName
      ? [
          {
            label: "Bloquear",
            icon: "i-lucide-lock",
            tooltip: { text: "Bloquear ou trocar de operador" },
            "aria-label": "Bloquear ou trocar de operador",
            "data-rail-lock": "",
            onSelect: () => emit("lock"),
          },
        ]
      : []),
  ];
}

function signalOf(item: unknown): RailSignal | undefined {
  return (item as { signal?: RailSignal }).signal;
}

/** O ponto da barra aberta tem o tamanho do chip do NavigationMenu (`linkLeadingChipSize`). */
function menuDotSize(size: string): ChipProps["size"] {
  return size as ChipProps["size"];
}


</script>

<template>
  <!-- A faixa "Sem conexão" (`OfflineBanner`) desce o shell pelo `top`; o sidebar e o
       painel trocam o `min-h-svh` do Nuxt UI por `min-h-0` para caber no que sobra
       (senão a barra inferior e o pé da barra lateral saem pela base). -->
  <NuxtDashboardGroup
    :storage-key="storageKey"
    unit="rem"
    class="top-[var(--operator-offline-inset,0px)] transition-[top] duration-200 ease-out motion-reduce:transition-none"
    data-operator-office-shell
    data-operator-suite-shell
    :data-rail-state="railState"
  >
    <NuxtDashboardSidebar
      v-if="!(hidden && isDesktop)"
      id="suite"
      v-model:collapsed="collapsed"
      v-model:open="drawerOpen"
      class="min-h-0"
      collapsible
      resizable
      :collapsed-size="4"
      :default-size="14"
      :min-size="12"
      :max-size="20"
      role="complementary"
      aria-label="Navegação do aplicativo"
      data-suite-rail
    >
      <template #header="{ collapsed: isCollapsed }">
        <div
          class="flex w-full items-center gap-2"
          :class="isCollapsed ? 'justify-center' : ''"
        >
          <OperatorAppSeal placement="rail" :home="home" />
          <span v-if="!isCollapsed && appLabel" class="font-semibold">{{
            appLabel
          }}</span>
        </div>
      </template>

      <template #default="{ collapsed: isCollapsed }">
        <NuxtNavigationMenu
          :collapsed="isCollapsed"
          :items="railItems(isCollapsed)"
          orientation="vertical"
          tooltip
          popover
          :aria-label="label"
          data-suite-rail-navigation
        >
          <!-- Aberto: o chip de contagem da suíte na ponta direita da linha, no centro
               vertical (`OperatorCountChip`). O ponto tem o tamanho do chip do
               NavigationMenu. -->
          <template #item-trailing="{ item, ui }">
            <OperatorCountChip
              v-if="!isCollapsed && signalOf(item)"
              :count="signalOf(item)!.count"
              :color="signalOf(item)!.color"
              :dot="signalOf(item)!.count === undefined"
              :dot-size="menuDotSize(ui.linkLeadingChipSize())"
            />
          </template>
        </NuxtNavigationMenu>
      </template>

      <template #footer="{ collapsed: isCollapsed }">
        <!-- DashboardSidebar compõe o footer como uma linha: UM filho, que organiza o
             pé no eixo vertical; irmãos soltos aqui vazam para dentro da página. -->
        <div class="flex w-full min-w-0 flex-col gap-1.5" data-suite-rail-footer>
          <NuxtNavigationMenu
            :collapsed="isCollapsed"
            :items="footItems(isCollapsed)"
            orientation="vertical"
            tooltip
            :aria-label="`${label}: pé`"
          >
            <template #item-trailing="{ item, ui }">
              <OperatorCountChip
                v-if="!isCollapsed && signalOf(item)"
                :count="signalOf(item)!.count"
                :color="signalOf(item)!.color"
                :dot="signalOf(item)!.count === undefined"
                :dot-size="menuDotSize(ui.linkLeadingChipSize())"
              />
            </template>
          </NuxtNavigationMenu>
          <div
            class="flex gap-1.5"
            :class="isCollapsed ? 'flex-col items-center' : 'flex-row items-center'"
          >
            <ClientOnly><OperatorInbox placement="rail" /></ClientOnly>
            <NuxtPopover v-if="operatorName" :content="{ side: 'right', align: 'end' }">
              <NuxtButton
                color="neutral"
                variant="soft"
                icon="i-lucide-user"
                :label="isCollapsed ? undefined : operatorName"
                :square="isCollapsed"
                aria-label="Menu do operador"
                data-suite-rail-menu
              />
              <template #content>
                <OperatorMenuItems
                  mode="rail"
                  :operator-name="operatorName"
                  @lock="emit('lock')"
                  @hide="setRail('hidden')"
                />
              </template>
            </NuxtPopover>
          </div>
        </div>
      </template>
    </NuxtDashboardSidebar>

    <!-- The DashboardPanel default slot intentionally replaces its padded,
         scrollable body. Each routed page exposes a fixed header and an explicitly
         scrollable content region; another scroller here made the canonical
         DashboardNavbar and DashboardToolbar move with the page. -->
    <NuxtDashboardPanel :id="`${storageKey}-content`" class="min-h-0" data-operator-content-panel>
      <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
        <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
          <slot />
        </div>

        <OperatorQuickBar
          v-if="switcherEnabled && form === 'office'"
          :sections="officeQuick"
          :current="switcherCurrent"
          :label="label"
          @select="emit('select', $event)"
          @more="switcherOpen = true"
        />
        <OperatorQuickBar
          v-else-if="!switcherEnabled"
          :sections="quickSections"
          :current="active"
          :label="label"
          @select="emit('select', $event)"
          @more="drawerOpen = true"
        />
      </div>
    </NuxtDashboardPanel>
  </NuxtDashboardGroup>
  <!-- Aviso com prazo correndo: interrompe a tela até alguém ver (dono, 07/10). -->
  <ClientOnly><OperatorUrgentAlert /></ClientOnly>
  <ClientOnly><OperatorSwitcher v-if="switcherEnabled" :sections="pool" :current="switcherCurrent" :operator-name="operatorName" @lock="emit('lock')" @select="emit('select', $event)" /></ClientOnly>
  <OperatorShortcutsHelp
    :sections="topSections"
    :app-label="label.replace(/^Seções d[oa] /, '')"
    rail
  />
</template>
