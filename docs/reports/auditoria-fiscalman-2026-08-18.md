# Auditoria profunda — Fiscalman

> Série "um app por vez", nº 3 · 2026-08-18 · Base: leitura integral do código (main, pós #215)
> Escopo lido: o pacote inteiro (classification, contracts, contrib/offerman, testes), mais toda a cadeia de emissão que vive fora dele — `shop/services/fiscal.py` (builder do payload + emission resolver), `shop/fiscal.py` (pool), `shop/handlers/fiscal.py` (emit/cancel com retry), `shop/adapters/fiscal_focusnfe.py` (659 loc, lido por inteiro nas partes críticas), `fiscal_resolvers.py`, comando `fiscal_emit`, e os 50 testes de framework (`test_fiscal_*`).

---

## Veredito em uma frase

O Fiscalman é dois códigos com maturidades opostas usando o mesmo nome: um pacote-esquema pequeno e correto, e uma cadeia de emissão no orquestrador que é **melhor do que a documentação admite** (cicatrizes reais de homologação SEFAZ-PR no código) — cortada por uma composição de falha que transforma soluço de banco em nota morta, uma contradição interna de CFOP esperando a mesa do contador, e o gate de completude que continua não existindo na hora certa.

---

## Parte I — O que está certo (e o que eu subestimei no relatório geral)

**1. O pacote faz pouco de propósito, e o pouco é limpo.** Dois perfis nomeados capturando o eixo real (ST vs não-ST), dataclasses congeladas, NCM/CEST como texto com regex (zeros à esquerda preservados — o erro clássico evitado), `errors()` como lista dirigindo o `clean()` do form, tolerância a chaves legadas na leitura (`codigo_ncm`), CEST proibido onde não se aplica (não só exigido onde se aplica). O form do admin injeta o fieldset fiscal no `ProductAdmin` do Offerman sem tocar no Offerman — a fronteira "Offerman guarda o blob, Fiscalman é dono do schema" está respeitada dos dois lados.

**2. O adapter Focus NFe é o código mais calejado da fronteira — e eu o subestimei.** Não é integração de manual; é integração de quem já apanhou da SEFAZ-PR e anotou:
- **Frete só entra como entrega a domicílio** (indPres=4 + destinatário identificado + grupo transportador), com as rejeições específicas citadas (753/787/786); sem CPF/endereço, a taxa fica **fora do documento** com o pagamento reduzido na mesma medida — "nunca emitir um XML incoerente" como regra escrita.
- **Desconto rateado por item** com resíduo de arredondamento no último (porque a SEFAZ valida vDesc do total contra o somatório — "confirmado em homologação").
- **vUnCom derivado com 10 casas** quando desconto rateado quebra `vUnCom × qCom = vProd` — evitando a rejeição em vez de rezar contra ela.
- **Venda mista tratada:** `_payment_forms` lê a lista de `tenders` e emite múltiplas `formas_pagamento` — o documento fiscal diz a verdade sobre o mix. (Minha hipótese do relatório geral, de pagamento único, estava errada.)

Dois corolários que corrigem o relatório geral: a camada de risco **tem** 50 testes de framework (não zero), e os comentários "confirmado em homologação" indicam que a homologação SEFAZ-PR já foi exercitada ao menos manualmente — o gap real é o e2e automatizado e a produção, não ausência total de contato.

**3. O handler de emissão entende at-least-once de verdade.** Retry **nunca re-POSTa cego**: consulta `query_status` antes (um timeout pós-emissão deixa a nota autorizada com o mesmo ref; re-POST daria 422 eterno e nota órfã); 422 de referência é tratado como "a nota existe — adotar"; transiente vs terminal separados por código com prefixos. A sutileza do `attempts > 1` (o dispatcher incrementa antes da 1ª execução) está documentada no lugar onde alguém quebraria.

**4. O resolver de emissão é política como configuração, com combinadores.** `SHOPMAN_FISCAL_EMISSION_RESOLVER` aceita callables compostos (`any_of`/`all_of`/`not_`), exemplos prontos incluem `always` e `on_request_or_tax_id`, resolver quebrado cai no fallback com log em vez de travar o pedido. A regra de negócio fiscal tem um lugar, e esse lugar não é um `if` no checkout.

---

## Parte II — Falhas e brechas (por severidade)

### F1 · ALTA — A guarda de completude existe na camada errada, e as outras portas do catálogo não têm porteiro

Confirmei no código o que o relatório geral hipotetizou, com uma correção: a guarda do NCM **existe** (`_map_item` recusa item sem NCM com `FocusNFePayloadError` nominal), mas mora **na emissão** — assíncrona, horas depois da venda, num directive que vira erro terminal na fila. O comentário do form admite a escolha: *"a product may be saved without classification yet (pre-go-live); the emission/adapter guards missing NCM at issue time"*. Três problemas compostos:

1. **A validação do form é opt-in de fato:** só roda "once any fiscal data is present" — produto salvo sem nada fiscal passa limpo, sempre, inclusive pós-go-live. Não há flag que endureça isso na virada.
2. **As outras portas não passam pelo form:** sync de catálogo iFood, seed, scripts, futuros agentes criam Product por ORM — zero validação fiscal. O porteiro só existe na porta que o operador usa.
3. **Não há auditoria de catálogo:** nenhum comando/check responde "quais vendáveis publicados estão fiscalmente incompletos?" — a pergunta que precisa de resposta *antes* do primeiro dia de emissão obrigatória, não a cada nota recusada.

**Ação:** extrair a pergunta para o dono do schema — um `fiscalman.validate_for_emission(product) -> errors` usado por (a) um gate de publicação em canal com emissão ("vendável publicado no PDV ⇒ fiscal completo", ligável por setting na virada), (b) um comando de auditoria do catálogo, e (c) o próprio builder. A guarda tardia do adapter continua como última linha; deixa de ser a única.

### F2 · ALTA — Fail-open + fail-closed + terminal: um soluço de banco vira nota morta na fila

Composição de três decisões individualmente razoáveis:

1. `_products_by_sku` (builder) captura **`except Exception`** e devolve `{}` — qualquer indisponibilidade momentânea do banco/Offerman faz **todos** os itens perderem seus metadados fiscais (fail-open);
2. o adapter, correto, recusa item sem NCM → `focus_nfe_invalid_payload` (fail-closed);
3. o handler classifica esse código como **`DirectiveTerminalError`** — sem retry, visível na fila, exigindo intervenção manual.

Resultado: um blip transiente de infraestrutura no momento de montar o payload é convertido em falha *permanente* de payload. A nota não sai, ninguém re-tenta, e o diagnóstico ("produto sem NCM") **mente sobre a causa** ("o SELECT falhou"). Correção em duas partes: o builder deve **deixar a exceção subir** (a fila já sabe re-tentar transientes — engolir ali rouba do dispatcher a chance de fazer seu trabalho); e/ou distinguir "NCM ausente no produto" (terminal, verdade) de "metadados indisponíveis" (transiente). O `except Exception → {}` com `logger.debug` é a única linha genuinamente descuidada que encontrei nesta cadeia.

### F3 · MÉDIA-ALTA — 5101 ou 5102? O código responde os dois

Para fabricação própria: o dataclass — a fonte executável — emite **CFOP 5102**; o help_text do admin ensina ao operador *"Fabricação própria (**5101**/102)"*; o comentário de exemplo no próprio `FiscalProfile` diz *"e.g. \"5101\""*; e o fallback do adapter (`default_cfop_nfce`) volta a 5102. Na tabela CFOP, 5101 é venda de produção do estabelecimento e 5102 é revenda de terceiros — o perfil `own_production` cobre **os dois casos de propósito** ("fabricação própria + revenda comum", diz o header), então 5102 para tudo pode ser exatamente a simplificação parametrizada pelo contador… ou não. Eu não sei qual é o certo — **e é esse o problema**: a validação do contador (pendente, P2 do roadmap) vai tropeçar numa contradição interna antes de chegar à pergunta de mérito. Alinhar as três vozes à decisão dele, e gravar a decisão no docstring do perfil com a referência da parametrização.

### F4 · MÉDIA — O dono do contrato está atrás do próprio contrato

`FiscalBackend.emit()` no `contracts.py` — a razão de existir do pacote como "dono do contrato fiscal" — **não tem o parâmetro `delivery`**. O handler passa `delivery=payload.get("delivery")`; o FocusNFeBackend o aceita. Funciona porque `runtime_checkable` não confere assinaturas — ou seja, o Protocol não protege nada: um segundo backend implementado fielmente *pelo contrato* quebraria em produção com `TypeError` na primeira entrega a domicílio. Uma linha no Protocol resolve; o achado que fica é o padrão — a mesma doença dos comentários-fantasma do Cashman e do chargeback do Payman: **a suite tem o hábito de deixar a declaração descolar da implementação em lugares de baixa circulação.**

### F5 · MÉDIA — O default da emissão é opt-in por pedido, e a virada legal não tem trava

Sem resolver configurado, a NFC-e só sai se o operador marcar `issue_document` no pedido — correto para o pré-go-live. Mas venda presencial com emissão obrigatória é o destino declarado, o resolver `always` já existe pronto, e **nada acusa a configuração ausente na virada**: o sistema com adapter fiscal ligado e resolver vazio simplesmente… não emite, em silêncio, venda após venda. Isso merece um deploy check (a casa já tem a infraestrutura — `test_deploy_checks` cobre credenciais da Efí): *adapter fiscal configurado + canal PDV ativo ⇒ resolver de emissão explícito*, falha de deploy caso contrário. Silêncio fiscal é o pior modo de falha possível deste domínio.

### F6 · BAIXA — O adapter tem uma segunda opinião fiscal escondida

`_map_item` carrega defaults próprios para quando o bloco fiscal vier incompleto: CSOSN `"102"`, PIS/COFINS **`"07"`** — divergindo do `"99"` que a parametrização do contador manda (e que o perfil emite). Na prática quase nunca disparam (o `resolve_fiscal_item` sempre preenche), mas são uma política fiscal paralela dormindo no adapter, e **errada** onde diverge. Mesma doutrina aplicada ao NCM deveria valer para o resto: campo tributário ausente **falha**, não adivinha.

### F7 · BAIXA — Desconto fantasma se o pagamento estiver defasado

O builder faz `payment.setdefault("amount_q", order.total_q)` e o adapter deriva `valor_desconto = produtos + frete − pagamento`. Se `payment.amount_q` gravado no pedido ficar menor que o total real (edição pós-pagamento que escape do `_reconcile_order_payment_to_total` do PDV), o documento sai com um desconto que não houve. O reconcile do POS mitiga o caminho principal; canais futuros (ManyChat, iFood direto) precisam herdar a mesma disciplina. Registrar como invariante de canal: *quem escreve `payment` escreve o valor final*.

### F8 · Ponto de verificação — escrita concorrente em `order.data`

`NFCeEmitHandler._record` lê-modifica-grava `order.data` inteiro (`save(update_fields=["data"])`) **sem lock**, num handler assíncrono, enquanto outros escritores (pagamento, POS) também gravam o mesmo JSON. Se o dispatcher de directives não segurar lock do pedido durante o handle, dois escritores concorrentes fazem last-write-wins e um deles **perde chaves** — por exemplo, as chaves `nfce_*` sumindo sob uma gravação de payment, deixando nota autorizada na SEFAZ sem registro local (o dedupe por `nfce_access_key` deixaria de ver a nota e o retry adotaria via consulta — há rede, mas por acidente). Verificar o locking do dispatcher; se ausente, `select_for_update` no `_record`.

---

## Parte III — Desconstruir ou não?

**Não — mas mover uma parede.** A divisão atual (pacote = schema; orquestrador = emissão) segue a convenção da casa e deve ficar. O que está no lugar errado é a **pergunta de completude**: hoje só o adapter sabe recusar um produto fiscalmente incompleto, e ele responde tarde demais. O F1 move essa pergunta para o Fiscalman e a faz nos três momentos certos (publicar, auditar, emitir).

Plano de ação natural, em três PRs pequenas e uma conversa:

1. **PR "porteiro":** `validate_for_emission` no pacote + gate de publicação por canal (atrás de setting para a virada) + comando de auditoria do catálogo (F1) + deploy check do resolver (F5).
2. **PR "cadeia honesta":** deixar a exceção do builder subir / distinguir transiente de terminal (F2) + `delivery` no Protocol (F4) + remover os defaults tributários do adapter em favor de falha nominal (F6) + verificação/lock do F8.
3. **Conversa com o contador, depois PR "uma voz":** resolver 5101×5102 e alinhar dataclass, help_text e comentários à decisão dele, com referência (F3). Essa conversa já está no caminho crítico do go-live (validação NCM/CEST) — a contradição só precisa chegar lá resolvida do nosso lado.

O risco dominante do Fiscalman continua sendo o que não é código: contador → homolog e2e → credencial de produção → DANFE no PDV, em série. Mas depois desta leitura, meu ajuste ao relatório geral é: o código está **mais pronto** para essa fila do que o roadmap sugere — as cicatrizes de homologação já estão nele.

Falta um da série: **Buyman** — o menor, e o único com uma questão filosófica aberta (custo mutável in-place vs. suite ledger-first) que vale decidir antes de o BI construir em cima.
