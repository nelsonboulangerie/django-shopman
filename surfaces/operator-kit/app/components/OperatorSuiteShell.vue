<script setup lang="ts">
import { activeSectionKey, type OperatorSection } from "../presentation/appBar";
import { PHONE_BAR_SECTIONS, phoneBarLayout, withSectionShortcuts } from "../presentation/suiteChrome";
import { SUITE_HELP_SHORTCUT, SUITE_SECTION_SHORTCUTS } from "../shortcuts/suiteShortcuts";

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
const active = computed(() => props.current ?? activeSectionKey(route.path, props.sections));
const topSections = computed(() => withSectionShortcuts(props.sections.filter((section) => section.where !== "bar" && !section.foot)));
const footSections = computed(() => props.sections.filter((section) => section.where !== "bar" && section.foot));
const phoneSections = computed(() => props.sections.filter((section) => section.where !== "rail"));
const phoneLayout = computed(() => phoneBarLayout(phoneSections.value, props.mobileMax ?? PHONE_BAR_SECTIONS));
const shortcuts = useOperatorShortcuts();

function go(section: OperatorSection) {
  if (section.to) void navigateTo(section.to);
  else emit("select", section.key);
}

useOperatorShortcutMap(
  [...SUITE_SECTION_SHORTCUTS, ...SUITE_HELP_SHORTCUT],
  Object.fromEntries([
    ...SUITE_SECTION_SHORTCUTS.map((command, index) => [command.id, () => {
      const section = topSections.value[index];
      if (section) go(section);
    }]),
    ["suite.shortcuts-help", () => { shortcuts.open.value = true; }],
  ]),
  computed<ReadonlySet<string>>(() => new Set(["ready"])),
);

function itemFor(section: OperatorSection) {
  return {
    label: section.label,
    icon: section.icon,
    to: section.to,
    active: active.value === section.key,
    badge: section.badge || undefined,
    chip: section.attention ? { color: "warning" as const, inset: true } : undefined,
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
      <OperatorAppSeal placement="rail" />
    </template>

    <template #sidebar>
      <NuxtNavigationMenu
        orientation="vertical"
        collapsed
        :items="railItems"
        :aria-label="label"
      />
    </template>

    <template #sidebar-footer>
      <NuxtNavigationMenu
        v-if="footItems.length"
        orientation="vertical"
        collapsed
        :items="footItems"
        :aria-label="`${label}: ajustes`"
      />
      <ClientOnly><OperatorInbox placement="header" /></ClientOnly>
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
        <NuxtButton color="neutral" variant="soft" icon="i-lucide-user" square aria-label="Menu do operador" />
        <template #content>
          <OperatorMenuItems mode="rail" :operator-name="operatorName" @lock="emit('lock')" />
        </template>
      </NuxtPopover>
    </template>

    <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div class="min-h-0 flex-1 overflow-y-auto">
        <slot />
      </div>

      <NuxtDashboardToolbar
        as="nav"
        class="lg:hidden print:hidden"
        :aria-label="label"
        data-operator-suite-tabs
        data-focus-obstruction
      >
        <NuxtNavigationMenu :items="tabItems" />
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
  <OperatorShortcutsHelp :sections="topSections" :app-label="label.replace(/^Seções d[oa] /, '')" />
</template>
