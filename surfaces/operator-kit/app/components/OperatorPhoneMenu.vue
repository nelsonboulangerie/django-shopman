<script setup lang="ts">
// O menu do operador no CELULAR (camada visual da suíte, V4-MKT).
//
// Do tablet para cima, tema, giro e Bloquear moram no menu das iniciais, no pé do
// `OperatorSuiteRail`. Abaixo de `md` o rail não existe, e sem esta peça o celular
// perdia as três funções que o `OperatorRail` clássico mostrava em qualquer largura.
// Ela é o mesmo menu, montado na barra de 56px do `OperatorPageHeader`
// (`#phone-actions`): as iniciais em 44px, o painel abrindo para baixo.
//
// Opt-in, como o resto da camada: só quem monta tem. O app decide onde (o Marketing
// põe depois do sino).
import { computed, ref } from "vue";
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";

import type { OperatorSession } from "../types/operator";

const props = withDefaults(defineProps<{
  /** Operador ativo: dá as iniciais e o Bloquear. */
  operatorName?: string;
}>(), { operatorName: undefined });

const emit = defineEmits<{ lock: [] }>();

const { data: operatorSession } = useNuxtData<OperatorSession>("operator-session");
const workstationContext = computed(() => operatorSession.value?.workstation?.context_label ?? "");

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

const open = ref(false);
function lock() {
  open.value = false;
  emit("lock");
}
</script>

<template>
  <PopoverRoot v-model:open="open">
    <PopoverTrigger as-child>
      <button
        type="button"
        class="grid size-12 shrink-0 place-items-center rounded-md md:hidden"
        :aria-label="operatorName ? `Menu de ${operatorName}` : 'Menu do dispositivo'"
        data-operator-phone-menu
      >
        <span
          class="grid size-9 place-items-center rounded-full bg-muted text-[13px] font-semibold text-foreground"
          aria-hidden="true"
        >
          <template v-if="initials">{{ initials }}</template>
          <Icon v-else name="lucide:settings-2" class="size-5" />
        </span>
      </button>
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        side="bottom"
        align="end"
        :side-offset="4"
        :collision-padding="8"
        class="z-50 w-64 rounded-lg border bg-popover p-1.5 text-popover-foreground shadow-lg outline-hidden"
        data-operator-phone-menu-panel
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
            @click="toggleOrientation"
          >
            <Icon :name="orientation.isLocked.value ? 'lucide:lock-keyhole' : 'lucide:rotate-cw-square'" class="size-4 text-muted-foreground" aria-hidden="true" />
            {{ orientationLabel }}
          </button>
        </ClientOnly>
        <button
          v-if="operatorName"
          type="button"
          class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
          data-operator-phone-menu-lock
          @click="lock"
        >
          <Icon name="lucide:lock" class="size-4 text-muted-foreground" aria-hidden="true" />
          Bloquear
        </button>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
