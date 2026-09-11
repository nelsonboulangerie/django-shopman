<script setup lang="ts">
// Modelos de anúncio — o texto que vai para o cliente.
//
// ⚠️ Esta tela existe por causa de um defeito real: os modelos viviam SÓ no Admin, e a
// tela de regra mandava o gestor para lá ("Crie um no Admin antes de criar a regra"). Com
// zero modelos, era impossível criar campanha pelo app — a operação travava numa porta que
// não é a dele. A API já existia; faltava isto.
import type { AnnouncementTemplate } from "~/types/campaign";
import {
  clearBrowserMarketingDraft,
  useMarketingDraftOwner,
} from "~/composables/useMarketingDraft";
import { marketingTemplateSummary } from "~/presentation/marketingVariables";

const { templates, loading, error, load, create, patch, remove } =
  useAnnouncementTemplates();
const { variables } = useCampaigns();
const { aiAssistAvailable } = useCampaignBoard();

const editing = ref<AnnouncementTemplate | null>(null);
const creating = ref(false);
const busy = ref(false);
const removing = ref<AnnouncementTemplate | null>(null);
const draftOwner = useMarketingDraftOwner();

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
  const resource = `template:${editing.value?.pk ?? "new"}`;
  busy.value = true;
  const ok = editing.value
    ? await patch(editing.value.pk, payload)
    : await create(payload);
  busy.value = false;
  if (ok) {
    close();
    await nextTick();
    clearBrowserMarketingDraft({ owner: draftOwner.value, resource });
  }
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
      <h1 class="text-lg font-semibold">Modelos</h1>
      <UiButton
        type="button"
        class="ml-auto"
        @click="openNew"
      >
        <Icon name="lucide:plus" class="size-4" />
        Novo modelo
      </UiButton>
    </div>

    <div
      v-if="error && !templates.length"
      class="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-5"
      role="alert"
    >
      <div class="flex items-start gap-3">
        <Icon
          name="lucide:cloud-off"
          class="mt-0.5 size-5 shrink-0 text-destructive"
        />
        <div>
          <p class="font-semibold">Não foi possível carregar os modelos</p>
          <p class="mt-1 text-sm text-muted-foreground">
            A lista está indisponível agora; isso não significa que ela esteja
            vazia. Seus modelos não foram alterados.
          </p>
          <UiButton
            type="button"
            variant="outline"
            class="mt-3"
            :disabled="loading"
            @click="load()"
          >
            {{ loading ? "Carregando…" : "Tentar novamente" }}
          </UiButton>
        </div>
      </div>
    </div>

    <div v-else-if="loading && !templates.length" class="space-y-2" aria-busy="true">
      <div
        v-for="n in 3"
        :key="n"
        class="h-16 animate-pulse rounded-md bg-muted"
      ></div>
    </div>

    <!-- Vazio é o estado que mais importa aqui: era exatamente ele que travava tudo. -->
    <div
      v-else-if="!templates.length"
      class="rounded-md border border-border bg-card px-4 py-8 text-center"
    >
      <Icon
        name="lucide:file-text"
        class="mx-auto size-8 text-muted-foreground"
      />
      <p class="mt-3 font-semibold">Nenhum modelo ainda</p>
      <p class="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
        O modelo é o texto que sai para o cliente. Sem pelo menos um, não há
        como criar campanha.
      </p>
      <UiButton
        type="button"
        class="mt-4"
        @click="openNew"
      >
        <Icon name="lucide:plus" class="size-4" />
        Criar o primeiro
      </UiButton>
    </div>

    <ul
      v-else
      class="divide-y divide-border rounded-md border border-border bg-card"
    >
      <li
        v-for="template in templates"
        :key="template.pk"
        class="flex items-start gap-3 px-4 py-3"
      >
        <!-- A linha inteira abre a edição; o alvo amplo reduz precisão e navegação do operador. -->
        <button
          type="button"
          class="min-w-0 flex-1 text-left"
          @click="openEdit(template)"
        >
          <p
            class="font-semibold"
            :class="template.is_active ? '' : 'text-muted-foreground'"
          >
            {{ template.name }}
          </p>
          <p class="mt-0.5 truncate text-sm text-muted-foreground">
            {{ marketingTemplateSummary(template.body) }}
          </p>
          <p
            v-if="template.use_ai_generation"
            class="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground"
          >
            <Icon name="lucide:sparkles" class="size-3.5" />
            Sugestão disponível na revisão
          </p>
        </button>
        <div class="flex shrink-0 items-center gap-2">
          <span
            v-if="!template.is_active"
            class="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
          >
            Inativo
          </span>
          <UiIconButton
            icon="lucide:trash-2"
            :label="`Apagar o modelo ${template.name}`"
            @click="removing = template"
          />
          <Icon
            name="lucide:chevron-right"
            class="size-4 text-muted-foreground"
          />
        </div>
      </li>
    </ul>

    <UiSheet
      :open="panelOpen"
      @update:open="
        (v) => {
          if (!v) close();
        }
      "
    >
      <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg">
        <UiSheetHeader class="border-b border-border">
          <UiSheetTitle>{{
            editing ? "Editar modelo" : "Novo modelo"
          }}</UiSheetTitle>
          <UiSheetDescription>
            O texto que sai para o cliente. As variáveis são substituídas no
            envio.
          </UiSheetDescription>
        </UiSheetHeader>
        <div class="flex-1 overflow-y-auto p-4">
          <AnnouncementTemplateForm
            :template="editing"
            :variables="variables"
            :ai-available="aiAssistAvailable"
            :busy="busy"
            :draft-owner="draftOwner"
            @submit="onSubmit"
            @cancel="close"
          />
        </div>
      </UiSheetContent>
    </UiSheet>

    <!-- Apagar é destrutivo: dependências aparecem antes da confirmação. -->
    <UiDialog
      :open="removing !== null"
      @update:open="
        (v) => {
          if (!v) removing = null;
        }
      "
    >
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>
            {{
              removing?.used_by_campaigns?.length
                ? `“${removing.name}” está em uso`
                : `Apagar “${removing?.name}”?`
            }}
          </UiDialogTitle>
          <UiDialogDescription v-if="removing?.used_by_campaigns?.length">
            Troque o modelo nas campanhas abaixo antes de apagá-lo. Nenhuma
            alteração foi feita.
          </UiDialogDescription>
          <UiDialogDescription v-else>
            O modelo será removido. Nada do que já saiu muda.
          </UiDialogDescription>
        </UiDialogHeader>
        <ul
          v-if="removing?.used_by_campaigns?.length"
          class="space-y-1 rounded-lg bg-muted/40 p-3 text-sm"
        >
          <li
            v-for="campaign in removing.used_by_campaigns"
            :key="campaign"
            class="flex items-center gap-2"
          >
            <Icon
              name="lucide:megaphone"
              class="size-4 text-muted-foreground"
            />
            {{ campaign }}
          </li>
        </ul>
        <UiDialogFooter>
          <UiButton
            type="button"
            variant="outline"
            @click="removing = null"
          >
            Manter
          </UiButton>
          <NuxtLink
            v-if="removing?.used_by_campaigns?.length"
            to="/campaigns"
            class="inline-flex min-h-11 items-center justify-center rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground"
            @click="removing = null"
          >
            Ver campanhas
          </NuxtLink>
          <UiButton
            v-else
            type="button"
            variant="destructive"
            @click="confirmRemove"
          >
            Apagar
          </UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
