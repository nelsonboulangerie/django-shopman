# CORE-SOVEREIGNTY-MISSION — Missão do agente externo

> **Base:** `main` (confirmar commit no início).
> **Plano canônico:** [CORE-SOVEREIGNTY-PLAN.md](CORE-SOVEREIGNTY-PLAN.md).
> **Natureza:** missão de **fronteira**, não de feature.
> **Regra de ouro:** a Fase 0 (revisão adversarial) é **bloqueante**. Nenhum código de produção é editado antes do parecer.

---

## 0. Papel e protocolo

Você é arquiteto sênior (Django/commerce) **e revisor adversarial**. Leia o `AGENTS.md`/`CLAUDE.md` da raiz. Entre num **worktree próprio** antes do primeiro edit. Trabalhe pela **esteira**: commit → push → PR (draft na Fase 0) → fila após verde. Frente não termina dormente.

Leitura obrigatória: `docs/constitution.md`, ADR-001/-005/-019/-021/-022, `CORE-BOUNDARIES-AUDIT.md`, este arquivo e o plano.

---

## 1. Fase 0 — revisão adversarial (bloqueante)

Tente **derrubar** o plano antes de executar. Os dez ataques estão em `CORE-SOVEREIGNTY-PLAN.md` §4. Acrescente até quatro seus. Entregue `docs/plans/CORE-SOVEREIGNTY-REVIEW.md` com veredito por item (derruba / repara / aceita), riscos não ditos e recomendação de sequência. **Sem aceite do dono, não há Fase 1.**

---

## 2. Sequência de execução (definida)

| Fase | Conteúdo | Depende de |
|---|---|---|
| **1. Lei e governança** | ADR-035 (titularidade) · Constituição (pétreas) · governança de ADRs · WP-8 (mapa de camadas) | Fase 0 aceita |
| **2. Soberania do kernel** | WP-2 stockman · WP-3 preço · WP-4 doorman | Fase 1 |
| **3. Orquestrador** | WP-7 unidades de composição (inventário → manifestos → piloto `promotion` → enforcement) | Fase 1 |
| **4. Superfícies e Admin** | WP-11 fronteira Admin×Superfícies · WP-10 topologia (shell, lacunas, kitchensink interno) | Fase 1 |
| **5. Instância e contratos** | WP-6 Instância · Seed · Testes de contrato | Fase 3 |
| **6. Renascimento** | WP-12 reorganização final do repo, docs e ADRs | Fases 1–5 |

Um WP por PR. O aceite de cada WP vai no corpo do PR.

---

## 3. Fase 1 em detalhe

### 1.1 ADR-035 — Titularidade das Decisões
A lei do plano §1: **a pergunta canônica de um domínio pertence ao pacote daquele domínio; a política que compõe dois ou mais domínios pertence ao orquestrador; nenhum invade o outro.** Corpus: ADR-005 §3, ADR-019, ADR-022 e o método do `CORE-BOUNDARIES-AUDIT.md`.

### 1.2 Constituição — cláusulas pétreas
Separar três degraus: **Constituição** (pétreas, curta e estável) · **ADRs** (datadas, revisáveis) · **Guias/Referência** (descritivos). Pétreas propostas: 001 (Porto/Adapter), 002 (centavos), 004 (refs), 005 (orquestrador), 006 (status de Order), 007 (lifecycle config-driven), 012/014 (contrato headless + corte dado/apresentação), 015 (compat pós-prod), 021 (BI read layer), 022 (ledger), 035 (titularidade).

### 1.3 Governança de ADRs — método

**Medido:** 1.358 referências `ADR-NNN` no repositório; ADR-017 tem 122, ADR-015 tem 101. Por isso:

- **NÃO renumerar em massa.** O custo quebra referência e não paga.
- **Renumerar apenas os duplicados** — hoje `adr-026` ×2 (concierge e operator-surface-security) e `adr-029` ×2 (marketing-fire e persistent-stock-alert). Em cada par, o **mais novo por data** recebe o próximo número livre (**036** e **037**; **035** é a titularidade).
- Ao renomear arquivo, atualizar **as duas formas** de referência: o **link para o arquivo** (renomeia junto) e o **texto `ADR-NNN`**, que só pode ser resolvido por **contexto** — 38 ocorrências de `ADR-026` e as de `ADR-029` misturam os dois ADRs. Cada uma deve ser lida e atribuída.
- **Normalizar status** para o vocabulário canônico: `Proposto` · `Aceito` · `Aceito; emendado por ADR-NNN` · `Substituído por ADR-NNN`. Corrigir: 009/012/013/014/015 (Accepted→Aceito), 019/018/020 (implementados marcados Proposto), 011 (substituído em parte por 022), 031/032 (emenda mútua).
- **Índice único** (`docs/decisions/README.md`): número, título, status, dono, data, tema.
- **Gate de prevenção** (é o que impede a reincidência): falha se houver **número duplicado**, **status fora do vocabulário** ou **arquivo sem entrada no índice**. O `GO-LIVE-ACCELERATION-PLAN-2026-09-29.md` já descreve esse gate — reaproveite.

**Aceite:** zero número duplicado; todo ADR com status canônico; índice responde "qual é a lei e o que a revisou"; gate verde.

### 1.4 WP-8 — Mapa de camadas
Declarar a hierarquia **Kernel > Orquestrador > Read-side > Superfícies** (+ Instância transversal) num único documento; testes de fronteira por seta; reescrever `docs/architecture.md` corrigindo contagem de pacotes (12) e apps.

---

## 4. Fases 2 a 6

Detalhe e aceite de cada WP estão em `CORE-SOVEREIGNTY-PLAN.md` §5. Resumo dos pontos que o agente não pode reinterpretar:

- **WP-2 stockman:** a decisão de promessa volta para o stockman; a cópia do orquestrador é deletada; `reason_code` vira enum; `untracked` não devolve `999999`.
- **WP-3 preço:** um verbo público, um caminho; `resolve` morto; toda cotação traz `conditions[]`.
- **WP-4 doorman:** porto `IdentityView` com handles; resolução `identifier`-first; sem import direto de guestman.
- **WP-7 orquestrador:** inventário e classificação **sem mover código**; manifestos; piloto `promotion`; enforcement. Se o piloto não reduzir o número de arquivos que precisam mudar para alterar a promoção, o WP é **abortado**.
- **WP-10 superfícies:** taxonomia por persona; decidir shell × apps em ADR; **kitchensink é recurso interno de Dev, não superfície de operador**; fechar lacunas (catálogo, clientes, fornecedores/estoque, fechamento).
- **WP-11 Admin:** fronteira por frequência/público/risco; nenhuma tarefa diária só no Admin.
- **WP-6 Instância:** DB é a verdade de runtime; descritor versionado para bootstrap/diff; testes de soberania, composição e evolução.
- **WP-12 renascimento:** passada final única de reorganização do repo, docs e ADRs.

---

## 5. Cercas

- Não criar pacote de kernel novo sem 2+ consumidores reais (ADR-001).
- Não transformar composição/política em pacote pip (ADR-005 §3).
- Não reimplementar decisão canônica de um kernel no orquestrador.
- Não importar model de um kernel dentro de outro kernel.
- Não renumerar ADR em massa; não renomear app por estética.
- Não reescrever lógica: os movimentos são de **titularidade**.
- Não commitar no checkout principal; `git add` só de arquivo nomeado.

---

## 6. Relatório (formato fixo)

- **Estado:** mergeado (nº) / na fila (nº) / PR aberto vermelho (causa + próximo passo) / esperando decisão (pergunta + PR draft).
- **Fase 0:** veredito por ataque, o que mudou no plano, o que ficou de fora e por quê.
- **Fases executadas:** WPs, arquivos, comandos de teste e resultado.
- **Pendências:** nome e motivo.
