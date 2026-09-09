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
    error.value = httpErrorMessage(err, "Não foi possível entrar. Confira usuário e senha.");
    pending.value = false;
  }
}
</script>

<template>
  <div class="fixed inset-0 z-[100] grid place-items-center bg-background p-4">
    <form
      class="w-full max-w-sm rounded-xl border bg-card p-6 shadow-lg"
      role="dialog"
      aria-modal="true"
      aria-labelledby="operator-login-title"
      aria-describedby="operator-login-description"
      @submit.prevent="submit"
    >
      <div class="mx-auto mb-3 grid size-12 place-items-center rounded-full border bg-muted">
        <Icon name="lucide:log-in" class="size-6 text-muted-foreground" />
      </div>
      <h2 id="operator-login-title" class="text-center text-lg font-bold">
        {{ expired ? "Sua sessão terminou" : "Entre para operar" }}
      </h2>
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
        <input
          v-model="username"
          type="text"
          autocomplete="username"
          autocapitalize="none"
          autocorrect="off"
          placeholder="Usuário"
          aria-label="Usuário"
          :disabled="pending"
          class="h-11 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
        >
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="Senha"
          aria-label="Senha"
          :disabled="pending"
          class="h-11 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
        >
      </div>

      <p v-if="error" class="mt-2 text-sm text-destructive" role="alert">{{ error }}</p>

      <button
        type="submit"
        :disabled="pending || !username.trim() || !password"
        class="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md border border-transparent bg-primary px-3 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
      >
        <Icon :name="pending ? 'line-md:loading-loop' : 'lucide:log-in'" class="size-4" />
        {{ pending ? "Entrando…" : "Entrar" }}
      </button>
    </form>
  </div>
</template>
