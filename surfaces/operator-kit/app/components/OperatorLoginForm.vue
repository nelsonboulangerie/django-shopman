<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    title: string;
    description: string;
    icon: string;
    iconSrc?: string;
    loginUrl: string;
    largeFields?: boolean;
    reloadOnSuccess?: boolean;
    heading?: boolean;
  }>(),
  {
    iconSrc: "",
    largeFields: false,
    reloadOnSuccess: true,
    heading: false,
  },
);

const emit = defineEmits<{ success: [] }>();
const username = ref("");
const password = ref("");
const pending = ref(false);
const error = ref("");
const usernameInput = ref<{ inputRef?: HTMLInputElement } | null>(null);
const { reset: resetSession } = useOperatorSession();

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
  <NuxtForm :state="{ username, password }" @submit="submit">
    <div class="flex flex-col gap-4">
      <NuxtAvatar class="mx-auto" size="3xl" :src="iconSrc" :icon="icon" />
      <div v-if="heading" class="grid gap-1.5 text-center">
        <h1 class="text-lg font-semibold">{{ title }}</h1>
        <p class="text-sm text-muted-foreground">{{ description }}</p>
      </div>

      <div class="grid gap-3 text-left">
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
            :aria-invalid="error ? 'true' : undefined"
            :disabled="pending"
            :size="largeFields ? 'xl' : 'lg'"
          />
        </NuxtFormField>
        <NuxtFormField label="Senha">
          <NuxtInput
            id="operator-login-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="Senha"
            :aria-invalid="error ? 'true' : undefined"
            :disabled="pending"
            :size="largeFields ? 'xl' : 'lg'"
          />
        </NuxtFormField>
        <NuxtAlert
          v-if="error"
          color="error"
          variant="subtle"
          :title="error"
          data-operator-login-error
        />
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
    </div>
  </NuxtForm>
</template>
