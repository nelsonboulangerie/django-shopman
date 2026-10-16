# Arquitetura canônica da suite Shopman

Este é o mapa único para localizar código por responsabilidade. A lei de
titularidade está na [ADR-037](decisions/adr-037-decision-ownership.md); o
contrato headless e o corte dado/apresentação estão nas ADRs
[012](decisions/adr-012-headless-surface-contract.md) e
[014](decisions/adr-014-surface-data-presentation-cut.md).

## O mapa

```text
Kernel  ->  Orquestrador  ->  Query/read-side  ->  Superfícies
  ^              ^                  ^                   ^
  +--------------+------------------+-------------------+
              Instância (DB + config de deploy + marca)
```

As setas indicam consumo, não transferência de titularidade. A API é a
**fronteira de entrega**, não uma superfície de produto:

- `GET` e SSE entram pelo lado query/read-side e não produzem efeitos;
- `POST`, `PUT`, `PATCH`, `DELETE` e intents entram pelo command ingress,
  autenticam, validam idempotência/concorrência e delegam ao dono;
- o transporte não recalcula decisão de kernel ou política do orquestrador.

### 1. Kernel

`packages/*` contém 13 distribuições pip independentes:

- dez kernels de domínio: `offerman`, `stockman`, `craftsman`, `orderman`,
  `guestman`, `doorman`, `payman`, `buyman`, `fiscalman`, `cashman`;
- duas primitivas compartilhadas sem regra de negócio: `utils`, `refs`;
- uma capacidade operacional horizontal: `watchman`.

Cada kernel possui sua pergunta canônica, seus invariantes e, quando existe,
seu ledger. Código de domínio de kernel não importa outro kernel. Bridges
opt-in só vivem em `adapters/` ou `contrib/<alvo>/`, com import lazy, conforme
a ADR-001.

### 2. Orquestrador

`shopman/shop/` é o único encontro deliberado de domínios. Ele sequencia
services, adapters, handlers, directives e lifecycle; também possui política
que só existe quando dois ou mais domínios se encontram. Pode consumir APIs
públicas de vários kernels, mas não reimplementa a decisão canônica deles e
não renderiza interface.

### 3. Query/read-side e command ingress

O read-side reúne projections e apresentação de dados em:

- `shopman/shop/projections/`;
- `shopman/storefront/presentation/` e `shopman/storefront/api/`;
- `shopman/backstage/projections/` e `shopman/backstage/api/`.

`storefront` e `backstage` são apps Django de **entrega headless**. Um módulo
nesses apps deve ser classificado pelo que faz: GET/SSE e projections são
read-side; endpoints mutáveis e intents são command ingress. Eles não são as
superfícies de produto e não ganham titularidade só por possuir a URL.

Projection lê estado e decisões já resolvidas, devolve dados semânticos e
Actions, e não escreve. Command ingress traduz HTTP, aplica permissões,
freshness, idempotência e concorrência, e chama o orquestrador ou o dono.

### 4. Superfícies

`surfaces/registry.json` registra 11 apps Nuxt:

- nove superfícies de produto: `storefront`, `hub`, `pos`, `kds`, `orders`,
  `production`, `marketing`, `bi`, `purchase`;
- `kitchensink`, preview interno de desenvolvimento;
- `status`, superfície pública externa de saúde.

`operator-kit` é a layer compartilhada dos apps de operador e
`operator-router` é infraestrutura de deploy; nenhum dos dois é app de
produto. Admin/Unfold é outra superfície, voltada a configuração, auditoria e
operações explicitamente mantidas no Admin.

Superfícies falam com a fronteira de entrega por HTTP/SSE. Não importam kernel,
não consultam banco e não recalculam política. Presentation possui copy,
formatação e interação; a Projection possui fatos semânticos.

### 5. Instância, transversal

A Instância não é uma quinta camada nem um pacote Python. O DB é a verdade de
runtime; `config/`, settings de infraestrutura e marca completam o deployment.
Ela parametriza todas as camadas sem alterar o código delas. Seed e descritor
versionado são mecanismos de bootstrap/diff, não uma segunda verdade.

## Teste de localização

| Pergunta | Endereço inicial |
|---|---|
| O que é vendável e qual o preço de lista? | `packages/offerman/` |
| Quanto e quando pode ser prometido? | `packages/stockman/` |
| Qual compromisso foi assumido? | `packages/orderman/` |
| Como domínios são sequenciados? | `shopman/shop/` |
| Qual dado/API um cliente lê? | `*/projections`, `*/presentation`, GET/SSE em `*/api` |
| Onde uma intenção HTTP é validada? | command ingress em `storefront/api` ou `backstage/api` |
| Onde a pessoa opera? | `surfaces/*-nuxt` ou Admin/Unfold |
| Qual horário, canal, regra ativa ou marca? | DB da Instância + `config/` |

## Setas protegidas

1. Kernel não importa host nem outro kernel no código de domínio.
2. Orquestrador só toca apps de entrega por bridge nomeada e não acessa
   internals protegidos dos kernels.
3. Query/read-side não chama escrita ORM nem service de mutação.
4. Superfície não importa kernel; comunica-se somente pela fronteira HTTP/SSE.
5. Command ingress delega a mutação; não contém uma segunda implementação.

O gate bloqueia arestas novas já neste WP. A dependência histórica
`doorman/services/verification.py -> guestman` fica explicitamente isolada na
baseline até o WP-4 retirar essa última exceção.

O inventário físico verificável vive em
[`architecture-map.json`](architecture-map.json). Os testes de fronteira
validam o inventário e as regras estruturais acima.
