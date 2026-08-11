<script setup lang="ts">
// Modelos de anúncio — o texto que vai para o cliente.
//
// ⚠️ Esta tela existe por causa de um defeito real: os modelos viviam SÓ no Admin, e a
// tela de regra mandava o gestor para lá ("Crie um no Admin antes de criar a regra"). Com
// zero modelos, era impossível criar campanha pelo app — a operação travava numa porta que
// não é a dele. A API já existia; faltava isto.
import type { AnnouncementTemplate } from "~/types/campaign";

const { templates, loading, create, patch, remove } = useAnnouncementTemplates();
const { variables } = useCampaigns();
const { aiAssistAvailable } = useCampaignBoard();

const editing = ref<AnnouncementTemplate | null>(null);
const creating = ref(false);
const busy = ref(false);
const removing = ref<AnnouncementTemplate | null>(null);

const panelOpen = computed(() => creating.value || editing.value !== null);

function openNew() {
  editing.value = null;
  creating.value = true;
}

function openEdit(template: AnnouncementTemplate) {
  creating.value = false;
  editing.value = template;
}

function close() {
  creating.value = false;
  editing.value = null;
}

async function onSubmit(payload: Record<string, unknown>) {
  busy.value = true;
  const ok = editing.value
    ? await patch(editing.value.pk, payload)
    : await create(payload);
  busy.value = false;
  if (ok) close();
}

async function confirmRemove() {
  const target = removing.value;
  if (!target) return;
  removing.value = null;
  busy.value = true;
  await remove(target.pk);
  busy.value = false;
}

useHead({ title: "Modelos · Marketing" });
</script>

<template>
  <main class="mx-auto w-full max-w-3xl flex-1 px-4 py-6">
    <div class="mb-4 flex items-center gap-3">
      <h1 class="text-xl font-semibold">Modelos</h1>
      <button
        type="button"
        class="ml-auto inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition"
        @click="openNew"
      >
        <Icon name="lucide:plus" class="size-4" />
        Novo modelo
      </button>
    </div>

    <div v-if="loading && !templates.length" class="space-y-2" aria-busy="true">
      <div v-for="n in 3" :key="n" class="h-16 animate-pulse rounded-xl bg-muted"></div>
    </div>

    <!-- Vazio é o estado que mais importa aqui: era exatamente ele que travava tudo. -->
    <div
      v-else-if="!templates.length"
      class="rounded-xl border border-border bg-card px-4 py-8 text-center"
    >
      <Icon name="lucide:file-text" class="mx-auto size-8 text-muted-foreground" />
      <p class="mt-3 font-semibold">Nenhum modelo ainda</p>
      <p class="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
        O modelo é o texto que sai para o cliente. Sem pelo menos um, não há como criar
        campanha.
      </p>
      <button
        type="button"
        class="mt-4 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground"
        @click="openNew"
      >
        <Icon name="lucide:plus" class="size-4" />
        Criar o primeiro
      </button>
    </div>

    <ul v-else class="divide-y divide-border rounded-xl border border-border bg-card">
      <li v-for="template in templates" :key="template.pk" class="flex items-start gap-3 px-4 py-3">
        <button type="button" class="min-w-0 flex-1 text-left" @click="openEdit(template)">
          <p class="font-semibold" :class="template.is_active ? '' : 'text-muted-foreground'">
            {{ template.name }}
          </p>
          <p class="mt-0.5 truncate text-sm text-muted-foreground">{{ template.body }}</p>
          <p v-if="template.use_ai_generation" class="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Icon name="lucide:sparkles" class="size-3.5" />
            a IA escreve
          </p>
        </button>
        <div class="flex shrink-0 items-center gap-2">
          <span
            v-if="!template.is_active"
            class="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
          >
            inativo
          </span>
          <button
            type="button"
            :aria-label="`Apagar o modelo ${template.name}`"
            class="rounded-md border border-border p-1.5 text-muted-foreground transition hover:bg-muted"
            @click="removing = template"
          >
            <Icon name="lucide:trash-2" class="size-4" />
          </button>
          <Icon name="lucide:chevron-right" class="size-4 text-muted-foreground" />
        </div>
      </li>
    </ul>

    <UiSheet :open="panelOpen" @update:open="(v) => { if (!v) close() }">
      <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg">
        <UiSheetHeader class="border-b border-border">
          <UiSheetTitle>{{ editing ? "Editar modelo" : "Novo modelo" }}</UiSheetTitle>
          <UiSheetDescription>
            O texto que sai para o cliente. As variáveis são substituídas no envio.
          </UiSheetDescription>
        </UiSheetHeader>
        <div class="flex-1 overflow-y-auto p-4">
          <AnnouncementTemplateForm
            :template="editing"
            :variables="variables"
            :ai-available="aiAssistAvailable"
            :busy="busy"
            @submit="onSubmit"
            @cancel="close"
          />
        </div>
      </UiSheetContent>
    </UiSheet>

    <!-- Apagar é destrutivo: confirma antes. O backend recusa modelo EM USO e explica. -->
    <UiDialog :open="removing !== null" @update:open="(v) => { if (!v) removing = null }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Apagar "{{ removing?.name }}"?</UiDialogTitle>
          <UiDialogDescription>
            Modelo usado por alguma campanha não pode ser apagado, e nós avisamos se for o
            caso. Nada do que já saiu muda.
          </UiDialogDescription>
        </UiDialogHeader>
        <UiDialogFooter>
          <button
            type="button"
            class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted"
            @click="removing = null"
          >
            Manter
          </button>
          <button
            type="button"
            class="rounded-md bg-destructive px-3 py-2 text-sm font-semibold text-destructive-foreground transition hover:bg-destructive/90"
            @click="confirmRemove"
          >
            Apagar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
