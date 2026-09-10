# 11 — A suíte não roda o que a imagem instala (achado da revisão crítica)

Este laudo nasceu da auditoria **da auditoria**: procurando os pontos cegos da própria
varredura, um deles se provou real, mede-se com precisão, e **caveia todo o resto** —
inclusive as provas dos consertos desta rodada.

## P1 — 40 de 100 pinos divergem entre a suíte e a imagem de deploy

- `constraints.txt` fixa o que o **Dockerfile** instala (`Dockerfile:26-27,42`).
- `make install` — usado pelo dev **e pelo CI** — resolve **livre** dentro de faixas
  (`Django>=6.0,<6.1`, `djangorestframework>=3.17,<4.0`, …) e **não** passa
  `-c constraints.txt` (`Makefile`, alvo `install`).
- `make test-constraints` verifica se o arquivo **cobre** o conjunto da imagem. Não
  verifica se a suíte roda esse conjunto. São perguntas diferentes.

Medido em 01/09 no `.venv` canônico da casa, contra `constraints.txt`:

| pacote | imagem (produção) | `.venv` (o que a suíte viu) |
|---|---|---|
| django | 6.0.8 | **6.0.5** |
| djangorestframework | 3.18.0 | **3.17.1** ← bump de *minor* |
| twisted | 26.4.0 | **25.5.0** |
| cryptography | 50.0.1 | **46.0.7** |
| daphne | 4.2.3 | 4.2.1 |
| pillow | 12.3.0 | 12.2.0 |
| urllib3 | 2.7.0 | 2.6.3 |
| sqlparse | 0.6.0 | 0.5.5 |
| django-simple-history | 3.13.0 | 3.11.0 |
| service-identity | 26.1.0 | **24.2.0** |
| rpds-py | 2026.6.3 | **0.30.0** |
| … | | **40 pacotes ao todo** |

**A casa já escreveu o invariante, e ele está quebrado.** O docstring de
`scripts/check_constraints.py` diz, com todas as letras:

> *"o valor do pin é ser a versão que a suíte viu, não a mais nova que existe"*

e, sobre a causa:

> *"O arquivo apodrece em silêncio porque o `make install` do CI não usa constraints;
> só o deploy sente."*

Hoje os pinos são **mais novos** que o conjunto testado — provavelmente por regeneração
ou por PR de dependência sem `make test` no mesmo conjunto. O sentido do drift não muda a
consequência: **verde na suíte não certifica o artefato que sobe.** Um bump de *minor* do
DRF (3.17→3.18) muda comportamento de serializer e de exceção por contrato de semver;
nada nesta suíte o exercitou.

**Isto caveia esta própria rodada.** Todas as provas dos seis consertos de hoje — as ~6.500
do `make test` — rodaram em Django 6.0.5 / DRF 3.17.1. A imagem sobe 6.0.8 / 3.18.0.

**Correção proposta**, em ordem de custo:
1. `make install` passa a instalar com `-c constraints.txt`. Uma linha; alinha dev e CI
   com a imagem de imediato.
2. Um passo no `runtime-gate` que compare `pip list` com `constraints.txt` e reprove na
   divergência — o alarme que hoje existe só para *cobertura*, estendido a *igualdade*.
3. Regenerar os pinos com `--write` só depois de `make test` verde no mesmo conjunto, que
   é a regra que o próprio script já manda seguir.

## Não é um alarme de CVE — e quase virou um

`pip-audit` no `.venv` acusa **75 vulnerabilidades conhecidas em 19 pacotes** (django,
cryptography, pillow, twisted, urllib3, sqlparse, DRF…). Reportar esse número teria sido
um erro grave, e é exatamente o erro que esta revisão crítica existe para pegar:

**a imagem de produção já está corrigida em todas elas.** Cada versão de
`constraints.txt` conferida contra a coluna *Fix Versions* do `pip-audit` está no fix ou
acima — Django 6.0.8 ≥ 6.0.8, DRF 3.18.0 ≥ 3.17.2, cryptography 50.0.1 ≥ 50.0.0,
daphne 4.2.3 ≥ 4.2.2, pillow 12.3.0 ≥ 12.3.0, urllib3 2.7.0 ≥ 2.7.0, Twisted 26.4.0 ≥
26.4.0, sqlparse 0.6.0 ≥ 0.6.0, idna 3.19 ≥ 3.15.

O achado real é **o inverso do susto**: as vulnerabilidades estão na máquina de quem
desenvolve, não na loja. E a razão de estarem lá é o mesmo drift do P1 acima.

> A lição vale registrar porque é a tese desta revisão: um número grande e assustador
> (*"75 CVEs"*) sem conferir a alcançabilidade é precisamente o defeito de que acusei os
> agentes. Estive a um passo de cometê-lo no meu próprio laudo.

## Ação para o dev, hoje

```
make install    # realinha o .venv; hoje ele está 40 pacotes atrás da imagem
```
