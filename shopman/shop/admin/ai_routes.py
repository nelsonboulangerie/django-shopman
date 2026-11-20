"""As rotas de IA da loja na página Integrações: uma lista por função, sem JSON (#2843).

``Shop.ai_routes`` continua sendo a fonte (``shopman.shop.ai`` lê dali): esta página só
troca o campo JSON por duas listas por função, a conexão e o modelo, e mostra ao lado se a
função está pronta, com o motivo que ``ai.explain`` daria. Rota que aponta para conexão
inativa, sem chave ou não liberada vira aviso no topo, com o botão que resolve.

Também mora aqui o histórico da decisão em sombra (``Shop.conversational_shadow_enabled``,
#2842): quem ligou e quem desligou, pelo registro do próprio Admin (``LogEntry``).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from django import forms
from django.urls import reverse
from django.utils.html import format_html
from shopman.utils import unfold_component
from unfold.widgets import UnfoldAdminSelectWidget

from shopman.shop import ai
from shopman.shop.services.ai_pricing import LLM_PRICES

#: A rota que vale para a função sem rota própria (nunca para o Jev, de outro formato).
DEFAULT_ROUTE = "default"
ROUTE_KEYS = (DEFAULT_ROUTE, *ai.PURPOSES)

ROUTE_LABELS = {DEFAULT_ROUTE: "Padrão: as funções sem rota própria", **ai.PURPOSES}

#: O host de cada fornecedor da tabela de preços: modelo de um não roda na conexão do outro.
VENDOR_HOSTS = {"claude-": "api.anthropic.com", "deepseek-": "api.deepseek.com"}

SHADOW_ON = "Ligou a decisão em sombra"
SHADOW_OFF = "Desligou a decisão em sombra"


def connection_field(key: str) -> str:
    return f"ai_route_{key}_connection"


def model_field(key: str) -> str:
    return f"ai_route_{key}_model"



def _protocol(key: str) -> str:
    from shopman.shop.models import AIProtocol

    return AIProtocol.JEV if key == "decision" else AIProtocol.ANTHROPIC


def form_fields() -> dict[str, forms.Field]:
    """Os campos da página. As opções dependem das conexões e entram no ``__init__``."""
    fields: dict[str, forms.Field] = {}
    for key in ROUTE_KEYS:
        fields[connection_field(key)] = forms.ChoiceField(
            label=ROUTE_LABELS[key],
            required=False,
            choices=(),
            widget=UnfoldAdminSelectWidget,
        )
        fields[model_field(key)] = forms.ChoiceField(
            label="Modelo",
            required=False,
            choices=(),
            widget=UnfoldAdminSelectWidget,
        )
    return fields


def _routes_of(instance) -> dict:
    routes = getattr(instance, "ai_routes", None)
    return routes if isinstance(routes, dict) else {}


def _connection_label(connection, key: str) -> str:
    notes = []
    if not connection.api_key_last4:
        notes.append("sem chave")
    if key in ai.CUSTOMER_TEXT_PURPOSES and not connection.customer_text_approved:
        notes.append("não liberada para mensagem de cliente")
    suffix = f" ({', '.join(notes)})" if notes else ""
    return f"{connection.name} · {connection.ref}{suffix}"


def _empty_connection_label(key: str) -> str:
    if key == DEFAULT_ROUTE:
        return "Sem rota padrão: a única conexão ativa"
    if key == "decision":
        return "Sem rota própria: a única conexão Jev ativa"
    return "Sem rota própria: a rota padrão"


def connection_choices(key: str, current: str) -> list[tuple[str, str]]:
    """Só conexão ativa do formato da função; a gravada que saiu da lista fica, marcada."""
    from shopman.shop.models import AIConnection

    active = AIConnection.objects.filter(is_active=True, protocol=_protocol(key)).order_by("name", "ref")
    choices = [("", _empty_connection_label(key))]
    choices += [(connection.ref, _connection_label(connection, key)) for connection in active]
    if current and current not in {ref for ref, _label in choices}:
        choices.append((current, f"{current} (inativa, apagada ou de outro formato)"))
    return choices


def model_choices(key: str, current: str) -> list[tuple[str, str]]:
    """Os modelos com preço conhecido e os das conexões ativas do formato."""
    from shopman.shop.models import AIConnection

    protocol = _protocol(key)
    known = [] if key == "decision" else list(LLM_PRICES)
    known += [
        model
        for model in AIConnection.objects.filter(is_active=True, protocol=protocol)
        .exclude(model="")
        .order_by("model")
        .values_list("model", flat=True)
        .distinct()
        if model not in known
    ]
    if current and current not in known:
        known.append(current)
    return [("", "O modelo da conexão"), *((model, model) for model in known)]


def set_initial(form) -> None:
    """Preenche opções e valores gravados. Página sem estes campos não é tocada."""
    if connection_field(DEFAULT_ROUTE) not in form.fields:
        return
    routes = _routes_of(form.instance)
    for key in ROUTE_KEYS:
        route = routes.get(key) if isinstance(routes.get(key), dict) else {}
        connection = str(route.get("connection") or "")
        model = str(route.get("model") or "")
        form.fields[connection_field(key)].choices = connection_choices(key, connection)
        form.fields[connection_field(key)].initial = connection
        form.fields[model_field(key)].choices = model_choices(key, model)
        form.fields[model_field(key)].initial = model
        # A situação da função, embaixo da lista dela (o Unfold mostra o texto de ajuda com ``safe``).
        form.fields[connection_field(key)].help_text = status_html(key)


def _vendor_host(model: str) -> str:
    for prefix, host in VENDOR_HOSTS.items():
        if model.startswith(prefix) and model in LLM_PRICES:
            return host
    return ""


def _connection_host(connection) -> str:
    return (urlparse((connection.base_url or "").strip()).hostname or "api.anthropic.com").lower()


def clean(form, cleaned_data: dict) -> None:
    """Modelo sem conexão não tem efeito; modelo de um fornecedor não roda na conexão de outro."""
    from shopman.shop.models import AIConnection

    if connection_field(DEFAULT_ROUTE) not in form.fields:
        return
    for key in ROUTE_KEYS:
        ref = cleaned_data.get(connection_field(key)) or ""
        model = cleaned_data.get(model_field(key)) or ""
        if model and not ref:
            form.add_error(
                model_field(key),
                "Escolha a conexão desta função antes do modelo. Sem conexão própria, a função "
                "usa a rota padrão inteira, com o modelo dela.",
            )
            continue
        if not (ref and model):
            continue
        connection = AIConnection.objects.filter(ref=ref).first()
        vendor = _vendor_host(model)
        host = _connection_host(connection) if connection is not None else ""
        # Só os dois fornecedores conhecidos: endereço fora da tabela pode servir qualquer modelo.
        if vendor and host in VENDOR_HOSTS.values() and host != vendor:
            form.add_error(
                model_field(key),
                f"O modelo {model} não roda na conexão {connection.name} ({host}). "
                "Escolha um modelo dessa conexão, ou outra conexão.",
            )


def build(form) -> dict:
    """``Shop.ai_routes`` a partir das listas. Chaves que a página não conhece ficam como estão."""
    routes = {
        key: (dict(value) if isinstance(value, dict) else value) for key, value in _routes_of(form.instance).items()
    }
    if connection_field(DEFAULT_ROUTE) not in form.fields:
        return routes
    for key in ROUTE_KEYS:
        ref = form.cleaned_data.get(connection_field(key)) or ""
        model = form.cleaned_data.get(model_field(key)) or ""
        if not ref:
            routes.pop(key, None)
            continue
        route = routes.get(key) if isinstance(routes.get(key), dict) else {}
        route["connection"] = ref
        if model:
            route["model"] = model
        else:
            route.pop("model", None)
        routes[key] = route
    return routes


# ── Prontidão ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Readiness:
    key: str
    ready: bool
    text: str
    fix_label: str = ""
    fix_url: str = ""


def _fix_for(purpose: str) -> tuple[str, str]:
    """O botão que resolve o motivo: a conexão a acertar, ou o campo desta página."""
    from shopman.shop.models import AIConnection

    route = _routes_of(_shop()).get(purpose) or _routes_of(_shop()).get(DEFAULT_ROUTE) or {}
    ref = str(route.get("connection") or "") if isinstance(route, dict) else ""
    connection = AIConnection.objects.filter(ref=ref).first() if ref else None
    if connection is None and not ref:
        candidates = list(AIConnection.objects.filter(is_active=True, protocol=_protocol(purpose))[:2])
        connection = candidates[0] if len(candidates) == 1 else None
        if len(candidates) > 1:
            return "Escolher a conexão", f"#id_{connection_field(purpose)}"
    if connection is not None:
        return f"Abrir a conexão {connection.name}", reverse("admin:shop_aiconnection_change", args=[connection.pk])
    return "Cadastrar uma conexão de IA", reverse("admin:shop_aiconnection_add")


def _shop():
    from shopman.shop.models import Shop

    return Shop.load()


def readiness(purpose: str) -> Readiness:
    """Pronta, com a conexão e o modelo que vão de fato; ou o motivo de ``ai.explain``."""
    from shopman.shop.ai_governor import AIBudgetExceeded, AIDisabled

    try:
        resolved = ai.resolve(purpose)
    except (AIDisabled, AIBudgetExceeded) as stopped:
        return Readiness(purpose, False, str(stopped), "Ajustar o freio de IA", "#id_ai_limits")
    except ai.AINotConfigured as reason:
        label, url = _fix_for(purpose)
        # O motivo é o de ``ai.explain``, sem a chave interna da função: a tela já diz qual é.
        text = str(reason).replace(f"a rota de IA '{purpose}' aponta", "a rota aponta")
        return Readiness(purpose, False, text, label, url)
    from shopman.shop.models import AIConnection

    name = AIConnection.objects.filter(ref=resolved.ref).values_list("name", flat=True).first() or resolved.ref
    return Readiness(purpose, True, f"Pronta: {name} · {resolved.model}")


def status_html(purpose: str) -> str:
    if purpose == DEFAULT_ROUTE:
        return format_html(
            '<span class="text-base-500 dark:text-base-400">{}</span>',
            "Vale para cada função com “Sem rota própria”. A situação de cada uma aparece embaixo dela.",
        )
    state = readiness(purpose)
    if state.ready:
        return format_html('<span class="font-medium text-green-700 dark:text-green-400">{}</span>', state.text)
    button = unfold_component(
        "unfold/components/button.html",
        href=state.fix_url,
        variant="default",
        size="sm",
        children=format_html("{}", state.fix_label),
    )
    return format_html(
        '<span class="flex flex-col gap-2 items-start">'
        '<span class="font-medium text-red-700 dark:text-red-400">Parada: {}.</span>{}</span>',
        state.text,
        button,
    )


def warnings() -> list[dict]:
    """Um aviso por motivo, com as funções que ele para e o botão que resolve.

    Só funções com rota gravada (a dela ou a padrão): função que nunca foi ligada não é
    defeito, e a linha dela já diz que está parada.
    """
    routes = _routes_of(_shop())
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for purpose in ai.PURPOSES:
        has_route = isinstance(routes.get(purpose), dict) or (
            purpose != "decision" and isinstance(routes.get(DEFAULT_ROUTE), dict)
        )
        if not has_route:
            continue
        state = readiness(purpose)
        if state.ready:
            continue
        grouped.setdefault((state.text, state.fix_label, state.fix_url), []).append(ai.PURPOSES[purpose].split(":")[0])
    return [
        {
            "functions": ", ".join(functions),
            "reason": reason,
            "message": format_html(
                # Texto à esquerda, botão à direita (empilha no celular): o mesmo lugar em todo aviso.
                '<span class="flex flex-col gap-2 items-start lg:flex-row lg:items-center">'
                '<span class="grow">A IA está parada em {}: {}.</span><span class="shrink-0">{}</span></span>',
                ", ".join(functions),
                reason,
                unfold_component(
                    "unfold/components/button.html",
                    href=url,
                    variant="default",
                    size="sm",
                    children=format_html("{}", label),
                ),
            ),
        }
        for (reason, label, url), functions in grouped.items()
    ]


# ── A decisão em sombra: quem ligou ─────────────────────────────────────────


def record_shadow_change(request, obj, enabled: bool) -> None:
    from django.contrib.admin.models import CHANGE, LogEntry

    LogEntry.objects.log_actions(
        request.user.pk,
        [obj],
        CHANGE,
        change_message=SHADOW_ON if enabled else SHADOW_OFF,
        single_object=True,
    )


def shadow_history(obj, limit: int = 10) -> list[tuple[str, str, str]]:
    """``(quando, quem, o quê)`` das últimas mudanças da decisão em sombra pelo Admin."""
    from django.contrib.admin.models import LogEntry
    from django.utils import timezone
    from shopman.utils.formatting import format_local

    entries = (
        LogEntry.objects.filter(
            object_id=str(obj.pk), content_type__app_label="shop", change_message__in=(SHADOW_ON, SHADOW_OFF)
        )
        .select_related("user")
        .order_by("-action_time")[:limit]
    )
    return [
        (
            format_local(timezone.localtime(entry.action_time), "%d/%m/%Y {clock}"),
            entry.user.get_full_name() or entry.user.get_username(),
            entry.change_message,
        )
        for entry in entries
    ]
