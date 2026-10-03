# UX-G2 — "Pronto" automático no Gestor e desfazer de 5 s em Entregar/Despachar

- **id:** UX-G2
- **branch:** claude/ux-g2-pronto-automatico-desfazer
- **PR:** (a abrir)
- **estado:** em execução
- **início (UTC):** 2026-10-03

## Objetivo
SUITE-UX-FUNCTION-PLAN §2 L1, §5.1 (linha "Avançar para 'pronto' quando a Cozinha conclui"),
§13 e §15 (decisões do dono):
1. Quando a Cozinha conclui todas as estações do pedido, ele vai a "pronto" sozinho; o cartão do
   Gestor diz "Pronto · automático · desfazer"; o "Marcar pronto" manual sai do cartão e fica no
   menu do pedido; o aviso ao cliente só sai depois da janela de desfazer.
2. Entregar e Despachar (Gestor e Saída da Cozinha) ganham desfazer de 5 s no servidor; o aviso ao
   cliente e o fim do pedido só valem quando o prazo acaba.
