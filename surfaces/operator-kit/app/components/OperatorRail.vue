<script setup lang="ts">
// Rail de operador CANÔNICO — a espinha vertical em `bg-rail` (token próprio do chrome,
// de marca: disciplina de ERP) que TODAS as superfícies de operador adotam. É o portador
// nº1 da familiaridade: mesma peça em POS/Gestor/KDS/Produção/Central. Segura o que é
// COMUM (voltar à Central, capacidade do serviço, operador/travar, tema, e o que o app
// puser em #status); o específico de cada app entra pelos slots (#nav = funções;
// #status = saúde/conexão).
//
// Três estados que o operador escolhe conforme precisa (persistidos por dispositivo via
// `useRailState`): colapsado (só um puxador) · compacto (só ícone) · estendido (ícone +
// rótulo). A nav de SEÇÃO de cada app (abas do Gestor, visões do Produção) NÃO vive aqui —
// fica no topo do conteúdo; o rail concentra só o comum e economiza a horizontal.
import { computed, ref } from "vue";

const props = defineProps<{
  /** Ícone forte do app (DS §6), com ou sem `lucide:`. Fallback quando `appIconSrc` falta ou falha. */
  appIcon: string;
  /** O ícone REAL do app — o PNG da família PWA (`/pwa/pwa-64x64.png?v=3`, ver PWA_ICONS.md). */
  appIconSrc?: string;
  appLabel: string;
  /** URL da Central (launcher). Omitido na própria Central → some o item. */
  centralUrl?: string;
  /** Operador ativo — mostra o item de travar/trocar; emite `lock` ao acionar. */
  operatorName?: string;
}>();

const emit = defineEmits<{ lock: [] }>();

const { state, isCollapsed, isExtended } = useRailState();

const colorMode = useColorMode();
function toggleTheme() {
  colorMode.preference = colorMode.value === "dark" ? "light" : "dark";
}
const themeLabel = computed(() => (colorMode.value === "dark" ? "Tema claro" : "Tema escuro"));

// Trava de giro (tablets): só aparece em aparelho de toque com a API; a recusa do
// aparelho é dita ao operador, nunca fingida como travada.
const orientation = useOrientationLock();
const orientationLabel = computed(() => (orientation.isLocked.value ? "Liberar giro" : "Travar giro"));
const orientationAriaLabel = computed(() => {
  if (!orientation.isLocked.value) return "Travar o giro da tela na orientação atual";
  return orientation.locked.value === "portrait"
    ? "Liberar o giro da tela (travado em retrato)"
    : "Liberar o giro da tela (travado em paisagem)";
});
async function toggleOrientation() {
  const result = await orientation.toggle();
  if (result.ok) useSonner.success(result.message);
  else useSonner.warning(result.message);
}

const appIconName = computed(() => (props.appIcon.startsWith("lucide:") ? props.appIcon : `lucide:${props.appIcon}`));

// Imagem que não carregou (build sem a família, cache velho) cai no Lucide — o rail
// nunca fica com um quadrado vazio no lugar da identidade.
const appIconBroken = ref(false);
const showAppImage = computed(() => Boolean(props.appIconSrc) && !appIconBroken.value);
</script>

<template>
  <!-- Colapsado → não renderiza nada (some de verdade); quem traz de volta é o
       RailToggle no cabeçalho do app. Compacto / estendido: -->
  <aside
    v-if="!isCollapsed"
    class="flex shrink-0 flex-col bg-rail py-2 text-rail-foreground print:hidden"
    :class="isExtended ? 'w-52 px-2' : 'w-14 items-center px-1.5'"
    :aria-label="`Barra do app ${appLabel}`"
    :data-rail-state="state"
  >
    <!-- Identidade + voltar à Central (padrão Odoo): o ícone forte do app é também o
         atalho pra Central — no hover/foco vira uma seta "voltar". Na própria Central
         (sem centralUrl) é identidade pura, sem atalho. -->
    <component
      :is="centralUrl ? 'a' : 'div'"
      :href="centralUrl"
      :aria-label="centralUrl ? 'Voltar à Central de Apps' : undefined"
      :title="centralUrl ? 'Voltar à Central de Apps' : undefined"
      class="group mb-1 flex items-center gap-2"
      :class="isExtended ? 'w-full' : ''"
    >
      <!-- O PNG da família tem os cantos arredondados e transparentes (PWA_ICONS.md):
           o fundo do quadrado só existe para o Lucide e para a seta do hover, senão
           apareceria como uma moldura clara nos quatro cantos do ícone. -->
      <span
        class="grid size-11 shrink-0 place-items-center overflow-hidden rounded-md transition"
        :class="[
          showAppImage ? '' : 'bg-rail-foreground/15',
          centralUrl ? 'group-hover:bg-rail-foreground/25 group-focus-visible:bg-rail-foreground/25' : '',
        ]"
      >
        <img
          v-if="showAppImage"
          :src="appIconSrc"
          class="size-11 rounded-md"
          :class="centralUrl ? 'group-hover:hidden group-focus-visible:hidden' : ''"
          alt=""
          decoding="async"
          @error="appIconBroken = true"
        >
        <Icon
          v-else
          :name="appIconName"
          class="size-5"
          :class="centralUrl ? 'group-hover:hidden group-focus-visible:hidden' : ''"
        />
        <Icon
          v-if="centralUrl"
          name="lucide:arrow-left"
          class="hidden size-5 group-hover:block group-focus-visible:block"
        />
      </span>
      <span v-if="isExtended" class="truncate text-sm font-semibold">
        <template v-if="centralUrl">
          <span class="group-hover:hidden group-focus-visible:hidden">{{ appLabel }}</span>
          <span class="hidden group-hover:inline group-focus-visible:inline">Central</span>
        </template>
        <template v-else>{{ appLabel }}</template>
      </span>
    </component>

    <!-- Funções específicas do app (RailItem no slot). -->
    <nav class="flex w-full flex-col gap-0.5" :aria-label="`Funções do app ${appLabel}`">
      <slot name="nav" />
    </nav>

    <!-- Cluster comum, ancorado embaixo. -->
    <div class="mt-auto flex w-full flex-col gap-0.5">
      <slot name="status" />

      <!-- Capacidade do serviço (memória/CPU do contêiner), comum a todo app: só com
           operador identificado, porque quem autoriza a leitura é a sessão. A chave
           remonta a leitura quando o operador troca. -->
      <ClientOnly>
        <OperatorCapacityStatus v-if="operatorName" :key="operatorName" />
      </ClientOnly>

      <RailItem
        v-if="operatorName"
        icon="user-round"
        :label="operatorName"
        :aria-label="`${operatorName} — travar / trocar`"
        @activate="emit('lock')"
      />

      <ClientOnly>
        <RailItem
          v-if="orientation.available.value"
          :icon="orientation.isLocked.value ? 'lucide:lock-keyhole' : 'lucide:rotate-cw-square'"
          :label="orientationLabel"
          :aria-label="orientationAriaLabel"
          :aria-pressed="orientation.isLocked.value"
          data-orientation-lock
          @activate="toggleOrientation"
        />
        <RailItem
          icon="lucide:moon"
          :label="themeLabel"
          :aria-label="themeLabel"
          @activate="toggleTheme"
        />
        <template #fallback>
          <span class="grid size-11 place-items-center rounded-md text-rail-foreground/80">
            <Icon name="lucide:moon" class="size-5" />
          </span>
        </template>
      </ClientOnly>
    </div>
  </aside>
</template>
