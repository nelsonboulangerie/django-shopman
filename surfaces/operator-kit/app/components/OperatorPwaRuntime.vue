<script setup lang="ts">
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

const publicConfig = useRuntimeConfig().public as { operatorPwa?: OperatorPwaRuntimeConfig; appVersion?: string };
const config = (publicConfig.operatorPwa || {}) as OperatorPwaRuntimeConfig;
const enabled = Boolean(config.app);
const route = useRoute();

// As APIs de aparelho continuam progressivas: uma surface sem suporte preserva
// exatamente o comportamento web atual. Só capabilities declaradas no manifesto
// do app são ativadas aqui.
useWakeLock({ enabled: enabled && config.wakeLock === true });
// Trava de giro escolhida no rail: o navegador a solta ao recarregar, então o app
// instalado a reaplica no boot (e ao voltar do segundo plano / da tela cheia).
useOrientationLock({ restore: enabled });
// Tela cheia progressiva do kiosk. A ociosidade que decide a troca de versão é a
// do `usePwaAutoUpdate` — uma só, com a mesma régua em todas as superfícies.
useKioskMode({ enabled: enabled && config.kiosk === true, idleMs: 60_000 });

// Sonda periódica + aplicação automática em momento seguro. `idleReloadPaths` vazio
// (Central, Gestor, Compras, B.I., Marketing) mantém só o aviso ao operador.
const { reasons } = useOperatorReloadHold();
const autoUpdate = usePwaAutoUpdate({
  enabled,
  app: config.app || "operator",
  appVersion: String(publicConfig.appVersion || ""),
  allowedPaths: () => config.idleReloadPaths || [],
  path: () => route.path,
  holds: () => reasons.value,
});
</script>

<template>
  <ClientOnly v-if="enabled && showPrompts">
    <OperatorPwaInstallInvite :app="config.app!" :app-name="config.manifest?.name || 'Shopman'" />
    <!-- Aplicando sozinho, o aviso sairia da tela no mesmo instante em que ela
         recarrega: pisca sem ninguém para ler. -->
    <OperatorPwaUpdatePrompt v-if="!autoUpdate.applying.value" />
    <OperatorPushInvite v-if="config.push && config.app !== 'hub'" />
  </ClientOnly>
</template>
