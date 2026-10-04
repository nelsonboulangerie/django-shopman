<script setup lang="ts">
// Rail da suíte (UX-KIT-V1): o rail das prévias v3/v4, com as SEÇÕES do app dentro dele.
//
// O `OperatorRail` clássico segura só o comum e deixa as seções numa barra no topo do
// conteúdo (`OperatorAppBar`). As prévias aprovadas (SUITE-UX §12, "a camada visual da
// v3: tokens, rail, cabeçalho, busca") tiram essa barra: as seções sobem para o rail
// (ícone + nome + contagem + ponto de atenção), e o topo do conteúdo fica com UMA linha
// (título, ao vivo, busca, controles: `OperatorPageHeader`). Medidas de `_rail3top.html`,
// `_rail3bottom.html` e `.rail-item` em `_shared.css`.
//
// Opt-in: o app que migra troca `OperatorRail` + barra de seções por este rail (e a
// `OperatorSectionBar` no celular). Quem não migrou não muda nada.
//
// Do celular para cima:
//   - abaixo de `md` o rail não aparece: o celular usa a barra de 56px do
//     `OperatorPageHeader` em cima e a `OperatorSectionBar` (polegar) embaixo;
//   - de `md` para cima (tablet em pé, tablet deitado, desktop) o rail tem 76px.
//
// Nada do rail clássico se perde: voltar à Central (o selo do app), capacidade do
// serviço, posto do dispositivo, operador/travar, tema e trava de giro. Os três últimos
// moram no menu do operador (as iniciais no pé), como nas prévias; "Ocultar a barra"
// também, e quem traz a barra de volta é o botão que o cabeçalho mostra quando ela some.
import { computed, ref } from "vue";
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";

import { operatorAppNamed } from "../../appIdentity";
import { activeSectionKey, type OperatorSection } from "../presentation/appBar";
import { workstationKindIcon } from "../presentation/workstation";
import type { OperatorSession } from "../types/operator";

const HUB_BACK = `Voltar ${operatorAppNamed("hub", "a")}`;
/** "Gestor de pedidos: voltar à Central" (o verbo minúsculo depois dos dois-pontos). */
const HUB_BACK_INLINE = `${HUB_BACK.charAt(0).toLowerCase()}${HUB_BACK.slice(1)}`;

interface SuiteRailIdentity { label: string; icon: string; iconSrc: string; color: string }

const props = withDefaults(defineProps<{
  /** Seções do app (as mesmas que iam para a barra do topo). */
  sections: readonly OperatorSection[];
  /** Nome da navegação para leitor de tela ("Seções do Gestor"). */
  label: string;
  /** URL da Central. Omitida (na própria Central) → o selo é só identidade. */
  hubUrl?: string;
  /** Operador ativo: mostra Bloquear e o menu do operador. */
  operatorName?: string;
  /** Seção ativa. Omitida, sai da rota. */
  current?: string;
  /** Imprime a tecla de cada seção sob o nome, com ponteiro fino (v4 da Produção: "Alt1"). */
  printShortcuts?: boolean;
  /** Rótulos de 10px para nomes longos (v4 da Produção: "Planejamento", "Preparação"). */
  denseLabels?: boolean;
  /**
   * Mostra Bloquear quando há operador (padrão). `false`: o app não trava operador (a
   * Central, que é a porta de entrada; cada app trava o seu), e as iniciais seguem no pé.
   */
  lockable?: boolean;
}>(), {
  hubUrl: undefined,
  operatorName: undefined,
  current: undefined,
  printShortcuts: false,
  denseLabels: false,
  lockable: true,
});

const emit = defineEmits<{ lock: []; select: [key: string] }>();

const identity = (useRuntimeConfig().public?.operatorPwa as { identity?: SuiteRailIdentity } | undefined)?.identity;
const appLabel = computed(() => identity?.label || "");
const appColor = computed(() => identity?.color || "var(--primary)");
const appIconName = computed(() => {
  const icon = identity?.icon || "layout-grid";
  return icon.includes(":") ? icon : `lucide:${icon}`;
});
const appIconBroken = ref(false);
const showAppImage = computed(() => Boolean(identity?.iconSrc) && !appIconBroken.value);

const route = useRoute();
const active = computed(() => props.current ?? activeSectionKey(route.path, props.sections));
// v4: a operação em cima (com o rótulo do grupo); Ajustes no pé, longe da fila.
const topSections = computed(() => props.sections.filter((section) => !section.foot));
const footSections = computed(() => props.sections.filter((section) => section.foot));
function groupStarts(index: number): string {
  const group = topSections.value[index]?.group;
  return group && topSections.value[index - 1]?.group !== group ? group : "";
}

const { attrsFor } = useOperatorAppLink();
const hubLink = computed(() => attrsFor(props.hubUrl || ""));

const { data: operatorSession } = useNuxtData<OperatorSession>("operator-session");
const workstationContext = computed(() => operatorSession.value?.workstation?.context_label ?? "");
const workstationIcon = computed(() => workstationKindIcon(operatorSession.value?.workstation?.kind ?? ""));

const { isCollapsed, set: setRail } = useRailState();

const initials = computed(() => {
  const words = (props.operatorName || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  const first = words[0]!.charAt(0);
  const last = words.length > 1 ? words[words.length - 1]!.charAt(0) : words[0]!.charAt(1);
  return `${first}${last}`.toUpperCase();
});

const colorMode = useColorMode();
const themeLabel = computed(() => (colorMode.value === "dark" ? "Tema claro" : "Tema escuro"));
function toggleTheme() {
  colorMode.preference = colorMode.value === "dark" ? "light" : "dark";
}

const orientation = useOrientationLock();
const orientationLabel = computed(() => (orientation.isLocked.value ? "Liberar giro" : "Travar giro"));
const { run: toggleOrientation, pending: orientationPending } = usePendingAction(async () => {
  const result = await orientation.toggle();
  if (result.ok) useSonner.success(result.message);
  else useSonner.warning(result.message);
});

const menuOpen = ref(false);
function hideRail() {
  menuOpen.value = false;
  setRail("collapsed");
}
</script>

<template>
  <aside
    v-if="!isCollapsed"
    class="sticky top-0 hidden h-dvh w-[76px] shrink-0 flex-col items-center gap-1 overflow-y-auto bg-rail pb-2 text-rail-foreground no-scrollbar md:flex print:hidden"
    :aria-label="`Barra do app ${appLabel}`"
    data-suite-rail
  >
    <!-- Selo do app: identidade e caminho para a Central (o "trocar de app"). -->
    <component
      :is="hubUrl ? 'a' : 'div'"
      :href="hubUrl"
      :target="hubUrl ? hubLink.target : undefined"
      :rel="hubUrl ? hubLink.rel : undefined"
      :aria-label="hubUrl ? `${appLabel}: ${HUB_BACK_INLINE}` : appLabel"
      :title="hubUrl ? `${appLabel}: ${HUB_BACK_INLINE}` : appLabel"
      class="relative mt-3 mb-2 grid h-[52px] w-[60px] shrink-0 place-items-center rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rail-foreground"
      :style="{ background: appColor }"
      data-suite-rail-app
    >
      <img
        v-if="showAppImage"
        :src="identity?.iconSrc"
        class="size-10 rounded-md"
        alt=""
        decoding="async"
        @error="appIconBroken = true"
      >
      <Icon v-else :name="appIconName" class="size-6 text-white" aria-hidden="true" />
      <span
        v-if="hubUrl"
        class="absolute -right-1 -bottom-1 grid size-5 place-items-center rounded-full bg-rail-foreground shadow"
        aria-hidden="true"
      >
        <Icon name="lucide:layout-grid" class="size-3 text-rail" />
      </span>
    </component>
    <div class="mb-2 h-px w-9 shrink-0 bg-rail-foreground/20" aria-hidden="true" />

    <nav class="flex flex-col items-center gap-1" :aria-label="label">
      <template v-for="(section, index) in topSections" :key="section.key">
        <p v-if="groupStarts(index)" class="mt-0.5 mb-1 text-[9px] leading-none font-semibold tracking-[0.09em] uppercase opacity-[.62]" data-rail-group>{{ groupStarts(index) }}</p>
        <RailSection
          :icon="section.icon"
          :label="section.label"
          :to="section.to"
          :active="active === section.key"
          :badge="section.badge"
          :aria-label="section.badgeLabel ? `${section.label}, ${section.badgeLabel}` : undefined"
          :attention="section.attention"
          :shortcut="section.shortcut"
          :print-shortcut="printShortcuts"
          :dense="denseLabels"
          :data-section="section.key"
          @activate="emit('select', section.key)"
        />
      </template>
    </nav>

    <div class="flex-1" />

    <nav v-if="footSections.length" class="flex flex-col items-center gap-1" :aria-label="`${label}: ajustes`">
      <RailSection
        v-for="section in footSections"
        :key="section.key"
        :icon="section.icon"
        :label="section.label"
        :to="section.to"
        :active="active === section.key"
        :badge="section.badge"
        :aria-label="section.badgeLabel ? `${section.label}, ${section.badgeLabel}` : undefined"
        :attention="section.attention"
        :shortcut="section.shortcut"
        :print-shortcut="printShortcuts"
        :dense="denseLabels"
        :data-section="section.key"
        @activate="emit('select', section.key)"
      />
      <div class="my-1 h-px w-9 shrink-0 bg-rail-foreground/20" aria-hidden="true" />
    </nav>

    <div class="flex flex-col items-center gap-1">
      <!-- O que é do app no pé (avisos, alertas). -->
      <slot name="foot" />

      <ClientOnly>
        <OperatorCapacityStatus v-if="operatorName" :key="operatorName" />
      </ClientOnly>

      <div
        v-if="workstationContext"
        class="grid size-11 place-items-center rounded-md text-rail-foreground/90"
        :title="workstationContext"
        data-rail-workstation
      >
        <Icon :name="workstationIcon" class="size-5" aria-hidden="true" />
        <span class="sr-only">{{ workstationContext }}</span>
      </div>

      <RailSection
        v-if="operatorName && lockable"
        icon="lucide:lock"
        label="Bloquear"
        :aria-label="`${operatorName}: travar ou trocar`"
        data-rail-lock
        @activate="emit('lock')"
      />

      <!-- Menu do operador: as iniciais. Tema, giro e ocultar a barra moram aqui. -->
      <PopoverRoot v-model:open="menuOpen">
        <PopoverTrigger as-child>
          <button
            type="button"
            class="mt-1 grid size-11 place-items-center rounded-full bg-black/20 text-[13px] font-semibold text-rail-foreground transition hover:bg-black/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rail-foreground"
            :aria-label="operatorName ? `Menu de ${operatorName}` : 'Menu do dispositivo'"
            data-suite-rail-menu
          >
            <span v-if="initials" aria-hidden="true">{{ initials }}</span>
            <Icon v-else name="lucide:settings-2" class="size-5" aria-hidden="true" />
          </button>
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent
            side="right"
            align="end"
            :side-offset="8"
            :collision-padding="8"
            class="z-50 w-64 rounded-lg border bg-popover p-1.5 text-popover-foreground shadow-lg outline-hidden"
            data-suite-rail-menu-panel
          >
            <div v-if="operatorName || workstationContext" class="px-2.5 pt-1.5 pb-2">
              <p v-if="operatorName" class="op-title truncate">{{ operatorName }}</p>
              <p v-if="workstationContext" class="op-micro text-muted-foreground">{{ workstationContext }}</p>
            </div>
            <ClientOnly>
              <button
                type="button"
                class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
                @click="toggleTheme"
              >
                <Icon name="lucide:moon" class="size-4 text-muted-foreground" aria-hidden="true" />
                {{ themeLabel }}
              </button>
              <button
                v-if="orientation.available.value"
                type="button"
                class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
                :aria-pressed="orientation.isLocked.value"
                :disabled="orientationPending"
                data-orientation-lock
                @click="toggleOrientation"
              >
                <Icon :name="orientation.isLocked.value ? 'lucide:lock-keyhole' : 'lucide:rotate-cw-square'" class="size-4 text-muted-foreground" aria-hidden="true" />
                {{ orientationLabel }}
              </button>
            </ClientOnly>
            <button
              type="button"
              class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
              data-suite-rail-hide
              @click="hideRail"
            >
              <Icon name="lucide:panel-left-close" class="size-4 text-muted-foreground" aria-hidden="true" />
              Ocultar a barra
            </button>
          </PopoverContent>
        </PopoverPortal>
      </PopoverRoot>
    </div>
  </aside>
</template>
