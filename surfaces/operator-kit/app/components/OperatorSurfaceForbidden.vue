<script setup lang="ts">
/**
 * "Seu acesso não inclui o PDV": a recusa de app, uma só na suíte.
 *
 * Cada `app.vue` desenhava a sua (beta 05/11, CEN-04, PDV2-15, CEN-11): Produção, B.I.,
 * Compras e Gestor sem nenhum botão, o Marketing só com "Voltar à Central", e três
 * redações diferentes. Num dispositivo instalado (sem barra de endereço) a pessoa ficava
 * presa na tela. Aqui a recusa sempre tem saída:
 *
 * - "Trocar operador": o dispositivo é compartilhado, e quem tem o acesso pode estar
 *   do lado. Trava a tela e sobe a identificação, a mesma do resto da suíte.
 * - "Voltar à Central", quando há Central para onde voltar.
 *
 * O nome do app vem com o artigo da identidade canônica (`app-identity.json`): "as
 * Compras", nunca "o Compras". O convite de instalar fica calado enquanto a recusa
 * está na tela: ele pedia para pôr na tela inicial um app que a pessoa não abre.
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { useOperatorAppLink } from "../composables/useOperatorAppLink";

interface ForbiddenIdentity {
  label: string;
  article: string;
}

const props = defineProps<{
  /** A permissão da superfície: quem aparece para destravar depois de trocar. */
  perm: string;
  /** Sobrescreve a identidade do runtime (harness de teste). */
  identity?: ForbiddenIdentity;
}>();

const config = useRuntimeConfig().public as {
  operatorHubUrl?: string;
  operatorPwa?: { identity?: ForbiddenIdentity };
};
const identity = computed(() => props.identity || config.operatorPwa?.identity || null);
const named = computed(() =>
  identity.value ? `${identity.value.article} ${identity.value.label}` : "este app",
);

// Auto-import, e não import direto: o app que monta a recusa já tem a trava, e o teste
// do app a substitui pelo `mockNuxtImport`.
const { operator, lock } = useOperatorLock(props.perm);
const switching = ref(false);
async function switchOperator() {
  if (switching.value) return;
  switching.value = true;
  try {
    await lock();
  } finally {
    switching.value = false;
  }
}

const hubUrl = config.operatorHubUrl || "";
const { attrsFor } = useOperatorAppLink();
const hubLink = computed(() => attrsFor(hubUrl));

const description = computed(() => {
  const who = operator.value?.name ? `Você entrou como ${operator.value.name}. ` : "";
  return `${who}Entrar de novo não resolve: peça o acesso a um gerente, ou troque para quem já tem.`;
});

const actions = computed(() => [
  {
    label: "Trocar operador",
    icon: "i-lucide-users",
    color: "primary" as const,
    variant: "solid" as const,
    loading: switching.value,
    onClick: switchOperator,
    "data-forbidden-switch": "",
  },
  ...(hubUrl
    ? [
        {
          label: "Voltar à Central",
          icon: "i-lucide-layout-grid",
          color: "neutral" as const,
          variant: "outline" as const,
          href: hubUrl,
          target: hubLink.value.target,
          rel: hubLink.value.rel,
          "data-forbidden-hub": "",
        },
      ]
    : []),
]);

// O convite de instalar e o de avisos ficam calados enquanto a recusa está na tela.
const quiet = useState<boolean>("operator-pwa-quiet", () => false);
onMounted(() => {
  quiet.value = true;
});
onBeforeUnmount(() => {
  quiet.value = false;
});
</script>

<template>
  <main
    class="grid min-h-dvh flex-1 place-items-center p-4"
    data-operator-surface-forbidden
  >
    <h1 v-if="identity" class="sr-only">{{ identity.label }}</h1>
    <NuxtEmpty
      class="max-w-sm text-center"
      icon="i-lucide-shield-x"
      :title="`Seu acesso não inclui ${named}`"
      :description="description"
      :actions="actions"
    />
  </main>
</template>
