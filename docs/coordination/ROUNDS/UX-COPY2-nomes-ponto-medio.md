# UX-COPY2: nomes de produto do seed com ponto médio

- **id:** UX-COPY2
- **sessão:** reforma SUITE-UX, onda 1 (Claude, subagente em worktree próprio)
- **branch:** claude/ux-copy2-nomes-ponto-medio
- **PR:** #1432
- **estado:** pronto, na fila (auto-merge)
- **início / fim (UTC):** 2026-10-03 / 2026-10-03

## Objetivo
Seguimento do UX-COPY1 (#1428), item 3 do "ficou de fora". Decisão do dono (03/10): nos
nomes de produto, trocar o travessão pelo ponto médio (" · "), como em "Chalosofia Kãnfa ·
Lata 50g". O hint do defeito "Contaminado" é texto de defeito: reescrever pela pontuação do
sentido. Seed, dado vivo do alpha (migração de dados reversível que só toca o texto exato
antigo) e travas.

## O que mudou
- **Seed** (`config/management/commands/seed.py`): os 12 chás Kãnfa da tabela de produtos
  ("Aconchego Chai Kãnfa · Lata 50g" e irmãos) e o hint do "Contaminado", que passou a
  "Matéria estranha: não vende" (o dois-pontos diz a consequência; os irmãos são lista de
  sintomas com vírgula, e vírgula aqui leria "não vende" como mais um sintoma).
- **`apply_grocery_catalog`** (a mesma tabela do banco vivo, que o seed chama): as duas
  latas que só existem lá (Chalosofia L50, Vital L70). Sem isso, o comando acusaria
  conflito de nome contra o banco migrado.
- **Migração de dados `shop.0087_nomes_kanfa_com_ponto_medio`** (padrão da `shop.0018`):
  reescreve `offerman.Product.name` e `buyman.Material.name` (o cadastro de compra do mesmo
  SKU nasce com o nome do produto) só onde SKU e nome batem EXATAMENTE com o texto antigo,
  e o `QualityDefect.hint` do `contaminated` só se ainda for o texto antigo. Reversível pela
  mesma tabela. Core intocado (a migração mora no `shop`, como a 0073).
- Testes que fixavam o nome antigo como fixture: `test_apply_grocery_catalog.py`,
  `test_purchase_recebe_revenda.py`.
- **Trava nova** `shopman/shop/tests/test_nomes_kanfa_ponto_medio.py`: lê as tabelas de
  catálogo do seed e do `apply_grocery_catalog` pelo AST e reprova nome de produto com
  travessão; confere que seed e migração escrevem o mesmo texto; testa a migração com nome
  antigo, nome editado à mão, hint editado, ida e volta, e banco vazio.

## Exceções nas travas
Não havia exceção nominal a tirar: a trava de Python (`test_copy_sem_travessao.py`) não lê
`management/commands/` nem `migrations/` por desenho, e a das superfícies não lê o seed. Por
isso a tabela de produtos ganhou a trava própria acima, em vez de abrir `management/commands/`
inteiro (a saída de terminal desses comandos continua fora, como decidido no #1428).

## Evidência
- `pytest` (trava nova, travas de copy, grocery, revenda): `1131 passed in 66.08s`
- `pytest` (seed operacional, campanhas, catálogo coerente, qualidade/QC, compra/venda,
  aliases, deploy checks): `196 passed, 5 warnings in 274.70s`
- `makemigrations --check --dry-run`: `No changes detected`
- `ruff check` nos arquivos tocados: limpo
- numeração: `shop` em `origin/main` termina em `0086`; nenhuma branch remota com
  `shop/0087` desde 28/09.

## Ficou de fora, com motivo
- A **descrição** do Jambon-Beurre no seed ("Baguette, manteiga e presunto — o clássico
  parisiense") e as notas de revisão das etiquetas do B.I. (fim do seed): não são nome nem
  rótulo de produto, que é o escopo da decisão do dono. A descrição é voz da loja (frente
  do Storefront).
- Integrações externas que guardam o nome (cardápio do iFood, feed social): o nome novo
  chega na próxima sincronização normal; nada aqui as dispara.
