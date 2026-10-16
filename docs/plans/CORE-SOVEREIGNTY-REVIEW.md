# CORE-SOVEREIGNTY-REVIEW — revisão adversarial bloqueante

> **Fase:** 0, sem edição de código de produção.
> **Plano revisado:** PR #1841, `plan/core-sovereignty @ ac3c75b6f`.
> **Base revalidada:** `origin/main @ f4b4943e8`, em 2026-10-16.
> **Base declarada pelo plano:** `main @ 35d95104d`, hoje 1.037 commits atrás.
> **Veredito global:** **DERRUBA na forma atual; reparável sem abandonar a missão.**

O diagnóstico central continua correto: há decisões de domínio duplicadas, política
cross-domain sem unidade explícita e governança documental incapaz de impedir reincidência.
O plano, porém, não pode entrar na Fase 1 como está. A baseline mudou materialmente, os
números 035 e 036 já têm donos aceitos, o mapa omite o command-side, e três contratos
propostos mudam comportamento sem uma transição falseável.

## 1. Sumário executivo dos dez ataques obrigatórios

| # | Ataque | Veredito | Consequência necessária |
|---|---|---|---|
| 1 | A Lei generaliza? | **REPARA** | Restringir a lei ao código de domínio e preservar bridges opt-in de ADR-001. |
| 2 | Steelman do `priceman` | **ACEITA** | Não criar pacote agora; registrar gatilho por consumidores, não por quantidade de condições. |
| 3 | Orquestrador vira god-module? | **REPARA** | Trocar teto por tamanho por métricas de acoplamento, mudança e dependência. |
| 4 | Teste de soberania é tautológico? | **REPARA** | Provar instalação isolada, ausência de host e unicidade da decisão; o teste atual só prova imports. |
| 5 | V1/V3/V4 preservam comportamento? | **DERRUBA** | Exigir caracterização, shadow comparison e rollback por contrato antes do corte. |
| 6 | Instância vira pacote pela porta dos fundos? | **REPARA** | Fixar schema, precedência, ownership e proibir decisão em descriptor/seed. |
| 7 | Go-live no meio | **ACEITA** | Revalidar a tag em cada WP; se aparecer, trocar imediatamente para expand-contract. |
| 8 | Aceite decorativo | **REPARA** | Substituir o aceite subjetivo do WP-8 por inventário e checks enumeráveis. |
| 9 | Taxonomia do WP-7 é exclusiva? | **REPARA** | Usar dois eixos; os seis baldes atuais se sobrepõem. |
| 10 | Manifesto é verificável? | **DERRUBA** | Definir schema e gate antes de escrever o primeiro manifesto ou iniciar o piloto. |

## 2. Ataques obrigatórios

### 2.1 A Lei generaliza? — REPARA

O núcleo da lei generaliza: decisão canônica de um domínio deve ter um dono; política
que só existe no encontro de domínios pertence ao orquestrador. A formulação absoluta
“kernel não importa kernel”, porém, contradiz uma exceção arquitetural já aceita.

- A ADR-001 permite imports lazy cross-kernel em `adapters/` e `contrib/<outro_core>/`,
  e limita a proibição absoluta a `models/`, `services/`, `protocols/`, `api/` e
  `admin.py`: `docs/decisions/adr-001-protocol-adapter.md:31-67`.
- Há um contraexemplo vivo e legítimo: `packages/doorman/shopman/doorman/adapters/customers.py:27-129`
  adapta Guestman para o contrato do Doorman. Apagar essa possibilidade faria a lei nova
  superar ADR-001 sem dizer que a está superando.
- Há também uma violação real fora da exceção: `_link_verified_identifier` importa models,
  services e contrib de Guestman dentro de um service do Doorman e engole qualquer falha:
  `packages/doorman/shopman/doorman/services/verification.py:_link_verified_identifier:550-595`.

**Reparo:** escrever “código de domínio de kernel não importa outro kernel; bridges opt-in,
lazy e nomeadas seguem ADR-001”. O critério de um verbo também precisa significar “um ponto
canônico por **decisão**”, não “um único verbo para todo o domínio”; Cashman e Stockman têm
várias mutações legítimas sobre a mesma pergunta canônica.

### 2.2 Steelman do `priceman` — ACEITA

Um pacote de pricing seria justificável se tivesse pergunta e linguagem próprias, motor
sem vocabulário de Offer/Customer/Order e **dois consumidores reais independentes**. O
número de condition types não é gatilho arquitetural: dez condições usadas só pelo Shopman
continuam sendo uma política interna do orquestrador.

Hoje já existe o seam correto, sem necessidade de pacote:

- `PricingBackend` é um porto opcional do Offerman:
  `packages/offerman/shopman/offerman/protocols/catalog.py:PricingBackend:121-135`.
- `CatalogService.get_price` mantém preço de lista explícito e injeta preço contextual:
  `packages/offerman/shopman/offerman/service.py:CatalogService.get_price:124-170`.
- A implementação real conhece `Promotion`, segmentos e fulfillment do orquestrador:
  `shopman/shop/adapters/pricing.py:PromotionPricingBackend.get_price:21-131`.
- A segunda implementação é `NoopPricingBackend`, útil como ausência de política, mas não
  um segundo consumidor do suposto domínio:
  `packages/offerman/shopman/offerman/adapters/noop.py:NoopPricingBackend:26-49`.

**Gatilho correto:** extração somente quando ao menos duas distribuições/aplicações reais,
fora do mesmo `shopman/shop`, consumirem o mesmo motor genérico e seu schema não carregar
SKU, segmento, fulfillment ou promoção do Shopman. O plano acerta ao dizer “não agora”.

### 2.3 O orquestrador vira god-module? — REPARA

Sim, se “política cross-domain” for licença sem teto. Contagem de arquivos não é o teto:
em `main`, `shopman/shop` tem 54 arquivos Python na raiz, 174 em `services/`, 52 em
`adapters/`, 41 em `handlers/` e zero em `policies/`; esses números medem volume, não
coesão.

O teto deve ser verificável por unidade de composição:

1. um ponto público por decisão;
2. lista explícita de domínios/portos;
3. nenhum model de kernel importado fora de adapters/public APIs permitidas;
4. fan-in/fan-out e ciclo de imports sem regressão;
5. cenário de mudança fixo toca um módulo de política + testes, não múltiplas
   implementações da decisão;
6. owner e suite isolada da unidade.

O gate atual cobre somente parte disso: proíbe imports de internals em
`shopman/shop/tests/test_import_boundaries.py:test_framework_does_not_import_protected_kernel_internals:153-173`,
mas não detecta duplicação semântica, múltiplos verbos ou dispersão por mudança.

### 2.4 O teste de soberania é tautológico? — REPARA

“O pacote passa seus próprios testes” prova regressão funcional, não soberania. O alvo
`test-cores` executa treze suites no ambiente do monorepo
(`Makefile:test-cores:76-83`); não cria um venv contendo apenas o wheel do pacote e suas
dependências declaradas. O gate AST existente prova apenas que packages não importam host,
e sua mensagem admite resolver integração por adapter/settings:
`shopman/shop/tests/test_import_boundaries.py:test_kernel_packages_do_not_import_host_layers:97-113`.

Um teste de soberania útil precisa provar, separadamente:

- build e instalação do wheel num venv limpo, sem `django-shopman` e sem kernels irmãos;
- import e suite pública nesse ambiente;
- decisão canônica exercitada por contract tests do consumidor;
- busca AST/símbolo demonstrando que não existe segunda implementação no orquestrador;
- fixture mínima que falha se o pacote tentar resolver settings/models do host.

Sem as duas últimas provas, o teste é compatível com V1: Stockman funciona sozinho e a
decisão continua duplicada no Shop.

### 2.5 V1/V3/V4 preservam comportamento? — DERRUBA

Na forma escrita, não. Os três movimentos precisam de transição explícita.

#### V1 — decisão de promessa

A duplicação é literal: o Stockman calcula a decisão em
`packages/stockman/shopman/stockman/services/availability.py:promise_decision_for_sku:295-349`,
e o orquestrador repete a mesma árvore em
`shopman/shop/adapters/stock.py:promise_decision_from_availability:1004-1039`.
Produção usa a cópia após já ter carregado `info`:
`shopman/shop/services/availability.py:_stock_decision:574-612`.

**Dual-run:** primeiro extrair no Stockman uma função pura
`decision_from_availability(info, qty, target_date)`; em testes de caracterização e no
shadow opt-in, serializar os dois resultados e comparar todos os campos, inclusive pausa,
`demand_ok`, datas e qualidade. Nenhuma segunda query é permitida. **Cutover:** trocar o
call site somente após zero divergência no corpus. **Rollback:** um único switch no adapter
volta ao cálculo anterior; a cópia só é apagada no commit seguinte ou, pós-go-live, após a
janela datada da ADR-015.

#### V3 — `untracked` e `demand_ok`

O sentinel existe em
`shopman/shop/services/availability.py:_stock_decision:574-589`. Porém `demand_ok`
também sintetiza quantidade no próprio kernel com `max(available_qty, qty_d)`:
`packages/stockman/shopman/stockman/services/availability.py:promise_decision_for_sku:319-343`.
Portanto “`demand_ok` deixa de sintetizar quantidade” é mudança de contrato, não simples
movimento de titularidade. A Storefront já trata `None` como ausência de teto em
`shopman/storefront/presentation/catalog.py:119-122`, enquanto checkout, lifecycle e stock
ainda consomem `untracked`: `shopman/storefront/intents/checkout.py:514`,
`shopman/shop/lifecycle.py:1297`, `shopman/shop/services/stock.py:_is_untracked:1139-1147`.

**Dual-run:** introduzir `is_tracked` + `available_qty: Decimal | None` num value object,
manter um serializer de compatibilidade somente na borda antiga, e comparar decisões
(`approved`, `reason_code`, hold criado) em vez da quantidade sentinela. **Cutover:** migrar
os consumidores enumerados e proibir comparação com número mágico. **Rollback:** o
serializer antigo volta a materializar `999999` sem reverter o contrato interno. A remoção
desse serializer é uma etapa separada e, se houver go-live, segue expand-contract.

#### V4 — preço

O caminho morto retorna `int`:
`shopman/shop/services/pricing.py:resolve:16-34`. O caminho canônico retorna
`ContextualPrice`: `shopman/shop/projections/catalog_context.py:contextual_price:581-597`.
O contrato atual já explica condições aplicadas como `adjustments[]`, não `conditions[]`:
`packages/offerman/shopman/offerman/protocols/catalog.py:ContextualPrice:41-63`.

**Dual-run:** caracterizar todos os callers e provar por busca que `resolve` não tem
consumidor de produção; comparar `resolve(...)` com `get_price(...).final_total_price_q`
para lista simples. **Cutover:** remover/redirecionar `resolve`, mantendo
`ContextualPrice.adjustments` como contrato canônico ou fazendo rename expand-contract.
**Rollback:** restaurar apenas o wrapper fino; nunca reintroduzir um segundo cálculo.

### 2.6 A Instância recria pacote pela porta dos fundos? — REPARA

Sim, se o descriptor versionado puder executar lógica, carregar secrets ou competir com o
DB. Já há política de instância codificada como fallback no orquestrador:
`shopman/shop/modifiers.py:DEFAULT_AVAILABILITY_DISCOUNT_PERCENT:45-48` e uso em
`shopman/shop/modifiers.py:154-159`. `ChannelConfig` também é simultaneamente contrato e
materialização de configuração: `shopman/shop/config.py:ChannelConfig:61-88`.

**Fronteira proposta:**

- código define schema, validação, defaults seguros e algoritmos genéricos;
- descriptor contém apenas dados não secretos, versionados e declarativos;
- DB é a única verdade de runtime;
- `instance-apply` é transacional, idempotente e registra versão/hash;
- `instance-dump` não exporta credenciais nem estado operacional;
- seed/bootstrap materializa o descriptor, mas nunca é relido por request;
- divergência descriptor↔DB é reportada, não corrigida silenciosamente.

O aceite do WP-6 deve incluir precedência e conflito, não apenas “segunda instância sobe”.

### 2.7 Go-live no meio — ACEITA, com trava

Na base revalidada não existe a tag `go-live-v1`; ADR-015 ainda está inativa. A política,
porém, arma-se pela existência da tag e torna migrations append-only, renames destrutivos
marcados e aliases temporários datados:
`docs/decisions/adr-015-backward-compat-policy-post-prod.md:Decisão:25-68` e
`docs/decisions/adr-015-backward-compat-policy-post-prod.md:Enforcement:70-100`.

Cada WP deve começar registrando `git tag --list go-live-v1`. Se a tag aparecer entre
dois WPs, todo passo restante muda de regime. Se aparecer no meio de um WP com contrato ou
schema em transição, o WP para antes do corte e é repartido em expand, backfill, migrate e
contract. “Movimento de titularidade” não isenta mudança de app label, JSON ou wire format.

### 2.8 Qual WP tem aceite decorativo? — REPARA

WP-8 aceita quando “um dev localiza qualquer artefato pelo mapa”. Isso não é falseável:
qualquer resultado pode ser defendido por leitura humana. WP-12 repete o problema com
“repo navegável”.

**Aceite reparado para WP-8:**

- inventário versionado classifica 100% dos diretórios/apps registrados;
- cada seta tem ao menos um check positivo e um negativo;
- nenhum diretório desconhecido sob `packages/`, `shopman/` e `surfaces/`;
- contagens vêm das fontes canônicas (`Makefile:test-cores`, `surfaces/registry.json`),
  não de números escritos à mão;
- links e owners resolvem;
- três exercícios fixos de localização encontram o dono por regra, sem conhecimento tribal.

WP-12 deve aceitar por zero links quebrados, zero plano ativo arquivado, índice completo e
zero contradição detectada pelo gate, não por “navegabilidade”.

### 2.9 A taxonomia do WP-7 é mutuamente exclusiva? — REPARA

Não. Contraexemplos:

- `shopman/shop/config.py:ChannelConfig:61-88` é contrato/value object **e** configuração
  da instância (categorias 3 e 5).
- `shopman/shop/projections/catalog_context.py:active_promotions:561-578` é leitura, mas
  chama um service que detém a decisão; o arquivo cabe em mecanismo e leitura (2 e 4).
- `shopman/shop/admin/` é simultaneamente infraestrutura e mecanismo de configuração
  (2, 5 e 6).
- handlers são mecanismo, mas frequentemente selecionam ordem e efeitos de composição.

**Reparo:** classificar em dois eixos independentes: (A) responsabilidade semântica
`decisão | composição | leitura | contrato | configuração | infraestrutura`; (B) mecanismo
`service | adapter | handler | projection | API | admin | model`. “Exatamente uma” vale
somente no eixo A e precisa permitir `mixed` como falha a decompor, não como mentira de
inventário.

### 2.10 O manifesto é verificável por máquina? — DERRUBA

Não na proposta atual. Um cabeçalho em comentário pode declarar domínios falsos, omitir
imports lazy e manter dois verbos sem que nada falhe. Hoje não existe `shopman/shop/policies/`
nem parser/gate correspondente; o gate de imports só conhece direção sintática:
`shopman/shop/tests/test_import_boundaries.py:1-12`.

Antes do piloto, o WP-7 precisa definir schema versionado (YAML/TOML ou registry Python
sem side effects) contendo `id`, `question`, `public_entrypoint`, `domains`, `ports`,
`events`, `directives`, `config_surface`, `tests` e `owner`. O gate deve:

- resolver todos os símbolos e testes declarados;
- comparar imports AST com domínios/portos declarados;
- rejeitar dois manifestos para a mesma pergunta/entrypoint;
- rejeitar módulo de política sem manifesto;
- detectar arquivo órfão e manifesto órfão;
- ter fixture negativa que prove cada falha.

Sem isso, o piloto só acrescenta documentação à mesma dispersão que tenta corrigir.

## 3. Quatro ataques adicionais

### 3.1 Numeração ADR impossível na `main` atual — DERRUBA

O plano reserva 035 para titularidade e 036/037 para duplicados. A realidade já ocupa:

- `docs/decisions/adr-035-entrega-sem-cpf-sai-presencial.md:1-4`, aceita em 2026-10-13;
- `docs/decisions/adr-036-loja-online-paga-ao-pedir.md:1-5`, aceita em 2026-10-14.

Renumerá-las violaria a regra explícita de renumerar somente os quatro arquivos duplicados;
reutilizar 035/036 criaria novas colisões. A alocação precisa ser refeita na ponta da fila.

**Recomendação:** no estado observado, titularidade = ADR-037;
`adr-038-operator-surface-security-envelope.md` = ADR-038 (criado em 2026-09-09, depois
do Concierge de 2026-09-03); `adr-039-persistent-stock-alert-occurrences.md` = ADR-039
(os dois cabeçalhos dizem 2026-09-11, mas os commits de criação são `a17e1ef97` às 11:44
para Marketing e `0beeddbc2` às 13:09 para Stock Alert). A regra precisa dizer “commit de
criação”, porque “data” empata no par 029. Revalidar imediatamente antes do commit e do
merge, pois outra frente pode ocupar esses números. Essa decisão precisa de aceite do dono
porque contradiz os números mandatados na missão, embora preserve sua intenção.

### 3.2 A baseline topológica expirou — DERRUBA

O plano diz 12 pacotes e usa `packages/*` como sinônimo de Kernel. Hoje existem 13 pacotes;
o Watchman foi criado como capacidade operacional reutilizável:
`Makefile:test-cores:76-83`, `Makefile:test-watchman:110-112` e
`README.md:19-21`. `packages/watchman` não responde uma pergunta de comércio como os doze
domínios, então “Kernel = `packages/*`” também deixou de ser uma equivalência segura.

O registro tem onze entradas de superfície, das quais nove são apps de negócio, uma é
preview interna (`kitchensink`) e uma é status externo:
`surfaces/registry.json:surfaces`. Contagem precisa declarar a unidade, não escolher um
número conveniente.

**Reparo obrigatório antes de WP-1/WP-8:** rebaseline automatizada e vocabulário que
separe “pacote instalável”, “kernel de domínio”, “capacidade operacional”, “superfície de
negócio”, “preview interna” e “status externo”.

### 3.3 O mapa não tem command-side — DERRUBA

O plano agrupa `presentation + api` em “Read-side” e diz que read-side nunca escreve.
As APIs são também portas de comando:

- recompra limpa e adiciona itens à sacola em
  `shopman/storefront/api/surface.py:OrderReorderView.post:721-803`;
- cupom é aplicado/removido em
  `shopman/storefront/api/surface.py:CartCouponView.post:956-999`;
- Marketing recusa, cancela e reagenda por services de comando em
  `shopman/backstage/api/marketing.py:AnnouncementRejectView.post:1030-1067`,
  `AnnouncementCancelView.post:1070-1107` e `AnnouncementRescheduleView.post:1110-1154`.

Isso não é violação: a API recebe o comando e delega a decisão. A violação é o mapa chamar
toda API de leitura. **Reparo:** separar `Query/read-side (projections + GET)` de
`Command ingress (POST/PATCH/DELETE + intents/API)`, ambos abaixo do orquestrador, com a
regra “command ingress não decide; valida transporte/permissão/idempotência e delega”.

### 3.4 O vocabulário de status não representa decisão parcialmente superada — REPARA

ADR-011 continua válida fora do caixa, mas parte dela foi superada por ADR-022:
`docs/decisions/adr-011-formula-and-cashshift.md:3`. Marcar simplesmente
`Substituído por ADR-022` mentiria sobre o restante. ADR-031/032 também registram emenda
mútua/escopo parcial nos próprios cabeçalhos.

Use `Aceito; emendado por ADR-NNN` para decisões parcialmente alteradas e reserve
`Substituído por ADR-NNN` para substituição integral. Detalhes de implementação, data e
rollout devem sair do campo `Status` para campos próprios; caso contrário um gate que exige
igualdade com quatro strings reprovará quase todos os ADRs aceitos atuais, como se vê em
`docs/decisions/adr-022-cashman-ledger.md:3` e
`docs/decisions/adr-036-loja-online-paga-ao-pedir.md:3-5`.

## 4. Riscos não ditos

1. **Corrida de numeração e índice:** PRs paralelos podem ocupar o próximo número depois da
   revisão. O gate precisa rodar contra a base de merge, não só contra o branch.
2. **Compatibilidade de wire/JSON:** `available_qty`, `reason_code` e preço chegam a
   Storefront, PDV, APIs e snapshots. Mudar value object sem adapters de borda quebra
   consumidores mesmo sem migration Django.
3. **ContentType/permissões em mudança de app:** qualquer futura mudança de model entre
   apps altera content types, permissions, nomes de Admin e FKs; “titularidade” não torna
   isso um rename inofensivo.
4. **PII no `IdentityView`:** handles verificados e primários são dados sensíveis. O contrato
   precisa de minimização por finalidade, redaction em logs e autorização por caller.
5. **Descriptor de Instância e secrets:** dump versionado não pode capturar tokens,
   credenciais ou dados operacionais. Apply parcial precisa rollback transacional e trilha.
6. **Shadow execution com efeitos:** dual-run só pode duplicar funções puras/leitura. Nunca
   duplicar hold, pagamento, notificação ou escrita de ledger.
7. **Métrica do piloto manipulável:** “arquivos a mudar” exige cenário e baseline congelados;
   um façade vazio pode reduzir a contagem sem reduzir acoplamento.
8. **Reorganização final quebra endereços:** WP-12 pode invalidar links, CODEOWNERS, paths de
   CI, docs e memórias. Deve mover por mapa e validar referências, nunca por estética.

## 5. O que eu removeria ou reescreveria no plano

- Remover os números fixos 035/036/037; alocar 037/038/039 apenas se continuarem livres no
  instante do merge.
- Remover “12 pacotes” e qualquer contagem manual; derivar e qualificar a contagem.
- Trocar “Kernel = `packages/*`” por categorias que acomodem Watchman sem fingir que saúde
  operacional é domínio de commerce.
- Remover “API” do read-side; introduzir command ingress.
- Remover “todo arquivo tem exatamente uma das seis categorias”; adotar os dois eixos.
- Remover `conditions[]` como rename obrigatório; o contrato atual é `adjustments[]`. Se o
  dono preferir `conditions`, tratá-lo como evolução de contrato.
- Remover “um verbo público” no sentido literal; manter um entrypoint canônico por decisão.
- Reescrever o aceite do WP-8 e do WP-12 em checks objetivos.
- Não prometer “behavior-preserving” para retirar sentinel/síntese de quantidade antes das
  provas de caracterização e compatibilidade.

## 6. Sequência recomendada

0. **Rebaseline da Fase 0:** atualizar inventário, números, contagens e mapa command/query;
   resolver com o dono ADR-037/038/039 e `adjustments` versus `conditions`.
1. **Lei e governança:** ADR de titularidade com a exceção de bridges; status estruturado;
   índice e gate executado contra merge-base; Constituição curta.
2. **Mapa antes de movimento:** Kernel de domínio + capacidade operacional > Orquestrador >
   Query/read-side e Command ingress > Superfícies, com Instância transversal.
3. **Caracterização de contratos:** snapshots/contract tests para promessa, `untracked`,
   preço e identidade; nenhum corte ainda.
4. **Soberania do kernel:** WP-2, WP-3 e WP-4 em PRs separados, cada um com dual-run puro,
   corte e rollback demonstrado.
5. **Orquestrador:** schema/gate de manifestos; inventário em dois eixos; piloto Promotion
   com cenário de mudança congelado; abortar se a métrica composta não melhorar.
6. **Superfícies/Admin:** WP-11 antes de WP-10 para definir o critério de colocação; depois
   topologia e lacunas por persona.
7. **Instância:** schema + apply/dump seguro + testes de soberania/composição/evolução.
8. **Renascimento:** somente depois de todos os contratos verdes, com gate de links/paths.

## 7. Decisão solicitada ao dono

Aceitar a missão com estas emendas, em especial:

1. titularidade passa a **ADR-037** e os duplicados mais novos a **038/039**, sujeitos a
   nova checagem de disponibilidade;
2. o mapa ganha **Command ingress** separado do read-side;
3. o contrato de preço preserva `adjustments[]` salvo decisão explícita de rename;
4. a taxonomia do WP-7 passa a dois eixos e manifestos ganham schema/gate antes do piloto.

Sem esse aceite, a Fase 1 permanece bloqueada.

## 8. Decisão do dono

**Aceito em 2026-10-16.** A autorização para a Fase 1 incorpora os reparos deste
parecer e fixa quatro interpretações para a execução:

1. números de ADR são alocados pela realidade da `main` no instante do trabalho;
   035/036 não são reutilizados e somente os duplicados mais novos são renumerados;
2. API é fronteira de entrega, não superfície de produto: consultas pertencem ao
   query/read-side e comandos entram por command ingress, que delega sem decidir;
3. `ContextualPrice.adjustments[]` permanece o contrato de efeitos aplicados;
   condições/regras de elegibilidade não substituem esse vocabulário;
4. WP-7 usa inventário em dois eixos, manifesto verificável e um piloto Promotion
   com cenário congelado; se a mudança continuar tocando os mesmos arquivos ou só
   ganhar uma fachada, o piloto e o WP são abortados.

Para V3, o aceite também distingue fato de política: retirar `999999` é obrigatório,
mas o contrato não pode colapsar estoque observado e teto de venda num único `None`.
A evolução deve separar `available_qty` (fato observado, opcional) de
`orderable_ceiling` (limite de política, opcional), com `is_tracked`, decisão e razão
explícitas, por expand-contract nas bordas que ainda consumirem o formato legado.

## 9. Escopo efetivamente executado

- Lidos integralmente `AGENTS.md`/`CLAUDE.md`, missão, plano, Constituição, ADR-001,
  ADR-005, ADR-019, ADR-021, ADR-022, ADR-015 e `CORE-BOUNDARIES-AUDIT.md`.
- Revalidado o código e a documentação em `origin/main @ f4b4943e8`.
- Criado somente este parecer. Nenhum arquivo de produção, migration, ADR ou plano foi
  alterado.
- Não executados `make test`/`make admin`: a Fase 0 muda apenas Markdown e o parecer não
  toca runtime nem Admin. Validações proporcionais: `git diff --check`, checagem de links
  locais citados e inspeção de estado/numeração.
