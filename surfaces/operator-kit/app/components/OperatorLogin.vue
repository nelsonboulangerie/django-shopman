<script setup lang="ts">
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
  <NuxtModal
    v-if="mode === 'overlay'"
    :open="true"
    :dismissible="false"
    :close="false"
    :title="displayTitle"
    :description="displayDescription"
    data-operator-login
  >
    <template #body>
      <OperatorLoginForm
        :title="displayTitle"
        :description="displayDescription"
        :icon="icon"
        :icon-src="iconSrc"
        :login-url="loginUrl"
        :large-fields="largeFields"
        :reload-on-success="reloadOnSuccess"
        @success="emit('success')"
      />
    </template>
  </NuxtModal>

  <div v-else class="grid min-h-dvh place-items-center p-4">
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
