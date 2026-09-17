<script setup lang="ts">
import { applyKioskUpdate, idleReloadPathAllowed } from "../presentation/pwaRuntime";

interface OperatorPwaRuntimeConfig {
  app?: string;
  kiosk?: boolean;
  wakeLock?: boolean;
  idleReloadPaths?: string[];
  manifest?: { name?: string };
  push?: { surfaceRef?: string };
}

withDefaults(defineProps<{
  showPrompts?: boolean;
}>(), {
  showPrompts: true,
});

const config = (useRuntimeConfig().public.operatorPwa || {}) as OperatorPwaRuntimeConfig;
const enabled = Boolean(config.app);
const route = useRoute();
const idleReloadSafe = computed(() => idleReloadPathAllowed(config.idleReloadPaths || [], route.path));

// As APIs de aparelho continuam progressivas: uma surface sem suporte preserva
// exatamente o comportamento web atual. Só capabilities declaradas no manifesto
// do app são ativadas aqui.
useWakeLock({ enabled: enabled && config.wakeLock === true });
// Trava de giro escolhida no rail: o navegador a solta ao recarregar, então o app
// instalado a reaplica no boot (e ao voltar do segundo plano / da tela cheia).
useOrientationLock({ restore: enabled });

const pwaUpdate = usePwaUpdate();
const applyingIdleUpdate = ref(false);

async function applyIdleUpdate() {
  await applyKioskUpdate({
    allowedPaths: config.idleReloadPaths || [],
    path: route.path,
    idle: kiosk.isIdle.value,
    needsRefresh: pwaUpdate.needRefresh.value,
    applying: applyingIdleUpdate.value,
  }, async () => {
    applyingIdleUpdate.value = true;
    const accepted = await pwaUpdate.update();
    if (!accepted) applyingIdleUpdate.value = false;
    return accepted;
  });
}

const kiosk = useKioskMode({
  enabled: enabled && config.kiosk === true,
  idleMs: 60_000,
  onIdle: () => applyIdleUpdate(),
});

// Se o worker terminar de baixar quando o kiosk já está ocioso, não existe novo
// evento de atividade para disparar o callback. Esta observação fecha essa janela.
watch(
  [kiosk.isIdle, pwaUpdate.needRefresh, idleReloadSafe],
  () => void applyIdleUpdate(),
  { flush: "post" },
);
</script>

<template>
  <ClientOnly v-if="enabled && showPrompts">
    <OperatorPwaInstallInvite :app="config.app!" :app-name="config.manifest?.name || 'Shopman'" />
    <OperatorPwaUpdatePrompt v-if="!applyingIdleUpdate" />
    <OperatorPushInvite v-if="config.push && config.app !== 'hub'" />
  </ClientOnly>
</template>
