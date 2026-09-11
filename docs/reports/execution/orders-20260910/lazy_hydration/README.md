# WP07 — hidratação sob demanda rejeitada

Nuxt4.5.2/Vue instalados oferecem componente Lazy com hydrate-on-visible.
A candidata usou essa implementação existente em ambos os grupos de OrderCard,
rootMargin300px, sem alterar regra, query, seleção ou quantidade carregada.
Mesmo backend atual, fixture500 rica, Chromium desktop, sessão autenticada e
20 páginas por rodada: navegar, hidratar, digitar filtro, conferir uma linha.

Baseline56f169108: p502113ms/p952324ms; candidata p502627,5ms/p953186ms.
Ambas completaram o fluxo funcional; **nenhuma atingiu1500ms**. A candidata foi
rejeitada e o diff exato está arquivado, sem aplicação no produto. Não é prova
de que toda forma de lazy rendering falha, nem justificativa para relaxar budget.
Login/tempo humano fora deste ensaio, conforme read.spec.ts; mesmos limites de
localhost/hardware declarados anteriormente. Sem provider, dinheiro ou DDL.
Builds/logs/raw preservados. Rollback técnico da experiência: restaurar somente
os dois tags próprios, parar Nitro próprio e reconstruir bundle normal.
