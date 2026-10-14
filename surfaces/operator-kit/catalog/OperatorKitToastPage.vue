<script setup lang="ts">
// Bancada do aviso passageiro (`OperatorSonner`): um aviso de cada tom, todos com ação,
// para a trava `tests/catalog/toast-action.spec.ts` medir no navegador que a ação acompanha
// a cor do aviso (D8). Só existe no harness do catálogo.
//   ?theme=dark   liga o tema escuro
//   ?types=warning,error   escolhe quais tons aparecem (padrão: os cinco)
import { onMounted } from "vue";
import { toast } from "vue-sonner";

const route = useRoute();
const colorMode = useColorMode();
if (route.query.theme === "dark" || route.query.theme === "light") {
  colorMode.preference = route.query.theme;
}

const SAMPLES = {
  normal: { title: "Pão de queijo removido.", action: "Desfazer" },
  success: { title: "Venda registrada.", action: "Imprimir" },
  info: { title: "Chegou uma encomenda nova.", action: "Ver" },
  warning: { title: "A encomenda 1042 ainda não foi paga.", action: "Abrir Pagamento" },
  error: { title: "A impressora não respondeu.", action: "Tentar de novo" },
} as const;
type Kind = keyof typeof SAMPLES;

const wanted = String(route.query.types || "normal,success,info,warning,error")
  .split(",")
  .filter((kind): kind is Kind => kind in SAMPLES);

onMounted(() => {
  for (const kind of wanted) {
    const sample = SAMPLES[kind];
    const options = { duration: Number.POSITIVE_INFINITY, action: { label: sample.action, onClick: () => {} } };
    if (kind === "normal") toast(sample.title, options);
    else toast[kind](sample.title, options);
  }
});
</script>

<template>
  <OperatorAppRoot>
    <main class="min-h-screen bg-background p-6 text-foreground" data-bench-toast>
      <p class="text-sm text-muted-foreground">Bancada do aviso passageiro.</p>
    </main>
    <OperatorSonner />
  </OperatorAppRoot>
</template>

<style>
@import "./catalog.css";
</style>
