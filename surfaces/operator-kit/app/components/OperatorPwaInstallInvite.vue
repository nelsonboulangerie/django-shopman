<script setup lang="ts">
// O convite de instalação tem DUAS camadas, e elas estavam trocadas.
//
// O COMO é comum — instalar um PWA é o mesmo gesto em todo app, e no iOS é o mesmo
// caminho no Safari. O QUÊ é de cada app: o que ele passa a fazer da tela inicial.
// Estava ao contrário: o título era genérico ao ponto de dizer a marca ("Instale
// Shopman" — o componente lia `manifest.name`, chave que o manifesto resolvido não tem,
// e caía no default), e a frase de benefício era específica do app errado ("Abra o
// caixa direto da tela inicial", no B.I., na Cozinha e no Marketing).
//
// Agora o nome e a frase saem da identidade canônica (`app-identity.json`), pelo
// `runtimeConfig` — a mesma fonte do manifesto, do ícone e da barra de título.
interface OperatorInstallIdentity {
  label: string;
  article: string;
  install: string;
}

const props = defineProps<{
  app: string;
  /** Sobrescreve a identidade canônica — existe para o harness de teste. */
  identity?: OperatorInstallIdentity;
}>();

const runtimeIdentity = (useRuntimeConfig().public?.operatorPwa as { identity?: OperatorInstallIdentity } | undefined)
  ?.identity;
const identity = computed<OperatorInstallIdentity | null>(() => props.identity || runtimeIdentity || null);
const title = computed(() =>
  identity.value ? `Instale ${identity.value.article} ${identity.value.label}` : "Instale este aplicativo",
);

const pwa = usePwaInstall({ app: props.app });
const visible = computed(() => !pwa.isStandalone.value
  && !pwa.isDismissed.value
  && (pwa.canInstall.value || pwa.isIos.value));

async function install() {
  if (await pwa.install()) pwa.dismiss();
}
</script>

<template>
  <aside
    v-if="visible"
    class="fixed inset-x-3 bottom-3 z-50 mx-auto max-w-md rounded-md border border-border bg-card p-4 text-card-foreground shadow-xl"
    aria-live="polite"
    data-operator-pwa-install
  >
    <div class="flex items-start gap-3">
      <div class="min-w-0 flex-1">
        <p class="text-sm font-semibold">{{ title }}</p>
        <!-- O COMO é comum aos oito apps; o QUÊ é de cada um. -->
        <p v-if="pwa.isIos.value" class="mt-1 text-sm text-muted-foreground">
          No Safari, toque em Compartilhar e depois em Adicionar à Tela de Início.
        </p>
        <p v-else-if="identity" class="mt-1 text-sm text-muted-foreground">
          {{ identity.install }}
        </p>
      </div>
      <button
        type="button"
        class="h-9 rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-muted"
        @click="pwa.dismiss"
      >
        Agora não
      </button>
    </div>
    <button
      v-if="pwa.canInstall.value"
      type="button"
      class="mt-3 h-11 w-full rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground"
      @click="install"
    >
      Instalar
    </button>
  </aside>
</template>
