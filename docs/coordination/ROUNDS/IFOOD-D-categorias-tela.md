# IFOOD-D - categorias na página do canal

- **id:** IFOOD-D
- **sessão:** frente 6, turno 2 de 19/10/2026 (Codex)
- **branch:** `codex/ifood-categorias-tela`
- **PR:** #1931, base `main`
- **estado:** na fila #1931
- **início / fim:** 2026-10-19 / 2026-10-20

## Objetivo

Dar ao operador uma tela única para conferir as categorias do catálogo iFood, renomeá-las,
alterar a posição e ligar cada coleção interna à categoria remota escolhida. Nenhum identificador
remoto ou JSON aparece como ferramenta de operação.

## O que mudou

- A projeção de revisão de vínculos agora também entrega categorias remotas, coleções internas,
  mapeamentos e ações. Não nasceu uma segunda projeção de edição.
- A leitura ao vivo só ocorre quando a captura selecionada pertence ao mesmo merchant configurado.
  Falha de confirmação conserva a última captura e vira aviso legível.
- Renomear envia só `name`; reordenar envia só `index`. Depois do PATCH, a API lista as categorias
  novamente e só conclui quando nome ou posição coincidem.
- O mapeamento de coleção exige que a categoria exista na leitura remota confirmada antes de
  persistir `Channel.config.ifood_catalog.category_map`.
- Todas as mutações usam intenção recuperável, ator autenticado e escopo da captura. A tela preserva
  a escolha em falha e bloqueia gravação com leitura desatualizada.
- A página passou a se chamar "Catálogo" e separa com clareza alterações externas de categoria dos
  vínculos de produto, que continuam locais.

## D1 a D12

- **D1:** card superior outline; cards internos soft; selos sem variante explícita, com `soft` do tema.
- **D2:** cards sem faixas próprias de cabeçalho ou rodapé.
- **D3:** botões do conjunto canônico, sem esticar e agrupados pelo conteúdo.
- **D4:** conteúdo usa toda a largura disponível em `md` e `xl`.
- **D5:** cards irmãos usam grid `items-stretch` e `h-full`.
- **D6:** rótulos completos: "Renomear", "Alterar posição" e "Categoria no iFood".
- **D7:** nome tem `max-w-sm` e posição `max-w-32`, ambos menores que o espaço das ações.
- **D8:** indisponibilidade da leitura usa aviso acionável da página, na cor de warning.
- **D9:** nome e posição são ajustes inline com Aplicar/Cancelar; mapeamento é escolha explícita.
- **D10:** copy revista com o vocabulário da casa, sem jargão, IDs ou JSON.
- **D11:** Nuxt UI canônico (`NuxtCard`, `NuxtBadge` sem `variant`, `NuxtAlert`, `NuxtFormField`,
  `NuxtInput`, `NuxtSelect`, `NuxtButton`).
- **D12:** as oito capturas foram abertas e inspecionadas depois do teste em navegador real.

## Desempenho

- Antes: `GET /catalog/channels/<ref>/review/` fazia 9 consultas e não publicava `Server-Timing`.
- Depois: 10 consultas, uma consulta fixa para listar coleções, sem consulta por categoria ou item.
  O header passou a publicar `projection` e `db`; amostra local: `projection=6,20 ms`, `db=0,89 ms`.
- O teste trava o teto em 10 consultas.

## Prova

- Django: 36 aprovados e 2 pulados; os pulos são os cenários concorrentes exclusivos de PostgreSQL.
- Nuxt unit/component: 17 aprovados.
- Navegador de produção: 4 aprovados (`md`/`xl`, claro/escuro), zero 4xx/5xx.
- Typecheck, ESLint, Ruff, inventário do orquestrador, JSON e `git diff --check` aprovados.
- Capturas antes: [md claro](img/ifood-d-before-md-light.png),
  [md escuro](img/ifood-d-before-md-dark.png), [xl claro](img/ifood-d-before-xl-light.png),
  [xl escuro](img/ifood-d-before-xl-dark.png).
- Capturas depois: [md claro](img/ifood-d-after-md-light.png),
  [md escuro](img/ifood-d-after-md-dark.png), [xl claro](img/ifood-d-after-xl-light.png),
  [xl escuro](img/ifood-d-after-xl-dark.png).

## Conserto do turno 4, 20/10/2026

- Removida a variante explícita dos dois selos novos; o teto `badgeVariant=0` do Gestor voltou a
  passar sem ampliar o conjunto mínimo.
- A falha da leitura remota agora registra canal, catálogo e traceback antes de conservar a captura
  conhecida e mostrar o aviso legível.
- Prova focada: conjunto mínimo 10/10; componente e composable 10/10; catálogo e higiene 27
  aprovados, 2 pulados; navegador de produção 4/4; ESLint e Ruff aprovados.
- `test-backstage`: 9.758 aprovados, 62 pulados e uma falha de infraestrutura do `xdist/execnet`
  ao serializar `datetime.date` de um `subTest` do PDV. O caso isolado, sem `xdist`, passou com 1
  teste e 3 subtestes.
- Capturas do conserto, abertas e inspecionadas: [md claro](img/ifood-d-fix-1931-after-md-light.png),
  [md escuro](img/ifood-d-fix-1931-after-md-dark.png),
  [xl claro](img/ifood-d-fix-1931-after-xl-light.png) e
  [xl escuro](img/ifood-d-fix-1931-after-xl-dark.png).

## O que ficou de fora

- Criar e mudar o status de categoria seguem disponíveis na API da frente A, mas não foram pedidos
  na tela desta fatia.
- Nenhuma chamada foi feita a loja real e nenhuma credencial foi usada.
- O ensaio real permanece na frente E. Merchant, credenciais locais e alvos de teste foram
  encontrados em 20/10; a execução aguarda a #1905 e esta tela entrarem no `main`.

## Perguntas ao dono

nada nesta frente
