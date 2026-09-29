# Evidência visual — Encomendas do PDV

**Base anterior:** `origin/main` após o merge do PR #1231  
**Cenário:** três encomendas, uma retirada a receber, uma entrega paga e uma entrega com pagamento a conferir  
**Harness:** backend hermético, relógio/locale fixos, sem credencial nem dado operacional

## Resultado

| Critério | Antes | Depois |
| --- | --- | --- |
| Hierarquia | Busca, período, resumo, filtros e impressão competiam no mesmo plano | Busca urgente, recorte, filtros/ação e quadro têm regiões nomeadas e separadas |
| Semana desktop | Sete colunas comprimidas; cards omitiam canal, itens e situação | Grade `auto-fit` com largura mínima útil; cards completos e situação visível |
| Semana mobile | Segunda árvore de DOM; impressão invadia filtros/aviso no cenário capturado | Uma única árvore; controles empilham sem sobreposição e dias viram cards táteis |
| Estados em voo | Texto solto mudava a geometria da página | Skeletons reservam o espaço e anunciam `aria-busy` |
| Falha | Mensagem remetia ao menu lateral | A região que falhou oferece “Tentar de novo” |
| Manutenção | Grade e lista duplicavam cada pedido no DOM | Cada encomenda aparece uma vez |

## Comparação revisável

### Desktop 1440×900

- Antes: [imagem](before/preorders-week-1440x900-light.png)
- Depois: [`preorders-week-1440x900-light.png`](../../../../surfaces/pos-nuxt/tests/visual/baselines/preorders-week-1440x900-light.png)

### Tablet 768×1024

- Antes: [imagem](before/preorders-week-768x1024-light.png)
- Depois: [`preorders-week-768x1024-light.png`](../../../../surfaces/pos-nuxt/tests/visual/baselines/preorders-week-768x1024-light.png)

### Mobile 390×844

- Antes: [imagem](before/preorders-week-390x844-light.png)
- Depois: [`preorders-week-390x844-light.png`](../../../../surfaces/pos-nuxt/tests/visual/baselines/preorders-week-390x844-light.png)

### Busca mobile

- Antes: [imagem](before/preorders-search-390x844-light.png)
- Depois: [`preorders-search-390x844-light.png`](../../../../surfaces/pos-nuxt/tests/visual/baselines/preorders-search-390x844-light.png)

## O que permaneceu igual

- busca nasce focada e aceita leitor/digitação;
- Enter abre o único resultado;
- Dia/Semana, data, filtros e busca continuam na URL;
- a volta do detalhe retorna ao mesmo recorte;
- lote imprime somente as encomendas visíveis;
- detalhe e ações continuam server-driven pelo contrato integrado no #1231;
- nenhum endpoint, migration, dado ou integração externa mudou.

## Verificação automatizada

- matriz visual: semana em 1440×900, 768×1024 e 390×844; busca em 390×844;
- teste funcional exige uma única árvore semanal e três cards no cenário;
- baselines vivem em `surfaces/pos-nuxt/tests/visual/baselines/` e são comparados por Playwright;
- snapshots “antes” foram produzidos no commit de `origin/main` com o mesmo harness e a mesma fixture.
