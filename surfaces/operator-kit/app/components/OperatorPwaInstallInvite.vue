<script setup lang="ts">
// O convite de instalação tem DUAS camadas, e elas estavam trocadas.
//
// O QUÊ é de cada app: o que ele passa a fazer da tela inicial. Sai da identidade
// canônica (`app-identity.json`), pelo `runtimeConfig` — a mesma fonte do manifesto, do
// ícone e da barra de título.
//
// O COMO NÃO é comum, e era aí que estava o erro. O convite dizia "No Safari, toque em
// Compartilhar" para qualquer pessoa em iOS — no Chrome, no Firefox, dentro do navegador
// do WhatsApp, onde barra do Safari não existe. Fora do iOS, ou o navegador oferecia o
// prompt nativo, ou o convite não dizia nada. Agora o caminho sai de `installPlan()`
// (`utils/installGuide.ts`), que responde por sistema + navegador e devolve `none`
// quando não existe caminho honesto — a regra do dono é informação correta, ou nada.
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

const pwa = usePwaInstall({ app: props.app });
const plan = computed(() => pwa.plan.value);
const visible = computed(() => pwa.canInvite.value);

// Um toque resolve, ou a pessoa vai seguir passos — o título diz qual dos dois é, antes
// de ela decidir se tem tempo agora.
const title = computed(() => {
  const named = identity.value ? `${identity.value.article} ${identity.value.label}` : "este aplicativo";
  return plan.value.kind === "prompt" ? `Instale ${named}` : `Coloque ${named} na tela inicial`;
});

async function install() {
  if (await pwa.install()) pwa.dismissAsDone();
}
</script>

<template>
  <aside
    v-if="visible"
    class="fixed inset-x-3 bottom-3 z-50 mx-auto max-w-md rounded-md border border-border bg-card p-4 text-card-foreground shadow-xl"
    aria-live="polite"
    data-operator-pwa-install
  >
    <p class="text-sm font-semibold">{{ title }}</p>
    <p v-if="identity" class="mt-1 mb-3 text-sm text-muted-foreground">{{ identity.install }}</p>

    <OperatorInstallSteps v-if="plan.kind === 'steps'" :plan="plan" />

    <div class="mt-4 flex gap-2">
      <button
        type="button"
        class="h-11 flex-1 rounded-md px-4 text-sm font-medium text-muted-foreground hover:bg-muted"
        @click="pwa.dismiss()"
      >
        Agora não
      </button>
      <button
        v-if="plan.kind === 'prompt'"
        type="button"
        class="h-11 flex-1 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground"
        @click="install"
      >
        Instalar
      </button>
      <!-- Ninguém sabe daqui se ela seguiu os passos; quem sabe é ela. Dizer "já
           instalei" encerra o convite de vez em vez de repeti-lo na semana seguinte. -->
      <button
        v-else
        type="button"
        class="h-11 flex-1 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground"
        @click="pwa.dismissAsDone()"
      >
        Já instalei
      </button>
    </div>
  </aside>
</template>
