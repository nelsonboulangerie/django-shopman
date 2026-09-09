<script setup lang="ts">
// Entrada por SENHA — no próprio app, sem bounce pro Django admin. Um formulário:
// usuário + senha → POST /operator/login/ (reusa a auth do Django, grava o cookie
// .<zona> que vale em todos os apps de operador) → recarrega já dentro. Uma tela,
// um submit. (Antes: pular pro admin, logar, voltar, "Já entrei" — um inferno.)
//
// A sessão que sai daqui é a DA PESSOA, igual à do PIN: não existe login "do
// aparelho". Este é o caminho de quem tem senha — quem provisiona a estação, e o
// aparelho pessoal do gestor. No balcão, quem pede identificação é o
// <OperatorLock>, com PIN ou crachá.
defineProps<{ expired?: boolean }>();

const username = ref("");
const password = ref("");
const pending = ref(false);
const error = ref("");
const dialog = ref<HTMLFormElement | null>(null);
const usernameInput = ref<HTMLInputElement | null>(null);

const fieldDescription = computed(() =>
  error.value
    ? "operator-login-description operator-login-error"
    : "operator-login-description",
);

function trapFocus(event: KeyboardEvent) {
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

async function submit() {
  if (pending.value) return;
  error.value = "";
  pending.value = true;
  try {
    await $fetch("/api/v1/backstage/operator/login/", {
      method: "POST",
      credentials: "same-origin",
      body: { username: username.value.trim(), password: password.value },
    });
    // Primeiro reconcilia a sessão mantendo o gate fechado pelo sinal `expired`;
    // só depois o libera. Assim a rota/draft sobrevivem sem um instante de mount
    // protegido apoiado na identidade stale.
    await refreshNuxtData("operator-session");
    useOperatorSession().reset();
  } catch (err) {
    error.value = httpErrorMessage(
      err,
      "Não foi possível entrar. Confira usuário e senha.",
    );
    pending.value = false;
  }
}

onMounted(() => nextTick(() => usernameInput.value?.focus()));
</script>

<template>
  <main class="fixed inset-0 z-[100] grid place-items-center bg-background p-4">
    <form
      ref="dialog"
      class="w-full max-w-sm rounded-xl border bg-card p-6 shadow-lg"
      role="dialog"
      aria-modal="true"
      aria-labelledby="operator-login-title"
      aria-describedby="operator-login-description"
      @submit.prevent="submit"
      @keydown.tab="trapFocus"
    >
      <div
        class="mx-auto mb-3 grid size-12 place-items-center rounded-full border bg-muted"
      >
        <Icon name="lucide:log-in" class="size-6 text-muted-foreground" />
      </div>
      <h1 id="operator-login-title" class="text-center text-lg font-bold">
        {{ expired ? "Sua sessão terminou" : "Entre para operar" }}
      </h1>
      <p
        id="operator-login-description"
        class="mt-1 text-center text-sm text-muted-foreground"
      >
        {{
          expired
            ? "Entre novamente. Seu rascunho e sua decisão ainda não enviada foram preservados."
            : "Acesse com sua conta autorizada."
        }}
      </p>

      <div class="mt-4 space-y-2.5">
        <label
          for="operator-login-username"
          class="block text-sm font-semibold"
        >
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
          :aria-describedby="fieldDescription"
          :aria-invalid="error ? 'true' : undefined"
          :disabled="pending"
          class="h-11 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
        />
        <label
          for="operator-login-password"
          class="block text-sm font-semibold"
        >
          Senha
        </label>
        <input
          id="operator-login-password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          :aria-describedby="fieldDescription"
          :aria-invalid="error ? 'true' : undefined"
          :disabled="pending"
          class="h-11 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
        />
      </div>

      <p
        v-if="error"
        id="operator-login-error"
        class="mt-2 text-sm text-destructive"
        role="alert"
      >
        {{ error }}
      </p>

      <button
        type="submit"
        :disabled="pending || !username.trim() || !password"
        :aria-busy="pending"
        class="mt-4 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md border border-transparent bg-primary px-3 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
      >
        <Icon
          :name="pending ? 'line-md:loading-loop' : 'lucide:log-in'"
          class="size-4 motion-reduce:animate-none"
        />
        {{ pending ? "Entrando…" : "Entrar" }}
      </button>
    </form>
  </main>
</template>
