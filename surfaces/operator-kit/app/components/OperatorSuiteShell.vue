<script setup lang="ts">
import { activeSectionKey, type OperatorSection } from "../presentation/appBar";
import {
  PHONE_BAR_SECTIONS,
  phoneBarLayout,
  withSectionShortcuts,
} from "../presentation/suiteChrome";
import {
  SUITE_HELP_SHORTCUT,
  SUITE_SECTION_SHORTCUTS,
} from "../shortcuts/suiteShortcuts";

const props = defineProps<{
  storageKey: string;
  sections: readonly OperatorSection[];
  label: string;
  current?: string;
  operatorName?: string;
  mobileMax?: number;
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
const phoneSections = computed(() =>
  props.sections.filter((section) => section.where !== "rail"),
);
const phoneLayout = computed(() =>
  phoneBarLayout(phoneSections.value, props.mobileMax ?? PHONE_BAR_SECTIONS),
);
const shortcuts = useOperatorShortcuts();

function go(section: OperatorSection) {
  if (section.to) void navigateTo(section.to);
  else emit("select", section.key);
}

useOperatorShortcutMap(
  [...SUITE_SECTION_SHORTCUTS, ...SUITE_HELP_SHORTCUT],
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
  ]),
  computed<ReadonlySet<string>>(() => new Set(["ready"])),
);

function itemFor(section: OperatorSection) {
  return {
    label: section.label,
    icon: section.icon,
    to: section.to,
    active: active.value === section.key,
    // A contagem mora no Chip do ícone, não num Badge ao lado do rótulo: o rail
    // recolhido não desenha Badge, e na barra do celular o Badge tirava a largura
    // do rótulo. Chip numérico 4xl; sem número, o indicativo 2xl de atenção.
    chip: section.badge
      ? { color: "warning" as const, text: section.badge, size: "4xl" as const, inset: true }
      : section.attention
        ? { color: "warning" as const, size: "2xl" as const, inset: true }
        : undefined,
    "aria-label": [section.label, section.badgeLabel, section.attention]
      .filter(Boolean)
      .join(", "),
    tooltip: { text: section.label },
    onSelect: section.to ? undefined : () => emit("select", section.key),
  };
}

const railItems = computed(() => topSections.value.map(itemFor));
const footItems = computed(() => footSections.value.map(itemFor));
const tabItems = computed(() => phoneLayout.value.visible.map(itemFor));
</script>

<template>
  <OperatorOfficeShell :storage-key="storageKey" rail :navbar="false">
    <template #sidebar-header>
      <div class="flex w-full justify-center">
        <OperatorAppSeal placement="rail" />
      </div>
    </template>

    <template #sidebar>
      <!-- O corpo canônico do DashboardSidebar rola no eixo vertical. Um menu
           com largura intrínseca alguns pixels maior fazia esse mesmo corpo criar
           também um scrollbar horizontal no rodapé do rail. O contêiner limita o
           filho à largura disponível sem alterar a geometria dos controles. -->
      <div
        class="flex w-full min-w-0 justify-center overflow-x-hidden"
        data-suite-rail-navigation
      >
        <NuxtNavigationMenu
          class="min-w-0"
          orientation="vertical"
          collapsed
          :items="railItems"
          :aria-label="label"
        />
      </div>
    </template>

    <template #sidebar-footer>
      <!-- DashboardSidebar compõe o footer como uma linha. O rail compacto precisa
           oferecer a ele UM filho, que organiza seus controles no eixo vertical;
           irmãos soltos aqui vazam horizontalmente para dentro da página. -->
      <div
        class="flex w-full min-w-0 flex-col items-center gap-1.5"
        data-suite-rail-footer
      >
        <NuxtNavigationMenu
          v-if="footItems.length"
          class="w-fit"
          orientation="vertical"
          collapsed
          :items="footItems"
          :aria-label="`${label}: ajustes`"
        />
        <ClientOnly><OperatorInbox placement="rail" /></ClientOnly>
        <NuxtButton
          class="hidden pointer-fine:inline-flex"
          icon="i-lucide-keyboard"
          color="neutral"
          variant="ghost"
          square
          aria-label="Atalhos do teclado"
          @click="shortcuts.open.value = true"
        />
        <NuxtButton
          v-if="operatorName"
          icon="i-lucide-lock"
          color="neutral"
          variant="ghost"
          square
          aria-label="Bloquear ou trocar de operador"
          @click="emit('lock')"
        />
        <NuxtPopover v-if="operatorName">
          <NuxtButton
            color="neutral"
            variant="soft"
            icon="i-lucide-user"
            square
            aria-label="Menu do operador"
          />
          <template #content>
            <OperatorMenuItems
              mode="rail"
              :operator-name="operatorName"
              @lock="emit('lock')"
            />
          </template>
        </NuxtPopover>
      </div>
    </template>

    <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
      <!-- Each routed page exposes a fixed header and an explicitly scrollable
           content region. Keeping another scroller here made the canonical
           DashboardNavbar and DashboardToolbar move with the page. -->
      <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
        <slot />
      </div>

      <NuxtDashboardToolbar
        as="nav"
        class="border-t border-default border-b-0 lg:hidden print:hidden pb-[env(safe-area-inset-bottom)]"
        :aria-label="label"
        data-operator-suite-tabs
        data-focus-obstruction
      >
        <NuxtNavigationMenu class="min-w-0 flex-1" :items="tabItems" />
        <OperatorPhoneMenu
          variant="bar"
          :operator-name="operatorName"
          :overflow="phoneLayout.overflow"
          :current="active"
          @lock="emit('lock')"
          @select="emit('select', $event)"
        >
          <template v-if="$slots.more" #extra><slot name="more" /></template>
        </OperatorPhoneMenu>
      </NuxtDashboardToolbar>
    </div>
  </OperatorOfficeShell>
  <OperatorShortcutsHelp
    :sections="topSections"
    :app-label="label.replace(/^Seções d[oa] /, '')"
  />
</template>
