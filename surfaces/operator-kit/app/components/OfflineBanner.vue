<script setup lang="ts">
// Aviso calmo e global de conexão para as superfícies de operador. Aparece só quando
// offline; feedback nunca no vácuo. Usa tokens do design system canônico (âmbar =
// aviso). Auto-importado pelo operator-kit — colocar uma vez no layout raiz de cada app.
import { computed, onMounted, ref } from "vue";

const { isOnline } = useConnectivity();
// So depois da hidratacao: no SSR o useOnline devolve false (sem navigator) e
// o banner entraria no HTML do servidor para o cliente (online) o remover —
// o "Hydration completed but contains mismatches" de toda superficie.
const mounted = ref(false);
onMounted(() => {
  mounted.value = true;
});
const show = computed(() => mounted.value && isOnline.value === false);
</script>

<template>
  <div
    v-if="show"
    class="fixed inset-x-0 top-0 z-[100] pt-[env(safe-area-inset-top)]"
    aria-live="assertive"
  >
    <NuxtBanner
      color="warning"
      icon="i-lucide-wifi-off"
      title="Sem conexão — tentando reconectar…"
      data-operator-offline-banner
    />
  </div>
</template>
