# Integrações no cadastro canônico do Gestor

## Direção definida com o usuário

Todos os produtos da loja iFood devem ser reconciliados e gerenciados pelo Shopman. Pendência de vínculo é transitória, não uma opção permanente de ignorar anúncios. Isso não implica publicar todo o catálogo interno no iFood. Coleções internas e categorias externas podem diferir; nomes, agrupamento e seleção comercial são independentes.

A aba Integrações concentra vínculo e particularidades do destino. Preço, publicação, pausa, informações do produto e ações em lote continuam pelos serviços e controles existentes. Vincular não publica, não renomeia o SKU interno e não movimenta o anúncio remoto.

## Estrutura existente verificada

- `CatalogProductPanel.vue`: painel canônico com rascunho, hidratação, validação e patch parcial; contém a aba Redes sociais com marca, GTIN, MPN, condição, categorias Google/TikTok, hashtags e legenda.
- `services/catalog.py`: leitura e mutação do detalhe, preços e publicação canônicos. Preservar auditoria e atomicidade da PR #649.
- `Channel`: identidade comum para canal de venda e feed. A política comercial mantém a distinção real entre venda e exibição (ADR-018).
- `ListingItem`: preço, publicação e vendabilidade por canal transacional; não duplicar esses campos em configuração de integração.
- `services/feeds.py`: seleção de coleções e pausa por SKU em `config.display`; feeds anunciam preços do canal de origem, não recebem tabela de preço própria.
- `CatalogSyncState`: resultado operacional por SKU/canal e indicadores da matriz; não basta como cadastro de vínculo, pois só guarda um ID e não identifica loja, catálogo e contexto.
- `catalog_projection_ifood.py`: hoje deriva UUIDs por merchant/SKU e envia payload completo. Não pode adotar anúncios preexistentes com segurança sem reconciliação dos IDs e preservação dos campos remotos.

## Experiência proposta

Reaproveitar o painel de produto e acrescentar Integrações, com seções apenas dos destinos configurados. Em cada destino: produto externo vinculado, código externo, categoria de destino e pendências específicas. IDs técnicos ficam em detalhes recolhidos; credenciais não pertencem ao produto.

O operador seleciona um resultado do inventário remoto, vendo nome, código e categoria; não precisa copiar UUID. Código exato só gera sugestão quando único no escopo da loja e catálogo. Nomes são sugestões, nunca confirmação automática. Vínculos duplicados ou ambíguos impedem o envio e aparecem como pendência.

Preservar os atributos atuais de Redes sociais como fonte única: marca, GTIN, MPN, condição, classificações Google/TikTok, hashtags e legenda. Na aba Integrações, indicar os atributos faltantes e oferecer atalho ao campo existente, sem copiá-lo. Uma reorganização visual futura pode reaproveitar esses componentes, mas não exige renomear ou migrar `metadata.social`.

Preço e pausa continuam na matriz; informações no cadastro; ações coletivas nos controles atuais. A aba pode mostrar estado e atalho para o controle canônico, sem uma segunda implementação de edição. O estado remoto confirmado vem da mesma projection usada na matriz.

## Organização por canal

Mapeamento padrão coleção/categoria pertence à configuração do canal dentro do Gestor, não deve ser repetido em cada produto. A aba do produto mostra o destino resolvido e permite uma exceção explícita. Várias coleções podem apontar à mesma categoria; uma coleção pode ser dividida por exceções individuais. Empate entre regras exige resolução, não depende da ordem de iteração.

O mapeamento não determina publicação. A seleção comercial continua no Listing do canal. Uma coleção interna inativa não deve, por esse motivo isolado, mover ou apagar anúncios remotos. A organização remota inicial é preservada até uma intenção explícita de mudança.

## Persistência e limites

Manter Offerman agnóstico: nenhum campo iFood em Product, Collection ou ListingItem e nenhum novo motor de preço/publicação. Particularidades de API ficam no adapter do shop; validação, permissões e projections do operador no Backstage.

Usar uma associação durável de catálogo no shop, separada do resultado de sincronização. O contrato precisa identificar canal, loja externa, catálogo/contexto, produto local e recurso externo. A unicidade remota deve ser garantida no banco, não só no formulário. O armazenamento final e a migração serão definidos após conferir ocorrências múltiplas de um produto na loja; não assumir relação bijetiva SKU/item. Dados específicos adicionais podem usar JSON validado e documentado, sem criar um framework genérico de formulários.

O bloco de leitura de integrações deve ficar separado do `product` editável na resposta. `ProductDetailPatch` e revisões derivam campos automaticamente do detalhe; não deixar IDs e estados remotos entrarem no salvamento geral. Ações de vínculo usam validação, revisão e recibo próprios, reaproveitando a infraestrutura existente.

`CatalogSyncState.external_id` continua diagnóstico do último envio; não se torna um segundo cadastro editável. Ao adicionar uma associação durável, definir um único resolvedor usado pelo adapter de saída e pelo ingresso dos pedidos, preservando a compatibilidade com códigos externos que já existam nos pedidos. Alteração de vínculo deve invalidar resultado antigo e impedir que diretivas já enfileiradas escrevam no destino anterior.

## Implantação incremental

1. Inventário somente leitura da loja correta: categorias, itens, produtos, complementos, códigos, contextos e duplicidades. Separar claramente evidência da loja real e da loja de teste.
2. Associação durável, resolvedor e testes de identidade; nenhuma alteração remota ao salvar vínculo.
3. Aba Integrações e reaproveitamento dos atributos de feeds, utilizando patch parcial e permissões existentes.
4. Envio pelos controles canônicos, com PATCH específico de preço/status; outras edições preservam estrutura remota. Registrar pendência, erro e confirmação por leitura remota.
5. Ensaio por produto na loja de teste, inclusive alterações rápidas, pausa/retomada e exceção de categoria. Publicação coordenada com #640 e #649.

## Critérios de aceitação

- Todos os anúncios da loja estão vinculados ou constam como pendências explícitas de reconciliação; concluir a adoção exige zerar essas pendências.
- Salvar vínculo não publica, pausa, muda preço ou categoria no iFood.
- O mesmo recurso remoto não pode ser atribuído por duas gravações concorrentes a produtos locais diferentes.
- Preço e pausa pela matriz usam os IDs existentes e preservam campos não alterados.
- Excluir campo do patch o preserva; limpar intencionalmente uma exceção restaura a regra padrão, sem apagar outros destinos.
- Uma coleção pode ficar fora do canal; a configuração do iFood não altera a organização de outros canais.
- Feeds preservam a seleção por coleções e o preço proveniente do canal anunciado.
- Auditoria registra autor e antes/depois; falha no enqueue reverte a intenção conforme B7.
- Nenhuma credencial entra na projection do produto; erro remoto é legível no celular.
- Registrar o vínculo não é apresentar a integração como homologada ou sincronizada.

## Referências

- [Endpoints oficiais iFood](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/endpoints)
- [Contextos de catálogo](https://developer.ifood.com.br/en-US/docs/food/guides/modules/catalog/guides/multisetup)
- `docs/decisions/adr-018-surface-is-channel-with-commerce-policy.md`

Documento de desenho baseado em inspeção do código. A aba e a associação durável ainda não estão implementadas.

## Revisão adversarial posterior: ponto de entrada e escopo

Esta revisão substitui a recomendação de começar pela nova aba do produto. A seção Feeds já é o centro de configuração de destinos: contém seleção de coleções, estado da saída, prévia, rotação de TV, rascunhos com revisão, recibos de intenção, atualização SSE e tratamento de leitura indisponível. A matriz já responde pelas operações comerciais. Criar outro centro de configuração no cadastro aumentaria navegação e duplicaria responsabilidades.

Recomendação amadurecida: evoluir Feeds para **Canais**, preservando três seções principais no Gestor (Pedidos, Catálogo, Canais). A página reúne destinos de venda e exibição que tenham configuração disponível; cada destino expõe suas ações reais. Integrações é um nome possível, porém não descreve tão bem a TV interna já atendida. O nome Canais corresponde à entidade existente sem exigir que a pessoa conheça `commerce_policy`.

No produto, começar com uma seção compacta de vínculos/atalho para o canal, reutilizando o MESMO editor contextual. Uma aba própria só se justifica quando o volume de configuração realmente exceder essa seção. Não acrescentar uma aba vazia para cada plataforma. A reconciliação inicial é coletiva na página do canal, com entrada reversa no produto para exceções; não exigir abrir cada produto para adotar uma loja pronta.

Não generalizar o contrato FeedProjection por renomeação: `active` altera Channel.is_active, seleção escreve config.display.collections, rotação e URL têm semântica de exibição. Marketplace não pode herdar esse conjunto. Reutilizar layout, identidade, permissões, ações e intenções; manter validadores e execução específicos. Não criar um switch único para conexão, projeção e abertura da loja. Estado de conexão, pendência de configuração e resultado de sincronização são informações distintas.

O modelo de vinculação durável proposto ainda precisa provar a necessidade de cada campo contra o inventário. Primeiro mapear registros existentes; não presumir um item por SKU nem criar taxonomia local concorrente. Guardar a categoria atual do anúncio como ponto de partida. Regras coleção/categoria são opcionais: o vínculo individual já resolve a adoção, e regras só entram se reduzirem trabalho real. Evitar motor de regras para organizar algumas categorias.

Crítica cética aplicada: uma única entidade Channel não implica um formulário universal; menos tabelas por si só não garante integridade; reutilizar feeds não significa aplicar ao iFood sua ordem global ou sua curadoria automática por coleções. Não alterar preço, publicação ou categoria só porque o vínculo foi salvo. Não mover atributos de Redes sociais por estética. O desenho foi validado por leitura da base 4fd373df0 e composição conhecida com B7, não por inspeção atual do navegador em produção.
