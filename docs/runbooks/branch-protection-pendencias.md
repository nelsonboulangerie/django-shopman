# Branch protection do `main` — três decisões pendentes do dono

> **Para quem:** o dono. Branch protection só muda pela mão dele, no GitHub —
> nenhum agente altera isto, e este documento não pede que altere: pede que
> decida.
>
> Estado medido em **05/09/2026** via
> `gh api repos/nelsonboulangerie/django-shopman/branches/main/protection`.

## O estado hoje

| Item | Valor |
|---|---|
| Checks obrigatórios | **21** |
| `enforce_admins` | **`true`** — nem o dono passa por cima |
| `required_status_checks.strict` | **`false`** |

A CI **não é fraca**. A suíte Python inteira roda em cada PR (7.780 testes
coletados), os 10 apps Nuxt rodam vitest, o Playwright é real. A hipótese
"features entram sem teste" foi medida e **não se sustenta** — ver
[`silencio-inventario.md`](../reference/silencio-inventario.md) para a causa
que se sustenta.

O que segue são três ajustes baratos, cada um com o trade-off honesto.

---

## 1. `admin-csp` roda e não bloqueia

**O quê:** o job `Admin CSP (production settings)`
(`.github/workflows/omotenashi-gate.yml:169`) sobe o Admin com `DEBUG=false` e
caça violação de CSP com Playwright. Ele roda em todo PR — e **não está na
lista de contextos obrigatórios**. É o único gate do repositório nessa
situação.

**Por que importa:** violação de CSP no Admin não aparece em teste de unidade e
não aparece em `DEBUG=true`. Ela aparece no navegador do gestor, em produção,
como um botão que não faz nada. O gate existe exatamente para isso e hoje pode
ficar vermelho sem consequência — o que, na prática, é o mesmo que não existir.

**Recomendação:** tornar obrigatório.

**Custo:** nenhum. O job já roda; a mudança é só passar a exigi-lo.

**Como:** Settings → Branches → `main` → *Require status checks to pass* →
adicionar `Admin CSP (production settings)`.

> ⚠️ Confira o nome do check **exatamente** como ele aparece num PR recente
> antes de adicionar. Check obrigatório com nome que nunca aparece **trava
> todos os PRs para sempre**, inclusive o que consertaria o nome.

---

## 2. `strict: false` — e 40+ worktrees em paralelo

**O quê:** `required_status_checks.strict` está `false`. Uma branch **não
precisa estar em dia com o `main`** para mergear. Os checks dela podem ter
rodado contra um `main` de ontem.

**Por que importa aqui mais do que num repositório normal:** com dezenas de
sessões trabalhando em paralelo, duas branches tocam o mesmo arquivo o tempo
todo. Se as duas passaram verde contra bases diferentes, o merge das duas
produz uma árvore que **nenhum check jamais viu**. É o vetor direto de "merge
sobrescreveu a feature".

**O trade-off, honesto — e ele é real:**

`strict: true` obriga toda branch a rebasear/mergear o `main` antes de entrar.
Com PRs chegando em rajada, isso **serializa a fila**: cada merge invalida
todas as outras branches, que precisam atualizar e rodar a suíte de novo. Numa
suíte de ~13 minutos e uma dúzia de PRs abertos, a fila engasga de verdade.

**E há um contrapeso que muda a conta:** este repositório **usa merge queue**.
A fila já testa o *resultado do merge*, não a branch isolada — os workflows têm
gatilho `merge_group` justamente por isso (`runtime-gate.yml` documenta a
decisão). Ou seja, a proteção que o `strict: true` daria, a fila **já dá**, e
sem serializar: ela agrupa e testa o lote.

**Recomendação: manter `strict: false`.** Não por descuido, mas porque a fila
de merge o tornou redundante — e ligá-lo cobraria o preço da lentidão por uma
garantia que já existe. O comentário em `runtime-gate.yml` sobre o
`test-migrations` chega à mesma conclusão por outro caminho.

**Quando revisitar:** se a fila de merge for desligada, ou se aparecer uma
regressão em que o `merge_group` passou verde e o `main` quebrou. Aí a conta
inverte.

---

## 3. O gate da meia-correção, quando vira obrigatório

**O quê:** este PR acrescenta o job `Gate da meia-correção (não-bloqueante)` ao
`runtime-gate.yml`, com `continue-on-error: true`.

**Por que não nasce obrigatório:** a medição encontrou **50 arquivos** de
produção já em contradição interna, com **94 sites** mudos. Um gate que nasce
reprovando 50 arquivos é desligado no primeiro dia — e aí não guarda nem os
arquivos novos.

**O portão para promovê-lo** está escrito no placar do inventário: **as faixas
💸 dinheiro e 🧾 nota fiscal zeradas — 6 arquivos, 16 sites.** Não são 50.

Quem fechar a última linha dessas duas faixas apaga o `continue-on-error` do
job. Aí sim a mão do dono é necessária, para adicionar
`Gate da meia-correção (não-bloqueante)` — com o nome que ele tiver naquele
momento — aos contextos obrigatórios.

> Se o job for renomeado ao virar bloqueante (o `(não-bloqueante)` no nome
> deixaria de fazer sentido), **renomeie primeiro, mergeie, confirme que o nome
> novo aparece num PR, e só então adicione à branch protection.** A ordem
> inversa trava a fila.

---

## Resumo do que precisa da sua mão

| # | Decisão | Recomendação | Custo |
|---|---|---|---|
| 1 | `admin-csp` obrigatório? | **Sim, agora** | zero — já roda |
| 2 | `strict: true`? | **Não** — a fila de merge já cobre | ligar custaria fila lenta |
| 3 | Gate da meia-correção obrigatório? | **Ainda não** — quando 💸 e 🧾 zerarem | zero — já roda |
