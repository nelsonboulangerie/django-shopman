# Avaliação do repositório Shopman — 2026-10-22

**Nota: 8,5 / 10** (média ponderada das dimensões: 8,4)

- **Escopo:** o repositório inteiro — `packages/` (13 kernels), `shopman/` (orquestrador e
  superfícies Django), `surfaces/` (11 apps Nuxt), `config/`, `docs/` e `.github/`.
- **Commit de referência:** `ec20167c6` (`origin/main` em 22/10/2026). As medições foram
  feitas nesse commit, num worktree limpo, sem alterar código.
- **Método:** contagem por AST e por `find`/`grep`, `ruff`, `pytest` por pacote, `gh` para
  CI e PRs, e leitura de código. Nenhuma modificação foi feita para avaliar.
- **Autoria:** sessão DSH (DeepSeek Harness), a pedido do dono.

> Este documento é autossuficiente de propósito: qualquer agente que o leia deve poder
> reproduzir as medições e discordar com número na mão. Os comandos estão na seção 7.
> **Isto é diagnóstico, não autorização de trabalho.** O que fazer com cada achado é
> decisão do dono, conforme a [ADR-037](../decisions/adr-037-decision-ownership.md).

---

## 1. Veredito em uma frase

Disciplina de engenharia acima da média — documentação normativa, testes em volume de
sistema, CI que de fato barra — com a manutenibilidade concentrada em poucos arquivos
gigantes e um custo de coordenação que já compete com o custo de código.

Vale como base de produto. Não está pronta para um time grande entrar amanhã, e o motivo
não é arquitetura: é que três arquivos concentram tanto que onboarding vira arqueologia.

---

## 2. Notas por dimensão

| Dimensão | Nota | Peso | O que decide a nota |
|---|---:|---:|---|
| Modelagem de domínio | 9,5 | 25% | 13 kernels pip-independentes, ledgers em stockman e cashman, dinheiro em centavos, identidade por `ref` |
| Documentação e governança | 9,5 | 15% | 951 páginas `.md`, 42 ADRs, constituição com hierarquia normativa, gates que reprovam deriva |
| Testes | 8,5 | 20% | 16.489 funções de teste; 12.558 testes só no app `shop`; cobertura não é portão |
| CI/CD | 8,5 | 10% | 13 workflows, Runtime Gate verde em série, merge queue ativa, smoke agendado no alpha |
| Segurança | 8,0 | 10% | CSP, OTP, device trust, decisão explícita de não usar cliente de geolocalização por rede |
| Manutenibilidade do código | 6,5 | 10% | 180 funções com 120+ linhas; god modules de 6.000 a 10.000 linhas |
| Higiene de repositório e processo | 6,0 | 10% | 1.374 branches remotas, 120 worktrees, checkout principal 96 commits atrás e sujo |

A média ponderada fecha em 8,4; a nota final arredonda para **8,5** porque o que a base
entrega (domínio e documentação) é o que mais custa para ser reconstruído, e o que ela
deve (higiene e tamanho de arquivo) é mais barato de consertar.

---

## 3. Medições no commit de referência

Todas em `ec20167c6`, worktree limpo.

| Métrica | Valor |
|---|---:|
| Arquivos `.py` (fora de `.venv`, `node_modules` e worktrees) | 2.999 |
| Linhas de produção (sem testes e sem migrações) | 406.886 |
| Linhas de teste | 356.004 |
| Funções `def test_` | 16.489 |
| Testes coletados em `shopman/shop/tests` | 12.558 |
| Migrações | 319 (121 em `shopman/shop`) |
| Páginas de documentação | 951 `.md`, ~243.586 linhas |
| ADRs | 42 |
| Workflows de CI | 13 |
| Funções com 120 linhas ou mais (produção) | 180 |
| `except Exception` em produção | 928 |
| Arquivos rastreados | 8.221 |
| Peso do `.git` | 1,5 GB |
| `ruff check` | limpo |
| `ruff format --check` | 2.160 arquivos divergem |
| Branches remotas fora da `main` | 1.374 |
| Worktrees registradas | 120 |
| PRs abertos | 15 (5 com mais de 3 dias, todos Dependabot) |
| Mediana de vida de PR | 2,2 h (p90 5,5 h, n=60) |
| Commits em outubro/2026 | 2.271 |

---

## 4. O que sustenta a nota

### 4.1 Fronteiras de domínio que se sustentam na prática

`packages/` não se importa entre si; integração entre domínios vira *signal*, *adapter* ou
*directive*, e a escolha entre os três é decidida por uma ADR, não por gosto de quem
escreve. Isso não é diagrama de slide: há guard script que reprova import cruzado e
baseline histórica que não pode crescer.

Os invariantes são verificáveis, não decorativos: dinheiro em inteiro de centavos com
sufixo `_q`, identidade cross-domain por `ref` textual, ledger imutável onde há
movimento de estoque e de caixa. São escolhas que cobram caro depois e foram pagas antes.

### 4.2 Documentação como artefato executável

A hierarquia é declarada e vale: Constituição > ADR aceita mais recente > guia >
código acidental ([constituição](../constitution.md)). Deriva entre documentação e
código é tratada como dívida explícita, com `check_docs_governance`,
`check_adr_governance` e `check_canonical_docs` no CI.

É raro ver um projeto solo manter 42 ADRs com contexto, alternativas e consequências, e
mais raro ainda ver os gates que as mantêm honestas.

### 4.3 Testes em volume de sistema

16.489 funções de teste não são vaidade: cobrem fiscal, pagamento, estoque, fechamento de
caixa e fluxo de produção, não só CRUD. O CI roda a suíte em shards por área, com
cobertura agregada entre jobs.

### 4.4 CI e disciplina de release

O [Runtime Gate](../../.github/workflows/runtime-gate.yml) leva 20 a 34 minutos e roda em
todo PR e na merge queue. A fila de merge está ativa, o smoke do alpha roda por agenda de
poucas horas, e os últimos PRs mergeados têm mediana de 2,2 h de vida. Para um projeto
desta escala, é cadência de time.

### 4.5 Postura de segurança acima do padrão do mercado brasileiro

CSP com nonce, envelope de segurança das superfícies de operador como capability opt-in,
OTP e confiança de dispositivo, e decisões explícitas de não embutir cliente de rede onde
o dado do titular não deve sair da casa. Segurança tratada como requisito de arquitetura,
não como checklist posterior.

---

## 5. O que puxa a nota para baixo

### 5.1 God modules concentram o risco

| Arquivo | Linhas |
|---|---:|
| [`config/management/commands/seed.py`](../../config/management/commands/seed.py) | 10.210 |
| [`shopman/backstage/api/operations.py`](../../shopman/backstage/api/operations.py) | 6.557 |
| [`shopman/shop/services/pos.py`](../../shopman/shop/services/pos.py) | 6.511 |
| [`shopman/backstage/projections/production.py`](../../shopman/backstage/projections/production.py) | 4.605 |
| [`shopman/backstage/services/production.py`](../../shopman/backstage/services/production.py) | 3.809 |
| [`shopman/backstage/projections/pos.py`](../../shopman/backstage/projections/pos.py) | 3.391 |

Há 180 funções com 120 linhas ou mais. As piores: `_seed_recipes` com 2.442 linhas,
`_seed_catalog` com 1.531, `_write_export` com 784, `approve_command` com 479,
`_checkout_contract` com 448 e `finish` com 403.

O efeito não é estético. Esses arquivos não admitem teste de unidade útil, então a
cobertura deles é por integração, mais lenta e mais frágil; e qualquer mudança neles exige
releitura integral, o que encarece justamente as áreas de maior valor (catálogo, PDV,
produção).

### 5.2 928 `except Exception` em produção

Muitos são legítimos em borda (webhook, adaptor, integração de terceiro). Nesse volume,
porém, a distinção entre "borda" e "engoli o erro" deixa de ser verificável por leitura,
e o guard de exceção silenciosa passa a confiar mais na disciplina do autor do que no
desenho.

### 5.3 Cobertura não é portão

O `pyproject.toml` declara `fail_under = 75`, mas o CI roda com `--cov-fail-under=0`:
a régua existe e não é executada. Medição pontual do `offerman` no checkout principal deu
67,19%, abaixo do declarado. A suíte é grande; a garantia de cobertura é optativa.

### 5.4 Processo e higiene do repositório

1.374 branches remotas para 15 PRs abertos, 120 worktrees registradas, `.git` de 1,5 GB.
Um checkout principal 96 commits atrás da `main`, com arquivos modificados e não
commitados, é exatamente o cenário que o `CLAUDE.md` descreve como causa das perdas de
trabalho de 30/07, 12/08, 13/08 e 19/08. A trava existe e o cenário reaparece.

Há ainda 2.271 commits só em outubro, com muitos `Merge remote-tracking branch` no
histórico: parte do esforço de engenharia está sendo gasta em reconciliação que um fluxo
de rebase contínuo evitaria.

### 5.5 Drift pequeno, mas sintomático

- O `CLAUDE.md` anuncia "~6.500 testes"; a realidade é 12.558 só em `shopman/shop/tests`
  e 16.489 funções de teste no total.
- `ruff check` está limpo, mas `ruff format --check` divergiria em 2.160 arquivos:
  formatação não é portão, então o estilo de fato é por autor.
- 928 `except Exception` e 180 funções longas convivem com gates sofisticados. O gate
  protege o que já foi decidido; não empurra o que ainda não foi.

### 5.6 Dependências paradas

`stripe` 15→16, `redis` 7→8, `django-filter` 25→26, `multidict` 6→7 e `@nuxt/kit`
abertos desde 15/10. São 5 dos 15 PRs abertos, e envelhecem sozinhos.

---

## 6. O que levaria a nota a 9,5

1. **Quebrar os três god modules** em serviços coesos com contrato testável. Não é
   refactor estético: é o que destrava teste de unidade em catálogo, PDV e produção.
   `seed.py` pode ser quebrado por domínio sem mudar comportamento.
2. **Ligar `--cov-fail-under`** por suíte, ou assumir por escrito que cobertura não é
   portão. Hoje há uma régua declarada que não vale nada, o que é pior que não ter régua.
3. **Podar branches e worktrees** com dono e prazo. 1.374 branches é dívida de atenção,
   não de disco.
4. **Padronizar formatação** (`ruff format` como portão) para eliminar 2.160 divergências.
5. **Corrigir o número de testes no `CLAUDE.md`** e derivá-lo de um comando, para que a
   documentação não envelheça em silêncio.

---

## 7. Limites do que foi medido

O que **não** está na nota, por falta de evidência:

- **Comportamento em produção:** não avaliei latência, taxa de erro, custo de infraestrutura
  nem comportamento sob carga real. O smoke do alpha estava verde no momento da medição.
- **Cobertura agregada real:** o percentual global não foi recomposto; só há a medição
  pontual do `offerman`.
- **Suíte completa local:** o checkout principal não roda a suíte inteira (o `.venv` não
  tem o editable de `shopman.watchman`, e `django.setup()` falha). Rodei pacotes isolados:
  `offerman` 308 passaram, `stockman` 359 passaram. Rodar os dois juntos sob um
  `PYTHONPATH` improvisado produziu 107 falhas — artefato da invocação, não do código, e
  por isso não entra na nota.
- **Qualidade do frontend Nuxt:** olhei volume (~1.971 arquivos `.vue`/`.ts` em 11 apps) e
  a existência de testes vitest por app, mas não auditei componente a componente.
- **Adequação de produto ao negócio:** não é o que esta nota mede.

---

## 8. Como reproduzir

Dois avisos antes de rodar:

- **Nunca escreva no checkout principal.** Abra worktree (`EnterWorktree` ou
  `git worktree add`), como manda o `CLAUDE.md`.
- **Comando com `| tail` mascara o exit code.** Na primeira tentativa desta avaliação a
  suíte "passou" com o `django.setup()` quebrado por causa disso. Confira `exitCode`.

```bash
# Tamanho e concentração
find packages shopman config -name '*.py' -not -path '*/tests/*' -not -path '*/migrations/*' \
  | xargs wc -l | sort -rn | head -15

# Funções longas (AST, não regex)
python - <<'PY'
import ast, os
rows = []
for d, _, fs in os.walk('.'):
    if any(s in d for s in ('/.git', '/.venv', 'node_modules', '/migrations')):
        continue
    for f in fs:
        if not f.endswith('.py') or f.startswith('test_'):
            continue
        p = os.path.join(d, f)
        try:
            tree = ast.parse(open(p, encoding='utf-8', errors='ignore').read())
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (n.end_lineno or n.lineno) - n.lineno + 1
                if length >= 120:
                    rows.append((length, p, n.name))
for row in sorted(rows, reverse=True)[:15]:
    print(row)
PY

# Testes
grep -r --include='test_*.py' -c 'def test_' packages shopman config \
  | awk -F: '{s+=$2} END {print "def test_:", s}'

# Lint e formatação
.venv/bin/ruff check .
.venv/bin/ruff format --check .

# Processo
git branch -r | grep -vc 'origin/main'
git worktree list | wc -l
gh pr list --state open --limit 200 --json number,createdAt,title
gh run list --workflow=runtime-gate.yml --limit 15
```

---

## 9. Para quem for agir a partir daqui

- O diagnóstico acima **não abre frente de trabalho**. Cada item vira decisão do dono ou
  entra como PR de escopo próprio, com número.
- Antes de abrir PR para qualquer item da seção 6, confira se já existe frente viva
  (`gh pr list`, `git branch -r`, lista de sessões). Achado repetido não justifica PR novo.
- Se este documento envelhecer, **ele deve ser corrigido por outro, com data nova**, em vez
  de ser apagado: a nota só tem valor se a evidência for rastreável.
