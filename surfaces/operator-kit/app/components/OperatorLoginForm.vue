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
// Alvo de toque do `main` (44 px; 48 em tablet touch) só nas páginas que vestem a
// suíte (`suite-page:`, os sete apps não migrados): o Gestor fica no tamanho oficial.
// Os campos ganham o mesmo envelope pelo `app.config` (input `lg`/`xl`); o botão, aqui.
const touchAction = computed(() =>
  props.largeFields ? "suite-page:min-h-action" : "suite-page:min-h-control",
);
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
      <!-- Decorativo: o título do diálogo já diz o app. `alt=""` tira a imagem da
           árvore de acessibilidade (axe `image-alt` reprova img sem alt). -->
      <NuxtAvatar class="mx-auto" size="3xl" :src="iconSrc" :icon="icon" alt="" />
      <div v-if="heading" class="grid gap-1.5 text-center">
        <h1 class="text-lg font-semibold">{{ title }}</h1>
        <p class="text-sm text-muted-foreground">{{ description }}</p>
      </div>

      <div class="grid gap-3 text-left">
        <!-- O erro é dos DOIS campos (não se sabe qual errou). O FormField é quem
             escreve `aria-invalid`/`aria-describedby` no input (sobrescreve o que se
             passa à mão), então o erro entra por ele: `error` booleano marca o campo e
             o slot `#error` dá ao leitor de tela o texto que o descreve. O texto visível
             e anunciado é um só, o Alert abaixo (região viva assertiva, o mesmo anúncio de
             um papel de alerta, sem recriar papel ARIA sobre o componente oficial). -->
        <NuxtFormField label="Usuário" :error="Boolean(error)">
          <NuxtInput
            id="operator-login-username"
            ref="usernameInput"
            v-model="username"
            class="w-full"
            type="text"
            autocomplete="username"
            autocapitalize="none"
            autocorrect="off"
            placeholder="Usuário"
            :disabled="pending"
            :size="largeFields ? 'xl' : 'lg'"
          />
          <template #error>
            <span class="sr-only">{{ error }}</span>
          </template>
        </NuxtFormField>
        <NuxtFormField label="Senha" :error="Boolean(error)">
          <NuxtInput
            id="operator-login-password"
            v-model="password"
            class="w-full"
            type="password"
            autocomplete="current-password"
            placeholder="Senha"
            :disabled="pending"
            :size="largeFields ? 'xl' : 'lg'"
          />
          <template #error>
            <span class="sr-only">{{ error }}</span>
          </template>
        </NuxtFormField>
        <NuxtAlert
          v-if="error"
          id="operator-login-error"
          aria-live="assertive"
          aria-atomic="true"
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
        :class="touchAction"
        :loading="pending"
        :disabled="pending || !username.trim() || !password"
        :label="pending ? 'Entrando…' : 'Entrar'"
      />
    </div>
  </NuxtForm>
</template>
