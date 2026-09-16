<script setup lang="ts">
import { shouldApplyKioskUpdate } from "../presentation/pwaRuntime";

interface OperatorPwaRuntimeConfig {
  app?: string;
  kiosk?: boolean;
  wakeLock?: boolean;
  manifest?: { name?: string };
}

withDefaults(defineProps<{ showPrompts?: boolean }>(), { showPrompts: true });

const config = (useRuntimeConfig().public.operatorPwa || {}) as OperatorPwaRuntimeConfig;
const enabled = Boolean(config.app);

// As APIs de aparelho continuam progressivas: uma surface sem suporte preserva
// exatamente o comportamento web atual. Só capabilities declaradas no manifesto
// do app são ativadas aqui.
useWakeLock({ enabled: enabled && config.wakeLock === true });

const pwaUpdate = usePwaUpdate();
const applyingIdleUpdate = ref(false);

async function applyIdleUpdate() {
  if (!shouldApplyKioskUpdate({
    idle: kiosk.isIdle.value,
    needsRefresh: pwaUpdate.needRefresh.value,
    applying: applyingIdleUpdate.value,
  })) return;
  applyingIdleUpdate.value = true;
  const accepted = await pwaUpdate.update();
  if (!accepted) applyingIdleUpdate.value = false;
}

const kiosk = useKioskMode({
  enabled: enabled && config.kiosk === true,
  idleMs: 60_000,
  onIdle: () => applyIdleUpdate(),
});

// Se o worker terminar de baixar quando o kiosk já está ocioso, não existe novo
// evento de atividade para disparar o callback. Esta observação fecha essa janela.
watch(
  [kiosk.isIdle, pwaUpdate.needRefresh],
  ([idle, needsRefresh]) => {
    if (idle && needsRefresh) void applyIdleUpdate();
  },
  { flush: "post" },
);
</script>

<template>
  <ClientOnly v-if="enabled && showPrompts">
    <OperatorPwaInstallInvite :app="config.app!" :app-name="config.manifest?.name || 'Shopman'" />
    <OperatorPwaUpdatePrompt v-if="!applyingIdleUpdate" />
  </ClientOnly>
</template>
