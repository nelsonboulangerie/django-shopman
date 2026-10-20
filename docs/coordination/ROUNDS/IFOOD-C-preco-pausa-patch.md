# IFOOD-C — preço e pausa por PATCH específico

- **id:** IFOOD-C
- **sessão:** frente 6, turno 2 de 19/10/2026 (Codex)
- **branch:** `codex/ifood-preco-pausa-patch`
- **PR:** #1928
- **estado final:** na fila #1928 (auto-merge pedido)
- **início / fim:** 2026-10-19

## Objetivo

Fazer alterações isoladas de preço e disponibilidade pelo PATCH específico do catálogo iFood,
preservando a estrutura completa do item e confirmando o resultado por leitura remota.

## O que mudou

- A diretiva conserva a causa da alteração. `price_changed` e `operator_price_intention` seguem por
  `PATCH /items/price`; `availability_changed` e `stock_changed` seguem por
  `PATCH /items/status`.
- O PATCH de preço envia somente `itemId` e `price`. O de disponibilidade envia somente `itemId` e
  `status`. Nome, descrição, categoria, índice, turnos, imagem e contextos alheios não entram.
- Criação, publicação estrutural, texto e sincronização manual continuam no PUT completo.
- Depois do PATCH, o adapter lê `GET /items/{itemId}/flat` e só confirma sucesso quando preço ou
  status remoto coincide com a intenção atual.
- O handler continua relendo o item dentro do mutex por SKU/canal. Mudanças rápidas e retries usam
  o estado atual, não o preço ou a pausa antigos guardados no evento.
- A guarda de escrita continua antes de OAuth e HTTP. Não houve ensaio externo.

## Prova

- 89 testes relacionados aprovados, com 4 casos PostgreSQL pulados no SQLite local.
- Cobertura de PATCH mínimo de preço/status, confirmação remota, falha de leitura sem falso
  sucesso, 429 com intenção preservada, retry lendo o preço vigente e pausa recebida durante envio
  convergindo em `UNAVAILABLE`.
- Ruff e `git diff --check` aprovados.
- Desempenho: nenhuma consulta ORM foi acrescentada ao handler ou adapter. Cada alteração pontual
  troca um PUT completo por um PATCH pequeno e uma leitura de confirmação. Não há endpoint de
  superfície nesta fatia, portanto Server-Timing não se aplica.

## O que ficou de fora

- O resolvedor de identidade remota da frente B ainda depende da #1905.
- A tela de categorias pertence à frente D.
- Nenhuma credencial, loja real ou item real foi usado.

## Perguntas ao dono

nada
