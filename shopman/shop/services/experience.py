"""Qual versão de uma superfície esta requisição vê (R4 do WP-RELEASE-01).

Quem decide é o servidor, pela coorte configurada no Admin (decisão D1 do dono,
23/11/2026). Nenhum parâmetro de URL, cabeçalho, cookie ou campo da requisição
escolhe a versão: o único insumo é QUEM está na sessão e o que a ``RuleConfig`` do
experimento diz (``shopman.shop.rules.experience.ExperienceRule``).

Precedência (WP-RELEASE-01 D5), por experimento ativo da superfície:

1. **kill switch**: regra desligada (``RuleConfig.enabled = False``) não aparece entre
   as regras ativas, e o experimento some da resposta. Ausente quer dizer padrão.
2. **prazo**: ``remove_after`` vencido resolve o padrão; o aviso ao operador sai do
   ``maintenance_worker`` (:func:`alert_expired_experiments`), não do GET.
3. **ambiente**: ``environments`` listado e o ambiente desta instância fora dele.
4. **loja**: por construção. A ``RuleConfig`` mora no banco da loja (um schema por
   loja, ADR-042), então o experimento de uma loja não existe para a outra.
5. **aderência**: a versão que esta sessão já recebeu, na mesma ``generation``.
   Recarregar a página não alterna a versão (D5).
6. **allow-list de coorte**: ``internal`` e ``pilot`` veem a versão candidata.
7. **percentual por identidade**: FORA (D2: nenhum cliente nas coortes por ora; a
   regra recusa alocação diferente de zero).
8. **padrão**.

Aderência: ``request.session["shopman_experience"] = {ref: {variant, generation}}``,
gravada no LOGIN do cliente (``user_logged_in``, que é comando), nunca no GET: a
camada de leitura não grava nada, nem a sessão (``test_read_side_never_writes``).
Nenhum cookie novo: a sessão de servidor já
existe e já é cookie necessário (a política de privacidade não muda). O anônimo
resolve sempre o padrão (D2) e não ganha sessão por isso, e é o que mantém a gêmea
pública de ``storefront/api/public_cache.py`` limpa.

Para cliente identificado a coorte é do ``customer_ref``, então o mesmo cliente vê a
mesma versão em qualquer dispositivo. ``generation`` incrementada descarta a
aderência gravada e reatribui pela configuração do momento.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shopman.shop.policies.experience import (
    EXPERIENCE_RULE_PATH,
    ExperienceRule,
    ExperienceRuleError,
    parse_remove_after,
)

logger = logging.getLogger(__name__)

#: Chave em ``request.session`` (sessão de servidor do Django, não ``Session.data``).
SESSION_KEY = "shopman_experience"

#: Por que a requisição recebeu a versão que recebeu. Vai ao log, não à resposta.
REASON_EXPIRED = "expired"
REASON_ENVIRONMENT = "environment"
REASON_SESSION = "session"
REASON_INTERNAL = "cohort:internal"
REASON_PILOT = "cohort:pilot"
REASON_DEFAULT = "default"


@dataclass(frozen=True)
class Assignment:
    """A versão que uma requisição vê de um experimento."""

    ref: str
    variant: str
    default: str
    generation: int
    reason: str

    @property
    def is_default(self) -> bool:
        return self.variant == self.default

    def exposure(self) -> dict:
        """O que a superfície recebe: só ``ref`` e ``variant``, nunca coorte nem motivo."""
        return {"ref": self.ref, "variant": self.variant}


def operator_customer_refs() -> frozenset[str]:
    """Os ``customer_ref`` da loja que pertencem a operadores cadastrados e ativos.

    É a coorte ``internal`` DERIVADA do cadastro de operadores (decisão D2): operador
    novo entra sozinho, desligado sai sozinho. Esta é a única função que liga
    operador a cliente; trocar a ligação é trocar o corpo dela.

    Hoje não existe ligação, e por isso devolve vazio (investigado no OC-20):

    - o operador é um ``User`` do Django com ``is_staff``, grupos e PIN/passkey, sem
      telefone (``backstage/services/operator.py:eligible_operators``,
      ``setup_operators``);
    - o cliente entra na loja pelo telefone e vira OUTRO ``User`` (``customer_<uuid>``),
      ligado ao Guestman por ``CustomerUser`` (``doorman/services/_user_bridge.py``);
    - a sessão do operador é fisicamente separada da sessão da loja
      (``OperatorSessionDomainMiddleware``), então a loja nunca vê o ``User`` do
      operador.

    Até o dono escolher a ligação, a coorte interna é a lista explícita por
    ``customer_ref`` em ``params["cohorts"]["internal"]``.
    """
    return frozenset()


def resolve(request, surface: str) -> tuple[Assignment, ...]:
    """As versões que esta requisição vê, uma por experimento ativo de ``surface``.

    Ordenadas por ``ref``. Experimento desligado não aparece (ausente = padrão).
    Só LÊ: a aderência é gravada no login (:func:`on_user_logged_in`), nunca num GET
    (trava ``test_read_side_never_writes``). Nunca levanta: configuração ilegível
    vira log e o experimento fica de fora.
    """
    rules = _active_experiments(surface)
    if not rules:
        return ()

    customer_ref = _customer_ref(request)
    stored = _stored(request)
    cohort_of = _cohort_lookup()
    assignments: list[Assignment] = []
    for _rule_config, params in rules:
        variant, reason = _decide(params, customer_ref, stored.get(params["ref"]), cohort_of)
        assignments.append(Assignment(
            ref=params["ref"],
            variant=variant,
            default=params["default"],
            generation=int(params.get("generation", 1)),
            reason=reason,
        ))
    return tuple(sorted(assignments, key=lambda a: a.ref))


def remember(request, customer_ref: str) -> None:
    """Grava na sessão a versão de cada experimento ativo para este cliente.

    É a aderência: a sessão guarda a versão com que nasceu identificada, e uma
    mudança de coorte no meio dela não alterna a tela. Chamado no login, que é
    comando; ``generation`` incrementada torna o registro velho inválido.
    """
    rules = _active_experiments(None)
    if not rules or not customer_ref:
        return
    stored = _stored(request)
    cohort_of = _cohort_lookup()
    updates: dict[str, dict] = {}
    for _rule_config, params in rules:
        variant, reason = _decide(params, customer_ref, stored.get(params["ref"]), cohort_of)
        if reason in (REASON_EXPIRED, REASON_ENVIRONMENT):
            continue
        updates[params["ref"]] = {"variant": variant, "generation": int(params.get("generation", 1))}
    _store(request, stored, updates)


def alert_expired_experiments() -> int:
    """Avisa o operador de cada experimento ligado com o prazo vencido. Devolve quantos.

    Roda no ``maintenance_worker`` (comando ``alert_expired_experiments``), nunca no
    GET: o GET só resolve o padrão para o vencido, e a leitura não grava. O
    ``create_operator_alert`` segura a repetição (um aviso por experimento a cada 24 h).
    """
    expired = 0
    for rule_config, params in _active_experiments(None):
        if _expired(params):
            expired += 1
            _alert_expired(rule_config, params)
    return expired


def on_user_logged_in(sender, request=None, user=None, **kwargs) -> None:
    """``user_logged_in``: a sessão que ganhou um cliente ganha a aderência dele.

    Toda porta de cliente (código, link, WhatsApp, chave de acesso, dispositivo
    reconhecido) termina no ``login()``. O ``request.customer`` do middleware ainda é
    o do anônimo neste ponto: o cliente vem do ``user`` que acabou de entrar. Equipe
    (``is_staff``, sessão do operador) sai sem consulta.
    """
    if request is None or user is None or getattr(user, "is_staff", False):
        return
    from django.core.exceptions import ObjectDoesNotExist

    try:
        customer_id = user.doorman_customer_user.customer_id
    except ObjectDoesNotExist:
        return
    try:
        remember(request, _ref_of(customer_id) or "")
    except Exception:  # silêncio-deliberado: experimento nunca impede a pessoa de entrar; sem aderência, resolve pela coorte
        logger.warning("experience.remember_failed", exc_info=True)


def _decide(params: dict, customer_ref: str | None, record, cohort_of) -> tuple[str, str]:
    """``(variante, motivo)`` de um experimento, na precedência do D5."""
    default = params["default"]
    generation = int(params.get("generation", 1))
    variants = list(params["variants"])
    if _expired(params):
        return default, REASON_EXPIRED
    if not _environment_allows(params):
        return default, REASON_ENVIRONMENT
    if not customer_ref:
        # D2: nenhum cliente anônimo nas coortes.
        return default, REASON_DEFAULT
    if (
        isinstance(record, dict)
        and record.get("generation") == generation
        and record.get("variant") in variants
    ):
        return record["variant"], REASON_SESSION
    candidate = next(v for v in variants if v != default)
    cohorts = params.get("cohorts") or {}
    if customer_ref in cohort_of() or customer_ref in (cohorts.get("internal") or ()):
        return candidate, REASON_INTERNAL
    if customer_ref in (cohorts.get("pilot") or ()):
        return candidate, REASON_PILOT
    return default, REASON_DEFAULT


def _cohort_lookup():
    """A coorte derivada dos operadores, lida no máximo uma vez por requisição."""
    cached: list[frozenset[str]] = []

    def internal() -> frozenset[str]:
        if not cached:
            cached.append(operator_customer_refs())
        return cached[0]

    return internal


def exposure(assignments) -> list[dict]:
    """``[{ref, variant}]`` para a resposta da superfície."""
    return [a.exposure() for a in assignments]


def has_non_default(assignments) -> bool:
    """Alguma versão fora do padrão? Então a resposta é de alguém, e é privada (X14)."""
    return any(not a.is_default for a in assignments)


# ── leitura ───────────────────────────────────────────────────────────────


def _active_experiments(surface: str | None) -> list[tuple[object, dict]]:
    """``[(RuleConfig, params)]`` dos experimentos ligados (de ``surface``, ou todos), por prioridade."""
    from shopman.shop.rules.engine import get_active_rules

    try:
        active = get_active_rules()
    except Exception:  # silêncio-deliberado: sem regras legíveis, todo mundo no padrão
        logger.warning("experience.rules_unavailable", exc_info=True)
        return []

    found: list[tuple[object, dict]] = []
    seen: set[str] = set()
    for rule_config in active:
        if rule_config.rule_path != EXPERIENCE_RULE_PATH:
            continue
        params = rule_config.params or {}
        if surface is not None and params.get("surface") != surface:
            continue
        try:
            ExperienceRule.validate_params(params)
        except ExperienceRuleError as exc:
            # A linha passou por fora do ``clean`` (SQL cru, fixture). O experimento
            # fica de fora, que é o padrão para todos, e o motivo vai ao log.
            logger.warning(
                "experience.invalid_rule",
                extra={"rule_ref": rule_config.ref, "error": str(exc)},
            )
            continue
        if params["ref"] in seen:
            logger.warning(
                "experience.duplicate_ref",
                extra={"rule_ref": rule_config.ref, "experience_ref": params["ref"]},
            )
            continue
        seen.add(params["ref"])
        found.append((rule_config, params))
    return found


def _customer_ref(request) -> str | None:
    """O ``customer_ref`` do cliente identificado na sessão da loja, ou ``None``."""
    info = getattr(request, "customer", None)
    if info is None:
        return None
    return _ref_of(info.subject_id)


def _ref_of(customer_uuid) -> str | None:
    try:
        from shopman.shop.services.auth import customer_by_uuid

        customer = customer_by_uuid(customer_uuid)
    except Exception:  # silêncio-deliberado: sem cliente legível, a requisição é anônima (padrão)
        logger.warning("experience.customer_unavailable", exc_info=True)
        return None
    return (getattr(customer, "ref", "") or "").strip() or None


def _stored(request) -> dict:
    session = getattr(request, "session", None)
    if session is None:
        return {}
    try:
        value = session.get(SESSION_KEY)
    except Exception:  # silêncio-deliberado: sessão ilegível é sessão sem aderência
        logger.debug("experience.session_unreadable", exc_info=True)
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _store(request, stored: dict, updates: dict[str, dict]) -> None:
    """Grava a aderência só quando muda."""
    merged = {**stored, **updates}
    if merged == stored:
        return
    session = getattr(request, "session", None)
    if session is None:
        return
    try:
        session[SESSION_KEY] = merged
    except Exception:  # silêncio-deliberado: sem sessão gravável, cada requisição resolve pela coorte
        logger.debug("experience.session_unwritable", exc_info=True)


def _expired(params: dict) -> bool:
    from django.utils import timezone

    return parse_remove_after(params["remove_after"]) < timezone.localdate()


def _environment_allows(params: dict) -> bool:
    environments = params.get("environments")
    if not environments:
        return True
    from shopman.shop.environment import environment_name

    return environment_name() in {str(e).strip().lower() for e in environments}


def _alert_expired(rule_config, params: dict) -> None:
    """Um aviso por experimento vencido, com debounce de 24 h."""
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type="integration_config_drift",
        severity="warning",
        message=(
            f"O experimento '{params['ref']}' da loja venceu em {params['remove_after']}. "
            f"Todos voltaram para a versão padrão '{params['default']}'. "
            f"Apague do código a versão que não ficou e desligue a regra '{rule_config.ref}'."
        ),
        dedupe_key=f"experience_expired:{params['ref']}",
        debounce_minutes=24 * 60,
        experience_ref=params["ref"],
        rule_ref=rule_config.ref,
    )
