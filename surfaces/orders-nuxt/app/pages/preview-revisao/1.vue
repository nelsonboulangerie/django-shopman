<script setup lang="ts">
// Prévia 1 da revisão das Entregas: o sheet "Chamar entregador" (CourierCallSheet).
// Dados fictícios, sem backend: nada aqui chama a API.
import { reactive } from "vue";
import { rideColor } from "~/presentation/ridePalette";

type CompanionState = "ready" | "preparing";

interface Sheet {
  id: string;
  column?: "A" | "B";
  heading: string;
  caption: string;
  companionState: CompanionState;
  together: boolean;
  suggested: boolean;
  /** A linha de cotação sob o companheiro (null = só a distância). */
  quoteLine: string | null;
  quoteTone: "suggest" | "warning" | "neutral";
  gestures: { alone: number; together: number };
}

// A próxima corrida pega a próxima cor livre (aqui, a terceira: amarelo).
const tone = rideColor(2);

const sheets = reactive<Sheet[]>([
  {
    id: "a",
    column: "A",
    heading: "A",
    caption: "C03 já vem marcado como sugestão da casa, com a economia e o atraso do segundo cliente.",
    companionState: "ready",
    together: true,
    suggested: true,
    quoteLine: "Juntas: R$ 11,00 · 18 min · 7,4 km ✔\nSeparadas sairiam R$ 17,00\nC03 chega uns 6 min depois.",
    quoteTone: "suggest",
    gestures: { alone: 2, together: 2 },
  },
  {
    id: "b",
    column: "B",
    heading: "B",
    caption: "C03 aparece desmarcado, só com a distância. Quem quiser juntar marca.",
    companionState: "ready",
    together: false,
    suggested: false,
    quoteLine: null,
    quoteTone: "neutral",
    gestures: { alone: 2, together: 3 },
  },
  {
    id: "no-quote",
    heading: "A TaOn não cotou agora",
    caption: "Sem cotação, nada vem marcado: dinheiro da casa não se decide no escuro.",
    companionState: "ready",
    together: false,
    suggested: false,
    quoteLine: "A TaOn não cotou agora. Marque C03 se quiser levar junto.",
    quoteTone: "warning",
    gestures: { alone: 2, together: 3 },
  },
  {
    id: "preparing",
    heading: "C03 em preparo",
    caption: "Pedido em preparo continua na lista (decisão 7), mas nunca vem marcado.",
    companionState: "preparing",
    together: false,
    suggested: false,
    quoteLine: "C03 ainda está em preparo e a casa não sabe a hora em que fica pronto. Marque só se ele sai agora.",
    quoteTone: "neutral",
    gestures: { alone: 2, together: 3 },
  },
]);

const columns = sheets.filter((s) => s.column);
const states = sheets.filter((s) => !s.column);

function primaryLabel(s: Sheet): string {
  return s.together ? "Chamar corrida com A47 e C03" : "Chamar entregador para A47";
}

function setTogether(s: Sheet, value: boolean | "indeterminate") {
  s.together = value === true;
}

// Comparação pedida pelo dono (16/11): a cotação só de leitura × a linha que vira
// botão. Cada coluna em dois momentos: como chega (sugestão aplicada) e depois que
// o operador escolhe o contrário.
const readOnly = reactive([{ together: true }, { together: false }]);
const asButton = reactive([{ together: true }, { together: false }]);
</script>

<template>
  <!-- Prévia de olhar: cobre a casca do Gestor (barra lateral e rolagem interna)
       para a página ter os 1440 px inteiros e rolar com o documento. -->
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default" data-preview-overlay>
        <div class="min-h-screen bg-muted py-8">
          <div class="mx-auto flex w-full max-w-[1440px] flex-col gap-8 px-8">
            <!-- topo da prévia -->
            <header class="flex flex-col gap-1">
              <PreviewNav :current="1" />
              <h1 class="op-title font-semibold text-highlighted">Prévia 1 · Chamar entregador</h1>
              <p class="op-body text-toned">
                Você decide: quando juntar sai mais barato, a casa já deixa o companheiro marcado (A), ou deixa
                desmarcado e só mostra a distância (B).
              </p>
              <p class="op-micro text-muted">
                Cena: A47 está Pronto na Gleba Palhano. C03, a 0,6 km dele, também pode ir. Troco R$ 50,00 (A47) e
                R$ 20,00 (C03). Uma maquininha livre: a azul. Dados fictícios.
              </p>
            </header>

            <!-- A e B lado a lado -->
            <section class="grid grid-cols-2 gap-8">
              <div v-for="s in columns" :key="s.id" class="flex flex-col gap-3">
                <div class="flex items-start gap-3">
                  <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-inverted text-lg font-bold text-inverted">{{ s.heading }}</span>
                  <p class="op-body pt-1.5 text-toned">{{ s.caption }}</p>
                </div>

                <!-- o sheet -->
                <div class="mx-auto w-[460px] overflow-hidden rounded-2xl border border-default bg-default shadow-lg">
                  <div class="flex items-start gap-3 border-b border-default px-5 py-4">
                    <NuxtIcon name="i-lucide-bike" class="mt-0.5 size-5 text-muted" />
                    <div class="min-w-0 flex-1">
                      <h2 class="op-title text-highlighted">Chamar entregador</h2>
                      <p class="op-micro text-muted">Pedido A47 · Pronto há 3 min · Gleba Palhano</p>
                    </div>
                    <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" aria-label="Fechar" />
                  </div>

                  <div class="flex flex-col gap-4 px-5 py-4">
                    <!-- mapa simples -->
                    <svg viewBox="0 0 420 170" class="w-full rounded-xl border border-default" role="img" aria-label="Mapa da corrida">
                      <defs>
                        <pattern :id="`grid-${s.id}`" width="20" height="20" patternUnits="userSpaceOnUse">
                          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#e5e7eb" stroke-width="1" />
                        </pattern>
                      </defs>
                      <rect width="420" height="170" fill="#f8f8f6" />
                      <rect width="420" height="170" :fill="`url(#grid-${s.id})`" />
                      <path d="M0 120 Q 160 100 420 135" stroke="#ffffff" stroke-width="9" fill="none" />
                      <path d="M210 0 Q 220 90 200 170" stroke="#ffffff" stroke-width="7" fill="none" />
                      <text x="14" y="160" font-size="10" fill="#9ca3af">Centro</text>
                      <text x="300" y="160" font-size="10" fill="#9ca3af">Gleba Palhano</text>
                      <polyline
                        v-if="s.together"
                        points="70,110 300,72 352,46 70,110"
                        fill="none"
                        :stroke="tone.bg"
                        stroke-width="3"
                        stroke-dasharray="7 5"
                        stroke-linejoin="round"
                      />
                      <line v-else x1="70" y1="110" x2="300" y2="72" :stroke="tone.bg" stroke-width="3" stroke-dasharray="7 5" />
                      <rect x="58" y="98" width="24" height="24" rx="5" fill="#111111" />
                      <text x="70" y="114" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">Loja</text>
                      <circle cx="300" cy="72" r="14" :fill="tone.bg" />
                      <text x="300" y="76" font-size="10" font-weight="700" :fill="tone.fg" text-anchor="middle">A47</text>
                      <circle
                        cx="352"
                        cy="46"
                        r="14"
                        :fill="s.together ? tone.bg : '#ffffff'"
                        :stroke="s.together ? tone.bg : '#6b7280'"
                        stroke-width="2"
                        :stroke-dasharray="s.companionState === 'preparing' ? '3 3' : undefined"
                      />
                      <text x="352" y="50" font-size="10" font-weight="700" :fill="s.together ? tone.fg : '#374151'" text-anchor="middle">C03</text>
                    </svg>
                    <p v-if="s.together" class="op-micro -mt-2 text-muted">Ordem: A47, depois C03. Ida e volta.</p>

                    <!-- quem vai junto -->
                    <div class="flex flex-col gap-2">
                      <p class="op-label text-highlighted">Vai junto nesta corrida?</p>
                      <div
                        class="flex flex-col gap-1.5 rounded-xl border px-3 py-2.5"
                        :class="s.together ? 'border-primary bg-primary/5' : 'border-default'"
                      >
                        <div class="flex items-center gap-3">
                          <NuxtCheckbox :model-value="s.together" @update:model-value="(v) => setTogether(s, v)" />
                          <span class="op-body font-semibold tabular-nums text-highlighted">C03</span>
                          <span class="op-micro text-muted">Gleba Palhano · 0,6 km de A47</span>
                          <NuxtBadge
                            v-if="s.companionState === 'preparing'"
                            class="ms-auto"
                            color="neutral"
                            label="Em preparo"
                          />
                          <NuxtBadge
                            v-else-if="s.suggested"
                            class="ms-auto"
                            color="primary"
                            icon="i-lucide-sparkles"
                            label="Sugestão da casa"
                          />
                          <NuxtBadge v-else class="ms-auto" color="success" label="Pronto" />
                        </div>
                        <PreviewQuote
                          v-if="s.quoteLine && s.quoteLine.includes('✔')"
                          class="ps-8"
                          size="micro"
                          :text="s.quoteLine"
                        />
                        <p
                          v-else-if="s.quoteLine"
                          class="op-micro whitespace-pre-line ps-8"
                          :class="s.quoteTone === 'warning' ? 'text-warning' : 'text-muted'"
                        >
                          {{ s.quoteLine }}
                        </p>
                      </div>
                    </div>

                    <NuxtSeparator />

                    <!-- o que o entregador leva -->
                    <div class="flex flex-col gap-2">
                      <p class="op-label text-highlighted">O entregador leva</p>
                      <div class="flex items-center justify-between op-body">
                        <span class="flex items-center gap-2 text-toned"><NuxtIcon name="i-lucide-circle-dollar-sign" class="size-4 text-muted" />Troco do pedido A47</span>
                        <span class="tabular-nums font-medium text-highlighted">R$ 50,00</span>
                      </div>
                      <div v-if="s.together" class="flex items-center justify-between op-body">
                        <span class="flex items-center gap-2 text-toned"><NuxtIcon name="i-lucide-circle-dollar-sign" class="size-4 text-muted" />Troco do pedido C03</span>
                        <span class="tabular-nums font-medium text-highlighted">R$ 20,00</span>
                      </div>
                      <div class="flex items-center justify-between op-body">
                        <span class="flex items-center gap-2 text-toned"><NuxtIcon name="i-lucide-credit-card" class="size-4 text-muted" />Maquininha</span>
                        <span class="flex items-center gap-1.5 font-medium text-highlighted"><span class="size-3 rounded-full bg-[#2563eb]" />Azul, a única livre</span>
                      </div>
                      <p class="op-micro text-muted">
                        Sai da gaveta: R$ {{ s.together ? "70,00" : "50,00" }} de troco.
                      </p>
                    </div>
                  </div>

                  <!-- ações -->
                  <div class="flex flex-col gap-2 border-t border-default bg-elevated/50 px-5 py-4">
                    <NuxtButton block color="primary" icon="i-lucide-bike" :label="primaryLabel(s)" />
                    <NuxtButton v-if="s.together" block color="neutral" variant="outline" label="Chamar só A47" />
                  </div>
                </div>

                <!-- contagem de gestos -->
                <div class="mx-auto flex w-[460px] items-center gap-3 rounded-xl border border-dashed border-accented px-4 py-2.5 op-micro text-toned">
                  <NuxtIcon name="i-lucide-pointer" class="size-4 text-muted" />
                  <span>Chamar sozinho: <strong class="tabular-nums text-highlighted">{{ s.gestures.alone }} toques</strong></span>
                  <span aria-hidden="true">·</span>
                  <span>Juntar: <strong class="tabular-nums text-highlighted">{{ s.gestures.together }} toques</strong></span>
                </div>
              </div>
            </section>

            <p class="op-micro text-muted">
              Toques contados a partir do cartão Pronto: abrir o sheet e chamar. Hoje são 3 para chamar sozinho (o cartão Pronto não
              tem o botão) e 2 mais 1 por companheiro para juntar, sem preço. Em A, juntar e chamar sozinho custam o mesmo.
            </p>

            <NuxtSeparator label="A cotação: só leitura ou botão" />

            <section class="flex flex-col gap-4">
              <div class="flex flex-col gap-1">
                <h3 class="op-title text-highlighted">Na alternativa A, a linha do ✔ é só leitura ou vira o botão de escolha?</h3>
                <p class="op-body text-toned">
                  Em cima, como o sheet chega: a sugestão da casa já aplicada. Embaixo, depois que o operador escolhe o contrário. Clique
                  para experimentar.
                </p>
              </div>

              <div class="grid grid-cols-2 gap-8">
                <!-- só leitura -->
                <div class="flex flex-col gap-4">
                  <div class="flex items-start gap-3">
                    <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-inverted text-sm font-bold text-inverted">1</span>
                    <p class="op-body pt-1.5 text-toned">
                      Só leitura. Quem escolhe é a caixa do C03 e o botão principal; a cotação explica. O ✔ fica sempre na opção mais barata.
                    </p>
                  </div>
                  <div v-for="(st, i) in readOnly" :key="`ro-${i}`" class="mx-auto flex w-[460px] flex-col gap-2">
                    <p class="op-micro font-semibold text-muted">{{ i === 0 ? "Como chega" : "O operador desmarcou o C03" }}</p>
                    <div class="overflow-hidden rounded-2xl border border-default bg-default shadow-lg">
                      <div class="flex flex-col gap-2 px-5 py-4">
                        <p class="op-label text-highlighted">Vai junto nesta corrida?</p>
                        <div class="flex flex-col gap-1.5 rounded-xl border px-3 py-2.5" :class="st.together ? 'border-primary bg-primary/5' : 'border-default'">
                          <div class="flex items-center gap-3">
                            <NuxtCheckbox :model-value="st.together" @update:model-value="(v) => (st.together = v === true)" />
                            <span class="op-body font-semibold tabular-nums text-highlighted">C03</span>
                            <span class="op-micro text-muted">Gleba Palhano · 0,6 km de A47</span>
                            <NuxtBadge class="ms-auto" color="primary" icon="i-lucide-sparkles" label="Sugestão da casa" />
                          </div>
                          <PreviewQuote class="ps-8" size="micro" :text="['Juntas: R$ 11,00 · 18 min · 7,4 km ✔', 'Separadas sairiam R$ 17,00', 'C03 chega uns 6 min depois.']" />
                        </div>
                      </div>
                      <div class="flex flex-col gap-2 border-t border-default bg-elevated/50 px-5 py-4">
                        <NuxtButton block color="primary" icon="i-lucide-bike" :label="st.together ? 'Chamar corrida com A47 e C03' : 'Chamar entregador para A47'" />
                        <NuxtButton v-if="st.together" block color="neutral" variant="outline" label="Chamar só A47" @click="st.together = false" />
                      </div>
                    </div>
                  </div>
                  <p class="mx-auto w-[460px] op-micro text-muted">
                    Desmarcado, o ✔ continua em Juntas: o operador vê que foi contra a sugestão, e o botão diz o que vai acontecer.
                  </p>
                </div>

                <!-- linha vira botão -->
                <div class="flex flex-col gap-4">
                  <div class="flex items-start gap-3">
                    <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-inverted text-sm font-bold text-inverted">2</span>
                    <p class="op-body pt-1.5 text-toned">
                      Linha vira botão. As duas linhas da cotação são a escolha: a marcada é a que vale, e a caixa do C03 some. O ✔ continua na
                      mais barata.
                    </p>
                  </div>
                  <div v-for="(st, i) in asButton" :key="`bt-${i}`" class="mx-auto flex w-[460px] flex-col gap-2">
                    <p class="op-micro font-semibold text-muted">{{ i === 0 ? "Como chega" : "O operador tocou em Separadas" }}</p>
                    <div class="overflow-hidden rounded-2xl border border-default bg-default shadow-lg">
                      <div class="flex flex-col gap-2 px-5 py-4">
                        <p class="op-label text-highlighted">Como sai o C03?</p>
                        <p class="op-micro text-muted">C03 · Gleba Palhano · 0,6 km de A47 · Pronto</p>
                        <div class="flex flex-col gap-1.5" role="radiogroup" aria-label="Como sai o C03">
                          <button
                            v-for="opt in [
                              { together: true, main: 'Juntas: R$ 11,00 · 18 min · 7,4 km ✔', sub: 'A47 e C03 na mesma corrida. C03 chega uns 6 min depois.' },
                              { together: false, main: 'Separadas sairiam R$ 17,00', sub: 'Uma corrida para cada pedido.' },
                            ]"
                            :key="String(opt.together)"
                            type="button"
                            role="radio"
                            :aria-checked="st.together === opt.together"
                            class="flex items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition"
                            :class="st.together === opt.together ? 'border-primary bg-primary/5 ring-1 ring-primary' : 'border-default hover:bg-elevated/60'"
                            @click="st.together = opt.together"
                          >
                            <span class="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border-2" :class="st.together === opt.together ? 'border-primary' : 'border-accented'">
                              <span v-if="st.together === opt.together" class="size-2 rounded-full bg-primary" />
                            </span>
                            <span class="flex min-w-0 flex-col">
                              <span class="op-body tabular-nums" :class="st.together === opt.together ? 'font-semibold text-highlighted' : 'text-toned'">{{ opt.main }}</span>
                              <span class="op-micro text-dimmed">{{ opt.sub }}</span>
                            </span>
                          </button>
                        </div>
                      </div>
                      <div class="flex flex-col gap-2 border-t border-default bg-elevated/50 px-5 py-4">
                        <NuxtButton block color="primary" icon="i-lucide-bike" :label="st.together ? 'Chamar corrida com A47 e C03' : 'Chamar 2 corridas: A47 e C03'" />
                      </div>
                    </div>
                  </div>
                  <p class="mx-auto w-[460px] op-micro text-muted">
                    Separadas aqui quer dizer: chamar as duas agora, cada uma na sua corrida. Para levar só o A47 e deixar o C03 esperando,
                    faltaria uma terceira opção.
                  </p>
                </div>
              </div>
            </section>

            <NuxtSeparator label="Outros estados (valem para A e B)" />

            <!-- estados -->
            <section class="grid grid-cols-2 gap-8">
              <div v-for="s in states" :key="s.id" class="flex flex-col gap-3">
                <div class="flex flex-col gap-0.5">
                  <h3 class="op-title text-highlighted">{{ s.heading }}</h3>
                  <p class="op-micro text-muted">{{ s.caption }}</p>
                </div>

                <div class="mx-auto w-[460px] overflow-hidden rounded-2xl border border-default bg-default shadow-lg">
                  <div class="flex items-start gap-3 border-b border-default px-5 py-4">
                    <NuxtIcon name="i-lucide-bike" class="mt-0.5 size-5 text-muted" />
                    <div class="min-w-0 flex-1">
                      <h2 class="op-title text-highlighted">Chamar entregador</h2>
                      <p class="op-micro text-muted">Pedido A47 · Pronto há 3 min · Gleba Palhano</p>
                    </div>
                    <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" aria-label="Fechar" />
                  </div>

                  <div class="flex flex-col gap-4 px-5 py-4">
                    <NuxtAlert
                      v-if="s.id === 'no-quote'"
                      color="warning"
                      variant="subtle"
                      icon="i-lucide-cloud-off"
                      title="A TaOn não cotou agora."
                      description="Sem o preço, a casa não compara juntas e separadas."
                    />

                    <div class="flex flex-col gap-2">
                      <p class="op-label text-highlighted">Vai junto nesta corrida?</p>
                      <div
                        class="flex flex-col gap-1.5 rounded-xl border px-3 py-2.5"
                        :class="s.together ? 'border-primary bg-primary/5' : 'border-default'"
                      >
                        <div class="flex items-center gap-3">
                          <NuxtCheckbox :model-value="s.together" @update:model-value="(v) => setTogether(s, v)" />
                          <span class="op-body font-semibold tabular-nums text-highlighted">C03</span>
                          <span class="op-micro text-muted">Gleba Palhano · 0,6 km de A47</span>
                          <NuxtBadge
                            v-if="s.companionState === 'preparing'"
                            class="ms-auto"
                            color="neutral"
                            label="Em preparo"
                          />
                          <NuxtBadge v-else class="ms-auto" color="success" label="Pronto" />
                        </div>
                        <p class="op-micro ps-8" :class="s.quoteTone === 'warning' ? 'text-warning' : 'text-muted'">
                          {{ s.quoteLine }}
                        </p>
                      </div>
                    </div>

                    <NuxtSeparator />

                    <div class="flex flex-col gap-2">
                      <div class="flex items-center justify-between op-body">
                        <span class="flex items-center gap-2 text-toned"><NuxtIcon name="i-lucide-circle-dollar-sign" class="size-4 text-muted" />Troco do pedido A47</span>
                        <span class="tabular-nums font-medium text-highlighted">R$ 50,00</span>
                      </div>
                      <div v-if="s.together" class="flex items-center justify-between op-body">
                        <span class="flex items-center gap-2 text-toned"><NuxtIcon name="i-lucide-circle-dollar-sign" class="size-4 text-muted" />Troco do pedido C03</span>
                        <span class="tabular-nums font-medium text-highlighted">R$ 20,00</span>
                      </div>
                      <div class="flex items-center justify-between op-body">
                        <span class="flex items-center gap-2 text-toned"><NuxtIcon name="i-lucide-credit-card" class="size-4 text-muted" />Maquininha</span>
                        <span class="flex items-center gap-1.5 font-medium text-highlighted"><span class="size-3 rounded-full bg-[#2563eb]" />Azul, a única livre</span>
                      </div>
                    </div>
                  </div>

                  <div class="flex flex-col gap-2 border-t border-default bg-elevated/50 px-5 py-4">
                    <NuxtButton block color="primary" icon="i-lucide-bike" :label="primaryLabel(s)" />
                    <NuxtButton v-if="s.together" block color="neutral" variant="outline" label="Chamar só A47" />
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
