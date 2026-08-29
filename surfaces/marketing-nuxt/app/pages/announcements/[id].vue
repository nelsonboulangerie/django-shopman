<script setup lang="ts">
// Um announcement, sozinho na tela — destino do link da notificação acionável
// (``UserNotification.action_url`` = /campaign/announcements/<pk>/).
//
// O gestor recebe o aviso no celular, toca e cai direto na decisão. Mesmo card
// do painel: uma única forma de decidir, um único lugar para acertar.
import { approvalBody, approvalMessage } from "~/presentation/campaign";
import type { Announcement, AnnouncementEdits } from "~/types/campaign";

const route = useRoute();
const pk = computed(() => Number(route.params.id));

const { data, refresh, pending, error } = await useFetch<{ announcement: Announcement }>(
  () => `/api/v1/backstage/marketing/announcements/${pk.value}/`,
  { key: () => `announcement-${pk.value}` },
);
const { platforms } = useCampaigns();

const announcement = computed(() => data.value?.announcement);
const busy = ref(false);
const confirmingReject = ref(false);
const rejectReason = ref("");

async function decide(
  action: "approve" | "reject",
  body: AnnouncementEdits | { reason: string } = {},
) {
  busy.value = true;
  try {
    // As duas decisões — o que ENVIAR e o que DIZER depois — são as mesmas do painel, e
    // moram em `~/presentation/campaign`. Repeti-las aqui foi como esta tela e o painel
    // passaram a mentir, cada um do seu jeito, sobre o mesmo botão.
    const corpo = action === "approve" ? approvalBody(body as AnnouncementEdits) : body;
    const resposta = await $fetch<{ scheduled?: boolean }>(
      `/api/v1/backstage/marketing/announcements/${pk.value}/${action}/`,
      { method: "POST", body: corpo },
    );
    useSonner.success(action === "reject" ? "Anúncio recusado." : approvalMessage(resposta));
    await navigateTo("/");
  } catch (err) {
    useSonner.error(httpErrorMessage(err, "Não foi possível concluir. Tente de novo."));
    await refresh();
  } finally {
    busy.value = false;
  }
}

useHead({ title: "Anúncio · Marketing" });
</script>

<template>
  <main class="mx-auto w-full max-w-2xl flex-1 px-4 py-6">
    <NuxtLink
      to="/"
      class="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition hover:text-foreground"
    >
      <Icon name="lucide:arrow-left" class="size-4" />
      Voltar ao painel
    </NuxtLink>

    <div v-if="pending && !announcement" class="h-64 animate-pulse rounded-xl bg-muted" aria-busy="true"></div>

    <div
      v-else-if="error || !announcement"
      class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon name="lucide:search-x" class="mx-auto size-8 text-muted-foreground" />
      <p class="mt-2 font-semibold">Não encontramos este announcement</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Ele pode ter expirado ou já ter sido decidido por outra pessoa.
      </p>
      <NuxtLink
        to="/"
        class="mt-3 inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition hover:bg-muted"
      >
        Ver o painel
      </NuxtLink>
    </div>

    <template v-else>
      <!-- Já decidido: mostra o estado em vez de oferecer botões que não valem mais -->
      <div
        v-if="announcement.status !== 'pending_review'"
        class="mb-4 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm"
      >
        <p class="font-semibold">Este announcement já foi decidido.</p>
        <p class="mt-0.5 text-muted-foreground">
          Situação: {{ announcement.status_label }}<template v-if="announcement.approved_by">
            · por {{ announcement.approved_by }}</template>
        </p>
      </div>

      <AnnouncementCard
        v-if="announcement.status === 'pending_review'"
        :announcement="announcement"
        :platform-options="platforms"
        :busy="busy"
        @approve="(_, edits) => decide('approve', edits)"
        @reject="confirmingReject = true; rejectReason = ''"
      />

      <article v-else class="rounded-xl border border-border bg-card p-4">
        <p class="whitespace-pre-line text-sm">{{ announcement.body }}</p>
        <!-- Recusa é decisão de alguém, e a decisão precisa ser legível depois. Sem
             isto, o motivo ficaria só no banco. -->
        <p
          v-if="announcement.status === 'rejected'"
          class="mt-3 flex items-start gap-1.5 border-t border-border pt-3 text-xs text-muted-foreground"
        >
          <Icon name="lucide:circle-slash" class="mt-0.5 size-3.5 shrink-0" />
          <span>
            Recusado{{ announcement.rejected_by ? ` por ${announcement.rejected_by}` : "" }}<template
              v-if="announcement.rejected_reason"
            >: {{ announcement.rejected_reason }}</template>
          </span>
        </p>
      </article>
    </template>

    <UiDialog :open="confirmingReject" @update:open="(v) => (confirmingReject = v)">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Recusar este anúncio?</UiDialogTitle>
          <UiDialogDescription>
            Ele não vai para nenhuma plataforma e não volta para a fila.
          </UiDialogDescription>
        </UiDialogHeader>
        <div>
          <label for="reject-reason" class="mb-1 block text-sm font-medium">
            Motivo (opcional)
          </label>
          <input
            id="reject-reason"
            v-model="rejectReason"
            type="text"
            maxlength="200"
            placeholder="Foto ruim, texto errado, produto acabou…"
            class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
          >
        </div>
        <UiDialogFooter>
          <button
            type="button"
            class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted"
            @click="confirmingReject = false"
          >
            Manter na fila
          </button>
          <button
            type="button"
            class="rounded-md bg-destructive px-3 py-2 text-sm font-semibold text-destructive-foreground transition hover:bg-destructive/90"
            @click="confirmingReject = false; decide('reject', { reason: rejectReason.trim() })"
          >
            Recusar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
