# IFOOD-A — categorias pela API

- **id:** IFOOD-A
- **sessão:** frente 6, turno 2 de 19/10/2026 (Codex)
- **branch:** `codex/ifood-categorias`
- **PR:** #1927
- **estado final:** na fila #1927 (auto-merge pedido)
- **início / fim:** 2026-10-19

## Objetivo

Listar, criar, renomear, reordenar e mudar o status de categorias do catálogo iFood com o contrato
v2.0, sem tocar no payload de itens nem relaxar a política que só permite escrita em merchant de
teste.

## O que mudou

- Serviço de categorias com `includeItems=true`, criação e PATCH mínimo por intenção.
- HTTP 409 interrompe a criação e pede reconciliação da identidade existente; não há segunda
  tentativa automática.
- HTTP 429 carrega `Retry-After` e conserva o corpo exato da intenção para o chamador.
- A guarda de escrita roda antes de OAuth e HTTP em todas as operações remotas.
- O mapa administrável fica em `Channel.config.ifood_catalog.category_map`. A leitura prioriza
  esse mapa e preserva `SHOPMAN_IFOOD.catalog_category_map` e
  `SHOPMAN_IFOOD.catalog_default_category` como fallback compatível.
- O mapa vazio só produz erro de categoria. Nunca cria uma categoria por conta própria.

## Prova

- 38 testes relacionados aprovados: serviço novo e suíte da projeção iFood.
- Ruff aprovado nos três arquivos de implementação/teste.
- `git diff --check` aprovado.
- Contagem de consultas: a configuração estática anterior fazia 0 consultas; a configuração
  administrável faz 1 consulta por lote projetado, nunca por item. Não há endpoint ou tela nesta
  fatia, portanto Server-Timing e capturas claro/escuro não se aplicam.

## O que ficou de fora

- A tela e seus endpoints de superfície pertencem à frente D.
- O resolvedor de identidade dos itens pertence à frente B e aguarda a #1905.
- Preço e pausa por PATCH específico pertencem à frente C.
- Nenhuma chamada foi feita a uma loja real e nenhuma credencial foi usada.

## Perguntas ao dono

nada
