<script setup lang="ts">
// PRÉVIA (modelo de navegação, aprovado 31/10/2026). O trocador: o que o selo abre.
// Três blocos, nesta ordem, porque é a ordem da pergunta de quem toca no selo:
//   1. Neste app: as seções, agrupadas pela forma (no posto, escritório, na parede);
//   2. Outros apps: cada um com a pendência mais urgente (a mesma da Central), e a Central;
//   3. Quem opera: o nome, e Trocar ou bloquear.
// Celular e tablet: folha de baixo. Computador: painel da esquerda, ao lado da barra.
import { computed, resolveComponent, watch } from "vue";

import { OPERATOR_APPS } from "../../appIdentity";
import type { OperatorSection } from "../presentation/appBar";
import { useScreen } from "../composables/useScreen";

const props = defineProps<{
  sections: readonly OperatorSection[];
  current?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();

const open = useState<boolean>("suite-switcher-open", () => false);
const screen = useScreen();
const Drawer = resolveComponent("NuxtDrawer");
const Slideover = resolveComponent("NuxtSlideover");
const frame = computed(() => (screen.belowLg.value ? Drawer : Slideover));
const route = useRoute();
watch(() => route.fullPath, () => { open.value = false; });

const config = useRuntimeConfig().public as {
  operatorHubUrl?: string;
  operatorPwa?: { identity?: { label: string; color: string; icon: string } };
};
const identity = config.operatorPwa?.identity;
const hubUrl = config.operatorHubUrl || "";
const { attrsFor } = useOperatorAppLink();

const GROUPS = [
  { form: "floor", title: "No posto" },
  { form: "office", title: "Escritório" },
  { form: "wall", title: "Na parede" },
] as const;
const groups = computed(() =>
  GROUPS.map((group) => ({
    ...group,
    items: props.sections.filter((section) => (section.form ?? "office") === group.form),
  })).filter((group) => group.items.length),
);
const place = computed(
  () => props.sections.find((section) => section.key === props.current)?.label ?? "",
);

// Os outros apps: a projeção da Central (`/api/v1/backstage/hub/`), lida quando abre.
interface HubTile {
  ref: string; label: string; url: string; icon: string; kind: string;
  status_attention: string; status_summary: string;
}
const TILE_TO_APP: Record<string, string> = { gestor: "orders" };
const { data: hub, error: hubError, execute: readHub, status: hubStatus } = useFetch<{ hub?: { tiles?: HubTile[] } }>(
  "/api/v1/backstage/hub/",
  { server: false, immediate: false, key: "suite-switcher-hub" },
);
watch(open, (now) => { if (now) void readHub(); });
const apps = computed(() =>
  (hub.value?.hub?.tiles ?? [])
    .filter((tile) => tile.kind === "launch" && tile.label !== identity?.label)
    .map((tile) => {
      const app = OPERATOR_APPS[(TILE_TO_APP[tile.ref] ?? tile.ref) as keyof typeof OPERATOR_APPS];
      return {
        ...tile,
        short: app?.shortLabel || tile.label,
        color: app?.color || "var(--ui-primary)",
        iconName: app?.symbol || `lucide:${tile.icon}`,
        link: attrsFor(tile.url),
      };
    }),
);
const hubLink = computed(() => attrsFor(hubUrl));

function go(section: OperatorSection) {
  open.value = false;
  if (section.to) void navigateTo(section.to);
}
</script>

<template>
  <component
    :is="frame"
    v-model:open="open"
    v-bind="screen.belowLg.value ? {} : { side: 'left' }"
    :title="identity?.label || 'Aplicativo'"
    :description="place ? `Você está em ${place}.` : 'Trocar de seção ou de app.'"
    data-suite-switcher
  >
    <template #body>
      <div class="flex flex-col gap-5 pb-2">
        <section v-for="group in groups" :key="group.form" :aria-label="group.title">
          <h3 class="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">{{ group.title }}</h3>
          <!-- Mais de três: duas colunas, para os outros apps caberem na primeira tela. -->
          <div class="grid gap-1" :class="group.items.length > 3 ? 'grid-cols-2' : 'grid-cols-1'">
            <NuxtButton
              v-for="section in group.items"
              :key="section.key"
              :icon="section.icon.replace('lucide:', 'i-lucide-')"
              :color="section.key === current ? 'primary' : 'neutral'"
              :variant="section.key === current ? 'soft' : 'ghost'"
              class="min-h-11 w-full justify-start"
              :aria-current="section.key === current ? 'page' : undefined"
              :data-switcher-section="section.key"
              @click="go(section)"
            >
              <span class="flex-1 text-left">{{ section.label }}</span>
              <NuxtBadge v-if="section.badge" :label="section.badge" color="warning" variant="soft" />
              <span v-else-if="section.attention" class="text-xs text-warning">{{ section.attention }}</span>
            </NuxtButton>
          </div>
        </section>

        <section aria-label="Outros apps">
          <h3 class="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Outros apps</h3>
          <p v-if="hubError && !apps.length" class="text-sm text-muted">
            Não deu para ler os outros apps agora. A Central continua a um toque.
          </p>
          <p v-else-if="hubStatus === 'pending' && !apps.length" class="text-sm text-muted">Lendo os apps…</p>
          <div class="grid grid-cols-1 gap-1 sm:grid-cols-2">
            <NuxtButton
              v-for="app in apps"
              :key="app.ref"
              :to="app.url"
              :target="app.link.target"
              :rel="app.link.rel"
              color="neutral"
              variant="ghost"
              class="min-h-12 w-full justify-start gap-3"
              :data-switcher-app="app.ref"
            >
              <!-- A letra do app na cor dele: o ícone de cada app não vem no pacote dos outros. -->
              <NuxtAvatar :text="app.short.charAt(0)" size="sm" alt="" :ui="{ fallback: 'text-white font-semibold' }" :style="{ background: app.color }" />
              <span class="flex min-w-0 flex-1 flex-col text-left leading-tight">
                <span class="font-medium text-highlighted">{{ app.short }}</span>
                <span v-if="app.status_attention" class="truncate text-xs font-semibold text-warning">{{ app.status_attention }}</span>
                <span v-else-if="app.status_summary" class="truncate text-xs text-muted">{{ app.status_summary }}</span>
              </span>
            </NuxtButton>
            <NuxtButton
              v-if="hubUrl"
              :to="hubUrl"
              :target="hubLink.target"
              :rel="hubLink.rel"
              color="neutral"
              variant="ghost"
              class="min-h-12 w-full justify-start gap-3"
              data-switcher-app="hub"
            >
              <NuxtAvatar icon="lucide:layout-grid" size="sm" alt="" :ui="{ icon: 'text-white' }" :style="{ background: OPERATOR_APPS.hub.color }" />
              <span class="flex flex-col text-left leading-tight">
                <span class="font-medium text-highlighted">Central</span>
                <span class="text-xs text-muted">Todos os apps, a tela inicial</span>
              </span>
            </NuxtButton>
          </div>
        </section>

        <section v-if="operatorName" aria-label="Quem opera" class="flex items-center gap-2 border-t border-default pt-3">
          <NuxtIcon name="i-lucide-user" class="size-4 text-muted" />
          <p class="min-w-0 flex-1 text-sm">Operando: <strong>{{ operatorName }}</strong></p>
          <NuxtButton
            label="Trocar ou bloquear"
            icon="i-lucide-lock"
            color="neutral"
            variant="outline"
            class="min-h-11"
            data-switcher-lock
            @click="open = false; emit('lock')"
          />
        </section>
      </div>
    </template>
  </component>
</template>
