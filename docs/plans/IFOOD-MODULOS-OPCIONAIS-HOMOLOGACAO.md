# Homologação dos módulos opcionais do iFood (Merchant, Catalog, Review, Financial)

Compromisso: DEV-2026-044. Chamado de origem: iFood Developer **36323618** (aberto em
14/11/2026, critérios recebidos em 17/11/2026 de Vinicius Mateus Armbruster, Time de
Integrações). O chamado 36323618 está "Resolvido": ele serviu só para entregar os critérios.
As evidências vão num **chamado novo**, categoria Homologação.

## Por que importa

Hoje só ORDER e EVENTS estão homologados (10/11/2026). Sem Merchant, a pausa e o horário do
Gestor batem em 403 e não chegam à loja real (PR #2556 transforma isso em aviso). Sem Catalog,
esgotar um item no Gestor não chega ao iFood (#2540). Review e Financial não existem no código.

## Regras de evidência (valem para os três módulos)

O iFood recusa e pede tudo de novo se faltar qualquer item:

1. **Um vídeo por cenário**, gravado dentro do NOSSO sistema, com o **Portal do Parceiro**
   mostrando o efeito quando o cenário pede ("valide se reflete no Portal do Parceiro").
2. Em todo vídeo, **data, hora e `client_id` do app de teste visíveis**.
3. Vídeo vai por **link** (Google Drive, pasta "iFood homologação 2026-11", um link por
   cenário, nome `merchant-c1-informacoes-da-loja.mp4` etc.), **nunca anexo**.
4. Junto, os **logs oficiais das requisições** de todos os fluxos gravados, exportados em JSON
   pelo Developer Portal (Logs da API).
5. Nota no chamado: data e hora de cada execução e o `client_id`.

**Ambiente:** app de teste `NB Teste (C)` (credenciais no `.env` local da árvore principal,
nunca copiadas para terminal gravado, log, captura ou PR) e loja de teste
"Teste - Nelson Boulangerie", merchant `2512433` / `f36a17d0-e10b-4fdd-a16d-c8ffd866e59b`.
Runtime local e efêmero, nunca alpha nem produção (mesma preparação de
[docs/runbooks/ifood-catalog-test-rehearsal.md](../runbooks/ifood-catalog-test-rehearsal.md)).
Uma faixa fixa de homologação na tela mostra relógio e `client_id` (só no runtime de teste).

**Gravação:** captura do Chrome em quadros, convertida para MP4 (ffmpeg), com a faixa de data,
hora e `client_id` já na tela. Upload pelo Drive do dono, link "qualquer pessoa com o link".

## F1. Merchant (prioridade: destrava pausa e horário reais)

| Cenário do iFood | O que temos no `main` | Falta |
|---|---|---|
| 1. Listar lojas vinculadas, detalhes completos, disponibilidade | `list_merchants`, `get_merchant`, `get_status` em `shop/services/ifood_merchant.py`; projeção `backstage/projections/ifood_store.py` | Tela no sistema que mostre as três consultas (lista, detalhe, status com motivos) |
| 2. Criar pausa, listar ativas, remover; refletir no Portal | `create_interruption`, `list_interruptions`, `delete_interruption`; modelo `IFoodInterruption` | Gesto de operador para criar, listar e remover pausa com a resposta do iFood na tela; tratamento de 409 (sobreposição) |
| 3. Horário: sábado 10:00-19:00; domingo 09:00-12:00, 13:00-16:00, 17:00-23:00; consultar | `put_opening_hours` / `get_opening_hours`; `desired_shifts` | **`Shop.opening_hours` só aceita uma janela por dia** e `desired_shifts` manda um turno por dia. Precisa de vários turnos por dia (casa, calendário e tradução para o iFood), tela para cadastrar e consultar, e 400 de sobreposição tratado |

## F2. Catalog

| Cenário do iFood | O que temos no `main` | Falta |
|---|---|---|
| 1. Categoria "Teste Homologação"; item "Produto Teste" ativo, com preço e foto | Upsert de item, upload de foto e categoria por mapa (`catalog_projection_ifood.py`), ensaio provado em 20/10 | **Criar categoria** pelo sistema (hoje só mapeia categoria existente) |
| 2. Grupo de complementos com dois complementos (nome, preço, ativo, foto) | nada | **Complementos não existem no nosso catálogo.** Cadastro de grupo e complementos do canal iFood, sem campo novo no Core (Offerman fica só com produto vendável) |
| 3. Renomear item, trocar foto e preço, pausar; o mesmo no segundo complemento | `PATCH /items/price` e `/items/status` com leitura de volta | `PATCH /options/price` e `/options/status`; renomear e trocar foto de item e complemento |

Toda escrita continua presa à loja de teste (`SHOPMAN_IFOOD_CATALOG_WRITE_POLICY`,
`environment=test`). Abrir escrita na loja real é decisão do dono, depois da homologação (#2540).

## F3. Review

Nada existe no código. Falta o módulo inteiro:

- listar avaliações com os campos obrigatórios, filtro por data e teste do limite de página (100);
- detalhe completo e ID inexistente (erro tratado na tela);
- responder: três respostas válidas, uma em avaliação com status `PUBLISHED` (erro esperado) e
  uma com texto inválido (erro esperado).

**Pré-requisito com relógio:** pedidos de teste feitos no app do iFood com o **usuário de
teste**, levados até concluído pela nossa integração (fluxo gravado), e **avaliados no app**.
As avaliações levam de 24 a 48 h para aparecer na API. São necessárias **pelo menos 6**
avaliações (3 respondidas, 1 já publicada, 1 para texto inválido, folga).

## F4. Financial

O iFood exige **chamado separado**. Primeiro passo: abrir o chamado de homologação do Financial e
pedir o checklist. A implementação começa quando o checklist chegar.

## Ordem

1. Hoje: cadastrar o usuário de teste (Pedidos de teste) e abrir o chamado do Financial.
2. Dono faz os pedidos de teste no app; a integração local leva até concluído (gravado); dono avalia.
3. Em paralelo, F1, F2 e F3 (código), uma sessão e um PR por frente.
4. Gravação por cenário assim que cada frente estiver no `main`. Review grava depois das 48 h.
5. Chamado novo de Homologação com os links e os logs, um bloco por módulo.

## O que depende do dono (e só isto)

- **Usuário de teste do app do iFood:** fazer os pedidos na loja de teste com o e-mail
  cadastrado e, depois de concluídos, avaliá-los no app. O agente não entra com senha nem
  código de acesso em serviço de produção, e o app de consumidor do iFood é produção.
