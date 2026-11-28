<script setup lang="ts">
// Versão do serviço no ar, numa linha discreta (WP-RELEASE-01 R1).
//
// Peça isolada de propósito: hoje mora no rodapé do detalhe "Capacidade do serviço"
// do rail (OperatorCapacityStatus); o novo modelo de navegação (selo único) pode
// encaixá-la onde quiser sem mexer na leitura. O mesmo processo Nitro responde
// `/health/release`, sem Django; lida uma vez por montagem. Falha ou build sem
// identidade = a linha não aparece (`presentation/release.ts`).
import { releaseLabel, type ReleaseIdentityResponse } from "../presentation/release";

const { data } = useFetch<ReleaseIdentityResponse | null>("/health/release", {
  key: "operator-release-identity",
  server: false,
  lazy: true,
  default: () => null,
});
const label = computed(() => releaseLabel(data.value));
</script>

<template>
  <p v-if="label" class="text-xs text-muted-foreground tabular-nums" data-release-label>{{ label }}</p>
</template>
