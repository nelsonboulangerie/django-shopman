"""Uma pergunta só: **esta instância é a loja de verdade?**

Antes deste módulo, `SHOPMAN_ENVIRONMENT` era lida com três vocabulários
diferentes, e eles discordavam justamente onde o estrago é irreversível:

- os checks de deploy e o piloto automático perguntavam
  ``not in {development, dev, local, staging}`` — desconhecido vira produção,
  falha FECHADO;
- a prontidão de integrações perguntava
  ``in {producao, produção, production, prod, live}``;
- e os quatro comandos destrutivos (``seed --flush``, ``import_backup
  --apply``, ``qa_scenarios``, ``refresh_seed_dates``) perguntavam
  ``== "production"`` — igualdade exata, desconhecido vira NÃO-produção, falha
  ABERTO.

Escrever ``prod`` no lugar de ``production`` fazia as duas primeiras famílias
tratarem a instância como produção e a terceira não. Resultado concreto:
``seed --flush`` apagaria a loja inteira sem sequer exigir ``--force``, calado.
É o inverso da regra da casa — onde o dano não tem volta, a omissão tem de ser
restritiva.

## A regra

``is_production()`` é o complemento exato de :data:`NON_PRODUCTION_ENVIRONMENTS`:
**só os quatro nomes reconhecidos de ambiente não-produtivo abrem a porta.**
Qualquer outra coisa — ``prod``, ``producao``, ``live``, um valor digitado
errado, uma variável vazia — é tratada como produção.

Isso é deliberadamente assimétrico. Errar para o lado de "é produção" custa um
comando recusado e uma mensagem que diz qual variável arrumar. Errar para o
outro lado custa a loja.

## O que NÃO mora aqui

O vocabulário do **terceiro**. ``SHOPMAN_FOCUS_NFE["environment"]`` vale
``producao``/``homologacao`` porque é assim que a Focus chama, e
``shopman/backstage/services/integration_readiness.py`` mantém o próprio
conjunto para ler esse rótulo. São perguntas diferentes: "em que ambiente EU
estou" e "o que o provedor diz que ELE é".
"""

from __future__ import annotations

from django.conf import settings

#: Os únicos valores que declaram uma instância não-produtiva. A lista é
#: fechada de propósito: sinônimo novo aqui é porta nova para `seed --flush`.
NON_PRODUCTION_ENVIRONMENTS = frozenset({"development", "dev", "local", "staging"})

#: Grafias que declaram produção de forma explícita. Não são usadas para
#: DECIDIR (quem decide é o complemento acima, que já cobre estas) — servem
#: para o check distinguir "escreveu produção com outro nome", que é aceitável,
#: de "escreveu qualquer outra coisa", que merece aviso. Ver SHOPMAN_W017.
PRODUCTION_ENVIRONMENTS = frozenset(
    {"production", "producao", "produção", "prod", "live"}
)


def environment_name() -> str:
    """O valor de ``SHOPMAN_ENVIRONMENT`` normalizado (sem espaços, minúsculo).

    O default é ``production`` porque a ausência da variável não pode ser um
    convite: instância que não se declarou é instância que se trata como a de
    verdade.
    """
    return str(getattr(settings, "SHOPMAN_ENVIRONMENT", "production")).strip().lower()


def is_production() -> bool:
    """``True`` quando esta instância deve ser tratada como a loja de verdade.

    Complemento exato de :data:`NON_PRODUCTION_ENVIRONMENTS` — ver o porquê da
    assimetria no topo do módulo.
    """
    return environment_name() not in NON_PRODUCTION_ENVIRONMENTS


def is_recognized_environment() -> bool:
    """``False`` para um valor que não é nenhum dos nomes conhecidos.

    Não muda decisão nenhuma: um valor irreconhecível já é tratado como
    produção por :func:`is_production`. Serve para o boot poder AVISAR, porque
    falhar fechado em silêncio esconde o dedo escorregado que causou o silêncio.
    """
    name = environment_name()
    return name in NON_PRODUCTION_ENVIRONMENTS or name in PRODUCTION_ENVIRONMENTS
