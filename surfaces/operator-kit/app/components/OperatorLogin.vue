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
const username = ref("");
const password = ref("");
const pending = ref(false);
const error = ref("");
const dialog = ref<HTMLElement | null>(null);
const usernameInput = ref<{ inputRef?: HTMLInputElement } | null>(null);
const { reset: resetSession } = useOperatorSession();
// Mesma identidade do rail: o PNG e o ícone de recurso saem de `app-identity.json` pelo
// `runtimeConfig`. O app sem a capability (harness de teste) cai no cadeado genérico.
const identity = (useRuntimeConfig().public?.operatorPwa as { identity?: { icon: string; iconSrc: string } } | undefined)?.identity;
const icon = computed(() => props.icon || (identity?.icon ? `lucide:${identity.icon}` : "lucide:log-in"));
const iconSrc = computed(() => props.iconSrc || identity?.iconSrc);

const displayTitle = computed(() =>
  props.title ?? (props.expired ? "Sua sessão terminou" : "Entre para operar"),
);
const displayDescription = computed(() =>
  props.description ??
  (props.expired
    ? "Entre novamente. Seu rascunho e sua decisão ainda não enviada foram preservados."
    : "Acesse com sua conta autorizada."),
);
const fieldDescription = computed(() => "operator-login-description");

function trapFocus(event: KeyboardEvent) {
  if (props.mode !== "overlay") return;
  const focusable = Array.from(
    dialog.value?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
    ) ?? [],
  );
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first?.focus();
  }
}

onMounted(() => nextTick(() => usernameInput.value?.inputRef?.focus()));

async function submit() {
  if (pending.value) return;
  error.value = "";
  pending.value = true;
  try {
    await $fetch(props.loginUrl, {
      method: "POST",
      credentials: "same-origin",
      body: { username: username.value.trim(), password: password.value },
    });
    await refreshNuxtData("operator-session");
    resetSession();
    emit("success");
    if (props.reloadOnSuccess && import.meta.client) {
      window.location.reload();
    } else {
      pending.value = false;
    }
  } catch (cause) {
    error.value = httpErrorMessage(
      cause,
      "Não foi possível entrar. Confira usuário e senha.",
    );
    pending.value = false;
  }
}
</script>

<template>
  <div
    :class="
      mode === 'overlay'
        ? 'fixed inset-0 z-[100] grid place-items-center bg-background p-4'
        : 'grid min-h-dvh place-items-center p-4'
    "
  >
    <NuxtCard
      ref="dialog"
      as="form"
      class="w-full max-w-sm text-center"
      :role="mode === 'overlay' ? 'dialog' : undefined"
      :aria-modal="mode === 'overlay' ? 'true' : undefined"
      aria-labelledby="operator-login-title"
      aria-describedby="operator-login-description"
      @submit.prevent="submit"
      @keydown.tab="trapFocus"
    >
      <NuxtAvatar class="mx-auto" size="3xl" :src="iconSrc" :icon="icon" />
      <div class="grid gap-1.5">
        <h2 id="operator-login-title" class="text-lg font-semibold">
          {{ displayTitle }}
        </h2>
        <p id="operator-login-description" class="text-sm text-muted-foreground">
          {{ displayDescription }}
        </p>
      </div>

      <div class="grid gap-2.5 text-left">
        <NuxtFormField label="Usuário">
        <NuxtInput
          id="operator-login-username"
          ref="usernameInput"
          v-model="username"
          type="text"
          autocomplete="username"
          autocapitalize="none"
          autocorrect="off"
          placeholder="Usuário"
          :aria-describedby="fieldDescription"
          :aria-invalid="error ? 'true' : undefined"
          :disabled="pending"
          :size="largeFields ? 'xl' : 'lg'"
          class="w-full"
        />
        </NuxtFormField>
        <NuxtFormField label="Senha">
        <NuxtInput
          id="operator-login-password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="Senha"
          :aria-describedby="fieldDescription"
          :aria-invalid="error ? 'true' : undefined"
          :disabled="pending"
          :size="largeFields ? 'xl' : 'lg'"
          class="w-full"
        />
        </NuxtFormField>
        <NuxtAlert v-if="error" color="error" :title="error" data-operator-login-error />
      </div>

      <NuxtButton
        type="submit"
        block
        icon="i-lucide-log-in"
        :size="largeFields ? 'xl' : 'lg'"
        :loading="pending"
        :disabled="pending || !username.trim() || !password"
        :label="pending ? 'Entrando…' : 'Entrar'"
      />
    </NuxtCard>
  </div>
</template>
