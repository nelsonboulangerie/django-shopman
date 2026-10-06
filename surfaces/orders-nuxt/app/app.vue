<script setup lang="ts">
// Gestor de Pedidos — casca canônica (DashboardGroup/Sidebar/Panel) com o rail da
// suíte: DashboardSidebar (4rem oficiais, sem resize/colapso) + NavigationMenu
// (collapsed labels + chip). No celular/tablet em pé a navegação é a bottom tab
// bar do NavigationMenu. O conteúdo/estado do board segue na página.
import { useRuntimeConfig, useRoute } from "#imports";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { operatorAlertToInbox, withSectionShortcuts } from "../../operator-kit/app/presentation/suiteChrome";
import {
  activeSectionKey,
  type OperatorSection,
} from "../../operator-kit/app/presentation/appBar";
import { SUITE_HELP_SHORTCUT, SUITE_SECTION_SHORTCUTS } from "../../operator-kit/app/shortcuts/suiteShortcuts";

const OPERATOR_PERM = "shop.manage_orders|backstage.operate_kds";
const { hasDirty: cashDraftDirty } = useOrderCashDrafts();
const { hasPending: intentionPending } = useOrderIntention();
function protectSessionExit(event: BeforeUnloadEvent) {
  if (!cashDraftDirty.value && !intentionPending.value) return;
  event.preventDefault();
  event.returnValue = "";
}
onMounted(() => window.addEventListener("beforeunload", protectSessionExit));
onBeforeUnmount(() => window.removeEventListener("beforeunload", protectSessionExit));

const { canIdentify, sessionUnavailable, refresh, locked, mustChange, operator, lock, stationRef } =
  useOperatorLock(OPERATOR_PERM);
const stationSetup = useStationSetupOffer({ canIdentify, locked, stationRef });

const workspaceOwner = ref(operator.value?.id ?? null);
watch(() => operator.value?.id, (id) => { if (id != null) workspaceOwner.value = id; });
const station = useStationLock();
async function restoreAuthenticatedWorkspace() {
  station.clear();
  await refreshNuxtData();
}

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;
const { attrsFor } = useOperatorAppLink();
const hubLink = computed(() => attrsFor(hubUrl || ""));

// Identidade do app (selo no topo do rail).
interface SuiteIdentity { label: string; icon: string; iconSrc: string; color: string }
const identity = (useRuntimeConfig().public?.operatorPwa as { identity?: SuiteIdentity } | undefined)?.identity;
const appLabel = computed(() => identity?.label || "");
const appColor = computed(() => identity?.color || "var(--primary)");
const appIconName = computed(() => {
  const icon = identity?.icon || "layout-grid";
  return icon.includes(":") ? icon : `lucide:${icon}`;
});
const appIconBroken = ref(false);
const showAppImage = computed(() => Boolean(identity?.iconSrc) && !appIconBroken.value);
const HUB_BACK_INLINE = `voltar ${appLabel.value.toLowerCase()}`;

// Seções do Gestor → itens do NavigationMenu.
const { sections, current } = useGestorSections();
const route = useRoute();
const active = computed(() => current.value ?? activeSectionKey(route.path, sections.value));
const railSections = computed(() => sections.value.filter((section) => section.where !== "bar"));
const topSections = computed(() => withSectionShortcuts(railSections.value.filter((section) => !section.foot)));
const footSections = computed(() => railSections.value.filter((section) => section.foot));

function chipFor(section: OperatorSection) {
  if (section.badge) return { text: section.badge, color: section.attention ? ("warning" as const) : ("neutral" as const) };
  if (section.attention) return { color: "warning" as const };
  return undefined;
}
function toItem(section: OperatorSection) {
  return {
    label: section.label,
    icon: section.icon,
    to: section.to,
    active: active.value === section.key,
    chip: chipFor(section),
  };
}
const railItems = computed(() => {
  const items: Array<Record<string, unknown>> = [{ label: "Operação", type: "label" }];
  for (const section of topSections.value) items.push(toItem(section));
  if (footSections.value.length) {
    items.push({ type: "separator" });
    for (const section of footSections.value) items.push(toItem(section));
  }
  return items;
});
const barItems = computed(() => [...topSections.value, ...footSections.value].map(toItem));
const railNavUi = {
  root: "w-full flex-col items-stretch gap-0.5",
  item: "w-full",
  link: "flex-col gap-0.5 px-1 py-1.5 justify-center text-center",
  linkLeadingIcon: "size-5",
  linkLabel: "block text-[10px]/3 font-normal",
} as const;
const barNavUi = {
  root: "justify-around border-t border-default py-2",
  item: "py-0",
  link: "flex-col gap-1 px-3",
  linkLeadingIcon: "size-5",
  linkLabel: "text-[10px]/3 font-normal",
} as const;

// Avisos: uma caixa única (alertas de pedido + pessoal) no pé do rail.
const { alerts, activeCount, ack } = useAlerts();
provideOperatorInboxAlerts(() => ({
  title: "Da operação",
  emptyText: "Nenhum alerta de pedido agora.",
  items: alerts.value.map(operatorAlertToInbox),
  count: activeCount.value,
  ack: (key) => {
    const alert = alerts.value.find((item) => item.pk === key);
    if (alert) return ack(alert);
  },
}));
const railShown = useSuiteRailShown();
const shortcuts = useOperatorShortcuts();
const shortcutContexts = computed<ReadonlySet<string>>(() => new Set(["ready"]));
useOperatorShortcutMap(
  [...SUITE_SECTION_SHORTCUTS, ...SUITE_HELP_SHORTCUT],
  Object.fromEntries([
    ...SUITE_SECTION_SHORTCUTS.map((command, index) => [command.id, () => {
      const section = topSections.value[index];
      if (section?.to) void navigateTo(section.to);
    }]),
    ["suite.shortcuts-help", () => { shortcuts.open.value = true; }],
  ]),
  shortcutContexts,
);

const initials = computed(() => {
  const words = (operator.value?.name || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  const first = words[0]!.charAt(0);
  const last = words.length > 1 ? words[words.length - 1]!.charAt(0) : words[0]!.charAt(1);
  return `${first}${last}`.toUpperCase();
});

useOperatorWindowTitle();
</script>

<template>
  <div class="bg-background text-foreground" data-suite="v3">
    <NuxtRouteAnnouncer />
    <OfflineBanner />

    <OperatorOfficeShell v-if="canIdentify" storage-key="gestor" rail :navbar="false">
      <template #sidebar-header>
        <component
          :is="hubUrl ? 'a' : 'div'"
          :href="hubUrl"
          :target="hubUrl ? hubLink.target : undefined"
          :rel="hubUrl ? hubLink.rel : undefined"
          :aria-label="hubUrl ? `${appLabel}: ${HUB_BACK_INLINE}` : appLabel"
          :title="hubUrl ? `${appLabel}: ${HUB_BACK_INLINE}` : appLabel"
          class="relative grid size-11 shrink-0 place-items-center rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rail-foreground"
          :style="{ background: appColor }"
          data-suite-rail-app
        >
          <img v-if="showAppImage" :src="identity?.iconSrc" class="size-8 rounded-md" alt="" decoding="async" @error="appIconBroken = true">
          <Icon v-else :name="appIconName" class="size-5 text-white" aria-hidden="true" />
          <span v-if="hubUrl" class="absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full bg-rail-foreground shadow" aria-hidden="true">
            <Icon name="lucide:layout-grid" class="size-2.5 text-rail" />
          </span>
        </component>
      </template>

      <template #sidebar>
        <NuxtNavigationMenu
          orientation="vertical"
          collapsed
          :items="railItems"
          :ui="railNavUi"
          aria-label="Seções do Gestor"
          class="w-full"
        />
      </template>

      <template #sidebar-footer>
        <ClientOnly>
          <OperatorInbox v-if="railShown" placement="rail" />
        </ClientOnly>
        <div class="hidden pointer-fine:block">
          <NuxtButton icon="i-lucide-keyboard" color="neutral" variant="ghost" square aria-label="Atalhos do teclado" title="Atalhos do teclado" @click="shortcuts.open.value = true" />
        </div>
        <NuxtButton v-if="operator" icon="i-lucide-lock" color="neutral" variant="ghost" square :aria-label="`${operator.name}: travar ou trocar`" title="Bloquear" @click="lock()" />
        <NuxtPopover v-if="operator">
          <NuxtButton
            color="neutral"
            variant="soft"
            square
            :aria-label="`Menu de ${operator.name}`"
            class="rounded-full"
          >
            <span v-if="initials" class="text-[13px] font-semibold" aria-hidden="true">{{ initials }}</span>
            <Icon v-else name="lucide:settings-2" class="size-5" aria-hidden="true" />
          </NuxtButton>
          <template #content>
            <OperatorMenuItems mode="rail" :operator-name="operator.name" />
          </template>
        </NuxtPopover>
      </template>

      <div v-show="!locked && !mustChange" class="flex min-h-0 flex-1 flex-col">
        <NuxtPage :key="workspaceOwner ?? 'unidentified'" />
      </div>
    </OperatorOfficeShell>

    <!-- Bottom tab bar canônica (<lg): NavigationMenu com o ui oficial. -->
    <nav v-if="canIdentify && !locked && !mustChange" class="fixed inset-x-0 bottom-0 z-40 border-t border-default bg-card lg:hidden print:hidden">
      <NuxtNavigationMenu :items="barItems" :ui="barNavUi" aria-label="Seções do Gestor" class="w-full" />
    </nav>

    <OperatorSessionUnavailable v-if="sessionUnavailable" scope="os pedidos" @retry="refresh()" />
    <OperatorLogin v-if="!canIdentify && !sessionUnavailable" :reload-on-success="false" @success="restoreAuthenticatedWorkspace" />
    <OperatorLock v-else-if="locked || mustChange" :perm="OPERATOR_PERM" />
    <OperatorStationSetup
      v-if="stationSetup.offer.value"
      @done="stationSetup.done()"
      @dismiss="stationSetup.dismiss()"
      @unavailable="stationSetup.dismiss({ remember: false })"
    />
    <OperatorShortcutsHelp :sections="topSections" :app-label="appLabel" />
    <OperatorSonner />
    <OperatorPwaRuntime />
  </div>
</template>
