<script setup lang="ts">
// Painel do Marketing — a fila de decisões do gestor.
//
// Ordem deliberada: primeiro o que PEDE decisão (pendentes), depois o que já
// saiu. Números do dia por último: contexto, não protagonista.
import { audienceSummary, announcementOutcome, shortDateTime } from "~/presentation/campaign";
import type { AnnouncementEdits } from "~/types/campaign";

// Mesma leitura do histórico: sucesso PARCIAL não se disfarça de pendente.
// Se o Google saiu e o Instagram falhou, a linha precisa chamar atenção.
const OUTCOME_META = {
  published: { icon: "lucide:check-circle-2", class: "text-emerald-600" },
  partial: { icon: "lucide:alert-circle", class: "text-amber-600" },
  failed: { icon: "lucide:x-circle", class: "text-destructive" },
  pending: { icon: "lucide:clock", class: "text-muted-foreground" },
} as const;

const { reachLimits, pendingPosts, recentPosts, stats, loading, error, refresh, approve, reject, aiAssistAvailable } =
  useCampaignBoard();
const { platforms } = useCampaigns();

// Escolher o template do WhatsApp AQUI: é config, mas é config da operação, e mandar o
// gestor para outro aplicativo para desbloquear o próprio anúncio é atrito sem motivo.
const waTemplate = useWhatsAppTemplate();
const choosingTemplate = ref(false);
const savingTemplate = ref(false);

async function openTemplatePicker() {
  choosingTemplate.value = true;
  await waTemplate.load();
}

async function onChooseTemplate(flowNs: string) {
  savingTemplate.value = true;
  const ok = await waTemplate.choose(flowNs);
  savingTemplate.value = false;
  if (ok) {
    choosingTemplate.value = false;
    await refresh();
  }
}

// Teste no próprio WhatsApp: o destinatário é digitado de propósito. Sem lista de
// clientes aqui, o gestor não erra o alvo por um clique.
const testRecipient = ref("");
const testSku = ref("");
const testName = ref("");

async function onSendTest() {
  if (!testRecipient.value.trim()) return;
  await waTemplate.sendTest(testRecipient.value.trim(), {
    sku: testSku.value.trim(),
    name: testName.value.trim(),
  });
}

const busyPk = ref<number | null>(null);
const rejecting = ref<number | null>(null);
const rejectReason = ref("");

async function onApprove(pk: number, edits: AnnouncementEdits) {
  busyPk.value = pk;
  await approve(pk, edits);
  busyPk.value = null;
}

async function confirmReject() {
  const pk = rejecting.value;
  if (pk === null) return;
  const reason = rejectReason.value.trim();
  busyPk.value = pk;
  rejecting.value = null;
  rejectReason.value = "";
  await reject(pk, reason);
  busyPk.value = null;
}

useHead({ title: "Painel · Marketing" });
</script>

<template>
  <main class="mx-auto w-full max-w-4xl flex-1 px-4 py-6">
    <div class="mb-5 flex items-center gap-3">
      <h1 class="text-xl font-bold">Painel</h1>
      <!-- ⚠️ Isto vivia SÓ dentro do aviso de alcance, e o aviso só aparece quando alguma
           campanha ativa usa WhatsApp e falta template. Ou seja: config escondida atrás de
           um alerta, invisível justo depois de configurada — o gestor não tinha como
           trocar nem conferir. Config que existe tem de ter porta fixa. -->
      <button
        type="button"
        class="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm text-muted-foreground transition hover:bg-muted"
        @click="openTemplatePicker()"
      >
        <Icon name="lucide:message-square-dot" class="size-3.5" />
        WhatsApp
      </button>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm text-muted-foreground transition hover:bg-muted"
        @click="refresh()"
      >
        <Icon name="lucide:refresh-cw" class="size-3.5" />
        Atualizar
      </button>
    </div>

    <!-- Entrega por plataforma, ANTES de publicar. Bloqueio e limitação não podem
         parecer iguais: um diz "nada sai por aqui", o outro diz "sai, mas não para
         todo mundo". Antes disto o aviso existia só no `check --deploy`, que o gestor
         nunca lê — e só sabia falar de WhatsApp. -->
    <section
      v-if="reachLimits.length"
      class="mb-5 space-y-2"
      aria-label="Situação de entrega por plataforma"
    >
      <div
        v-for="limit in reachLimits"
        :key="limit.code"
        class="flex items-start gap-2.5 rounded-lg border px-3 py-2.5"
        :class="limit.blocking
          ? 'border-destructive/40 bg-destructive/5'
          : 'border-amber-500/40 bg-amber-500/5'"
        role="status"
      >
        <Icon
          :name="limit.blocking ? 'lucide:circle-slash' : 'lucide:triangle-alert'"
          class="mt-0.5 size-4 shrink-0"
          :class="limit.blocking ? 'text-destructive' : 'text-amber-600'"
        />
        <div class="min-w-0">
          <p class="text-sm font-semibold">{{ limit.title }}</p>
          <p class="mt-0.5 text-sm text-muted-foreground">{{ limit.detail }}</p>
          <!-- Ação acionável quando é DAQUI que se resolve; texto quando o conserto
               está fora do alcance do gestor (credencial de plataforma, p.ex.). -->
          <button
            v-if="limit.platform === 'whatsapp' && !limit.blocking"
            type="button"
            class="mt-1.5 inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs font-semibold transition hover:bg-muted"
            @click="openTemplatePicker()"
          >
            <Icon name="lucide:settings-2" class="size-3.5" />
            Escolher o template aprovado
          </button>
          <p v-else-if="limit.action" class="mt-1 text-xs font-medium text-muted-foreground">
            {{ limit.action }}
          </p>
        </div>
      </div>
    </section>

    <!-- Escolha do template: painel próprio, aberto pelo aviso que ele resolve -->
    <UiSheet :open="choosingTemplate" @update:open="(v) => { if (!v) choosingTemplate = false }">
      <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg">
        <UiSheetHeader class="border-b border-border">
          <UiSheetTitle>Template aprovado do WhatsApp</UiSheetTitle>
          <UiSheetDescription>
            Com um template aprovado, o anúncio alcança quem não conversou nas últimas
            24 horas. Sem ele, só a janela.
          </UiSheetDescription>
        </UiSheetHeader>

        <div class="flex-1 overflow-y-auto p-4">
          <div v-if="waTemplate.loading.value" class="space-y-2" aria-busy="true">
            <div v-for="n in 3" :key="n" class="h-10 animate-pulse rounded-md bg-muted"></div>
          </div>

          <!-- Não conseguir perguntar à plataforma NÃO é "não há template": dizer o que
               é verdade em vez de sugerir uma conclusão errada. -->
          <div
            v-else-if="!waTemplate.canList.value"
            class="rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-sm"
          >
            <p class="font-semibold">Não foi possível consultar os templates agora</p>
            <p class="mt-1 text-muted-foreground">
              A plataforma não respondeu. Tente de novo em instantes; nada foi alterado.
            </p>
          </div>

          <div v-else class="space-y-1.5">
            <button
              type="button"
              class="flex w-full items-start gap-2 rounded-lg border px-3 py-2.5 text-left transition hover:bg-muted"
              :class="waTemplate.current.value === '' ? 'border-primary' : 'border-border'"
              :disabled="savingTemplate"
              @click="onChooseTemplate('')"
            >
              <Icon name="lucide:circle-slash" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <span>
                <span class="block text-sm font-medium">Sem template</span>
                <span class="block text-xs text-muted-foreground">
                  Texto livre — alcança só quem conversou nas últimas 24 horas.
                </span>
              </span>
            </button>

            <button
              v-for="option in waTemplate.available.value"
              :key="option.ns"
              type="button"
              class="flex w-full items-start gap-2 rounded-lg border px-3 py-2.5 text-left transition hover:bg-muted"
              :class="waTemplate.current.value === option.ns ? 'border-primary' : 'border-border'"
              :disabled="savingTemplate"
              @click="onChooseTemplate(option.ns)"
            >
              <Icon name="lucide:file-check-2" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <span class="min-w-0">
                <span class="block truncate text-sm font-medium">{{ option.name }}</span>
                <span class="block truncate font-mono text-xs text-muted-foreground">
                  {{ option.ns }}
                </span>
              </span>
            </button>
          </div>

          <!-- Conferir vale mais que supor: aceito pelo provedor não é o mesmo que
               vibrou no aparelho. Um número por vez, digitado, e sem lista de clientes
               por perto — não é caminho para alcançar ninguém além de você. -->
          <section class="mt-4 border-t border-border pt-4">
            <h3 class="text-sm font-semibold">Testar no meu WhatsApp</h3>
            <p class="mt-1 text-xs text-muted-foreground">
              Manda uma mensagem só para você, com as variáveis preenchidas de verdade.
            </p>

            <div class="mt-3 space-y-2">
              <div>
                <label for="test-recipient" class="mb-1 block text-xs font-medium">
                  WhatsApp ou subscriber
                </label>
                <input
                  id="test-recipient"
                  v-model="testRecipient"
                  type="text"
                  placeholder="4605528796186498"
                  class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                >
              </div>
              <div class="grid grid-cols-2 gap-2">
                <div>
                  <label for="test-sku" class="mb-1 block text-xs font-medium">SKU (opcional)</label>
                  <input
                    id="test-sku"
                    v-model="testSku"
                    type="text"
                    placeholder="BAGUETE"
                    class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                  >
                </div>
                <div>
                  <label for="test-name" class="mb-1 block text-xs font-medium">Nome (opcional)</label>
                  <input
                    id="test-name"
                    v-model="testName"
                    type="text"
                    placeholder="Pablo"
                    class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                  >
                </div>
              </div>
              <button
                type="button"
                :disabled="!testRecipient.trim() || waTemplate.testing.value"
                class="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground transition disabled:opacity-40"
                @click="onSendTest"
              >
                <Icon
                  :name="waTemplate.testing.value ? 'lucide:loader-circle' : 'lucide:send'"
                  class="size-4"
                  :class="waTemplate.testing.value ? 'animate-spin' : ''"
                />
                {{ waTemplate.testing.value ? "Enviando…" : "Enviar teste" }}
              </button>
            </div>

            <!-- O que o template REALMENTE recebeu. Campo vazio aqui explica variável
                 vazia no aparelho, sem o gestor ter que adivinhar. -->
            <dl
              v-if="Object.keys(waTemplate.testFields.value).length"
              class="mt-3 space-y-1 rounded-lg bg-muted/40 p-3 text-xs"
            >
              <div
                v-for="(value, key) in waTemplate.testFields.value"
                :key="key"
                class="flex gap-2"
              >
                <dt class="shrink-0 font-mono text-muted-foreground">{{ key }}</dt>
                <dd class="min-w-0 flex-1 truncate">
                  {{ value || "— vazio, o template renderiza sem" }}
                </dd>
              </div>
            </dl>
          </section>
        </div>
      </UiSheetContent>
    </UiSheet>

    <!-- Números do dia -->
    <section v-if="stats" class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Números de hoje">
      <div class="rounded-lg border border-border bg-card px-3 py-2.5">
        <p class="text-2xl font-bold">{{ stats.pending_count }}</p>
        <p class="text-xs text-muted-foreground">aguardando você</p>
      </div>
      <div class="rounded-lg border border-border bg-card px-3 py-2.5">
        <p class="text-2xl font-bold">{{ stats.published_today }}</p>
        <p class="text-xs text-muted-foreground">publicados hoje</p>
      </div>
      <div class="rounded-lg border border-border bg-card px-3 py-2.5">
        <p class="text-2xl font-bold">{{ stats.audience_reached_today }}</p>
        <p class="text-xs text-muted-foreground">clientes alcançados</p>
      </div>
      <div
        class="rounded-lg border px-3 py-2.5"
        :class="stats.failed_today > 0 ? 'border-destructive/40 bg-destructive/5' : 'border-border bg-card'"
      >
        <p class="text-2xl font-bold" :class="stats.failed_today > 0 ? 'text-destructive' : ''">
          {{ stats.failed_today }}
        </p>
        <p class="text-xs text-muted-foreground">falharam</p>
      </div>
    </section>

    <!-- Erro de carga: o painel não finge estar vazio quando não conseguiu ler -->
    <div
      v-if="error"
      class="mb-6 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
      role="alert"
    >
      <p class="font-semibold text-destructive">Não conseguimos carregar o painel.</p>
      <button type="button" class="mt-1 underline underline-offset-2" @click="refresh()">
        Tentar de novo
      </button>
    </div>

    <!-- Pendentes -->
    <section class="mb-8">
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Aguardando decisão
      </h2>

      <div v-if="loading && pendingPosts.length === 0" class="space-y-3" aria-busy="true">
        <div v-for="n in 2" :key="n" class="h-48 animate-pulse rounded-xl bg-muted"></div>
      </div>

      <div
        v-else-if="pendingPosts.length === 0"
        class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
      >
        <Icon name="lucide:coffee" class="mx-auto size-8 text-muted-foreground" />
        <p class="mt-2 font-semibold">Nada esperando por você</p>
        <p class="mt-1 text-sm text-muted-foreground">
          Quando uma fornada terminar, o anúncio aparece aqui para revisão.
        </p>
        <NuxtLink
          to="/rules"
          class="mt-3 inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition hover:bg-muted"
        >
          <Icon name="lucide:sliders-horizontal" class="size-4" />
          Ver as regras
        </NuxtLink>
      </div>

      <div v-else class="space-y-4">
        <AnnouncementCard
          v-for="announcement in pendingPosts"
          :key="announcement.pk"
          :announcement="announcement"
          :platform-options="platforms"
          :busy="busyPk === announcement.pk"
          :ai-assist-available="aiAssistAvailable"
          @approve="onApprove"
          @reject="(pk) => { rejecting = pk; rejectReason = '' }"
        />
      </div>
    </section>

    <!-- Publicados nas últimas 24h -->
    <section v-if="recentPosts.length > 0">
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Últimas 24 horas
      </h2>
      <ul class="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
        <li v-for="announcement in recentPosts" :key="announcement.pk" class="flex items-start gap-3 px-4 py-3">
          <Icon
            :name="OUTCOME_META[announcementOutcome(announcement.platform_results)].icon"
            class="mt-0.5 size-4 shrink-0"
            :class="OUTCOME_META[announcementOutcome(announcement.platform_results)].class"
          />
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm">{{ announcement.body }}</p>
            <p class="mt-0.5 text-xs text-muted-foreground">
              {{ shortDateTime(announcement.published_at || announcement.created_at) }} ·
              {{ audienceSummary(announcement.audience) }}
            </p>
          </div>
        </li>
      </ul>
      <NuxtLink
        to="/history"
        class="mt-3 inline-flex items-center gap-1.5 text-sm text-muted-foreground underline underline-offset-2 hover:text-foreground"
      >
        Ver o histórico completo
        <Icon name="lucide:arrow-right" class="size-3.5" />
      </NuxtLink>
    </section>

    <!-- Recusar é irreversível: confirma antes -->
    <UiDialog :open="rejecting !== null" @update:open="(v) => { if (!v) rejecting = null }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Recusar este anúncio?</UiDialogTitle>
          <UiDialogDescription>
            Ele não vai para nenhuma plataforma e não volta para a fila. A fornada segue
            normalmente.
          </UiDialogDescription>
        </UiDialogHeader>
        <!-- Opcional de propósito: campo obrigatório aqui só produziria "não" digitado
             com pressa. Quando o gestor escreve, a recusa passa a explicar a campanha. -->
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
            @keyup.enter="confirmReject"
          >
        </div>
        <UiDialogFooter>
          <button
            type="button"
            class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted"
            @click="rejecting = null"
          >
            Manter na fila
          </button>
          <button
            type="button"
            class="rounded-md bg-destructive px-3 py-2 text-sm font-semibold text-destructive-foreground transition hover:bg-destructive/90"
            @click="confirmReject"
          >
            Recusar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
