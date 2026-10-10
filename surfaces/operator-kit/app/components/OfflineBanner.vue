<script setup lang="ts">
// Aviso global de conexão para as superfícies de operador. Aparece só quando offline;
// feedback nunca no vácuo. Auto-importado pelo operator-kit: colocar uma vez no layout
// raiz de cada app.
//
// A faixa NÃO cobre nada (10/10/2026: no PDV ela escondia o cabeçalho da coluna da
// comanda e a barra do topo). Ela ocupa uma faixa própria no topo da janela, e o shell
// desce o mesmo tanto: enquanto a faixa existe, `html[data-operator-offline]` liga
// `--operator-offline-inset`, e os shells do kit (`OperatorSuiteShell`,
// `OperatorOfficeShell`, `OperatorOperationalShell`) e a trava (`OperatorLock`) usam
// essa variável como `top`. O shell é `fixed inset-0` (o DashboardGroup do Nuxt UI),
// então empurrar é mudar o `top`, não somar margem no fluxo.
//
// Sem salto: a altura é fixa (a do Banner do Nuxt UI, h-12, mais a área segura do
// topo), conhecida antes de a faixa aparecer; o shell desliza 200 ms (nada com
// movimento reduzido); e uma piscada de rede menor que `SHOW_AFTER_MS` não mexe na
// tela. Sem `z-index`: nada fica sob a faixa, e o que é sobreposto por natureza
// (diálogo, gaveta, aviso) passa por cima dela.
//
// "Sem conexão" leva o ponto vermelho (dono, 08/10/2026, conjunto mínimo #1539).
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

/** Piscada de rede menor que isto não move a tela. */
const SHOW_AFTER_MS = 1000;
/** O mesmo tempo do deslizar do shell: a faixa fica até ele cobrir o lugar dela. */
const LEAVE_MS = 200;

const { isOnline } = useConnectivity();
// Só depois da hidratação: no SSR o useOnline devolve false (sem navigator) e a faixa
// entraria no HTML do servidor para o cliente (online) a remover.
const show = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;

function settle(online: boolean) {
  if (timer) clearTimeout(timer);
  timer = undefined;
  if (online) {
    show.value = false;
    return;
  }
  timer = setTimeout(() => {
    show.value = true;
  }, SHOW_AFTER_MS);
}

onMounted(() => {
  watch(isOnline, (online) => settle(online !== false), { immediate: true });
  watch(
    show,
    (offline) => document.documentElement.toggleAttribute("data-operator-offline", offline),
    { immediate: true },
  );
});
onBeforeUnmount(() => {
  if (timer) clearTimeout(timer);
  document.documentElement.removeAttribute("data-operator-offline");
});
</script>

<template>
  <Transition :duration="{ enter: 0, leave: LEAVE_MS }">
    <div
      v-if="show"
      class="fixed inset-x-0 top-0 pt-[env(safe-area-inset-top)]"
      aria-live="assertive"
      data-operator-offline-band
    >
      <NuxtBanner color="neutral" data-operator-offline-banner>
        <template #title>
          <span class="flex min-w-0 items-center gap-2">
            <OperatorCountChip dot color="error" aria-hidden="true" />
            <span>Sem conexão. Tentando reconectar…</span>
          </span>
        </template>
      </NuxtBanner>
    </div>
  </Transition>
</template>

<style>
/* A faixa e o shell combinam a altura aqui, uma vez: a do Banner (h-12) mais a área
   segura do topo. Sem a faixa, 0. */
:root {
  --operator-offline-inset: 0px;
}
:root[data-operator-offline] {
  --operator-offline-inset: calc(3rem + env(safe-area-inset-top));
}
</style>
