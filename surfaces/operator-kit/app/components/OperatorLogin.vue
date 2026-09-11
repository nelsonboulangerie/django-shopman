<script setup lang="ts">
type LoginMode = "overlay" | "page";

const props = withDefaults(
  defineProps<{
    title?: string;
    description?: string;
    icon?: string;
    loginUrl?: string;
    mode?: LoginMode;
    largeFields?: boolean;
    reloadOnSuccess?: boolean;
    expired?: boolean;
  }>(),
  {
    icon: "lucide:log-in",
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
const dialog = ref<HTMLFormElement | null>(null);
const usernameInput = ref<HTMLInputElement | null>(null);
const { reset: resetSession } = useOperatorSession();

const displayTitle = computed(() =>
  props.title ?? (props.expired ? "Sua sessão terminou" : "Entre para operar"),
);
const displayDescription = computed(() =>
  props.description ??
  (props.expired
    ? "Entre novamente. Seu rascunho e sua decisão ainda não enviada foram preservados."
    : "Acesse com sua conta autorizada."),
);
const fieldDescription = computed(() =>
  error.value
    ? "operator-login-description operator-login-error"
    : "operator-login-description",
);

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

onMounted(() => nextTick(() => usernameInput.value?.focus()));

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
    <form
      ref="dialog"
      class="grid w-full max-w-sm gap-4 text-center"
      :class="mode === 'overlay' ? 'rounded-md border bg-card p-6 shadow-lg' : ''"
      :role="mode === 'overlay' ? 'dialog' : undefined"
      :aria-modal="mode === 'overlay' ? 'true' : undefined"
      aria-labelledby="operator-login-title"
      aria-describedby="operator-login-description"
      @submit.prevent="submit"
      @keydown.tab="trapFocus"
    >
      <div class="mx-auto grid size-14 place-items-center rounded-full border bg-muted">
        <Icon :name="icon" class="size-7 text-muted-foreground" />
      </div>
      <div class="grid gap-1.5">
        <h2 id="operator-login-title" class="text-lg font-semibold">
          {{ displayTitle }}
        </h2>
        <p id="operator-login-description" class="text-sm text-muted-foreground">
          {{ displayDescription }}
        </p>
      </div>

      <div class="grid gap-2.5 text-left">
        <label for="operator-login-username" class="text-sm font-semibold">
          Usuário
        </label>
        <input
          id="operator-login-username"
          ref="usernameInput"
          v-model="username"
          type="text"
          autocomplete="username"
          autocapitalize="none"
          autocorrect="off"
          placeholder="Usuário"
          aria-label="Usuário"
          :aria-describedby="fieldDescription"
          :aria-invalid="error ? 'true' : undefined"
          :disabled="pending"
          class="w-full rounded-md border bg-background px-3 outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-60"
          :class="largeFields ? 'h-12 text-base' : 'h-11 text-sm'"
        >
        <label for="operator-login-password" class="text-sm font-semibold">
          Senha
        </label>
        <input
          id="operator-login-password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="Senha"
          aria-label="Senha"
          :aria-describedby="fieldDescription"
          :aria-invalid="error ? 'true' : undefined"
          :disabled="pending"
          class="w-full rounded-md border bg-background px-3 outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-60"
          :class="largeFields ? 'h-12 text-base' : 'h-11 text-sm'"
        >
        <p
          v-if="error"
          id="operator-login-error"
          class="text-sm text-destructive"
          role="alert"
        >
          {{ error }}
        </p>
      </div>

      <button
        type="submit"
        :disabled="pending || !username.trim() || !password"
        :aria-busy="pending"
        class="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
        :class="largeFields ? 'h-14' : 'h-11'"
      >
        <Icon :name="pending ? 'line-md:loading-loop' : 'lucide:log-in'" class="size-5" />
        {{ pending ? "Entrando…" : "Entrar" }}
      </button>
    </form>
  </div>
</template>
