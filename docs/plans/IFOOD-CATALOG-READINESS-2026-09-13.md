# Catálogo iFood: preparação e critérios de validação

## Objetivo

Operar o catálogo pelo Nuxt Gestor, mantendo categorias, informações, preço e disponibilidade coerentes com o catálogo canônico. O chamado 33298264 trata a conectividade de pedidos; sua resposta não impede corrigir e testar os defeitos internos de catálogo.

Estado observado em 12/09/2026 BRT: projeção iFood desligada no runtime, credenciais de teste, mapa de categorias vazio e nenhuma categoria padrão. Gestor com 111 produtos e nove coleções; catálogo remoto de teste com três categorias e nove itens. São observações datadas, não configuração a aplicar automaticamente.

## Sequência de trabalho

| Etapa | Resultado exigido | Evidência de conclusão |
|---|---|---|
| Concorrência de envio | Alteração durante envio permanece pendente e converge à última revisão; dois workers não deixam um envio antigo prevalecer | Regressões de pausa/retomada/preço durante HTTP, retry e dois workers; conferir payload final e ausência de falso sucesso |
| Identidade e contexto | Vínculo por merchant, catálogo, contexto e SKU; ambiguidades bloqueiam escrita | Inventário lido da API comparado ao catálogo local, sem recriar IDs preexistentes |
| Preço e disponibilidade | Alteração pontual preserva imagem, complementos, horários e contextos alheios | PATCH específico seguido de leitura do item; repetir a mesma intenção não duplica recursos |
| Categorias | Criar, renomear, mover e ordenar conforme coleção canônica; mostrar pendência/erro | Alteração local e leitura remota com identidade e ordem preservadas; corpo de atualização validado na loja de teste |
| Informações do produto | Nome/descrição/imagem e complementos aplicáveis preservados | Upload e leitura da imagem; comparação integral antes/depois sem apagar estrutura fora do escopo |
| Operação no celular | Distinguir mudança local, envio pendente, falha e resultado confirmado | Erro legível por toque; nenhuma indicação de sincronizado antes da convergência |
| Ensaio oficial | Ações pelo Gestor reproduzidas na loja de teste | Gravação com data/hora e leituras remotas; estados anteriores registrados e restauração conferida |

## Matriz de regressão da fila

- Uma pausa feita enquanto um snapshot AVAILABLE está em trânsito precisa resultar em UNAVAILABLE, sem deixar a última intenção sem execução.
- Pausa seguida de retomada durante o envio deve terminar na última intenção, inclusive quando os gatilhos têm o mesmo nome.
- Um worker concorrente não pode ultrapassar a operação em trânsito do mesmo SKU/canal; SKUs/canais independentes continuam processáveis.
- Erro transitório e 429 preservam a mudança posterior e o estado pendente; o retry lê os dados atuais.
- O limite de tentativas e a recuperação de execução interrompida precisam ter resultado explícito; não confundir término da Directive com confirmação do remoto.
- Rollback da edição deve reverter também o enqueue. Preservar o contrato do bulk: flags, auditoria, recibo e Directive são atômicos.
- Reenvio manual mantém a assinatura de enqueue; nenhum novo fluxo paralelo de escrita no catálogo.

## Ensaio oficial de catálogo

Preparar um item de teste vinculado a uma categoria de teste, com descrição, preço, imagem e complemento quando aplicável. Registrar seu estado inicial completo e IDs. Usar o Gestor para pausar, retomar, alterar preço, alterar descrição e mover categoria; após cada ação, conferir a resposta e o estado retornado pela API. Repetir com duas alterações rápidas e com resposta perdida simulada somente no ambiente isolado. Restaurar os valores iniciais e conferir a leitura final.

Não confundir AVAILABLE com vendável: categoria, horários, contexto e complementos obrigatórios podem impedir a venda. O teste deve observar essas restrições. Não habilitar a projeção em massa como forma de testar um único item.

## Contratos oficiais conferidos em 13/09/2026

- [Endpoints FOOD](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/endpoints): preço e status têm PATCH específicos; podem ser globais ou por contexto. Atualizar somente o contexto explicitamente pretendido.
- [Disponibilidade](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/guides/availability): usar a operação de status para pausar/retomar sem reenviar o item completo.
- [Uso da API](https://developer.ifood.com.br/en-US/docs/guides/modules/catalog/using-api): preservar os valores e overrides que não fazem parte da alteração.
- [Homologação Catalog](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/homologation): processo próprio de Catalog, separado de Order/Events.

Na leitura autenticada anterior, `GET /catalog/v2.0/merchants/{merchantId}/catalogs/{catalogId}/categories?includeItems=true` retornou os nove itens. A variante `include_items=true` retornou listas vazias no mesmo endpoint: ausência aparente de itens não autoriza recriação. O Swagger atual confirma `includeItems` e marca `include_items` como deprecated.

### Categorias: contrato confirmado

Fonte: [referência oficial](https://developer.ifood.com.br/en-US/docs/references), Swagger `catalog-v2` no [JSON público da página](https://developer.ifood.com.br/page-data/en-US/docs/references/page-data.json), esquemas `PostCategoryDto` e `PatchCategoryDto`.

- Criar: `POST /catalog/v2.0/merchants/{merchantId}/catalogs/{catalogId}/categories`. Obrigatórios `name`, `status`, `template`; opcionais `id`, `externalCode`, `index`. Resposta 201.
- Editar: `PATCH /catalog/v2.0/merchants/{merchantId}/catalogs/{catalogId}/categories/{categoryId}`. Opcionais `name`, `externalCode`, `status`, `index`; resposta 200. Omitir campos que não se pretende alterar.
- Nome com até 100 caracteres; status AVAILABLE/UNAVAILABLE; template DEFAULT/PIZZA apenas na criação. Ordenação usa `index`, não `sequence`.
- Nome duplicado pode retornar 409. Não criar outra categoria automaticamente após esse conflito: reconciliar a identidade existente.
- Alterar status da categoria pode afetar seus itens. Renomear envia somente `name`; reordenar envia somente `index`.

Contrato documental confirmado; criação/edição ainda precisam ser exercitadas no merchant de teste antes de ativar o espelhamento.

## Coordenação

Esta etapa prepara correção e testes em worktree própria. Publicação será ordenada pela tarefa Coord Repo; a correção não altera preços, categorias, permissões ou a flag de projeção no ambiente publicado. A frente B7 mantém autoria, auditoria e recibos de pausas em massa; o enqueue precisa preservar sua atomicidade.

## Entrega da correção de concorrência

O handler agora serializa os envios por SKU/canal com advisory lock transacional PostgreSQL. A edição do operador não segura esse mutex: registra seu estado pendente e uma nova ocorrência durável quando o envio anterior já começou. Ocorrências ainda na fila podem ser agrupadas. A finalização compara o snapshot enviado ao estado atual sob uma trava curta de sincronização, preservando a edição posterior e evitando pendência falsa após finalização fora de ordem.

Validação local: 45 testes em PostgreSQL 16; 62 em SQLite (quatro casos de concorrência reservados ao PostgreSQL); 115 testes do Backstage aprovados e dois skips existentes. Ruff, gate de falhas silenciosas e diff-check aprovados. O PostgreSQL temporário foi encerrado e removido. As verificações usam transporte simulado, sem alteração de catálogo remoto.

Limites: o mutex cobre o handler, não chamadas diretas de sincronização pelo CLI/CatalogService. SQLite usa mutex restrito ao processo para desenvolvimento. Uma conexão com o banco perdida não desfaz uma requisição já recebida pelo provedor; a leitura remota e reconciliação continuam parte necessária do ensaio antes da ativação. As demais etapas da matriz permanecem pendentes.
