<script setup lang="ts">
interface OperatorPwaRuntimeConfig {
  app?: string;
  kiosk?: boolean;
  wakeLock?: boolean;
  idleReloadPaths?: string[];
  push?: { surfaceRef?: string };
}

withDefaults(
  defineProps<{
    showPrompts?: boolean;
  }>(),
  {
    showPrompts: true,
  },
);

const publicConfig = useRuntimeConfig().public as {
  operatorPwa?: OperatorPwaRuntimeConfig;
  appVersion?: string;
};
const config = (publicConfig.operatorPwa || {}) as OperatorPwaRuntimeConfig;
const enabled = Boolean(config.app);
const route = useRoute();

// As APIs de dispositivo continuam progressivas: uma surface sem suporte preserva
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
  <!-- A caixa do `useConfirm()` mora aqui porque esta é a peça que TODO app de
       operador monta: assim nenhum app monta a sua. Fora do `enabled`/`showPrompts`:
       perguntar antes de descartar não depende de o app ser instalável. -->
  <OperatorConfirmDialog />
  <ClientOnly v-if="enabled && showPrompts">
    <OperatorPwaInstallInvite :app="config.app!" />
    <!-- Avisos persistentes do app compartilham uma região: update e push podem
         coexistir e nunca devem ocupar o mesmo canto um por cima do outro. -->
    <aside
      class="fixed inset-x-4 bottom-[calc(var(--ui-header-height)+1rem+env(safe-area-inset-bottom))] z-[60] flex flex-col gap-2 sm:end-6 sm:start-auto sm:w-[28rem] lg:bottom-[calc(1.5rem+env(safe-area-inset-bottom))]"
      aria-live="polite"
      data-operator-pwa-notices
    >
      <!-- Aplicando sozinho, o aviso sairia da tela no mesmo instante em que ela
           recarrega: pisca sem ninguém para ler. -->
      <OperatorPwaUpdatePrompt v-if="!autoUpdate.applying.value" />
      <OperatorPushInvite v-if="config.push && config.app !== 'hub'" />
    </aside>
  </ClientOnly>
</template>
