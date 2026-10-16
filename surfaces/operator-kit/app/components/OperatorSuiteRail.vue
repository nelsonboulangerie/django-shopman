<script setup lang="ts">
// Rail da suíte (UX-KIT-V1, pé refeito na V6-KIT): o rail das prévias v3/v4, com as
// SEÇÕES do app dentro dele.
//
// O topo do conteúdo fica com UMA linha (título, ao vivo, busca, controles:
// `OperatorPageHeader`). Medidas de `_rail3top.html`, `_rail3bottom.html` e
// `.rail-item` em `_shared.css`.
//
// Onde ele existe (V6-KIT, `depois-navegacao.jpg` nível 1): no tablet DEITADO e no
// desktop (variante `rail:`). No celular e no tablet em pé a navegação é a barra de
// baixo (`OperatorSectionBar`), e o selo e os Avisos sobem para a barra de 56px do
// `OperatorPageHeader`.
//
// O pé é o da v4, igual em todo app (`_rail3bottom.html`):
//   [seções do pé do app: Ajustes, Terminal…] · traço · Avisos · Atalhos · Bloquear · iniciais.
// A Cozinha (`cozinha-estacao4.html`) diz Avisos · Ajustes · Bloquear, sem traço:
// `footOrder="inbox-first"`. "Avisos" é UM item (`OperatorInbox`: alertas da operação e
// caixa pessoal no mesmo painel). "Atalhos" só com ponteiro fino (no toque não há
// teclado). A capacidade do serviço saiu do rail para o menu das iniciais, e o posto do
// dispositivo também (a v4 o diz no cabeçalho e no menu, não num ícone no rail).
//
// Teclas: Alt 1…9 levam às seções de cima, na ordem, em todo app, impressas sob o nome
// com ponteiro fino (T-05). "?" abre a ajuda de atalhos.
import { computed, ref, useAttrs } from "vue";
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";

import { operatorAppNamed } from "../../appIdentity";
import { activeSectionKey, type OperatorSection } from "../presentation/appBar";
import { sectionDescription, withSectionShortcuts } from "../presentation/suiteChrome";
import { SUITE_HELP_SHORTCUT, SUITE_SECTION_SHORTCUTS } from "../shortcuts/suiteShortcuts";

defineOptions({ inheritAttrs: false });

const HUB_BACK = `Voltar ${operatorAppNamed("hub", "a")}`;
/** "Gestor de pedidos: voltar à Central" (o verbo minúsculo depois dos dois-pontos). */
const HUB_BACK_INLINE = `${HUB_BACK.charAt(0).toLowerCase()}${HUB_BACK.slice(1)}`;

interface SuiteRailIdentity { label: string; icon: string; iconSrc: string; color: string }

const props = withDefaults(defineProps<{
  /** Seções do app (as mesmas da barra do polegar). */
  sections: readonly OperatorSection[];
  /** Nome da navegação para leitor de tela ("Seções do Gestor"). */
  label: string;
  /** URL da Central. Omitida (na própria Central) → o selo é só identidade. */
  hubUrl?: string;
  /** Operador ativo: mostra Bloquear e o menu do operador. */
  operatorName?: string;
  /** Seção ativa. Omitida, sai da rota. */
  current?: string;
  /**
   * Imprime a tecla de cada seção sob o nome, com ponteiro fino ("Alt1"). Padrão: sim,
   * em todo app (`depois-navegacao.jpg`: "Alt 1…9 em todo app", impresso no desktop).
   */
  printShortcuts?: boolean;
  /** Rótulos de 10px para nomes longos (v4 da Produção: "Planejamento", "Preparação"). */
  denseLabels?: boolean;
  /**
   * Ordem do pé. `settings-first` (padrão, v4 do Gestor, do PDV, da Produção, do B.I.):
   * seções do pé, traço, Avisos. `inbox-first` (v4 da Cozinha): Avisos, seções do pé,
   * sem traço.
   */
  footOrder?: "settings-first" | "inbox-first";
  /** Mostra a caixa de Avisos (padrão). */
  inbox?: boolean;
  /** No toque, só o ícone (`none`, o PDV) ou o rótulo curto (`short`, padrão). */
  touchLabel?: "short" | "none";
}>(), {
  hubUrl: undefined,
  operatorName: undefined,
  current: undefined,
  printShortcuts: true,
  denseLabels: false,
  footOrder: "settings-first",
  inbox: true,
  touchLabel: "short",
});

const emit = defineEmits<{ lock: []; select: [key: string] }>();
const attrs = useAttrs();

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
const railSections = computed(() => props.sections.filter((section) => section.where !== "bar"));
const topSections = computed(() => withSectionShortcuts(railSections.value.filter((section) => !section.foot)));
const footSections = computed(() => railSections.value.filter((section) => section.foot));
function groupStarts(index: number): string {
  const group = topSections.value[index]?.group;
  return group && topSections.value[index - 1]?.group !== group ? group : "";
}

const { attrsFor } = useOperatorAppLink();
const hubLink = computed(() => attrsFor(props.hubUrl || ""));

const { isCollapsed, set: setRail } = useRailState();
const railShown = useSuiteRailShown();
const shortcuts = useOperatorShortcuts();

const initials = computed(() => {
  const words = (props.operatorName || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  const first = words[0]!.charAt(0);
  const last = words.length > 1 ? words[words.length - 1]!.charAt(0) : words[0]!.charAt(1);
  return `${first}${last}`.toUpperCase();
});

const menuOpen = ref(false);
function hideRail() {
  menuOpen.value = false;
  setRail("collapsed");
}

function go(section: OperatorSection) {
  if (section.to) void navigateTo(section.to);
  else emit("select", section.key);
}

const shortcutContexts = computed<ReadonlySet<string>>(() => new Set(["ready"]));
useOperatorShortcutMap(
  [...SUITE_SECTION_SHORTCUTS, ...SUITE_HELP_SHORTCUT],
  Object.fromEntries([
    ...SUITE_SECTION_SHORTCUTS.map((command, index) => [command.id, () => {
      const section = topSections.value[index];
      if (section) go(section);
    }]),
    ["suite.shortcuts-help", () => { shortcuts.open.value = true; }],
  ]),
  shortcutContexts,
);
</script>

<template>
  <aside
    v-if="!isCollapsed"
    v-bind="attrs"
    class="sticky top-0 hidden h-dvh w-[var(--op-rail-compact-width)] shrink-0 flex-col items-center gap-1 overflow-y-auto bg-rail pb-2 text-rail-foreground no-scrollbar rail:flex print:hidden"
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
      class="relative mt-3 mb-2 grid h-[52px] w-[68px] shrink-0 place-items-center rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rail-foreground"
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
    <div class="mb-2 h-px w-10 shrink-0 bg-rail-foreground/20" aria-hidden="true" />

    <nav class="flex flex-col items-center gap-1" :aria-label="label">
      <template v-for="(section, index) in topSections" :key="section.key">
        <p v-if="groupStarts(index)" class="mt-0.5 mb-1 text-[9px] leading-none font-semibold tracking-[0.09em] uppercase opacity-[.62]" data-rail-group>{{ groupStarts(index) }}</p>
        <div v-if="section.divider && index > 0" class="my-1 h-px w-10 shrink-0 bg-rail-foreground/20" aria-hidden="true" data-rail-divider />
        <RailSection
          :icon="section.icon"
          :label="section.label"
          :to="section.to"
          :active="active === section.key"
          :badge="section.badge"
          :aria-label="sectionDescription(section)"
          :attention="section.attention"
          :shortcut="section.shortcut"
          :print-shortcut="printShortcuts"
          :dense="denseLabels"
          :short-label="section.shortLabel"
          :touch-label="touchLabel"
          :data-section="section.key"
          @activate="emit('select', section.key)"
        />
      </template>
    </nav>

    <div class="flex-1" />

    <!-- O pé (v4). A caixa de Avisos só existe montada onde o rail aparece: no celular
         e no tablet em pé ela mora na barra de 56px, e duas no DOM seriam duas leituras
         e dois "Avisos" para quem procura pelo nome. -->
    <div class="flex flex-col items-center gap-1" data-rail-foot :data-foot-order="footOrder">
      <ClientOnly v-if="inbox && footOrder === 'inbox-first'">
        <OperatorInbox v-if="railShown" placement="rail" labeled />
      </ClientOnly>

      <nav v-if="footSections.length" class="flex flex-col items-center gap-1" :aria-label="`${label}: ajustes`">
        <RailSection
          v-for="section in footSections"
          :key="section.key"
          :icon="section.icon"
          :label="section.label"
          :to="section.to"
          :active="active === section.key"
          :badge="section.badge"
          :aria-label="sectionDescription(section)"
          :attention="section.attention"
          :shortcut="section.shortcut"
          :print-shortcut="printShortcuts"
          :dense="denseLabels"
          :data-section="section.key"
          @activate="emit('select', section.key)"
        />
      </nav>
      <!-- O que é do app no pé, antes do traço (o Terminal do PDV). -->
      <slot name="foot" />
      <div
        v-if="footOrder === 'settings-first' && (footSections.length || $slots.foot)"
        class="my-1 h-px w-10 shrink-0 bg-rail-foreground/20"
        aria-hidden="true"
        data-rail-foot-rule
      />

      <ClientOnly v-if="inbox && footOrder === 'settings-first'">
        <OperatorInbox v-if="railShown" placement="rail" labeled />
      </ClientOnly>

      <!-- Atalhos (?): só com ponteiro fino; no toque não há teclado. -->
      <div class="hidden pointer-fine:block">
        <RailSection
          icon="lucide:keyboard"
          label="Atalhos"
          aria-label="Atalhos do teclado"
          shortcut="?"
          data-rail-shortcuts
          @activate="shortcuts.open.value = true"
        />
      </div>

      <RailSection
        v-if="operatorName"
        icon="lucide:lock"
        label="Bloquear"
        :aria-label="`${operatorName}: travar ou trocar`"
        data-rail-lock
        @activate="emit('lock')"
      />

      <!-- Menu do operador: as iniciais. 44px (alvo de toque da casa; a v4 desenha 40,
           e o gate de toque da Produção reprova) e fundo escuro, não o
           `bg-rail-foreground/15` da prévia: no rail claro da Produção as iniciais
           ficavam com contraste 3,7:1 (axe, AA pede 4,5). -->
      <PopoverRoot v-model:open="menuOpen">
        <PopoverTrigger as-child>
          <button
            type="button"
            class="my-1.5 grid size-11 place-items-center rounded-full bg-black/25 text-[13px] font-semibold text-rail-foreground transition hover:bg-black/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rail-foreground"
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
            class="z-50 w-72 rounded-lg border bg-popover p-1.5 text-popover-foreground shadow-lg outline-hidden"
            data-suite-rail-menu-panel
          >
            <OperatorMenuItems mode="rail" :operator-name="operatorName" @hide="hideRail" />
          </PopoverContent>
        </PopoverPortal>
      </PopoverRoot>
    </div>
  </aside>
  <OperatorShortcutsHelp :sections="topSections" :app-label="appLabel" />
</template>
