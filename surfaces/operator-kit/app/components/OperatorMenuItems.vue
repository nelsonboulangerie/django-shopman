<script setup lang="ts">
// O conteúdo do menu do operador, um só para o rail (as iniciais no pé) e para o
// celular (o "Mais" da barra do polegar, ou as iniciais na barra de 56px de quem não tem
// barra embaixo, a Central). V6-KIT.
//
// Mora aqui o que o rail clássico mostrava em qualquer largura e o pé da v4 não mostra:
// quem está operando, o posto deste dispositivo, a capacidade do serviço (escrita, não
// um ponto vermelho permanente no rail: K02/T-03), o tema e a trava de giro. No celular,
// também o Bloquear (que é como se troca de operador: a trava pede o PIN de quem entra).
import { computed } from "vue";
import { useNow } from "@vueuse/core";

import { useOperatorCapacity } from "../composables/useOperatorCapacity";
import { useSharedCapacity } from "../composables/useSuiteChrome";
import {
  CAPACITY_LEVEL_META,
  capacityLevel,
  capacitySummary,
  capacityUpdatedAgo,
} from "../presentation/capacity";
import type { OperatorSession } from "../types/operator";

const props = withDefaults(defineProps<{
  operatorName?: string;
  /** `rail`: com "Ocultar a barra lateral". `phone`: com Bloquear. */
  mode: "rail" | "phone";
}>(), { operatorName: undefined });

const emit = defineEmits<{ lock: []; hide: [] }>();

const { data: operatorSession } = useNuxtData<OperatorSession>("operator-session");
const workstationContext = computed(() => operatorSession.value?.workstation?.context_label ?? "");

// A leitura que a caixa de Avisos já faz; sem ela (tela sem a caixa), uma própria.
const shared = useSharedCapacity().value;
const { reading, authorized, stale } = shared ?? useOperatorCapacity();
const now = useNow({ interval: 10_000 });
const level = computed(() => capacityLevel(reading.value));
const capacityMeta = computed(() => CAPACITY_LEVEL_META[level.value]);
const capacityUpdated = computed(() => capacityUpdatedAgo(reading.value?.measured_at, now.value.getTime()));

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

</script>

<template>
  <div class="flex flex-col" data-operator-menu :data-mode="props.mode">
    <div v-if="operatorName || workstationContext" class="px-2.5 pt-1.5 pb-2">
      <p v-if="operatorName" class="op-title truncate">{{ operatorName }}</p>
      <p v-if="workstationContext" class="op-micro text-muted-foreground" data-operator-menu-workstation>
        {{ workstationContext }} · este dispositivo
      </p>
    </div>

    <NuxtButton
      v-if="props.mode === 'phone' && operatorName"
      block
      class="justify-start"
      color="neutral"
      variant="ghost"
      icon="i-lucide-lock"
      label="Bloquear"
      description="Outra pessoa entra com o PIN dela"
      data-operator-menu-lock
      @click="emit('lock')"
    />

    <ClientOnly>
      <NuxtButton block class="justify-start" color="neutral" variant="ghost" icon="i-lucide-moon" :label="themeLabel" data-operator-menu-theme @click="toggleTheme" />
      <NuxtButton
        v-if="orientation.available.value"
        block
        class="justify-start"
        color="neutral"
        variant="ghost"
        :icon="orientation.isLocked.value ? 'i-lucide-lock-keyhole' : 'i-lucide-rotate-cw-square'"
        :label="orientationLabel"
        :aria-pressed="orientation.isLocked.value"
        :disabled="orientationPending"
        :loading="orientationPending"
        data-orientation-lock
        @click="toggleOrientation"
      />
    </ClientOnly>

    <NuxtButton
      v-if="props.mode === 'rail'"
      block
      class="justify-start"
      color="neutral"
      variant="ghost"
      icon="i-lucide-panel-left-close"
      label="Ocultar a barra lateral"
      data-suite-rail-hide
      @click="emit('hide')"
    />

    <!-- Capacidade do serviço: o estado escrito, sempre com o número. Quando passa do
         limite, ela também entra na caixa de Avisos. -->
    <ClientOnly>
      <div
        v-if="authorized && reading"
        class="mt-1 px-2.5 pt-2 pb-1"
        data-operator-menu-capacity
        :data-capacity-level="level"
      >
        <NuxtSeparator class="mb-2" />
        <p class="flex items-center gap-2 op-label">
          <Icon name="lucide:gauge" class="size-4 text-muted-foreground" aria-hidden="true" />
          <span class="flex-1">Capacidade do serviço</span>
          <span class="font-semibold" :class="capacityMeta.text">{{ capacityMeta.label }}</span>
        </p>
        <p class="mt-0.5 pl-6 op-micro text-muted-foreground tnum">
          {{ capacitySummary(reading) }}<template v-if="capacityUpdated"> · {{ capacityUpdated }}</template><template v-if="stale"> · sem resposta na última tentativa</template>
        </p>
      </div>
    </ClientOnly>
  </div>
</template>
