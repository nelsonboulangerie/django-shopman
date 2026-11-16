<script setup lang="ts">
// Prévia M1 (DEV-2026-030): o sheet "Chamar entregador" com "Quem leva". Parte da prévia 1
// da revisão das Entregas (decisão A: C03 já marcado como sugestão da casa) e soma a
// escolha do serviço no mesmo gesto. Dados fictícios, sem backend: nada aqui chama a API.
import { reactive } from "vue";
import { rideColor } from "~/presentation/ridePalette";

type Kind = "casa" | "taon";
interface Option {
  id: string;
  kind: Kind;
  label: string;
  /** Estado da pessoa ou do serviço, a segunda linha do chip. */
  state: string;
  busy?: boolean;
  /** Corrida inteira (juntas) e a soma das sozinhas, em reais. null = sem cotação. */
  together: number | null;
  separate: number | null;
  minutes?: number;
}
type Rule = "own_first" | "cheapest";
interface Scene {
  id: string;
  title: string;
  caption: string;
  options: Option[];
  rule: Rule;
  selected: string;
  note: string;
}

const tone = rideColor(2);
const brl = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}`;

const diego: Option = { id: "diego", kind: "casa", label: "Diego", state: "Livre", together: 15, separate: 24 };
const rui: Option = { id: "rui", kind: "casa", label: "Rui", state: "Volta 12h50", busy: true, together: 15, separate: 24 };
const taon: Option = { id: "taon", kind: "taon", label: "TaOn", state: "18 min", together: 11, separate: 17, minutes: 18 };

function suggestion(options: Option[], rule: Rule): Option {
  const free = options.filter((o) => !o.busy);
  if (rule === "own_first") {
    const own = free.find((o) => o.kind === "casa");
    if (own) return own;
    return free.find((o) => o.kind === "taon") ?? options[0]!;
  }
  const quoted = free.filter((o) => o.together !== null).sort((a, b) => a.together! - b.together!);
  return quoted[0] ?? free[0] ?? options[0]!;
}

function reason(s: Scene): string {
  const sug = suggestion(s.options, s.rule);
  if (s.rule === "cheapest") {
    const others = s.options.filter((o) => o.id !== sug.id && o.together !== null && !o.busy);
    const next = others.sort((a, b) => a.together! - b.together!)[0];
    return next ? `Sugestão da casa: ${sug.label} sai ${brl(next.together! - sug.together!)} mais barato.` : `Sugestão da casa: ${sug.label}.`;
  }
  if (sug.kind === "casa") return `Sugestão da casa: ${sug.label} está livre.`;
  return "Sugestão da casa: ninguém da casa está livre agora.";
}

function makeScene(id: string, title: string, caption: string, options: Option[], rule: Rule): Scene {
  return reactive({ id, title, caption, options, rule, selected: suggestion(options, rule).id, note: "" });
}

const main = makeScene(
  "a",
  "A · Quem leva no topo do sheet",
  "Um chip por quem pode levar. A sugestão já vem marcada; trocar é um toque. A cotação abaixo é a de quem está marcado.",
  [diego, rui, taon],
  "own_first",
);

const states: Scene[] = [
  makeScene(
    "busy",
    "Ninguém da casa livre",
    "Diego e Rui estão na rua: a TaOn vem marcada. Escolher Diego mesmo assim é um toque, e a tela diz a hora em que ele volta.",
    [
      { ...diego, state: "Volta 12h50", busy: true },
      { ...rui, state: "Volta 13h05" },
      taon,
    ],
    "own_first",
  ),
  makeScene(
    "noquote",
    "A TaOn não cotou agora",
    "Sem cotação, o chip da TaOn diz isso e nunca vem marcado por preço. A casa cota sempre: o valor vem da tabela.",
    [diego, rui, { ...taon, state: "Sem cotação agora", together: null, separate: null }],
    "cheapest",
  ),
];

function setRule(s: Scene, rule: Rule) {
  s.rule = rule;
  s.selected = suggestion(s.options, rule).id;
}
const sel = (s: Scene) => s.options.find((o) => o.id === s.selected)!;
const isSuggested = (s: Scene, o: Option) => suggestion(s.options, s.rule).id === o.id;

function quoteLines(o: Option): string[] {
  if (o.together === null) return [];
  const juntas = o.kind === "taon" ? `Juntas: ${brl(o.together)} · ${o.minutes} min · 7,4 km` : `Juntas: ${brl(o.together)} · 7,4 km`;
  const sep = o.separate!;
  return o.together <= sep ? [`${juntas} ✔`, `Separadas sairiam ${brl(sep)}`] : [juntas, `Separadas sai mais barato: ${brl(sep)} ✔`];
}
function primary(o: Option) {
  return o.kind === "taon" ? "Chamar TaOn para A47 e C03" : `Enviar para ${o.label}: A47 e C03`;
}
function secondary(o: Option) {
  return o.kind === "taon" ? "Chamar só A47" : `Enviar só A47 para ${o.label}`;
}

// Alternativa B: o sheet de hoje, e "quem leva" como segundo passo depois de Chamar.
const b = reactive({ step: 1 as 1 | 2, choice: "diego" });
</script>

<template>
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default pb-32" data-preview-overlay>
        <div class="min-h-screen bg-muted py-8">
          <div class="mx-auto flex w-full max-w-[1440px] flex-col gap-8 px-8">
            <header class="flex flex-col gap-1">
              <MsPreviewNav :current="1" />
              <h1 class="op-title font-semibold text-highlighted">Prévia M1 · Chamar entregador: quem leva</h1>
              <p class="op-body text-toned">
                Você decide: escolher quem leva cabe no mesmo sheet, com a sugestão já marcada (A, a minha recomendação), ou vira um
                segundo passo depois de Chamar (B).
              </p>
              <p class="op-micro text-muted">
                Cena: A47 está Pronto na Gleba Palhano e C03, a 0,6 km dele, vai junto (sugestão da casa, como na prévia 1 da revisão).
                Diego, da casa, está livre; Rui volta às 12h50; a TaOn cotou. Troco R$ 50,00 (A47) e R$ 20,00 (C03). Maquininha azul.
                Valores da casa pela tabela de exemplo: até 6 km R$ 12,00, mais R$ 3,00 por parada extra. Dados fictícios.
              </p>
            </header>

            <section class="grid grid-cols-2 gap-8">
              <!-- A -->
              <div class="flex flex-col gap-3">
                <div class="flex items-start gap-3">
                  <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-inverted text-lg font-bold text-inverted">A</span>
                  <p class="op-body pt-1.5 text-toned">{{ main.caption }} <strong class="text-highlighted">Recomendo.</strong></p>
                </div>

                <div class="mx-auto flex w-[460px] items-center gap-2 op-micro text-toned">
                  <span>Regra de sugestão (pergunta 1):</span>
                  <NuxtButton size="xs" :variant="main.rule === 'own_first' ? 'solid' : 'outline'" color="neutral" label="1 · Casa primeiro" @click="setRule(main, 'own_first')" />
                  <NuxtButton size="xs" :variant="main.rule === 'cheapest' ? 'solid' : 'outline'" color="neutral" label="2 · Mais barato" @click="setRule(main, 'cheapest')" />
                </div>

                <MsCallSheet :scene="main" :sel="sel(main)" :reason="reason(main)" :quote="quoteLines(sel(main))" :primary="primary(sel(main))" :secondary="secondary(sel(main))" :tone="tone" :is-suggested="(o) => isSuggested(main, o)" @pick="(id) => (main.selected = id)" />

                <div class="mx-auto flex w-[460px] items-center gap-3 rounded-xl border border-dashed border-accented px-4 py-2.5 op-micro text-toned">
                  <NuxtIcon name="i-lucide-pointer" class="size-4 text-muted" />
                  <span>Com a sugestão: <strong class="tabular-nums text-highlighted">2 toques</strong></span>
                  <span aria-hidden="true">·</span>
                  <span>Trocar quem leva: <strong class="tabular-nums text-highlighted">+1 toque</strong></span>
                </div>
              </div>

              <!-- B -->
              <div class="flex flex-col gap-3">
                <div class="flex items-start gap-3">
                  <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-inverted text-lg font-bold text-inverted">B</span>
                  <p class="op-body pt-1.5 text-toned">
                    O sheet de hoje, sem saber quem leva. Depois de Chamar, um segundo passo pergunta quem. A cotação não acompanha a escolha.
                  </p>
                </div>

                <div class="mx-auto w-[460px] overflow-hidden rounded-2xl border border-default bg-default shadow-lg">
                  <div class="flex items-start gap-3 border-b border-default px-5 py-4">
                    <NuxtIcon name="i-lucide-bike" class="mt-0.5 size-5 text-muted" />
                    <div class="min-w-0 flex-1">
                      <h2 class="op-title text-highlighted">{{ b.step === 1 ? "Chamar entregador" : "Quem leva A47 e C03?" }}</h2>
                      <p class="op-micro text-muted">Pedido A47 · Pronto há 3 min · Gleba Palhano</p>
                    </div>
                    <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" aria-label="Fechar" />
                  </div>
                  <div v-if="b.step === 1" class="flex flex-col gap-3 px-5 py-4">
                    <p class="op-label text-highlighted">Vai junto nesta corrida?</p>
                    <div class="flex items-center gap-3 rounded-xl border border-primary bg-primary/5 px-3 py-2.5">
                      <NuxtCheckbox :model-value="true" />
                      <span class="op-body font-semibold text-highlighted">C03</span>
                      <span class="op-micro text-muted">Gleba Palhano · 0,6 km de A47</span>
                      <NuxtBadge class="ms-auto" color="primary" icon="i-lucide-sparkles" label="Sugestão da casa" />
                    </div>
                    <p class="op-micro text-muted">Sai da gaveta: R$ 70,00 de troco. Maquininha azul.</p>
                  </div>
                  <div v-else class="flex flex-col gap-1.5 px-5 py-4" role="radiogroup" aria-label="Quem leva">
                    <button
                      v-for="o in [diego, rui, taon]"
                      :key="o.id"
                      type="button"
                      role="radio"
                      :aria-checked="b.choice === o.id"
                      class="flex items-center gap-3 rounded-xl border px-3 py-2.5 text-left"
                      :class="b.choice === o.id ? 'border-primary bg-primary/5 ring-1 ring-primary' : 'border-default'"
                      @click="b.choice = o.id"
                    >
                      <span class="grid size-4 place-items-center rounded-full border-2" :class="b.choice === o.id ? 'border-primary' : 'border-accented'">
                        <span v-if="b.choice === o.id" class="size-2 rounded-full bg-primary" />
                      </span>
                      <span class="op-body font-semibold text-highlighted">{{ o.label }}</span>
                      <span class="op-micro text-muted">{{ o.kind === "casa" ? "Entregador da casa" : "Serviço de entrega" }} · {{ o.state }}</span>
                    </button>
                  </div>
                  <div class="flex flex-col gap-2 border-t border-default bg-elevated/50 px-5 py-4">
                    <NuxtButton v-if="b.step === 1" block color="primary" icon="i-lucide-bike" label="Chamar corrida com A47 e C03" @click="b.step = 2" />
                    <template v-else>
                      <NuxtButton block color="primary" icon="i-lucide-check" label="Confirmar" @click="b.step = 1" />
                      <NuxtButton block color="neutral" variant="outline" label="Voltar" @click="b.step = 1" />
                    </template>
                  </div>
                </div>

                <div class="mx-auto flex w-[460px] items-center gap-3 rounded-xl border border-dashed border-accented px-4 py-2.5 op-micro text-toned">
                  <NuxtIcon name="i-lucide-pointer" class="size-4 text-muted" />
                  <span>Sempre: <strong class="tabular-nums text-highlighted">3 toques</strong> (abrir, chamar, confirmar quem leva)</span>
                </div>
              </div>
            </section>

            <p class="op-micro text-muted">
              Em A, o caminho comum continua com 2 toques, sozinho ou junto, igual à prévia 1 da revisão. Com um serviço só (como hoje), a linha
              "Quem leva" não aparece e o sheet é exatamente o da revisão.
            </p>

            <NuxtSeparator label="Outros estados da alternativa A" />

            <section class="grid grid-cols-2 gap-8">
              <div v-for="s in states" :key="s.id" class="flex flex-col gap-3">
                <div class="flex flex-col gap-0.5">
                  <h3 class="op-title text-highlighted">{{ s.title }}</h3>
                  <p class="op-micro text-muted">{{ s.caption }}</p>
                </div>
                <MsCallSheet :scene="s" :sel="sel(s)" :reason="reason(s)" :quote="quoteLines(sel(s))" :primary="primary(sel(s))" :secondary="secondary(sel(s))" :tone="tone" :is-suggested="(o) => isSuggested(s, o)" @pick="(id) => (s.selected = id)" />
              </div>
            </section>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
