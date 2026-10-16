# CORE-SOVEREIGNTY-MISSION — Missão do agente externo

> **Base:** `main` (confirmar commit no início).
> **Plano canônico:** [CORE-SOVEREIGNTY-PLAN.md](CORE-SOVEREIGNTY-PLAN.md).
> **Natureza:** missão de **fronteira**, não de feature.
> **Estado:** Fase 0 concluída e aceita em 2026-10-16; execução autorizada conforme o
> [parecer](CORE-SOVEREIGNTY-REVIEW.md).
> **Regra de ouro preservada:** a revisão adversarial foi bloqueante; nenhum código de
> produção foi editado antes do parecer e do aceite.

---

## 0. Papel e protocolo

Você é arquiteto sênior (Django/commerce) **e revisor adversarial**. Leia o `AGENTS.md`/`CLAUDE.md` da raiz. Entre num **worktree próprio** antes do primeiro edit. Trabalhe pela **esteira**: commit → push → PR (draft na Fase 0) → fila após verde. Frente não termina dormente.

Leitura obrigatória: `docs/constitution.md`, ADR-001/-005/-019/-021/-022, `CORE-BOUNDARIES-AUDIT.md`, este arquivo e o plano.

---

## 1. Fase 0 — revisão adversarial (concluída)

O plano foi atacado nos dez pontos obrigatórios e em quatro adicionais. O parecer em
`docs/plans/CORE-SOVEREIGNTY-REVIEW.md` registrou veredito por item, riscos, remoções e
sequência; o dono aceitou os reparos em 2026-10-16. Fases seguintes continuam obrigadas a
revalidar evidência, tag `go-live-v1` e compatibilidade antes de cada corte.

---

## 2. Sequência de execução (definida)

| Fase | Conteúdo | Depende de |
|---|---|---|
| **1. Lei e governança** | ADR-037 (titularidade) · Constituição (pétreas) · governança de ADRs · WP-8 (mapa de camadas) | Fase 0 aceita |
| **2. Soberania do kernel** | WP-2 stockman · WP-3 preço · WP-4 doorman | Fase 1 |
| **3. Orquestrador** | WP-7 unidades de composição (inventário → manifestos → piloto `promotion` → enforcement) | Fase 1 |
| **4. Superfícies e Admin** | WP-11 fronteira Admin×Superfícies · WP-10 topologia (shell, lacunas, kitchensink interno) | Fase 1 |
| **5. Instância e contratos** | WP-6 Instância · Seed · Testes de contrato | Fase 3 |
| **6. Renascimento** | WP-12 reorganização final do repo, docs e ADRs | Fases 1–5 |

Um WP por PR. O aceite de cada WP vai no corpo do PR.

---

## 3. Fase 1 em detalhe

### 1.1 ADR-037 — Titularidade das Decisões
A lei do plano §1: **a pergunta canônica de um domínio pertence ao pacote daquele domínio; a política que compõe dois ou mais domínios pertence ao orquestrador; nenhum invade o outro.** Corpus: ADR-005 §3, ADR-019, ADR-022 e o método do `CORE-BOUNDARIES-AUDIT.md`.

“Um ponto de entrada” vale por decisão, não por pacote inteiro. Bridges opt-in, nomeadas e
lazy em `adapters/` ou `contrib/<alvo>/` permanecem válidas nos termos da ADR-001.

### 1.2 Constituição — cláusulas pétreas
Separar três degraus: **Constituição** (pétreas, curta e estável) · **ADRs** (datadas, revisáveis) · **Guias/Referência** (descritivos). Pétreas: 001 (Porto/Adapter), 002 (centavos), 004 (refs), 005 (orquestrador), 006 (status de Order), 007 (lifecycle config-driven), 012/014 (contrato headless + corte dado/apresentação), 015 (compat pós-prod), 021 (BI read layer), 022 (ledger), 037 (titularidade).

### 1.3 Governança de ADRs — método

**Medido:** 1.358 referências `ADR-NNN` no repositório; ADR-017 tem 122, ADR-015 tem 101. Por isso:

- **NÃO renumerar em massa.** O custo quebra referência e não paga.
- **Renumerar apenas os duplicados**: os ADRs mais antigos permanecem 026 (concierge) e
  029 (marketing-fire); os mais novos por commit de criação já receberam 038
  (operator-surface-security) e 039 (persistent-stock-alert). 035/036 não foram
  reutilizados e a titularidade recebeu 037.
- Ao renomear arquivo, atualizar **as duas formas** de referência: o **link para o arquivo** (renomeia junto) e o **texto `ADR-NNN`**, que só pode ser resolvido por **contexto** — 38 ocorrências de `ADR-026` e as de `ADR-029` misturam os dois ADRs. Cada uma deve ser lida e atribuída.
- **Normalizar status** para o vocabulário canônico: `Proposto` · `Aceito` · `Aceito; emendado por ADR-NNN` · `Substituído por ADR-NNN`. A cadeia factual é 011 emendado por 022 e 031 → 032 → 033; não existe emenda circular 031/032.
- **Índice único** (`docs/decisions/README.md`): número, título, status, dono, data, tema.
- **Gate de prevenção** (é o que impede a reincidência): falha se houver **número duplicado**, **status fora do vocabulário** ou **arquivo sem entrada no índice**. O `GO-LIVE-ACCELERATION-PLAN-2026-09-29.md` já descreve esse gate — reaproveite.

**Aceite:** zero número duplicado; todo ADR com status canônico; índice responde "qual é a lei e o que a revisou"; gate verde.

### 1.4 WP-8 — Mapa de camadas
Declarar a hierarquia **Kernel/capacidades horizontais > Orquestrador > Query/read-side +
Command ingress > Superfícies** (+ Instância transversal) num único documento. API é
fronteira de entrega, não superfície de produto: GET/SSE não produz efeito novo; métodos
mutáveis e intents validam a borda e delegam sem decidir. Inventário e contagens são
derivados de `packages/*`, `surfaces/registry.json` e `docs/architecture-map.json`.

### 1.5 Estado factual da Fase 1

ADR-037 e Constituição: PR #1843; governança/renumeração/índice/gate: PR #1844; mapa e
enforcement de command/query: PR #1845. Todos estão em `main`. WPs 2, 3, 4, 7, 11, 10,
6 e 12 permanecem futuros até seus próprios PRs e aceites.

---

## 4. Fases 2 a 6

Detalhe e aceite de cada WP estão em `CORE-SOVEREIGNTY-PLAN.md` §5. Resumo dos pontos que o agente não pode reinterpretar:

- **WP-2 stockman:** a decisão de promessa volta para o stockman; a cópia do orquestrador é deletada; `reason_code` vira enum; `untracked` não devolve `999999`. O contrato separa `available_qty` factual de `orderable_ceiling` político, ambos opcionais, com `is_tracked`; bordas evoluem por expand-contract.
- **WP-3 preço:** um entrypoint canônico por decisão; `resolve` morto; preço contextual preserva `ContextualPrice.adjustments[]`. Elegibilidade não é renomeada para ajuste e total de cesta não é confundido com cotação unitária.
- **WP-4 doorman:** porto `IdentityView` com handles; resolução `identifier`-first; sem import direto de guestman em service de domínio; PII minimizada e redigida em logs.
- **WP-7 orquestrador:** inventário em dois eixos (**responsabilidade semântica + mecanismo/touchpoint**) sem mover código; schema e gate dos manifestos antes do piloto; cenários e baseline de arquivos congelados; piloto `promotion`; enforcement. Se a métrica composta não melhorar, se só surgir uma façade ou se o teste isolado depender de Django/DB, o piloto e o WP são **abortados**.
- **WP-10 superfícies:** taxonomia por persona; decidir shell × apps em ADR sem presumir monólito (baseline atual: apps federados + Central launcher + `operator-kit`); **kitchensink é recurso interno de Dev, não superfície de operador**; validar lacunas reais antes de criá-las.
- **WP-11 Admin:** fronteira por frequência/público/risco; nenhuma tarefa diária só no Admin.
- **WP-6 Instância:** DB é a verdade de runtime; descritor declarativo, versionado e sem secrets para bootstrap/diff; apply transacional; testes de soberania, composição e evolução.
- **WP-12 renascimento:** passada final única, sem reorganização estética em massa; zero link vivo quebrado, zero plano ativo arquivado e índice/gates completos.

---

## 5. Cercas

- Não criar pacote de kernel novo sem 2+ consumidores reais (ADR-001).
- Não transformar composição/política em pacote pip (ADR-005 §3).
- Não reimplementar decisão canônica de um kernel no orquestrador.
- Não importar outro kernel no código de domínio; somente bridges opt-in, nomeadas e lazy da ADR-001 podem cruzar kernels.
- Não renumerar ADR em massa; não renomear app por estética.
- Não reescrever lógica: os movimentos são de **titularidade**.
- Não fazer shadow/dual-run de efeito: apenas cálculo puro pode rodar em paralelo.
- Não commitar no checkout principal; `git add` só de arquivo nomeado.

---

## 6. Relatório (formato fixo)

- **Estado:** mergeado (nº) / na fila (nº) / PR aberto vermelho (causa + próximo passo) / esperando decisão (pergunta + PR draft).
- **Fase 0:** veredito por ataque, o que mudou no plano, o que ficou de fora e por quê.
- **Fases executadas:** WPs, arquivos, comandos de teste e resultado.
- **Pendências:** nome e motivo.
