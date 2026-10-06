# Auditoria visual do Gestor (orders) — mapa único

**Data:** 2026-10-06 · **Branch:** `codex/orders-canonical-shell` (PR #1516) · **Ambiente:** `:3004`, `admin/admin` (PIN 1234)
**Regra desta passada:** diagnóstico. **Nenhum** código de app/kit foi alterado.

## Método
11 superfícies do ledger × 3 viewports (desktop 1440×900, tablet 768×1024, mobile 390×844) × 2 temas (claro/escuro) = **66 capturas** em `auditoria/` (padrão `<surface>__<viewport>__<theme>.png`), com varredura objetiva no DOM: overflow horizontal, truncamento (`scrollWidth > clientWidth` com overflow/ellipsis), recorte fora da viewport, alvo interativo < 44 e contraste calculado (texto vs fundo composto). Dados brutos: `auditoria/audit-findings.json`.

## Números (objetivos)
| sinal | total | concentração |
|---|---|---|
| **overflow horizontal** | **0** | — (documento não rola para o lado) |
| **truncamento** | **80** | 72 no **catálogo** |
| **recorte fora da viewport** | **48** | 48 no **catálogo** |
| **alvo < 44** | **252** | ver *caveat* (§A) |
| **contraste baixo (<4.5 texto)** | **88** | CTA do banner A1 em **11 telas × 2 temas** + rótulos do rail |

**Caveat (§A):** a contagem de alvo inclui falsos positivos: o rail é `hidden lg:flex` (só desktop, ponteiro fino — 32px é aceitável) e `switch`/`checkbox` usam pseudo-`after:size-control` (o alvo efetivo é 44, mesmo com o visual 24/20). Os alvos **realmente** abaixo de 44 em toque aparecem na tabela.

---

## Top 10 (por gravidade × frequência)

| # | Gav. | Tela | Tam./Tema | Tipo | Evidência | Correção sugerida |
|---|---|---|---|---|---|---|
| 1 | **Alta** | Banner A1 "Usar sem vincular" | 11 telas, claro+escuro | **Quebrado** (contraste 2.76 claro / 1.83 dark, texto 12px) | `orders-board__desktop__light.png` | CTA com contraste ≥4.5 sobre o dourado (token próprio ou fundo de botão) |
| 2 | **Alta** | Catálogo — nomes de produto | desktop+tablet+mobile, ambos | **Quebrado** (72 truncamentos: "Aconchego Chai Kãnfa · L…", "Azeite Defumado Mirante…") | `catalog__desktop__light.png`, `catalog__mobile__light.png` | Alargar a coluna PRODUTO; tirar o selo "Oculto" de cima do nome; `title`/tooltip |
| 3 | **Alta** | Catálogo **mobile** — tabela | mobile, ambos | **Quebrado**: só a coluna PDV; o nome some e sobra o SKU cortado ("CHA-ACONC…") | `catalog__mobile__light.png` | No mobile, virar **lista** (nome + selo + toggle), não tabela de 8 colunas |
| 4 | **Alta** | Catálogo — imagens de produto | desktop, ambos | **Quebrado**: placeholder cinza "A" em vez da foto (2 de 4 na 1ª dobra) | `catalog__desktop__light.png` | Fallback consistente (ícone) ou corrigir a origem; nunca letra aleatória |
| 5 | Média | Catálogo — SKU | desktop | **Quebrado**: quebra/corta ("AZEITE-DEFUMADO-PICANTE-MIRANTE-:") | `catalog__desktop__light.png` | `truncate`+`title` ou largura mínima; não quebrar no meio sem ellipsis |
| 6 | Média | Catálogo — trilha de coleções | mobile, ambos | **Quebrado**: rola na horizontal e corta ("Fol…", "Combos") | `catalog__mobile__light.png` | Quebra em 2 linhas ou scroll com afordância (fade/seta) |
| 7 | Média | Alvo de toque — banner e toggles | mobile/tablet, ambos | **Quebrado**: "Usar sem vincular" 118×28; "Oculto. Toque para pausar" 28×16; toggles 44×24 (visual) | `catalog__mobile__light.png`, `channels__desktop__light.png` | Garantir ≥44 reais; conferir se o pseudo cobre o switch |
| 8 | Média | Recortes fora da viewport | catálogo, ambos | **Quebrado**: nomes de coleção e tooltips ("Bebidas quentes. Para reordenar…") | `catalog__desktop__light.png` | `min-w-0`/`truncate` ou quebra |
| 9 | Média | **Título × conteúdo centralizado** | Ajustes, Postos (desktop) | **Feio** (hierarquia/alinhamento): título na borda esquerda, conteúdo numa coluna central estreita | `settings__desktop__light.png`, `workstations__desktop__light.png` | Alinhar a coluna ao título (ou o título à coluna); largura de conteúdo intencional |
| 10 | Média | Banner A1 dourado de largura total | 11 telas, ambos | **Feio** (peso/competição): barra pesada competindo com o rail; ação solta na ponta | `orders-board__desktop__light.png` | Reduzir peso (faixa neutra/contorno) e agrupar a ação |

## Resto (11–18)

| # | Gav. | Tela | Tam./Tema | Tipo | Evidência | Correção |
|---|---|---|---|---|---|---|
| 11 | Baixa | Catálogo denso | desktop | **Feio**: 8 colunas de canal com toggle por linha; grade pesada | `catalog__desktop__light.png` | Agrupar canais / modo compacto |
| 12 | Baixa | Cards de canal | desktop | **Feio**: card dentro de card ("Automático") | `channels__desktop__light.png` | Achatar o subcard |
| 13 | Baixa | Pedido (detalhe) | desktop | **Feio**: botões da "Nota para a cozinha" em bege (parecem desabilitados); vazio grande à direita | `order-detail__desktop__light.png` | Diferenciar chip-ação de ação primária; usar o espaço |
| 14 | Baixa | Trilha de coleções (board) | desktop | **Feio**: régua longa de recortes | `orders-board__desktop__light.png` | Limitar/agrupar |
| 15 | Baixa | Rail — rótulos | desktop | **Feio/gosto**: rótulos 10px e ícones pequenos | `catalog__desktop__light.png` | Ajuste de densidade (gosto) |
| 16 | Baixa | Contraste de separadores | 11 telas, ambos | **Quebrado** (não-texto): `border`/`bg` ≈ 1.45/1.51; WCAG 1.4.11 pede 3:1 | todas | Token do kit (WP de tema) — candidatos `#a37c67`/`#7e624c` |
| 17 | Baixa | Rótulos inativos do rail | desktop | **Indeterminado**: a varredura deu r≈1 (provável falso positivo de composição; no print estão legíveis) | `catalog__desktop__light.png` | Reconfere manual antes de mexer |
| 18 | Baixa | Densidade do card "Bloqueado" | mobile | **Feio**: régua "CRO · Planejada 0%" + faixa vermelha + botão competem | `orders-board__mobile__light.png` | Decidir o que cortar (produto) |

---

## Objetivo × gosto (explicitação pedida)

**Defeito objetivo** (não é opinião): #1 contraste do CTA (medido 2.76/1.83 < 4.5); #2/#5 truncamento e quebra de SKU; #3 tabela mobile inutilizável; #4 imagem falhando; #6 rolagem/corte da trilha; #7 alvo < 44 em toque; #8 recorte; #16 contraste não-texto (1.45/1.51 < 3).

**Gosto/nível de produto** (decisão do dono): #9 alinhamento título×conteúdo; #10 peso do banner; #11 densidade do catálogo; #12 nesting dos cards; #13 estado dos botões do detalhe; #14 extensão da régua de recortes; #15 densidade do rail; #18 o que cortar do card no mobile.

**Saudável:** **0 overflow horizontal** em 66 telas — a casca (rail/header/bottom bar) está geometricamente contida em todos os tamanhos.

## Arquivos
- Capturas: `auditoria/<surface>__<viewport>__<theme>.png` (66).
- Dados brutos: `auditoria/audit-findings.json`.
