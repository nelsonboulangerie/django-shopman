"""Base de cidade velha vira ``OperatorAlert`` — porque velha ela erra CALADA.

A tela "Segurança e dados" da loja escreve "Próximo a Londrina, PR · Brasil" ao lado de
cada dispositivo confiável, lendo uma base GeoLite2-City de dentro da imagem (PR #991 e a
seguinte; ver ``shopman/shop/services/ip_location.py``). A base entra no build e **não se
atualiza sozinha**: só troca quando alguém bumpa o ``ARG GEOLITE2_SNAPSHOT`` do
``Dockerfile`` e refaz o deploy.

## Por que isto precisa de alerta, e não só de documentação

Porque esta é a única forma de erro que aquele módulo não sabia enxergar. Todo o resto
falha alto: base ausente não abre, base corrompida levanta exceção, raio de precisão ruim
é descartado. A base velha **abre, lê e responde** — e responde errado com exatamente a
mesma confiança de uma base correta. Um bloco de IP que mudou de operadora continua
nomeando a cidade antiga, com raio bom, passando por todos os filtros que existem. A tela
escreve a frase com a autoridade de sempre, e ninguém tem como desconfiar.

Já estava escrito no guia que a atualização não é automática. Documentação não é
mecanismo: quem lê o guia é quem já foi olhar. Este comando é o irmão de
``check_integration_drift`` — mesma forma (varredura no ciclo do ``maintenance_worker``,
resultado vira alerta com dedupe), aplicada ao frescor de um arquivo em vez da
configuração de um provedor.

## As duas faixas

Os limiares moram em ``config/settings.py``, com o raciocínio de cada número:

======================  ==========================  ============  =========
idade da base           o que acontece na tela      severidade    lembrete
======================  ==========================  ============  =========
< 21 dias               mostra a cidade             (sem alerta)  —
21 a 89 dias            mostra a cidade             ``warning``   7 dias
90 dias ou mais         **não mostra** a cidade     ``error``     24 horas
======================  ==========================  ============  =========

O lembrete semanal na primeira faixa não é escolha estética: a MaxMind republica a base
toda terça, então uma semana é exatamente o intervalo em que passou a existir algo novo a
fazer. Na segunda faixa a tela já perdeu a linha — isso é regressão visível para o
cliente, e lembrete semanal seria lento demais para uma regressão.

## O dedupe

A identidade é ``(data de construção da base, faixa)``. Bumpar a base muda a data e
recomeça a história, que é o que se quer: o alerta seguinte, se houver, é fato novo e não
eco do anterior. Trocar de faixa (21 → 90) também é fato novo, e sai na hora em vez de
esperar a janela da faixa antiga vencer. Como em ``check_integration_drift``, a busca usa
``active_only=False``: alerta já **reconhecido** também segura a janela — reconhecer é dar
ciência, não é bumpar a base.

## O que este comando deliberadamente NÃO faz

**Não alerta quando a base está ausente.** Ausência não é atraso: não há idade, não há o
que bumpar, e a tela já degrada sozinha para "navegador e data" — que é o estado previsto
em desenvolvimento, na CI e em qualquer imagem construída sem ``MAXMIND_LICENSE_KEY``
(chave que, em 23/09/2026, o dono ainda não criou). Alertar ali mandaria o operador atrás
de um problema que não existe, todo dia, até ele aprender a ignorar o tipo inteiro — e aí
o aviso que importa chegaria num canal já surdo. A ausência aparece no diagnóstico
(``scripts/diagnose_operational.py``), que é onde se pergunta, e que não empurra.

**Não entra no ``/ready/``.** Prontidão que reprova por causa de um rótulo de cidade
transforma um enfeite em bloqueio de deploy — a mesma troca que o ``fetch-geolite2.sh``
recusa quando sai com 0 sem a chave.

Uso:
    python manage.py check_geoip_freshness
    python manage.py check_geoip_freshness --dry-run
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

ALERT_TYPE = "geoip_database_stale"

#: Janela do lembrete enquanto a tela AINDA mostra a cidade. Uma semana = uma publicação
#: da MaxMind = uma oportunidade real de bumpar que passou.
STALE_WINDOW_HOURS = 24 * 7

#: Janela depois que a tela já perdeu a linha. Regressão visível pede cadência diária.
DARK_WINDOW_HOURS = 24

#: O gesto, escrito. Um alerta que diz "base desatualizada" e para por aí devolve ao
#: leitor o trabalho de descobrir o que fazer — e quem lê a tela de alertas é o gestor,
#: que não tem por que saber de cor o nome de um ARG de Dockerfile.
REMEDY = (
    "Para atualizar: bump do `ARG GEOLITE2_SNAPSHOT` no Dockerfile (a data da edição nova, "
    "ex. 2026-10) e novo deploy — é o bump que invalida a camada e rebaixa a base. Passo a "
    "passo em docs/guides/geolite2-city.md."
)


def grade(freshness) -> tuple[str, int, str]:
    """Devolve ``(severidade, janela em horas, faixa)`` para uma base velha.

    A faixa entra no dedupe, então o nome dela é contrato: mudar a palavra reabre uma vez
    todos os alertas em aberto. São só duas porque a decisão é binária — a tela mostra ou
    não mostra.
    """
    if freshness.too_old_to_show:
        return ("error", DARK_WINDOW_HOURS, "sem-cidade")
    return ("warning", STALE_WINDOW_HOURS, "envelhecendo")


def message(freshness) -> str:
    """Qual base, quanto tempo, o que isso causa na tela, e o que fazer."""
    if freshness.age_days is None:
        # Presente e sem data legível. `database_freshness` já tratou isso como velho e a
        # tela já calou; o alerta tem de dizer a verdade — que a idade é DESCONHECIDA — em
        # vez de inventar um número, senão manda o leitor conferir a data errada.
        head = (
            "A base de cidade dos dispositivos não informa a data em que foi construída "
            "(metadado ausente ou ilegível — provavelmente arquivo truncado no build)."
        )
        effect = (
            "Sem a data não há como saber se ela ainda serve, então a cidade deixou de "
            "aparecer na tela de segurança da loja: a linha ficou só com navegador e data."
        )
        return f"{head} {effect} {REMEDY}"

    built = freshness.built_at
    quando = f" (construída em {built:%d/%m/%Y})" if built else ""
    head = f"A base de cidade dos dispositivos está com {freshness.age_days} dias{quando}."
    if freshness.too_old_to_show:
        effect = (
            "Passou do limite e a cidade DEIXOU DE APARECER na tela de segurança da loja: "
            "a linha ficou só com navegador e data. Isso é proposital — depois desse tempo "
            "um bloco de IP pode ter mudado de operadora, e a base antiga nomearia a cidade "
            "errada com a mesma confiança de uma certa."
        )
    else:
        effect = (
            "A cidade continua aparecendo, mas a base já perdeu publicações: a MaxMind "
            "republica toda terça. Quanto mais velha, maior a chance de nomear a cidade do "
            "dono anterior de um bloco de IP — e esse erro não aparece em lugar nenhum, "
            "porque a tela mostra a cidade errada com a confiança de sempre."
        )
    return f"{head} {effect} {REMEDY}"


class Command(BaseCommand):
    help = "Alerta o operador quando a base de cidade dos dispositivos está velha."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Só reporta, não alerta.")

    def handle(self, *args, **options):
        from shopman.shop.services.ip_location import database_freshness
        from shopman.shop.services.observability import operational_event

        freshness = database_freshness()

        if not freshness.present:
            # Ver "O que este comando deliberadamente NÃO faz", no topo.
            self.stdout.write("geoip_freshness: sem base — nada a alertar (degradação prevista).")
            operational_event("geoip_freshness.checked", present=False)
            return

        self.stdout.write(
            "geoip_freshness: "
            f"idade={freshness.age_days if freshness.age_days is not None else 'desconhecida'} "
            f"construida={freshness.built_at.date().isoformat() if freshness.built_at else '-'} "
            f"stale={freshness.stale} sem_cidade={freshness.too_old_to_show}"
        )
        operational_event(
            "geoip_freshness.checked",
            present=True,
            age_days=freshness.age_days,
            stale=freshness.stale,
            too_old_to_show=freshness.too_old_to_show,
        )

        if not freshness.stale or options["dry_run"]:
            return

        self._alert(freshness)

    def _alert(self, freshness) -> None:
        from shopman.shop.adapters import alert as alert_adapter
        from shopman.shop.services.observability import create_operator_alert

        severity, window_hours, band = grade(freshness)
        built = freshness.built_at.date().isoformat() if freshness.built_at else "desconhecida"
        # ⚠️ O fecho `:fim` é a mesma lição do `certificate_expiring`: a busca do dedupe é
        # por SUBSTRING, e sem ele uma chave contida na outra silenciaria a segunda.
        dedupe_key = f"{ALERT_TYPE}:{built}:{band}:fim"

        cutoff = timezone.now() - timedelta(hours=window_hours)
        if alert_adapter.recent_exists(
            ALERT_TYPE, cutoff, message_contains=dedupe_key, active_only=False
        ):
            logger.info(
                "geoip_freshness: base de %s já avisada nesta janela (%s) — sem novo alerta.",
                built,
                dedupe_key,
            )
            return

        create_operator_alert(
            type=ALERT_TYPE,
            severity=severity,
            message=message(freshness),
            dedupe_key=dedupe_key,
            debounce_minutes=window_hours * 60,
            built_on=built,
            age_days=freshness.age_days,
            band=band,
        )
