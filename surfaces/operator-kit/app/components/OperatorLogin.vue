<script setup lang="ts">
import { useAttrs } from "vue";

type LoginMode = "overlay" | "page";

const props = withDefaults(
  defineProps<{
    title?: string;
    description?: string;
    /** Ícone de recurso. Omitido → o ícone canônico do app (`app-identity.json`). */
    icon?: string;
    /** Identidade do app no gate: o PNG da família PWA. Omitido → o PNG canônico do app. */
    iconSrc?: string;
    loginUrl?: string;
    mode?: LoginMode;
    largeFields?: boolean;
    reloadOnSuccess?: boolean;
    expired?: boolean;
  }>(),
  {
    loginUrl: "/api/v1/backstage/operator/login/",
    mode: "overlay",
    largeFields: false,
    reloadOnSuccess: true,
    expired: false,
  },
);

const emit = defineEmits<{ success: [] }>();

// Marco da página (WP-OPERADOR-NUXTUI-ONDAS, onda 0, 08/10/2026). O app que dá ao
// login um papel de marco (`role="main"`, o Marketing) espera achá-lo na árvore de
// acessibilidade: no `main` ele envolvia o diálogo. Com o Modal canônico, o atributo
// caía no componente e sumia, e o Modal no portal escondia todo o resto do leitor de
// tela. Opt-in pelo próprio atributo: com ele, o Modal nasce DENTRO do marco (sem
// portal), e o `hideOthers` do reka preserva os ancestrais do conteúdo. Sem ele (os
// outros apps e o Gestor), nada muda.
defineOptions({ inheritAttrs: false });
const attrs = useAttrs();
const landmark = computed(() => Boolean(attrs.role));
const identity = (
  useRuntimeConfig().public?.operatorPwa as
    { identity?: { icon: string; iconSrc: string } } | undefined
)?.identity;
const icon = computed(
  () =>
    props.icon ||
    (identity?.icon ? `lucide:${identity.icon}` : "lucide:log-in"),
);
const iconSrc = computed(() => props.iconSrc || identity?.iconSrc);
const displayTitle = computed(
  () =>
    props.title ??
    (props.expired ? "Sua sessão terminou" : "Entre para operar"),
);
const displayDescription = computed(
  () =>
    props.description ??
    (props.expired
      ? "Entre novamente. Seu rascunho e sua decisão ainda não enviada foram preservados."
      : "Acesse com sua conta autorizada."),
);
</script>

<template>
  <!-- Foco, aria e bloqueio de fundo pertencem ao Modal canônico, não a uma
       imitação feita com div fixa, Card e focus trap manual. -->
  <!-- O marco ocupa a tela que o diálogo cobre (um marco vazio, de 0 px, não é
       "visível" para ninguém). -->
  <div
    v-if="mode === 'overlay' && landmark"
    v-bind="attrs"
    class="min-h-dvh w-full flex-1"
    data-operator-login-landmark
  >
    <NuxtModal
      :open="true"
      :portal="false"
      :dismissible="false"
      :close="false"
      :title="displayTitle"
      :description="displayDescription"
      data-operator-login
    >
      <template #content>
        <div class="p-6">
          <OperatorLoginForm
            heading
            :title="displayTitle"
            :description="displayDescription"
            :icon="icon"
            :icon-src="iconSrc"
            :login-url="loginUrl"
            :large-fields="largeFields"
            :reload-on-success="reloadOnSuccess"
            @success="emit('success')"
          />
        </div>
      </template>
    </NuxtModal>
  </div>

  <NuxtModal
    v-else-if="mode === 'overlay'"
    v-bind="attrs"
    :open="true"
    :dismissible="false"
    :close="false"
    :title="displayTitle"
    :description="displayDescription"
    data-operator-login
  >
    <!-- Como era antes (dono, 07/10/2026): um bloco só, sem a faixa de cabeçalho do
         Modal. Com #content, o Nuxt UI mantém título e descrição como DialogTitle e
         DialogDescription ocultos (o leitor de tela continua ouvindo) e o selo, o
         título e os campos ficam juntos, centralizados. -->
    <template #content>
      <div class="p-6">
        <OperatorLoginForm
          heading
          :title="displayTitle"
          :description="displayDescription"
          :icon="icon"
          :icon-src="iconSrc"
          :login-url="loginUrl"
          :large-fields="largeFields"
          :reload-on-success="reloadOnSuccess"
          @success="emit('success')"
        />
      </div>
    </template>
  </NuxtModal>

  <div v-else v-bind="attrs" class="grid min-h-dvh place-items-center p-4">
    <NuxtCard class="w-full max-w-sm text-center" data-operator-login>
      <OperatorLoginForm
        heading
        :title="displayTitle"
        :description="displayDescription"
        :icon="icon"
        :icon-src="iconSrc"
        :login-url="loginUrl"
        :large-fields="largeFields"
        :reload-on-success="reloadOnSuccess"
        @success="emit('success')"
      />
    </NuxtCard>
  </div>
</template>
