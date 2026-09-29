# WP — Production Operational Data Readiness: abrir amanhã com dados reais

> **Status:** pronto para execução; nenhum dado foi importado e nenhuma alteração foi feita no Live.
>
> **Data-base:** 29/09/2026.
>
> **Missão:** deixar o Shopman pronto para a loja **abrir amanhã**, com todos os dados operacionais atuais, completos e aprovados. O legado ajuda a reconstruir identidade, fiscal, receitas e referências; vendas antigas ficam numa trilha analítica paralela que não bloqueia o Day-1. O plano falha fechado: ausência, divergência e fonte não acessível são `UNKNOWN`, nunca “zero”, “não se aplica” ou fato inferido.
>
> **Decisão do owner em 29/09/2026:** **`Catálogo Nelson — consolidado` é a fonte autoritativa inicial para o mix ativo e os preços atuais.** Shopman Live, cofre, iFood/Bling/outros canais e histórico apenas reconciliam; divergência sempre entra numa fila humana explícita e nunca sobrescreve o consolidado silenciosamente.

## 1. Resultado que este WP precisa entregar

### Trilha crítica — usar o sistema amanhã

No fim da trilha crítica, o Shopman terá:

1. organização/loja, identidade fiscal e parâmetros básicos corretos;
2. mix ativo, SKUs, listings, coleções e **todos os preços atuais por canal** aprovados;
3. fiscal de saída completo e assinado pelo contador;
4. receitas/BOM, rendimentos, fatores, perdas e validades vigentes;
5. insumos, unidades, conversões, fornecedores e custos vigentes;
6. contagem física inicial, lotes/validades e saldo de abertura assinado;
7. produção, capacidade, horários, calendário e restrições operacionais;
8. fulfillment, zonas, fretes, cutoffs e canais configurados sem defaults perigosos;
9. operadores, grupos, 2FA, PINs seguros, terminais, KDS, impressão, caixa e float conferidos;
10. integrações, templates, copy e readiness testados;
11. um cofre curado ampliado, exportado e restaurável, sem PII nem segredos;
12. um placar de Go-live por domínio: `GO`, `NO-GO` ou `UNKNOWN`, com evidência e responsável.

### Trilha paralela — memória histórica

Yooga e XMLs de vendas alimentam **exclusivamente** `HistoricalSale`, `HistoricalSaleItem`, B.I. e reconciliação analítica/fiscal. Essa trilha pode continuar depois da abertura e não bloqueia o Day-1, salvo quando uma evidência é necessária para resolver a identidade de SKU ou a classificação fiscal de um item ativo.

Cada registro histórico continua ligado a arquivo, hash, lote, chave externa e regra de transformação, mas nunca entra nos modelos operacionais.

O critério não é “tem alguma informação”. É: **a operação consegue confiar no valor, explicar sua origem e recuar sem fabricar realidade**.

## 2. Antiobjetivos e travas invioláveis

Este WP não:

- cria `Order`, `OrderItem`, lançamento de caixa, `PaymentIntent`, pagamento, reembolso, movimento de estoque, lote físico, ordem de produção, `Customer`, documento fiscal emitido ou consentimento a partir de histórico;
- transforma uma venda antiga em receita financeira ou saldo atual;
- trata telefone/endereço histórico como consentimento de marketing;
- mescla clientes por nome, endereço ou semelhança textual;
- publica preço, fiscal, alergênico, nutrição ou imagem sem aprovação responsável;
- infere saldo atual de compras, receitas, XMLs ou vendas passadas;
- importa SQLite inteiro, restaura dump legado sobre o banco atual ou executa `loaddata` indiscriminado;
- sincroniza catálogo para iFood, Google, Meta ou outro canal durante recuperação;
- aciona SEFAZ, manifesta ciência da operação, emite/cancela documento, consulta provider com efeito colateral ou cria promoção real;
- grava segredos, PII crua, certificado, token ou caminho pessoal no Git;
- apaga dado ausente na fonte. Ausência nunca significa exclusão;
- usa seed, fixture, imagem genérica ou default de desenvolvimento como fato da loja.

### Regra-mãe

**Histórico nunca cria pedido, cliente, ledger, estoque, pagamento ou consentimento vivos — automática ou manualmente por este WP.** Yooga/XML de venda entram somente em `HistoricalSale*`, B.I. e reconciliação. A operação viva nasce de gesto operacional explícito e auditado.

## 3. Evidência conhecida — e limites do que foi medido

As contagens abaixo são um ponto de partida sanitizado, não autorização de importação.

| Fonte/objeto | Evidência em 29/09/2026 | Estado |
|---|---:|---|
| Yooga — vendas autorizadas | **81.255** | medir novamente no artefato congelado |
| Yooga — itens | **~380.199** | aproximado; versões anteriores registraram outro total no banco, portanto recontagem obrigatória |
| Yooga — produtos | **220** | medir novamente |
| Yooga — clientes identificados | **4.769** | PII; não vira consentimento |
| Yooga — itens sem SKU | **~27.177** | resolver por alias/revisão; não casar só por nome |
| Período Yooga | **UNKNOWN**: `jul/2024–20/07/2026` conflita com `16/01/2024–20/07/2026` | gate bloqueado até recontagem por `min/max occurred_at` e fonte física |
| Mapa SKU Yooga | **143 linhas de dados** em [`sku-real-mapa.csv`](sku-real-mapa.csv) | proposta/curadoria; conferir estados e assinaturas |
| `Catálogo Nelson — consolidado` | **183 linhas**: 114 casa, 62 revenda, 57 materiais | fonte autoritativa inicial de mix/preço; categorias se sobrepõem, então medir chaves únicas e duplicatas |
| API pública viva — amostra | **44 itens** | amostra, não inventário completo do banco |
| Sem alergênicos na amostra | **11/44** | revisão humana obrigatória |
| Sem informação dietética | **25/44** | não publicar afirmação positiva por silêncio |
| Sem `warnings` | **44/44** | verificar semântica e cobertura |
| Sem `available_qty` | **18/44** | não interpretar como zero |
| `can_add=false`/quantidade 0 | **3/44** | conferir motivo operacional |
| Cofre curado | **33 entidades** + **6 abas transacionais somente leitura** | sem scheduler, retenção ou alerta comprovados |
| Receitas XLSX legadas | **34 abas**, incluindo versões `OLD` | versão vigente é decisão humana |
| Snapshot antigo de catálogo | **59 produtos, 9 coleções, 59 vínculos e 229 aliases** | evidência/diff; não restaurar cegamente |
| Imagens legadas | **43 hashes únicos** | deduplicar por conteúdo; aprovação visual por SKU |
| XML de fornecedor | parser unitário já existe | bulk/landing ainda não existem |
| XML de saída | não há landing/importador bulk comprovado | criar leitura histórica, nunca venda viva |

### Como encerrar os números `UNKNOWN`

O profiling de O0 deve publicar um `manifest.json` sanitizado por artefato com:

- nome lógico e `sha256` do arquivo, sem caminho pessoal;
- tamanho, formato, encoding e abas;
- quantidade de linhas brutas, válidas, duplicadas, rejeitadas e em branco;
- chaves mínima/máxima e datas mínima/máxima;
- contagem de chaves distintas, nulas e conflitantes;
- versão do parser e da regra de normalização;
- divergência contra toda contagem deste quadro.

Se `~380.199` não fechar, o relatório mostra as contagens por aba/arquivo e explica a diferença; não escolhe a que “parece certa”. O mesmo vale para o início do período Yooga.

## 4. Fontes físicas e finalidade permitida

| Fonte | Valor aproveitável | Uso permitido | Proibido |
|---|---|---|---|
| Export Yooga, três abas | vendas, itens, produtos, pagamentos textuais, clientes externos e contexto | histórico analítico; aliases; demanda; referência de preço passado | criar pedido, pagamento, estoque ou cliente contatável |
| XML NFC-e/NF-e de saída | chave, emissor/destinatário permitido, itens, totais, status fiscal, datas | arquivo histórico fiscal; conciliação com Yooga; evidência de cancelamento/autorização | reemitir, criar `Order`, assumir recebimento financeiro |
| XML NF-e de entrada | fornecedor, produtos, GTIN, unidades, quantidades, preços, NCM/CFOP/lote/validade quando declarados | enriquecer cadastro e preparar recebimento revisável; custo histórico | lançar estoque/contas a pagar sem conferência e recebimento explícitos |
| Cofre XLSX/CSV e Google Sheets | 33 entidades curadas | migração de curadoria por chave natural, com dry-run | incluir segredo, PII ou transacional no import |
| `Catálogo Nelson — consolidado` | fonte autoritativa inicial de mix ativo e preços atuais | preparar a candidata canônica e a fila de validação | aplicar linha sem identidade inequívoca, proveniência ou aprovação |
| `sku-real-mapa.csv` | mapa Yooga → SKU canônico | aliases assinados após validação | resolver ambiguidades silenciosamente |
| `RECEITAS 2.4.xlsx` e “Ficha Técnica - Maysa” | fórmulas, rendimentos, perdas, custos históricos e versões | rascunhos versionados e revisão do responsável técnico | escolher aba vigente, custo atual ou rendimento real por inferência |
| Snapshots de catálogo/SQLite | estado antigo e relações que podem ter sumido | whitelist, diff semântico e recuperação registro a registro | importar banco inteiro, PKs ou credenciais |
| Imagens legadas | candidatos por hash e possível SKU | deduplicação e fila de aprovação | assumir autoria/licença ou correspondência com produto |
| Bling | produtos, fornecedores, XMLs ou preços se exportação autêntica for localizada | reconciliação com data e id externo | sobrescrever o consolidado; promover divergência sem decisão humana |
| iFood/outros canais | catálogo e ids externos capturados | reconciliar publicação, disponibilidade e preço exibido | virar fonte de preço/mix, retroalimentar o canônico ou escrever/publicar durante este programa |
| API pública do Storefront | visão do que o cliente recebe | profiling de cobertura e regressão | tratá-la como inventário completo do banco |
| Live DB | estado operacional atual | leitura/profiling quando acesso read-only existir | mutação ad hoc no console |

### Artefatos que exigem localização antes do profiling

- export Yooga canônico e todas as versões candidatas;
- diretórios de XMLs de entrada e saída, com período e origem;
- arquivo local lógico `RECEITAS 2.4.xlsx` (fora do repositório) — somente metadados foram usados nesta auditoria; o arquivo não entra no Git;
- Google Drive “Ficha Técnica - Maysa” e planilhas do cofre;
- eventual export Bling/iFood;
- snapshots SQLite e diretório antigo `.claude/backup-cardapio-staging-2026-08-19/`, se ainda estiver disponível fora da branch;
- pasta original das imagens e prova de autoria/licença.

Localização ausente permanece `UNKNOWN`; nenhum agente deve vasculhar diretórios pessoais fora do escopo declarado.

## 5. Fonte de verdade e precedência

### 5.1 Regra geral

Precedência não é “último arquivo vence”. Para cada campo:

1. fato operacional nativo, assinado e atual;
2. decisão humana explícita, datada e atribuída, compatível com o domínio;
3. fonte externa oficial contemporânea ao fato;
4. fonte histórica autenticada;
5. inferência reproduzível, sempre marcada como candidata;
6. seed/default/exemplo — nunca verdade de produção.

Uma fonte de menor prioridade pode preencher campo vazio; não sobrescreve campo aprovado de maior prioridade. Conflito vira item de revisão.

Para **mix ativo e preço atual**, a regra específica substitui a precedência genérica: o ponto de partida é `Catálogo Nelson — consolidado`. Live, cofre, canais e histórico são comparadores. Cada diferença gera uma decisão com `field`, valor do consolidado, valor encontrado, fonte comparada, impacto, decisão, justificativa, ator e data. Nenhum job adota “o valor mais novo”, “o valor do Live” ou “o valor do canal” automaticamente.

Todo preço candidato/aprovado carrega, no mínimo:

- `amount_q` e moeda;
- escopo (`base` ou canal explícito);
- `as_of` — instante/data a partir do qual o valor é considerado vigente;
- `source` — `catalogo_nelson_consolidado` ou decisão humana posterior identificada;
- `approver` e `approved_at`;
- referência da divergência quando substitui o consolidado;
- validade/fim, quando temporário.

Preço sem `as_of`, `source` ou `approver` é `VALIDAR` e não pode ser publicado.

### 5.2 Precedência por domínio

| Domínio/campo | Fonte de verdade | Fontes auxiliares | Gate humano |
|---|---|---|---|
| SKU e identidade do produto | `Catálogo Nelson — consolidado` + alias aprovado | Shopman Live, cofre, Yooga, iFood, Bling | dono do catálogo resolve conflitos |
| Sortimento atual/publicação | `Catálogo Nelson — consolidado` como fonte inicial | Live, cofre, canais e vendas apenas reconciliam | dono decide cada divergência material |
| Preço de venda atual e por canal | `Catálogo Nelson — consolidado`, com `as_of/source/approver`; override por canal só por decisão explícita | Live/cofre/iFood/Bling/Yooga apenas reconciliam | dono; nenhuma vitória por “mais recente” ou aprovação implícita |
| NCM/CEST/CFOP/CSOSN/CST/origem/unidade tributável | parametrização fiscal aprovada | XMLs, GTIN e cadastro legado | contador/responsável fiscal |
| Alergênicos | receita vigente + declaração de cada insumo, com revisão | rótulo do fornecedor | responsável técnico |
| Nutrição | receita vigente, rendimento e base nutricional identificada | planilha antiga apenas como pista | responsável técnico; laudo quando aplicável |
| Imagem | foto real aprovada e licenciada para o SKU | arquivo legado por hash | dono/marketing |
| Receita e rendimento | versão publicada e assinada por quem produz | XLSX/Drive e fotos do caderno | padeiro/responsável de produção |
| Insumo e unidade-base | cadastro físico atual | XML NF-e e receita | compras/produção |
| Fornecedor | identidade legal atual por documento | XML de entrada, Bling | compras/financeiro |
| Custo vigente | última cotação/nota válida com data, embalagem e conversão aprovadas | custos 2017–2023 como referência histórica | compras; frescor definido |
| Estoque inicial | contagem física no instante de corte | nenhum histórico calcula saldo | dupla conferência operacional |
| Cliente | identidade explícita atual | external ids e hash de telefone | privacidade; merge revisável |
| Consentimento | recibo de consentimento nativo e verificável | nenhum dado histórico | encarregado LGPD |
| Venda histórica | Yooga/XML conforme lote e origem | de-paras canônicos | dados/financeiro |
| Pedido/pagamento/caixa vivos | ledgers nativos | nenhum legado | operação nativa somente |
| Horários, zonas, frete, cutoff e capacidade | decisão operacional vigente | configurações/snapshots antigos | dono/operação |
| Canais e fulfillment | configuração vigente testada | defaults apenas como alerta | dono/operação |

## 6. Classificação obrigatória de cada dado

Todo campo/fonte recebe uma destas ações no manifest de profiling:

| Código | Ação | Significado |
|---|---|---|
| `IMPORTAR` | gravar fato confiável no destino permitido | chave e precedência comprovadas; dry-run e gate passaram |
| `DERIVAR` | calcular de fontes registradas | fórmula/versionamento/proveniência disponíveis; recalculável |
| `VALIDAR` | manter candidato fora da publicação | plausível, mas requer pessoa ou fonte mais forte |
| `CRIAR` | cadastrar dado novo por gesto explícito | não há fonte confiável; responsável fornece o valor |
| `EXCLUIR` | retirar apenas da candidata/importação | segredo, PII desnecessária, seed, duplicata ou lixo comprovado; **não** apaga Live |

Exemplos normativos:

- mix/preço do `Catálogo Nelson — consolidado`: `IMPORTAR` apenas depois de identidade inequívoca e aprovação registrada; até lá, `VALIDAR`;
- divergência Live/cofre/canal versus consolidado: `VALIDAR` em fila humana; nunca resolver por sobrescrita automática;
- preço Yooga antigo: `VALIDAR`, nunca `IMPORTAR` como preço atual;
- chave de acesso e total de XML autêntico: `IMPORTAR` no histórico fiscal;
- alergênico derivado de receita incompleta: `VALIDAR`/bloquear, não afirmar “não contém”;
- nutrição com rendimento aprovado: `DERIVAR`, mas publicação ainda exige gate humano;
- saldo de estoque vindo de XML antigo: `EXCLUIR` do saldo; manter apenas histórico da compra;
- telefone Yooga: hash/últimos quatro quando necessários ao histórico; PII crua `EXCLUIR` da landing analítica após política de retenção;
- imagem genérica: `EXCLUIR` de feeds; pode servir apenas como ilustração de coleção nas superfícies próprias;
- default DDD 11 em operação de Londrina/DDD 43: `EXCLUIR`/corrigir antes do Live.

## 7. Landing raw imutável, lote e proveniência

### 7.1 Fluxo de dados

```text
fonte original
  → inventário read-only + hash
  → landing RAW imutável e criptografada
  → parser versionado
  → staging normalizado, ainda sem efeito operacional
  → profiling + reconciliação + fila de conflitos
  → aprovação por domínio
  → apply idempotente na curadoria ou histórico permitido
  → export pós-apply + relatório de diferenças
```

### 7.2 Contrato da landing

Cada artefato recebe:

- `source`, `logical_name`, `sha256`, bytes, MIME, encoding, timestamps disponíveis;
- local seguro/URI opaco; caminho pessoal e URL assinada não entram em log;
- período declarado e período medido;
- parser + versão/commit;
- classificação LGPD e prazo de retenção;
- relação de arquivos contêiner/filho (ZIP/XML/XLSX/abas);
- estado `discovered`, `profiled`, `rejected`, `approved` ou `applied`;
- responsável/aprovador e evidência do gate.

O RAW é append-only. Correção gera novo artefato/hash; não edita o original. Criptografia em trânsito e repouso, acesso mínimo e log de leitura são obrigatórios. O local definitivo da landing deve ser definido em O0 sem commitar arquivos de negócio.

### 7.3 Evolução do `ImportBatch`

O importador Yooga já possui `ImportBatch` com `source`, nome, SHA-256, estado, contagens, erro e operador, além de recusa de hash concluído repetido. O0 deve reutilizar esse padrão e torná-lo genérico, sem quebrar o histórico atual:

- acrescentar `artifact_ref`, `schema_version`, `parser_version`, `mode` (`dry_run`/`apply`), `started_at`, `finished_at`, `counts` e `report_ref`;
- separar contagens genéricas de contagens Yooga legadas;
- registrar lote falho fora da transação que é revertida;
- garantir unicidade por `(source, sha256, purpose, parser_version)` quando `done`;
- gravar `source_key` e `source_row` na proveniência normalizada;
- ligar cada alias/registro curado ao lote ou revisão que o sustentou;
- impedir que `--rebuild` destrutivo exista no Live sem procedimento explícito e snapshot.

Nenhuma PII entra em `error`, `notes`, métricas ou logs.

## 8. Grafo de identidade e reconciliação

O grafo torna explícito “isto no legado é aquilo no Shopman”; sem aresta aprovada, não existe join.

### 8.1 Nós e chaves

| Entidade | Chaves fortes | Chaves candidatas, nunca suficientes sozinhas |
|---|---|---|
| Produto vendável | SKU canônico; GTIN validado quando aplicável | nome, categoria, preço |
| Produto externo | `(source, external_sku, external_name)` | nome normalizado |
| Insumo | SKU interno; GTIN por embalagem | descrição de NF-e |
| Item de fornecedor | documento do fornecedor + código do item/GTIN | fuzzy match do nome |
| Fornecedor | CNPJ/CPF válido + `ref` | razão social/nome fantasia |
| Receita | `ref` + versão | título/aba da planilha |
| Identidade histórica pseudonimizada | external id da fonte; hash do contato quando necessário à análise | nome/endereço/últimos quatro dígitos |
| Venda histórica | `(source, external_id)` | chave fiscal associada, quando provada |
| Documento fiscal | chave de acesso de 44 dígitos | número/série isolados |
| Imagem | SHA-256 do conteúdo | nome do arquivo |

### 8.2 Arestas e estados

Usar os modelos de alias existentes onde cabem (`ProductAlias`, `CategoryAlias`, `PaymentMethodAlias`) e criar tabela genérica apenas para relações sem casa canônica. Estados mínimos:

- `suggested`: máquina propôs, nenhum efeito;
- `confirmed`: pessoa aprovou com ator/data;
- `rejected`: proposta recusada e não deve reaparecer com a mesma evidência;
- `superseded`: nova decisão substituiu a anterior sem apagar auditoria;
- `ambiguous`: mais de um alvo plausível, bloqueia apply.

Regras:

- fuzzy matching nunca preenche alvo; apenas ordena a fila;
- nome igual não une produto, fornecedor ou cliente;
- `ProductAlias` confirmado sobrevive a reseed e religa pelo SKU;
- item Yooga sem SKU só entra em agregação por produto canônico depois de alias confirmado; antes disso permanece identificável por origem/nome;
- uma chave fiscal nunca é reaproveitada;
- cliente histórico pode enriquecer somente a análise por identificador pseudonimizado; este WP não cria nem mescla `Customer` e não cria permissão de contato;
- uma futura vinculação a cliente operacional, se algum dia aprovada, será outro WP, com verificação de identidade, LGPD e o mecanismo auditável do Guestman — nunca bulk SQL.

## 9. Profiling obrigatório antes de qualquer importação

O0 gera um relatório por fonte e um consolidado com:

1. schema observado versus esperado;
2. duplicidade intra/interarquivo;
3. chaves ausentes, inválidas e colidentes;
4. datas fora do intervalo, timezone e lacunas por dia;
5. moedas por centavos/`Decimal`, totais negativos, zero e discrepância cabeçalho×itens;
6. cancelamentos, autorizações e status desconhecidos;
7. SKUs/GTINs/NCMs/CFOPs inválidos ou divergentes;
8. unidades físicas incompatíveis e conversões ausentes;
9. produtos sem coleção, preço, imagem, receita ou atributos de segurança;
10. receitas duplicadas/`OLD`, rendimento, unidade, fator de correção e consumidor inexistente;
11. fornecedores por documento e frescor dos custos;
12. PII presente, fundamento de uso, minimização e retenção;
13. cobertura e conflitos do grafo de identidade;
14. comparação `Catálogo Nelson — consolidado` × Live × cofre × canais × histórico, com uma linha de conflito por campo;
15. defaults perigosos e valores de desenvolvimento.

Saídas obrigatórias: CSV sanitizado de exceções, sumário Markdown, JSON para gate automatizado e zero amostras de PII nos artefatos versionados.

## 10. Caminho crítico Day-1 — nesta ordem

O programa prioriza aquilo que impede abrir e operar amanhã. Nenhum trabalho de migração histórica toma lease, atenção humana ou janela de deploy desta sequência:

1. **Loja e identidade:** razão/nome, documentos, endereço, timezone, contato, ambientes, unidades e parâmetros legais.
2. **Mix vendável:** carregar a candidata de `Catálogo Nelson — consolidado`; reconciliar SKU, produto ativo/inativo, coleções, listings, componentes e disponibilidade contra as demais fontes; conflitos aguardam decisão.
3. **Preço atual:** partir do consolidado e registrar preço-base/por canal com `as_of`, `source`, `approver`, validade, arredondamento, adicionais, promoções reais e bloqueio de zero; canais apenas reconciliam.
4. **Fiscal e segurança alimentar:** NCM/CEST/CFOP/CSOSN/CST/origem, unidade tributável, alergênicos, dietético, warnings e nutrição no escopo aprovado.
5. **Como fabricar:** receitas/BOM vigentes, sub-receitas, rendimento, fator de correção, perdas, validade e capacidade.
6. **Como comprar:** insumos reais, unidade-base, conversões, fornecedores, contatos operacionais mínimos e custo vigente.
7. **O que existe agora:** inventário físico por SKU/lote/validade, dupla conferência e lançamento de abertura.
8. **Como atender:** horários, calendário, canais, fulfillment, zonas, fretes, cutoffs, preorder, lead times e capacidade.
9. **Quem e com quê:** operadores, grupos, 2FA/PIN, terminais, KDS, impressoras, caixa e float.
10. **Como comunicar/integrar:** gateways, fiscal, notificações, templates, copy e checks de readiness.
11. **Prova e recuo:** export curado, PITR, dry-run, smokes, reconciliação e decisão GO/NO-GO.

O histórico segue em `H1/H2` em paralelo, com recursos separados. Se não terminar, a loja ainda pode abrir; o B.I. mostrará uma janela histórica parcial/indisponível de modo honesto.

## 11. Estratégia por fonte

### 11.1 Yooga — trilha histórica paralela

Reusar [`ingest_yooga`](../../shopman/backstage/management/commands/ingest_yooga.py) e o parser em [`backstage/bi/ingest/yooga.py`](../../shopman/backstage/bi/ingest/yooga.py), que já entregam `Decimal`, timezone, validação de fronteira, transação, lote/hash, idempotência e preenchimento sem sobrescrever. Alinhar a execução com o [BI Data Foundation Plan](BI-DATA-FOUNDATION-PLAN.md). A execução fica fora do caminho crítico: termina apenas em `HistoricalSale*`/B.I.

Antes do apply:

- congelar o export canônico e comparar hashes/versões;
- resolver a divergência de período;
- fechar total de vendas, itens e soma financeira por mês;
- reconciliar cabeçalhos×itens e identificar canceladas ausentes;
- validar as 143 linhas do mapa de SKU e abrir fila para os ~27.177 itens sem SKU;
- confirmar por teste e auditoria que o apply só toca `HistoricalSale*`, `ImportBatch` e aliases aprovados — contagens de `Order`, `Customer`, pagamentos e ledgers ficam invariantes;
- provar reexecução idempotente e que fonte nova apenas completa lacunas, sem sobrescrever evidência anterior;
- manter endereço/observação sob política LGPD; telefone somente pseudonimizado na camada analítica.

### 11.2 XML de fornecedor — NF-e de entrada

Não criar outro parser. Reusar `parse_nfe_xml_to_purchase_draft` de [`purchase_invoice_nfe.py`](../../shopman/shop/adapters/purchase_invoice_nfe.py) e as regras do [runbook de NF-e de compras](../runbooks/purchase-nfe-reader.md).

O bulk importer novo deve apenas:

1. enumerar XMLs da landing;
2. validar XML com parser seguro, chave, documento destinatário e duplicidade;
3. chamar o parser canônico por documento;
4. guardar fatos normalizados e sugestões, sem confirmar recebimento;
5. reconciliar fornecedor/código/GTIN/unidade;
6. produzir candidatos de `Supplier`, `Material`, conversão e `SupplierMaterialCost`;
7. exigir aceite para fuzzy match e conversão convencional;
8. impedir qualquer `Move`, saldo, contas a pagar ou manifestação SEFAZ no modo histórico.

O custo do XML é histórico na data de emissão. Só vira custo vigente se estiver dentro da janela de frescor aprovada e a embalagem/conversão estiver conferida.

### 11.3 XML de saída — NFC-e/NF-e, trilha histórica paralela

Reusar leitores/normalizadores fiscais existentes, incluindo [`danfe_xml.py`](../../shopman/shop/services/danfe_xml.py), e biblioteca fiscal testada quando o contrato atual não cobre o documento completo. Não duplicar parsing XML com XPath solto por comando.

Destino: landing + leitura histórica fiscal própria, chaveada pela chave de acesso e ligada opcionalmente à venda Yooga. O documento pode provar autorização/cancelamento e total fiscal; não cria `Order`, `Customer`, venda nativa, pagamento nem estoque. Divergência fiscal×Yooga vira reconciliação para o contador. A leitura histórica não bloqueia Day-1; somente a parametrização fiscal atual dos SKUs ativos bloqueia.

### 11.4 Cofre/Google Sheets

O cofre atual possui 27 entidades do Shop/Core e 6 do Backstage, total **33**, mais seis abas transacionais somente leitura. Preservar as garantias documentadas em [Backup e restore](../guides/backup-and-restore.md): chave natural, validação de schema, `full_clean`, dry-run, transação única, sem delete e `--force` no Live.

O7 deve:

- incluir entidades curadas hoje descobertas fora do cofre, após análise de dependência: `SupplierContact`, `RecipeEntry`/`RecipeVersion`, `AttributeDefinition` e configurações duráveis de KDS/terminais/impressão/caixa/dispositivos/checklists;
- continuar excluindo clientes, credenciais, integrações secretas e ledgers;
- criar teste que falha quando nova entidade de curadoria não está registrada nem explicitamente excluída;
- automatizar export periódico para destino aprovado, com hash, retenção, alerta de atraso e restore ensaiado;
- fazer a ponte Google falhar fechada e nunca versionar service account;
- preservar as seis abas transacionais como leitura, jamais importáveis.

### 11.5 Receitas XLSX/Drive

- catalogar 34 abas, marcando `OLD`, duplicatas, datas e referências cruzadas;
- não escolher a versão vigente automaticamente;
- converter cada candidata para `RecipeEntry`/`RecipeVersion` em rascunho, com proveniência de arquivo/aba/célula;
- preservar quantidade líquida, rendimento/fator de correção, quantidade bruta derivável, rendimento do lote, perda, validade, passos e unidade;
- bloquear ficha com `quanto baste`, unidade ambígua, rendimento inexistente, ingrediente sem identidade ou sub-receita não resolvida;
- só publicar depois de revisão do responsável de produção;
- custos de 2017–2023 servem para comparação, não custo atual nem preço.

### 11.6 Snapshots, SQLite, Bling e iFood

- SQLite: abrir cópia read-only, inventariar tabelas/schema e comparar apenas whitelist. Exportar candidato por chave natural; nunca importar PK, auth, session, migration, secret ou banco inteiro;
- snapshot de catálogo: comparar os 59 produtos, 9 coleções, 59 vínculos e 229 aliases contra o canônico; recuperar apenas valor ausente e comprovadamente curado;
- imagens: hash de conteúdo primeiro; ligar a SKU só após inspeção/aprovação e registrar licença/origem;
- Bling/iFood: capturar snapshot read-only com data e ids externos, se disponível; usar como fonte de comparação/alias, não como escritor nem precedência automática.

## 12. Matriz de gates por domínio

| Domínio | Gate automático | Gate humano | Condição de GO |
|---|---|---|---|
| Organização/loja | documento/formato, endereço, timezone, DDD e unidade sem fallback dev | dono confirma identidade e contatos | dados legais/operacionais vigentes em todas as superfícies |
| Produtos/SKUs | unicidade, SKU válido, alias sem ambiguidade, nenhum seed marcado como real; diff consolidado×demais fontes | sortimento e descontinuados do consolidado aprovados; cada conflito decidido | 100% dos publicados com identidade confirmada e nenhuma divergência silenciosa |
| Coleções/listings | vínculos íntegros, coleção ativa, ordem sem duplicata | taxonomia e exposição aprovadas | todo publicado pertence a navegação intencional |
| Preços | `>0`, moeda/centavos, canal e `as_of/source/approver`; diff consolidado×Live/cofre/canais/histórico | **todos os preços atuais e overrides aprovados** | zero preço sem proveniência/aprovador, zero publicado a R$0 e zero conflito auto-resolvido |
| Fiscal | formato NCM/CEST/GTIN, combinações permitidas, unidade tributável, origem | **contador assina a matriz** | 100% do vendável no strict gate fiscal ou exceção formal bloqueada |
| Alergênicos | derivação fecha pela receita/insumo; ausência não vira negativo | **responsável técnico aprova** | 100% do alimento publicado com declaração revisada |
| Informação dietética | consistência com ingredientes e contaminação cruzada | responsável técnico | nenhuma alegação positiva baseada em silêncio |
| Nutrição | base identificada, receita/rendimento vigentes, unidade/porção | **responsável aprova publicação** | 100% do escopo legal/comercial coberto ou explicitamente bloqueado |
| Imagens | hash, MIME/dimensão, URL HTTPS, sem duplicata indevida | **correspondência e licença aprovadas** | foto real para feed; placeholder só em superfície própria |
| Receitas | grafo acíclico, unidades, rendimento, fator, versão, consumidor | produção publica versão | toda ficha usada em custo/rótulo/estoque está vigente e assinada |
| Insumos | SKU/unidade-base únicos; GTIN/códigos não colidem | compras/produção aprovam identidade | 100% dos ingredientes de receitas vigentes resolvidos |
| Fornecedores | documento válido/único; contato minimizado | compras aprova ativo | fornecedor usado por custo/compra está identificado |
| Custos/conversões | data, fornecedor, embalagem, fator e unidade fecham; outlier alerta | compras aprova frescor e aproximações | custo vigente para itens críticos e nenhuma conversão silenciosa |
| Estoque inicial | planilha de contagem fecha por SKU/lote/unidade, dupla assinatura | **contagem física** | um único lançamento explícito de abertura por item; nenhuma derivação histórica |
| Clientes operacionais existentes | external id único; nenhuma criação/mescla pelo legado | privacidade trata conflitos atuais | PII mínima, origem/retenção e nenhum consentimento inventado |
| Histórico de vendas (não bloqueante) | hash/lote, período, totais, itens, duplicatas e cobertura de alias | financeiro aceita discrepâncias documentadas | import idempotente; incompletude fica explícita no B.I. |
| XML fiscal histórico (não bloqueante) | chave única, assinatura/schema quando disponível, status e total | contador resolve divergências | arquivo íntegro; não cria entidade operacional |
| Promoções/cupons | janela, stacking, orçamento e público válidos | comercial aprova | nenhuma promoção de seed/expirada ativa |
| Horários/zonas/frete | geometria/faixas sem buraco, timezone/cutoff | operação aprova | simulações de endereço/agenda passam |
| Canais/fulfillment | adapter/modo explícitos; bloquear defaults `immediate/cash/untracked/no commit check/preorder/lead0` | operação aprova por canal | zero default perigoso não revisado |
| Produção/capacidade | BOM vigente, posições/equipamentos, capacidade e calendário fecham | produção aprova o plano Day-1 | primeira jornada simulada sem falta estrutural |
| Operadores/permissões | contas nominais, menor privilégio, 2FA conforme política | dono aprova roster | `setup_operators`/PIN `1234` e credenciais dev ausentes |
| Terminais/KDS/impressão/caixa | ids únicos, hardware/config testados, sem token no cofre | operador valida em aparelho | terminal, fila, impressora e fundo de caixa conferidos |
| Copy/avisos | placeholders e links válidos; nenhuma promessa falsa | aprovador de voz/legal | textos críticos aprovados e versões registradas |
| Integrações/readiness | adapter/ambiente/credenciais declarados, health sem mutação e webhook contratual | dono aceita providers/canais ativos | cada integração Day-1 pronta ou explicitamente desligada |
| Backup curado | export, hash, retenção, alerta e dry-run restore | dono confirma acesso | export recente e restore ensaiado |

### Defaults conhecidos que bloqueiam GO se encontrados

- DDD padrão **11** em operação de Londrina/DDD **43**;
- produto publicado/vendável com preço zero;
- preço sem `as_of`, `source` e `approver`, ou canal usado como fonte de verdade por sincronização reversa;
- coleção/listing ativa por default sem decisão;
- `SupplierMaterialCost` antigo tratado como atual;
- canal em `immediate`, dinheiro, entrega não rastreada, sem commit check, preorder ou lead time zero por fallback;
- conta dev, PIN `1234`, OTP/debug, usuário compartilhado ou privilégio excessivo;
- imagem de banco/IA apresentada como foto real do produto;
- metadata fiscal opcional usada para escapar do strict gate.

## 13. Checklist “abrir amanhã”, ordem de carga e cutover

### Checklist operacional Day-1

- [ ] loja/organização, documento, endereço e timezone conferidos;
- [ ] mix ativo fechado; descontinuados não aparecem; SKU/GTIN não colidem;
- [ ] todos os preços atuais por canal carregam `as_of/source/approver`, estão aprovados e nenhum vendável custa zero;
- [ ] contador aprovou fiscal de todo item ativo;
- [ ] alergênicos/dietético/warnings estão completos e não fazem alegação por ausência;
- [ ] receitas usadas amanhã, rendimentos, perdas e validades estão publicadas;
- [ ] insumos dessas receitas, conversões, fornecedores e custos vigentes estão prontos;
- [ ] inventário físico inicial foi contado e reconferido; lotes/validades críticos foram registrados;
- [ ] plano/capacidade da produção de amanhã cabe em pessoas, equipamentos e insumos;
- [ ] horário, feriado, zona, frete, cutoff, preorder e lead time foram simulados;
- [ ] canais aceitos e seus meios de pagamento/fulfillment estão explícitos;
- [ ] operadores nominais, grupos, 2FA e PINs seguros estão ativos; contas dev estão fora;
- [ ] terminal, KDS, impressora, caixa e float passaram em aparelho real;
- [ ] integrações, templates e copy críticos passaram em readiness/smoke;
- [ ] cofre curado, backup/PITR e rollback estão acessíveis;
- [ ] placar final não possui P0/P1 `UNKNOWN` e o dono registrou GO.

### Ordem de carga operacional

1. organização/loja e referências sem dependência;
2. atributos, unidades, grades de qualidade e copy-base;
3. produtos, materiais, fornecedores e price tiers;
4. canais, listings e coleções;
5. conversões de material e custos vigentes;
6. receitas/sub-receitas e itens de receita;
7. preços por canal, componentes e publicação;
8. fiscal, segurança alimentar, nutrição e imagens aprovadas;
9. horários, regras, zonas, fretes, cutoffs e capacidade;
10. operadores/grupos, terminais, KDS, impressão e caixa;
11. integrações/templates, sem acionar efeitos externos;
12. inventário físico e lançamento de abertura, somente na janela autorizada;
13. smokes, reconciliação e abertura.

Os imports históricos `H1/H2` podem ocorrer antes ou depois, mas nunca são encaixados entre os passos 1–13 da janela de abertura.

### T-14 a T-7 dias

- fechar fontes físicas, hashes e profiling;
- aprovar identidade, sortimento, preço, fiscal e receitas prioritárias;
- executar a carga operacional primeiro em clone restaurado/staging; históricos rodam em trilha paralela;
- produzir o cofre pós-import e comparar com a candidata;
- treinar contagem e cadastrar unidades/lotes necessários.

### T-48 horas

- congelar alterações em planilhas/fontes ou abrir changelog explícito;
- exportar cofre atual e registrar hash;
- rodar dry-run completo contra snapshot recente do Live;
- fechar toda exceção P0/P1 e assinar matriz de gates;
- preparar folha/app de contagem física por área, sem saldo esperado visível quando isso induzir viés.

### T-0 — janela autorizada

1. pausar escrita operacional pelo procedimento de cutover;
2. capturar backup/PITR e export curado;
3. aplicar somente lotes aprovados, em ordem do DAG;
4. contar estoque físico com dupla conferência;
5. criar saldo inicial por comando/serviço dedicado, com lote de abertura e assinaturas — **não por SQL nem pelo histórico**;
6. configurar fundo de caixa, terminais, KDS e impressoras por gesto operacional;
7. executar smokes sem venda financeira real até o gate específico;
8. comparar placares e decidir GO/NO-GO.

### Pós-corte

- reconciliação em 15 min, 2 h, fechamento do dia, D+1 e D+7;
- alertar alias desconhecido, preço zero, fiscal incompleto, estoque negativo/anômalo, custo stale e queda de cobertura;
- congelar artefatos/relatórios da execução;
- remover acessos temporários e aplicar retenção à landing.

## 14. Testes, observabilidade e rollback

### Testes mínimos

- unitários por conversor, normalizador e regra de precedência;
- fixtures sintéticas, sem dados reais/PII;
- property tests para dinheiro, quantidade, timezone, chave fiscal e idempotência;
- golden files sanitizados para cada schema/versionamento;
- reexecução do mesmo hash = recusa declarada, não duplicação;
- arquivo novo = apenas cria/completa conforme precedência, nunca apaga;
- erro na última linha = zero apply parcial;
- concorrência: um lote aplica, o outro observa/rejeita;
- equivalência de totais por dia/mês/SKU e relatório das diferenças;
- teste explícito que histórico não cria objetos dos ledgers proibidos;
- export→import dry-run→export preserva curadoria;
- restore do cofre em banco vazio de ensaio;
- autorização e auditoria de toda ação de apply/aprovação.

### Observabilidade

Métricas sem PII:

- lotes por fonte/estado/duração;
- linhas lidas, aceitas, rejeitadas, ambíguas e completadas;
- cobertura de alias por volume e por SKU;
- cobertura de preço/fiscal/alergênico/nutrição/imagem/receita/custo;
- discrepância financeira mensal e cabeçalho×itens;
- idade do custo e do backup curado;
- quantidade de `UNKNOWN`, por severidade/responsável;
- importações fora de janela e tentativas de hash repetido.

Alertas: lote falho, schema novo, queda de cobertura, backup atrasado, preço zero publicado, default perigoso, conflito de identidade, divergência fiscal relevante e PII em log.

### Rollback

- antes de apply: PITR/backup verificado + export do cofre e relatório/hash;
- curadoria: gerar patch inverso a partir do export anterior; não usar delete implícito;
- histórico: desativar/ignorar o lote por mecanismo auditável ou restaurar em ambiente controlado; não `DELETE` manual silencioso;
- saldo inicial/ledger: correção compensatória assinada, nunca editar/apagar lançamento;
- publicação: feature flag/listing rollback sem apagar cadastro;
- migração/schema: expand/contract e `migration_safety` conforme política vigente.

## 15. DAG de dependências

```text
O0 Contratos, segurança, fontes e leases
 ├─→ O1 Loja + mix + identidade de SKU
 │    ├─→ O2 Preço atual + fiscal + segurança alimentar
 │    └─→ O3 Receitas + insumos + fornecedor + custo vigente
 │             └─→ O4 Produção + capacidade + calendário
 ├─→ O5 Canais + fulfillment + zonas + frete + cutoffs
 ├─→ O6 Pessoas + terminais + KDS + impressão + caixa
 └─→ O7 Cofre curado + backup + readiness

O2 + O3 + O4 + O5 + O6 + O7
 └─→ O8 Ensaio integral em clone/staging
      └─→ O9 Contagem física + carga + cutover autorizado
           └─→ O10 Reconciliação e handoff

TRILHA PARALELA, NÃO BLOQUEANTE:
O0 ─→ H1 Yooga → HistoricalSale*/BI
   └→ H2 XML de venda → arquivo/reconciliação fiscal histórica
```

O acesso read-only ao Live melhora O0–O8, mas sua ausência não autoriza extrapolar da amostra pública. O apply no Live só existe em O9, após gates e autorização contemporânea. H1/H2 não são predecessores de O9; só um conflito de SKU ativo ou fiscal atual sobe uma exceção pontual para O1/O2.

## 16. Ownership e leases

Um coordenador único mantém o placar e os leases. Nenhuma frente toca os mesmos modelos/arquivos simultaneamente.

| Lease | Dono funcional | Arquivos/domínios exclusivos durante a janela |
|---|---|---|
| `catalog-identity` | catálogo | Product/Alias/Collection/Listing e consolidado |
| `recipe-material` | produção/compras | Recipe/Material/conversões/rendimentos |
| `pricing-fiscal-safety` | dono + contador | preço, impostos, alergênicos/nutrição e publicação |
| `operations-configuration` | operação | loja, calendário, fulfillment, zonas, capacidade e canais |
| `people-hardware` | dono + operação | usuários/grupos/2FA, terminais, KDS, impressão, caixa e float |
| `curated-vault` | plataforma | registry/resources/Drive/scheduler/restore |
| `cutover-stock` | operação | contagem e abertura de estoque; ninguém mais escreve Stockman |
| `data-foundation` | engenharia de dados | `ImportBatch`, landing, provenance, comandos base |
| `yooga-history` | BI/dados | parser/import Yooga, `HistoricalSale*` e aliases Yooga; sem acesso de escrita aos modelos operacionais |
| `fiscal-xml-history` | fiscal + engenharia | landing/read model XML de venda; parsers compartilhados só com lease explícito |

Cada lease tem branch/worktree, base SHA, arquivos permitidos, predecessor, saída esperada e gate de liberação. PR docs/code separados de lotes de dados. Um lote nunca é transportado dentro de commit Git.

## 17. Work packages executáveis

### O0 — Descoberta e contrato seguro

**Entregas:** inventário físico sanitizado; profiling do estado atual; ADR curta; manifest; landing; RBAC; retenção; política de PII; CLI comum `profile`, `dry-run`, `apply`, `report`; separação em trilha operacional e histórica.

**Gate:** fontes operacionais localizadas ou `UNKNOWN` com responsável; fixtures sintéticas provam hash, idempotência, transação, logs sem PII, sem delete e proibição de modelos operacionais para H1/H2.

### O1 — Loja, mix ativo e identidade

**Entregas:** organização/loja; candidata de mix nascida de `Catálogo Nelson — consolidado`; diff contra Shopman Live, cofre, canais e histórico; SKUs/GTINs; aliases; coleções/listings/componentes; ativos/descontinuados; fila explícita de conflitos e de imagens.

**Gate:** 183 linhas consolidadas decompostas em chaves únicas/sobreposições; 100% do mix Day-1 com SKU e estado aprovados; toda divergência externa decidida por pessoa; nenhuma identidade ambígua ou sobrescrita silenciosa publicada.

### O2 — Preço, fiscal e segurança do produto

**Entregas:** preços atuais iniciados pelo consolidado e registrados com `as_of/source/approver`; fila de divergências/overrides por canal; regras de adicionais/promoções reais; matriz fiscal; alergênicos, dietético, warnings, nutrição e imagens aprovadas.

**Gate:** todo item vendável tem preço positivo e proveniência completa; canal nenhum retroalimenta o canônico; conflitos/overrides foram aprovados; strict gate fiscal e contador verdes; segurança alimentar completa; imagem real/licenciada quando publicada em feed.

### O3 — Receitas, insumos, fornecedores e custo vigente

**Entregas:** 34 abas catalogadas; versões vigentes em `RecipeVersion`; BOM/rendimento/fator/perda/validade; materiais/unidades/conversões; fornecedores e custo atual datado.

**Gate:** receitas necessárias ao Day-1 assinadas; nenhum ingrediente órfão; custo/conversão fecham; custo antigo não se apresenta como vigente.

### O4 — Produção, capacidade e calendário

**Entregas:** posições/equipamentos, capacidade, lotes, shelf life, plano inicial, horários, feriados e calendário operacional.

**Gate:** produção do primeiro dia simulada ponta a ponta e cabe nos recursos/estoque; nenhuma versão `OLD` foi escolhida por máquina.

### O5 — Canais, fulfillment e entrega

**Entregas:** canais ativos, meios de pagamento permitidos, pickup/delivery, zonas, fretes, cutoffs, preorder, lead times e capacidade.

**Gate:** casos dentro/fora de zona, aberto/fechado, hoje/futuro e indisponibilidade simulados; nenhum default perigoso.

### O6 — Pessoas, hardware e caixa

**Entregas:** roster; grupos; 2FA/PIN; estações; terminais; KDS; impressoras; dispositivos; caixa/float; checklists de abertura/fechamento.

**Gate:** contas nominais e menor privilégio; PIN dev ausente; cada aparelho real passa smoke e tem responsável.

### O7 — Cofre curado e readiness

**Entregas:** cobertura declarada das entidades faltantes, export agendado, hashes, retenção, alerta, Drive seguro e restore ensaiado.

**Gate:** backup fresco restaurado em banco vazio de ensaio e diff semântico aprovado; transacionais continuam read-only; integrações/templates/copy passam readiness sem efeito externo.

### O8 — Ensaio operacional integral

**Entregas:** clone restaurado, carga operacional na ordem da seção 13, relatório de tempo/erros/rollback e checklist “abrir amanhã”.

**Gate:** duas execuções determinísticas; segunda não duplica; rollback ensaiado; smokes de todas as superfícies relevantes.

### O9 — Inventário físico e cutover

**Entregas:** contagem física assinada, saldo inicial explícito, configurações de operação, execução aprovada e placar GO/NO-GO.

**Gate:** autorização específica no momento; backup/PITR; todos os aprovadores presentes; nenhum lote fora do manifest.

### O10 — Reconciliação e handoff

**Entregas:** reconciliações de T+15 min, T+2 h, fechamento, D+1 e D+7; exceções aceitas; runbooks; ownership recorrente e fechamento do acesso temporário.

**Gate:** operação e contabilidade aceitam números; alertas/backup estão ativos; toda pendência residual tem responsável/data.

### H1 — Yooga em `HistoricalSale*`/B.I. (paralelo, não bloqueante)

**Entregas:** recontagem do período/volumes; importador existente endurecido; aliases/de-paras; reconciliação mensal; cobertura dos ~27.177 itens sem SKU.

**Gate:** vendas históricas representadas uma vez; rerun idempotente; contagens de `Order`, `Customer`, pagamentos, caixa e estoque invariantes.

### H2 — XML de venda histórico (paralelo, não bloqueante)

**Entregas:** bulk sobre parser canônico; arquivo fiscal histórico; conciliação XML×Yooga; relatório ao contador.

**Gate:** chave única, XML malicioso rejeitado, zero efeito SEFAZ e zero criação de objeto operacional. Só conflitos de identidade/fiscal do mix ativo voltam para O1/O2.

## 18. Critérios de aceite e Definition of Done

### Gate Day-1 — bloqueia abrir

- [ ] 100% dos produtos publicados vêm do mix consolidado ou de exceção humana registrada, com SKU, preço positivo aprovado e coleção intencional;
- [ ] divergências entre consolidado, Live, cofre, canais e histórico estão decididas ou bloqueadas; nenhuma fonte reconciliadora sobrescreveu o canônico;
- [ ] 100% dos produtos alimentícios publicados passaram por fiscal, alergênicos e gate dietético; nutrição cumpre o escopo aprovado;
- [ ] toda imagem publicada como produto é real, correspondente e licenciada;
- [ ] toda receita usada para custo/rótulo/estoque é versão vigente, assinada e fecha unidade/rendimento;
- [ ] custos vigentes têm fornecedor, embalagem, conversão, data e regra de frescor;
- [ ] saldo inicial veio exclusivamente de contagem física assinada;
- [ ] defaults perigosos e contas/PINs de desenvolvimento foram eliminados;
- [ ] o cofre cobre toda curadoria declarada, exporta automaticamente, alerta atraso e foi restaurado em ensaio;
- [ ] dados LGPD têm finalidade, minimização, retenção e acesso definidos;
- [ ] dry-run e apply foram ensaiados duas vezes em clone/staging com resultado determinístico;
- [ ] rollback foi ensaiado e os relatórios não expõem PII/segredos;
- [ ] contador, produção, compras, catálogo e operação assinaram seus gates;
- [ ] evidência final contém hashes, contagens, diferenças, aprovadores, timestamps, commit/imagem e placar GO/NO-GO;
- [ ] nenhum arquivo real de negócio foi commitado no repositório.

### DoD da trilha histórica — não bloqueia abrir

- [ ] fontes Yooga/XML de venda localizadas estão inventariadas por hash; fonte ausente permanece `UNKNOWN` com responsável;
- [ ] conflitos de contagem/período foram remedidos e explicados;
- [ ] importadores são idempotentes, dry-run por padrão, transacionais e sem delete;
- [ ] cada registro histórico é rastreável a artefato, lote, parser e chave externa;
- [ ] o grafo de identidade histórica não tem aresta ambígua aplicada;
- [ ] nenhuma importação histórica criou `Order`, `Customer`, ledger, estoque, pagamento ou consentimento;
- [ ] Yooga termina somente em `HistoricalSale*`/B.I.; XML de venda, somente em arquivo/reconciliação;
- [ ] divergências restantes aparecem no B.I. como cobertura parcial/`UNKNOWN`, não como zero.

H1/H2 incompletos não mudam um `GO` operacional para `NO-GO`, exceto quando revelam conflito ainda não resolvido na identidade ou no fiscal de um SKU que será vendido no Day-1.

## 19. Pacote mínimo de perguntas humanas

Perguntar em um único pacote, depois de O0–O4 preencherem tudo o que os dados respondem:

1. **Sortimento e preço:** revisar somente a fila de divergências entre `Catálogo Nelson — consolidado` e Live/cofre/canais/histórico; aprovar exceções/overrides por canal e a tabela final inteira.
2. **Receitas:** entre as 34 abas e versões `OLD`, quais são vigentes? Quem confirma rendimentos, fatores, validade e os casos incompletos?
3. **Fiscal:** quem é o contador aprovador e qual matriz fiscal final deve valer por SKU/canal?
4. **Compras:** qual janela define custo “atual”? Quais fornecedores/embalagens/conversões ainda valem?
5. **Estoque:** quem lidera e quem reconfere o inventário, em qual data/janela?
6. **Operação:** confirmar horários, feriados, zonas, fretes, cutoffs, capacidade, preorder e lead times.
7. **Pessoas e hardware:** roster, papéis, 2FA/PIN e responsáveis por terminais, KDS, impressoras e fundo de caixa.
8. **Privacidade atual:** quais contatos/consentimentos têm recibo válido e qual retenção operacional se aplica?
9. **Publicação:** quem aprova copy e fotos do mix Day-1?

Se uma resposta não vier, o domínio correspondente continua `UNKNOWN`/`NO-GO`; o sistema não escolhe pelo usuário.

Localização/período de XMLs e do export Yooga não entram neste pacote decisório: O0/H1/H2 procuram primeiro nas fontes já declaradas e só pedem um caminho específico se a descoberta se esgotar. A ausência continua registrada, mas não impede abrir.

## 20. Referências versionadas

- [Fundação de dados do BI](BI-DATA-FOUNDATION-PLAN.md)
- [Mapa real de SKU](sku-real-mapa.csv)
- [Backup e restore do cofre](../guides/backup-and-restore.md)
- [Backup/PITR do PostgreSQL](../runbooks/backup-e-restore.md)
- [Leitor NF-e de compras](../runbooks/purchase-nfe-reader.md)
- [Receitas da casa](WP-RECEITAS-DA-CASA.md)
- [Fichas reais e fator de correção](WP-FICHAS-REAIS-DA-CASA.md)
- [Insumos da vida real](WP-INSUMOS-DA-VIDA-REAL.md)
- [Fotos da casa](WP-FOTOS-DA-CASA.md)

---

**Decisão de execução:** este documento autoriza construir e ensaiar a esteira em ambientes isolados. Não autoriza importar no Live, publicar canais, criar estoque inicial, emitir/cancelar fiscal ou executar o cutover. Essas ações exigem os gates e a autorização contemporânea descritos em O9.
