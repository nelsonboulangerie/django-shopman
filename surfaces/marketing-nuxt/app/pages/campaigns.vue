<script setup lang="ts">
// Campanhas — o que a operação dispara sozinha.
//
// O gesto mais comum é ligar/desligar, então ele fica a um toque na própria
// linha. Editar abre um painel lateral: a lista continua visível, e o gestor
// não perde o contexto de quais outras campanhas já existem.
import { audienceRulesSummary, platformsSummary } from "~/presentation/campaign";
import type { Campaign, ChosenAudience } from "~/types/campaign";

const {
  rules, templates, triggers, platforms, platformLabels, customerGroups, rfmSegments, offers,
  loading, error, refresh, toggle, patch, create, fire,
} = useCampaigns();
// A prévia precisa saber se há template aprovado: com ele, o texto que sai no WhatsApp é o
// da Meta, e prometer o do modelo seria mentira.
const waTemplate = useWhatsAppTemplate();
onMounted(() => { waTemplate.load(); });

const editing = ref<Campaign | null>(null);
const creating = ref(false);
const firing = ref<Campaign | null>(null);
const busy = ref(false);

const panelOpen = computed(() => creating.value || editing.value !== null);

function openNew() {
  editing.value = null;
  creating.value = true;
}

function openEdit(rule: Campaign) {
  creating.value = false;
  editing.value = rule;
}

function close() {
  creating.value = false;
  editing.value = null;
}

/** Disparar agora: a campanha manual, sem esperar evento da padaria. */
function openFire(rule: Campaign) {
  firing.value = rule;
}

async function onFire(request: { body: string; audience: ChosenAudience }) {
  if (!firing.value) return;
  busy.value = true;
  const ok = await fire(firing.value.pk, request);
  busy.value = false;
  if (ok) firing.value = null;
}

async function onSubmit(payload: Record<string, unknown>) {
  busy.value = true;
  const ok = editing.value ? await patch(editing.value.pk, payload) : await create(payload);
  busy.value = false;
  if (ok) close();
}

useHead({ title: "Campanhas · Marketing" });
</script>

<template>
  <main class="mx-auto w-full max-w-4xl flex-1 px-4 py-6">
    <div class="mb-5 flex items-center gap-3">
      <h1 class="text-xl font-bold">Campanhas</h1>
      <!-- A biblioteca de modelos é vista SECUNDÁRIA daqui, não seção irmã: o gestor pensa
           "o que a padaria diz quando X acontece", e separar o texto da intenção o obrigava
           a montar isso em duas telas. -->
      <NuxtLink
        to="/templates"
        class="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm text-muted-foreground transition hover:bg-muted"
      >
        <Icon name="lucide:file-text" class="size-3.5" />
        Modelos
      </NuxtLink>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        @click="openNew"
      >
        <Icon name="lucide:plus" class="size-4" />
        Nova campanha
      </button>
    </div>

    <div
      v-if="error"
      class="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
      role="alert"
    >
      <p class="font-semibold text-destructive">Não conseguimos carregar as campanhas.</p>
      <button type="button" class="mt-1 underline underline-offset-2" @click="refresh()">
        Tentar de novo
      </button>
    </div>

    <div v-else-if="loading && rules.length === 0" class="space-y-3" aria-busy="true">
      <div v-for="n in 3" :key="n" class="h-20 animate-pulse rounded-xl bg-muted"></div>
    </div>

    <div
      v-else-if="rules.length === 0"
      class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon name="lucide:sliders-horizontal" class="mx-auto size-8 text-muted-foreground" />
      <p class="mt-2 font-semibold">Nenhuma campanha ainda</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Uma campanha liga um evento da padaria a um anúncio. Comece pela fornada.
      </p>
      <button
        type="button"
        class="mt-3 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        @click="openNew"
      >
        <Icon name="lucide:plus" class="size-4" />
        Criar a primeira
      </button>
    </div>

    <ul v-else class="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
      <li v-for="rule in rules" :key="rule.pk" class="flex items-start gap-3 px-4 py-3">
        <!-- Liga/desliga: o gesto mais comum, a um toque -->
        <button
          type="button"
          role="switch"
          :aria-checked="rule.is_active"
          :aria-label="`${rule.is_active ? 'Desligar' : 'Ligar'} a campanha ${rule.name}`"
          class="mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors"
          :class="rule.is_active ? 'bg-primary' : 'bg-muted-foreground/30'"
          @click="toggle(rule)"
        >
          <span
            class="size-4 rounded-full bg-white shadow transition-transform"
            :class="rule.is_active ? 'translate-x-4' : 'translate-x-0.5'"
          ></span>
        </button>

        <button
          type="button"
          class="min-w-0 flex-1 text-left"
          @click="openEdit(rule)"
        >
          <p class="font-semibold" :class="rule.is_active ? '' : 'text-muted-foreground'">
            {{ rule.name }}
          </p>
          <p class="mt-0.5 text-sm text-muted-foreground">
            {{ rule.trigger_label }} → {{ platformsSummary(rule.platforms, platformLabels) }}
          </p>
          <p class="mt-0.5 text-xs text-muted-foreground">
            {{ audienceRulesSummary(rule.audience_rules) }}
          </p>
          <!-- Uma campanha agendada que nunca mais dispara é indistinguível de uma
               que ainda não disparou. A frase vem do servidor pronta. -->
          <p
            v-if="rule.fires_on_its_own"
            class="mt-1 inline-flex items-center gap-1 text-xs"
            :class="rule.exhausted ? 'text-destructive' : 'text-muted-foreground'"
          >
            <Icon
              :name="rule.exhausted ? 'lucide:calendar-x' : 'lucide:calendar-clock'"
              class="size-3.5"
            />
            {{ rule.exhausted ? 'não dispara mais' : rule.schedule_label }}
          </p>
        </button>

        <div class="flex shrink-0 items-center gap-2">
          <span
            v-if="!rule.requires_approval"
            class="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400"
            title="Publica sem passar por revisão"
          >
            automática
          </span>
          <!-- Disparar não espera o evento: fica ao lado da campanha, mas só ativo
               quando ela está ligada — disparar campanha desligada é engano. -->
          <button
            type="button"
            :disabled="!rule.is_active"
            :aria-label="`Disparar a campanha ${rule.name} agora`"
            class="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs font-semibold transition hover:bg-muted disabled:opacity-40"
            @click="openFire(rule)"
          >
            <Icon name="lucide:send" class="size-3.5" />
            Disparar
          </button>
          <Icon name="lucide:chevron-right" class="size-4 text-muted-foreground" />
        </div>
      </li>
    </ul>

    <!-- Painel lateral: edita sem tirar a lista da vista -->
    <UiSheet :open="panelOpen" @update:open="(v) => { if (!v) close() }">
      <!-- Casca sem padding + regiões com o seu: o cabeçalho fica parado e só o corpo
           rola. Mesmo desenho do slide-over de produto do gestor de pedidos. -->
      <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg">
        <UiSheetHeader class="border-b border-border">
          <UiSheetTitle>{{ editing ? "Editar campanha" : "Nova campanha" }}</UiSheetTitle>
          <UiSheetDescription>
            Um evento da padaria vira um announcement, para as pessoas certas.
          </UiSheetDescription>
        </UiSheetHeader>
        <div class="flex-1 overflow-y-auto p-4">
          <CampaignForm
            :rule="editing"
            :triggers="triggers"
            :platform-options="platforms"
            :templates="templates"
            :offers="offers"
            :platform-labels="platformLabels"
            :whatsapp-template="waTemplate.current.value"
            :busy="busy"
            @submit="onSubmit"
            @cancel="close"
          />
        </div>
      </UiSheetContent>
    </UiSheet>

    <!-- Disparo manual: painel próprio, para não se confundir com editar a campanha -->
    <UiSheet :open="firing !== null" @update:open="(v) => { if (!v) firing = null }">
      <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg">
        <UiSheetHeader class="border-b border-border">
          <UiSheetTitle>Disparar agora</UiSheetTitle>
          <UiSheetDescription>
            {{ firing?.name }} — escreva o texto e ele publica direto; em branco, nasce
            para você revisar.
          </UiSheetDescription>
        </UiSheetHeader>
        <div class="flex-1 overflow-y-auto p-4">
          <FireCampaignPanel
            :rule="firing"
            :customer-groups="customerGroups"
            :rfm-segments="rfmSegments"
            :busy="busy"
            @submit="onFire"
            @cancel="firing = null"
          />
        </div>
      </UiSheetContent>
    </UiSheet>
  </main>
</template>
