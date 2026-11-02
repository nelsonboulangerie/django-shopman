<script setup lang="ts">
// O trocador (modelo de navegação, aprovado 31/10/2026): o que o selo abre.
// Três blocos, nesta ordem, porque é a ordem da pergunta de quem toca no selo:
//   1. Neste app: as seções numa lista só, as do chão primeiro. A forma decide a barra
//      de baixo, não vira título: "no posto" e "escritório" são palavras de quem
//      desenha, não de quem opera (dono, 02/11/2026);
//   2. Outros apps: cada um com a pendência mais urgente (a mesma da Central), e a Central;
//   3. Quem opera: o nome, e Trocar ou bloquear.
// Celular e tablet: folha de baixo. Computador: painel da esquerda, ao lado da barra.
import { computed, reactive, resolveComponent, watch } from "vue";

import { OPERATOR_APPS, operatorShortcutIconSrc } from "../../appIdentity";
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

// O ícone de cada app é o da Central: o PNG que o próprio app publica na origem dele, num
// quadrado de cantos arredondados; se não carregar, o símbolo Lucide do app no mesmo quadrado.
const brokenIcons = reactive(new Set<string>());
function iconUrl(url: string): string | null {
  try {
    return new URL(operatorShortcutIconSrc(), url).toString();
  } catch {
    return null;
  }
}

const FORM_ORDER = ["floor", "office", "wall"] as const;
const ordered = computed(() =>
  FORM_ORDER.flatMap((form) => props.sections.filter((section) => (section.form ?? "office") === form)),
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
        iconSrc: brokenIcons.has(tile.ref) ? null : iconUrl(tile.url),
        iconName: `lucide:${app?.fallbackIcon || tile.icon}`,
        link: attrsFor(tile.url),
      };
    }),
);
const hubLink = computed(() => attrsFor(hubUrl));
const hubIconSrc = computed(() => (brokenIcons.has("hub") ? null : iconUrl(hubUrl)));

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
        <section :aria-label="`Seções: ${identity?.label || 'este app'}`">
          <!-- Mais de três: duas colunas, para os outros apps caberem na primeira tela. -->
          <div class="grid gap-1" :class="ordered.length > 3 ? 'grid-cols-2' : 'grid-cols-1'">
            <NuxtButton
              v-for="section in ordered"
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
          <!-- Uma coluna: a pendência de cada app se lê inteira (em duas, cortava). -->
          <div class="grid grid-cols-1 gap-1">
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
              <span class="grid size-10 shrink-0 place-items-center overflow-hidden rounded-lg text-primary" :class="app.iconSrc ? '' : 'bg-primary/10'" aria-hidden="true" data-switcher-app-icon>
                <img v-if="app.iconSrc" :src="app.iconSrc" class="size-10 rounded-lg" alt="" loading="lazy" decoding="async" @error="brokenIcons.add(app.ref)">
                <NuxtIcon v-else :name="app.iconName" class="size-5" />
              </span>
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
              <span class="grid size-10 shrink-0 place-items-center overflow-hidden rounded-lg text-primary" :class="hubIconSrc ? '' : 'bg-primary/10'" aria-hidden="true" data-switcher-app-icon>
                <img v-if="hubIconSrc" :src="hubIconSrc" class="size-10 rounded-lg" alt="" loading="lazy" decoding="async" @error="brokenIcons.add('hub')">
                <NuxtIcon v-else :name="`lucide:${OPERATOR_APPS.hub.fallbackIcon}`" class="size-5" />
              </span>
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
