"""Dump, diff e apply dos descritores versionados de Instância.

Três regras, uma por achado do laudo de 18/10/2026 (WP-6):

- **A loja é uma só.** O apply cria a ``Shop`` quando não há nenhuma e recusa,
  gritando, quando há mais de uma (``the_shop``). O ``seed`` atualiza a loja que
  o apply criou, nunca uma ``pk`` fixa.
- **Configuração declarada × estado operacional.** O descritor manda na
  configuração; o operador manda no estado operacional (``OPERATIONAL_STATE``:
  canal ligado/desligado, registro do último gesto no liga/desliga, SKUs pausados
  num canal de exibição). O apply nunca toca no estado operacional e o dump nunca o
  exporta. Na configuração, o apply compara três vias: o declarado agora, o banco
  e a última versão aplicada (``InstanceApplyRecord``). Valor que o banco tem
  diferente da última versão aplicada foi mudado por fora; o apply não o
  sobrescreve sem ordem explícita (``on_drift``). Todo apply relata o diff e
  grava a trilha (quem, quando, o quê).
- **O dump é allowlist.** Sai do banco só chave que um contrato tipado declara:
  os campos do dataclass ``ChannelConfig``, os parâmetros que a classe da regra
  aceita, as chaves conhecidas da configuração de tarefa. Chave desconhecida
  recusa o dump inteiro, dizendo onde, sem mostrar o valor. A denylist de nomes e
  padrões de valor fica como segunda camada.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import inspect
import json
import re
from pathlib import Path

from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.utils.text import slugify

SECTIONS = ("channels", "rule_configs", "rbac_personas", "templates")
UNOWNED_SECTIONS = ("pipelines", "pricing_policies", "units", "fiscal_profiles")

# Segunda camada (defesa em profundidade): nomes e valores com cara de segredo.
# A primeira camada é a allowlist; isto pega o que um contrato tipado deixasse
# passar por engano.
SECRET_KEY_RE = re.compile(
    r"(?:secret|password|passwd|senha|token|credential|api[_-]?key|private[_-]?key"
    r"|pix|chave|hmac|signing|signature|authorization|bearer|certificad|certificate"
    r"|webhook|cookie|session[_-]?key|otp|pin[_-]?code)",
    re.I,
)
SECRET_VALUE_RES = (
    re.compile(r"-----BEGIN [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bwhsec_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"\b(?:postgres(?:ql)?|redis|amqp|mysql)://[^\s/@:]+:[^\s/@]+@", re.I),
)

# Estado operacional: o operador manda. Caminho relativo ao item da seção.
# O apply preserva o que o banco tem; o dump e o diff não o enxergam.
OPERATIONAL_STATE: dict[str, tuple[tuple[str, ...], ...]] = {
    "channels": (
        # Ligar/desligar o canal é gesto do operador (``services/channel_switch``).
        # O ``enabled`` do descritor vale só para o canal que NASCE.
        ("enabled",),
        # O registro do último gesto (quem, quando, por quê, até quando).
        ("config", "overrides", "activation"),
        # Exceção por SKU num canal de exibição (pausa local, ``services/feeds``).
        ("config", "overrides", "display", "paused_skus"),
        ("config", "overrides", "display", "hidden_skus"),
    ),
}

DRIFT_POLICIES = ("refuse", "keep", "overwrite")

# Chaves conhecidas de ``OperationTaskTemplate.config``. Hoje só o marcador de
# origem que o seed grava; chave nova entra aqui antes de entrar no descritor.
TASK_CONFIG_KEYS = frozenset({"seed"})

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class UnsafeDescriptor(ValueError):
    """The projection contains material that must never be emitted."""


class UnsupportedInstanceSection(ValueError):
    """A descriptor asks to mutate configuration without a proven DB owner."""


class ShopSingletonViolation(ValueError):
    """There is more than one ``Shop``: the singleton is broken."""


class InstanceDriftConflict(ValueError):
    """The database diverged from the last applied version and the policy refuses."""

    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        paths = ", ".join(change["path"] for change in conflicts[:10])
        more = f" (+{len(conflicts) - 10})" if len(conflicts) > 10 else ""
        super().__init__(
            f"{len(conflicts)} valor(es) do banco divergem da última versão aplicada: "
            f"{paths}{more}. Use --keep-drift para preservá-los ou --overwrite-drift "
            "para sobrescrevê-los."
        )


def load_descriptor(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def configured_descriptor_path() -> Path:
    """The Instance descriptor this deployment declares (``SHOPMAN_INSTANCE_DESCRIPTOR``).

    Release commands read their configuration from here instead of carrying a
    second copy in code. Missing setting or file fails loudly.
    """
    from django.conf import settings

    raw = getattr(settings, "SHOPMAN_INSTANCE_DESCRIPTOR", "")
    if not raw:
        raise ValueError("SHOPMAN_INSTANCE_DESCRIPTOR is not configured")
    path = Path(raw)
    if not path.is_file():
        raise ValueError(f"SHOPMAN_INSTANCE_DESCRIPTOR not found: {path}")
    return path


def configured_descriptor() -> dict:
    descriptor = load_descriptor(configured_descriptor_path())
    assert_export_safe(descriptor["bootstrap"])
    return descriptor


def declared_channel(descriptor: dict, ref: str) -> dict | None:
    """The ``bootstrap.channels`` item for ``ref``, or ``None`` when undeclared."""
    return next(
        (item for item in descriptor["bootstrap"]["channels"] if item["ref"] == ref),
        None,
    )


def descriptor_sha256(descriptor: dict) -> str:
    canonical = json.dumps(descriptor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── A loja ────────────────────────────────────────────────────────────────


def the_shop(*, required: bool = True):
    """A única ``Shop``. Falha gritando se houver duas (ou nenhuma, se exigida)."""
    from shopman.shop.models import Shop

    shops = list(Shop.objects.order_by("pk")[:2])
    if len(shops) > 1:
        pks = list(Shop.objects.order_by("pk").values_list("pk", flat=True))
        raise ShopSingletonViolation(
            f"há {len(pks)} lojas (pk {pks}); a Shop é singleton. Os canais e o "
            "Shop.load() podem estar apontando para lojas diferentes: confira e "
            "apague a sobra antes de continuar."
        )
    if not shops:
        if required:
            raise ShopSingletonViolation("nenhuma loja; aplique o descritor de Instância antes")
        return None
    return shops[0]


# ── Projeção crua (tudo o que o banco tem, inclusive estado operacional) ──


def _config_item(ref: str, *, enabled: bool | None = None, config: dict | None = None) -> dict:
    item: dict = {"ref": ref}
    if enabled is not None:
        item["enabled"] = enabled
    if config:
        item["config"] = config
    return item


def _project_templates() -> list[dict]:
    from shopman.backstage.models import OperationChecklistTemplate

    projected = []
    templates = OperationChecklistTemplate.objects.prefetch_related(
        "task_links__task_template"
    ).order_by("ref")
    for template in templates:
        tasks = []
        for link in template.task_links.all().order_by("sort_order", "task_template__ref"):
            task = link.task_template
            tasks.append({
                "ref": task.ref,
                "title": task.title,
                "description": task.description,
                "moment": task.moment,
                "area": task.area,
                "evidence_required": task.evidence_required,
                "expected_role": task.expected_role,
                "required": link.effective_required,
                "enabled": task.is_active,
                "system": task.is_system,
                "task_sort_order": task.sort_order,
                "sort_order": link.sort_order,
                "config": copy.deepcopy(task.config),
            })
        projected.append(_config_item(
            template.ref,
            enabled=template.is_active,
            config={
                "title": template.title,
                "description": template.description,
                "moment": template.moment,
                "sort_order": template.sort_order,
                "tasks": tasks,
            },
        ))
    return projected


def _project_customer_groups() -> list[dict]:
    """Grupos comerciais com a promoção ``grupo-<ref>`` que lhes dá o desconto."""
    from shopman.guestman.models import PriceTier

    from shopman.shop.models import Promotion

    promotions = {
        promotion.ref: promotion
        for promotion in Promotion.objects.filter(ref__startswith="grupo-")
    }
    projected = []
    for tier in PriceTier.objects.order_by("ref"):
        promotion = promotions.get(f"grupo-{tier.ref}")
        if promotion is None:
            continue
        metadata = tier.metadata or {}
        projected.append(_config_item(tier.ref, config={
            "name": tier.name,
            "discount_kind": metadata.get("discount_kind"),
            "rounding": metadata.get("rounding"),
            "savings_message": metadata.get("savings_message"),
            "discount_percent": promotion.value,
            "fulfillment_types": promotion.fulfillment_types,
        }))
    return projected


def _project_raw(template: dict) -> dict:
    """O banco no formato do descritor, sem filtro. Uso interno do apply."""
    from shopman.shop.models import Channel, RuleConfig

    descriptor = {
        "schema_version": template["schema_version"],
        "instance": copy.deepcopy(template["instance"]),
        "ownership": copy.deepcopy(template["ownership"]),
        "bootstrap": {section: [] for section in template["bootstrap"]},
    }
    shop = the_shop(required=False)
    if shop is not None:
        descriptor["instance"]["display_name"] = shop.name

    descriptor["bootstrap"]["channels"] = [
        _config_item(
            channel.ref,
            enabled=channel.is_active,
            config={
                "name": channel.name,
                "commerce_policy": channel.commerce_policy,
                "display_order": channel.display_order,
                "overrides": copy.deepcopy(channel.config or {}),
            },
        )
        for channel in Channel.objects.order_by("ref")
    ]
    descriptor["bootstrap"]["rule_configs"] = [
        _config_item(
            rule.ref,
            enabled=rule.enabled,
            config={
                "rule_path": rule.rule_path,
                "label": rule.label,
                "params": copy.deepcopy(rule.params or {}),
                "channels": sorted(rule.channels.values_list("ref", flat=True)),
                "priority": rule.priority,
            },
        )
        for rule in RuleConfig.objects.prefetch_related("channels").order_by("ref")
    ]
    descriptor["bootstrap"]["customer_groups"] = _project_customer_groups()
    descriptor["bootstrap"]["rbac_personas"] = [
        {
            "ref": slugify(group.name),
            "name": group.name,
            "permissions": sorted(
                f"{app_label}.{codename}"
                for app_label, codename in group.permissions.values_list(
                    "content_type__app_label", "codename"
                )
            ),
        }
        for group in Group.objects.prefetch_related("permissions__content_type").order_by("name")
    ]
    refs = [item["ref"] for item in descriptor["bootstrap"]["rbac_personas"]]
    if len(refs) != len(set(refs)):
        raise ValueError("group names produce duplicate persona refs")
    descriptor["bootstrap"]["templates"] = _project_templates()
    return descriptor


# ── Estado operacional ────────────────────────────────────────────────────


def _is_operational(section: str, rel_path: tuple[str, ...]) -> bool:
    return rel_path in OPERATIONAL_STATE.get(section, ())


def _drop_path(item: dict, path: tuple[str, ...]) -> None:
    node = item
    for key in path[:-1]:
        node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            return
    node.pop(path[-1], None)


def without_operational_state(descriptor: dict) -> dict:
    """Cópia do descritor sem o que é do operador (base do dump e do diff)."""
    result = copy.deepcopy(descriptor)
    for section, paths in OPERATIONAL_STATE.items():
        for item in result.get("bootstrap", {}).get(section, []):
            for path in paths:
                _drop_path(item, path)
    return result


# ── Allowlist do dump ─────────────────────────────────────────────────────


def _channel_schema() -> dict:
    """``{campo: subesquema | None}`` a partir do dataclass ``ChannelConfig``.

    ``None`` é folha. Campo que é ``dict`` livre tem validador próprio
    (``_MAPPING_FIELDS``) em vez de passar inteiro.
    """
    from shopman.shop.config import ChannelConfig

    def schema_of(instance) -> dict:
        schema = {}
        for field in dataclasses.fields(instance):
            value = getattr(instance, field.name)
            schema[field.name] = schema_of(value) if dataclasses.is_dataclass(value) else None
        return schema

    return schema_of(ChannelConfig())


def _check_identifier_mapping(value, path: str, *, keys: frozenset | None = None) -> None:
    if not isinstance(value, dict):
        if isinstance(value, list):
            for index, child in enumerate(value):
                _check_identifier_mapping(child, f"{path}[{index}]")
        return
    for key, child in value.items():
        if not isinstance(key, str) or not _IDENT_RE.fullmatch(key):
            raise UnsafeDescriptor(f"chave não exportável em {path} (não é identificador)")
        if keys is not None and key not in keys:
            raise UnsafeDescriptor(f"chave desconhecida em {path}.{key}")
        _check_identifier_mapping(child, f"{path}.{key}")


def _mapping_fields() -> dict[tuple[str, ...], frozenset | None]:
    from shopman.shop.config import STAGE_GOAL_DEFAULTS

    return {
        ("lifecycle",): frozenset({"transitions", "terminal_statuses"}),
        ("fulfillment", "stage_goal_minutes"): frozenset(STAGE_GOAL_DEFAULTS),
        ("notifications", "routing"): None,
    }


def _allowlist_channel_overrides(overrides: dict, path: str) -> dict:
    schema = _channel_schema()
    mappings = _mapping_fields()

    def walk(value: dict, node_schema: dict, rel: tuple[str, ...], where: str) -> dict:
        out = {}
        for key, child in value.items():
            child_rel = rel + (key,)
            if key not in node_schema:
                raise UnsafeDescriptor(f"chave desconhecida em {where}.{key}")
            if child_rel in mappings:
                if child is not None and not isinstance(child, dict):
                    raise UnsafeDescriptor(f"{where}.{key} precisa ser objeto")
                _check_identifier_mapping(child or {}, f"{where}.{key}", keys=mappings[child_rel])
                out[key] = copy.deepcopy(child)
            elif node_schema[key] is None:
                if isinstance(child, dict):
                    raise UnsafeDescriptor(f"{where}.{key} é folha e chegou objeto")
                out[key] = copy.deepcopy(child)
            else:
                if not isinstance(child, dict):
                    raise UnsafeDescriptor(f"{where}.{key} precisa ser objeto")
                out[key] = walk(child, node_schema[key], child_rel, f"{where}.{key}")
        return out

    return walk(overrides, schema, (), path)


def _rule_param_keys(rule_path: str) -> frozenset:
    from django.utils.module_loading import import_string

    try:
        cls = import_string(rule_path)
    except ImportError as exc:
        raise UnsafeDescriptor(f"regra sem classe importável: {rule_path}") from exc
    known = set(getattr(cls, "KNOWN", ()) or ())
    for name, parameter in inspect.signature(cls.__init__).parameters.items():
        if name == "self" or parameter.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        known.add(name)
    return frozenset(known)


def _export_view(raw: dict) -> dict:
    """Do banco cru para o que pode sair: sem estado operacional, só allowlist."""
    view = without_operational_state(raw)
    bootstrap = view["bootstrap"]
    for item in bootstrap["channels"]:
        config = item.get("config", {})
        config["overrides"] = _allowlist_channel_overrides(
            config.get("overrides") or {},
            f"bootstrap.channels.{item['ref']}.config.overrides",
        )
    for item in bootstrap["rule_configs"]:
        config = item["config"]
        allowed = _rule_param_keys(config["rule_path"])
        for key in config["params"]:
            if key not in allowed:
                raise UnsafeDescriptor(
                    f"chave desconhecida em bootstrap.rule_configs.{item['ref']}.config.params.{key}"
                )
    for item in bootstrap["templates"]:
        for task in item.get("config", {}).get("tasks", []):
            for key in task["config"]:
                if key not in TASK_CONFIG_KEYS:
                    raise UnsafeDescriptor(
                        f"chave desconhecida em bootstrap.templates.{item['ref']}"
                        f".tasks.{task['ref']}.config.{key}"
                    )
    assert_export_safe(bootstrap)
    return view


def project_from_database(template: dict) -> dict:
    """A projeção exportável do banco: determinística, só leitura, só allowlist."""
    return _export_view(_project_raw(template))


def assert_export_safe(value, path: str = "bootstrap") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_KEY_RE.search(str(key)):
                raise UnsafeDescriptor(f"secret-like key at {path}.{key}")
            assert_export_safe(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_export_safe(child, f"{path}[{index}]")
    elif isinstance(value, str) and any(pattern.search(value) for pattern in SECRET_VALUE_RES):
        raise UnsafeDescriptor(f"secret-like value at {path}")


def assert_no_operational_state(descriptor: dict) -> None:
    """O descritor não declara estado operacional (só ``enabled`` do canal que nasce)."""
    for section, paths in OPERATIONAL_STATE.items():
        for item in descriptor["bootstrap"].get(section, []):
            for path in paths:
                if path == ("enabled",):
                    continue
                node = item
                for key in path:
                    node = node.get(key) if isinstance(node, dict) else None
                if node is not None:
                    raise ValueError(
                        f"estado operacional não se declara: bootstrap.{section}."
                        f"{item['ref']}.{'.'.join(path)}"
                    )


def descriptor_diff(expected, actual, path: str = "") -> list[dict]:
    """Return stable JSON-pointer changes from versioned descriptor to DB projection."""
    if type(expected) is not type(actual):
        return [{"path": path or "/", "declared": expected, "database": actual}]
    if isinstance(expected, dict):
        changes = []
        for key in sorted(set(expected) | set(actual)):
            child_path = f"{path}/{key.replace('~', '~0').replace('/', '~1')}"
            if key not in expected:
                changes.append({"path": child_path, "declared": None, "database": actual[key]})
            elif key not in actual:
                changes.append({"path": child_path, "declared": expected[key], "database": None})
            else:
                changes.extend(descriptor_diff(expected[key], actual[key], child_path))
        return changes
    if isinstance(expected, list):
        if expected == actual:
            return []
        return [{"path": path or "/", "declared": expected, "database": actual}]
    if expected != actual:
        return [{"path": path or "/", "declared": expected, "database": actual}]
    return []


# ── Plano de três vias ────────────────────────────────────────────────────

_MISSING = object()


def _pointer(parts) -> str:
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _keyed(descriptor: dict) -> dict:
    """Seções como ``{ref: item}``; tarefas do template como ``{ref: tarefa}``."""
    keyed = {"instance": {"display_name": descriptor["instance"]["display_name"]}}
    for section in SECTIONS:
        items = {}
        for item in descriptor["bootstrap"].get(section, []):
            item = copy.deepcopy(item)
            ref = item.pop("ref")
            if section == "templates" and "config" in item:
                item["config"]["tasks"] = {
                    task.pop("ref"): task for task in item["config"].get("tasks", [])
                }
            items[ref] = item
        keyed[section] = items
    return keyed


def _unkeyed_templates(items: dict) -> list[dict]:
    result = []
    for ref, item in items.items():
        item = copy.deepcopy(item)
        if "config" in item:
            tasks = [{"ref": task_ref, **task} for task_ref, task in item["config"]["tasks"].items()]
            item["config"]["tasks"] = sorted(tasks, key=lambda t: (t["sort_order"], t["ref"]))
        result.append({"ref": ref, **item})
    return result


class _Planner:
    def __init__(self, on_drift: str):
        self.on_drift = on_drift
        self.changes: list[dict] = []

    def _record(self, action: str, parts, declared=_MISSING, database=_MISSING) -> None:
        change = {"action": action, "path": _pointer(parts)}
        if declared is not _MISSING:
            change["declared"] = copy.deepcopy(declared)
        if database is not _MISSING:
            change["database"] = copy.deepcopy(database)
        self.changes.append(change)

    def _conflict(self, parts, declared, database):
        """O banco mudou por fora. Devolve o valor que fica (``_MISSING`` = ausente)."""
        if self.on_drift == "overwrite":
            self._record("overwritten", parts, declared, database)
            return declared
        action = "kept" if self.on_drift == "keep" else "conflict"
        self._record(action, parts, declared, database)
        return database

    def merge(self, declared, database, base, parts, section: str, rel: tuple):
        if isinstance(declared, dict) and isinstance(database, dict):
            base_dict = base if isinstance(base, dict) else None
            out = {}
            for key in sorted(set(declared) | set(database), key=str):
                child_rel = rel + (key,)
                child_parts = parts + [key]
                d = declared.get(key, _MISSING)
                v = database.get(key, _MISSING)
                b = base_dict.get(key, _MISSING) if base_dict is not None else _MISSING
                if _is_operational(section, child_rel):
                    if v is not _MISSING:
                        out[key] = v
                    continue
                if d is _MISSING:
                    # Chave que o descritor não declara agora.
                    if b is _MISSING:
                        out[key] = v  # nunca foi do descritor: não é dele
                    elif b == v:
                        self._record("remove", child_parts, database=v)  # o descritor tirou
                    else:
                        kept = self._conflict(child_parts, _MISSING, v)
                        if kept is not _MISSING:
                            out[key] = kept
                    continue
                if v is _MISSING:
                    if b is _MISSING:
                        self._record("add", child_parts, declared=d)
                        out[key] = d
                    else:
                        kept = self._conflict(child_parts, d, _MISSING)
                        if kept is not _MISSING:
                            out[key] = kept
                    continue
                out[key] = self.merge(d, v, b, child_parts, section, child_rel)
            return out
        if declared == database:
            return database
        if base is not _MISSING and base == database:
            self._record("update", parts, declared, database)
            return declared
        return self._conflict(parts, declared, database)


def _last_applied(instance_ref: str):
    from shopman.shop.models import InstanceApplyRecord

    return InstanceApplyRecord.objects.filter(instance_ref=instance_ref).order_by(
        "-applied_at", "-pk"
    ).first()


def _plan_customer_groups(items: list[dict], planner) -> None:
    from config.management.commands.setup_commercial_groups import promotion_ref
    from shopman.shop.models import Promotion

    existing = set(
        Promotion.objects.filter(ref__in=[promotion_ref(item["ref"]) for item in items]).values_list(
            "ref", flat=True
        )
    )
    for item in items:
        if promotion_ref(item["ref"]) not in existing:
            planner._record("create", ["bootstrap", "customer_groups", item["ref"]], declared=item)


def plan_apply(descriptor: dict, *, on_drift: str = "refuse") -> dict:
    """O que o apply faria: alvo efetivo + lista de mudanças. Não escreve nada."""
    if on_drift not in DRIFT_POLICIES:
        raise ValueError(f"on_drift precisa ser um de {DRIFT_POLICIES}")
    last = _last_applied(descriptor["instance"]["ref"])
    base = _keyed(last.descriptor) if last is not None else None
    declared = _keyed(descriptor)
    database = _keyed(_project_raw(descriptor))
    planner = _Planner(on_drift)

    shop = the_shop(required=False)
    target_instance = dict(descriptor["instance"])
    if shop is None:
        planner._record("create", ["instance", "shop"], declared=descriptor["instance"]["display_name"])
    else:
        kept = planner.merge(
            declared["instance"]["display_name"],
            database["instance"]["display_name"],
            base["instance"]["display_name"] if base else _MISSING,
            ["instance", "display_name"],
            "instance",
            ("display_name",),
        )
        target_instance["display_name"] = kept

    target_bootstrap = copy.deepcopy(descriptor["bootstrap"])
    for section in SECTIONS:
        merged = {}
        for ref, item in declared[section].items():
            parts = ["bootstrap", section, ref]
            if ref not in database[section]:
                planner._record("create", parts, declared=item)
                merged[ref] = item
                continue
            base_item = base[section].get(ref, _MISSING) if base else _MISSING
            merged[ref] = planner.merge(item, database[section][ref], base_item, parts, section, ())
        if section == "templates":
            target_bootstrap[section] = _unkeyed_templates(merged)
        else:
            target_bootstrap[section] = [{"ref": ref, **item} for ref, item in merged.items()]

    # Grupo comercial é seção de criar-se-faltar: o apply nunca o compara nem o
    # reescreve (depois de criado, o cadastro é do gestor); só relata o que cria.
    _plan_customer_groups(descriptor["bootstrap"].get("customer_groups", []), planner)

    target = {**descriptor, "instance": target_instance, "bootstrap": target_bootstrap}
    return {
        "target": target,
        "shop_missing": shop is None,
        "changes": planner.changes,
        "base_sha256": last.descriptor_sha256 if last is not None else None,
    }


# ── Escrita ───────────────────────────────────────────────────────────────


def _permission(permission_ref: str) -> Permission:
    app_label, codename = permission_ref.split(".", 1)
    try:
        return Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )
    except Permission.DoesNotExist as exc:
        raise ValueError(f"unknown permission: {permission_ref}") from exc


def _get_or_update(model, *, lookup: dict, defaults: dict):
    obj, created = model.objects.get_or_create(**lookup, defaults=defaults)
    if created:
        return obj, True

    changed_fields = [
        field
        for field, value in defaults.items()
        if getattr(obj, field) != value
    ]
    if changed_fields:
        for field in changed_fields:
            setattr(obj, field, defaults[field])
        obj.save(update_fields=changed_fields)
    return obj, False


def _apply_channels(items: list[dict], shop) -> None:
    from shopman.shop.models import Channel

    for item in items:
        config = item.get("config", {})
        _get_or_update(
            Channel,
            lookup={"ref": item["ref"]},
            defaults={
                "shop": shop,
                "name": config.get("name", ""),
                "commerce_policy": config.get("commerce_policy", "order"),
                "display_order": config.get("display_order", 0),
                "config": config.get("overrides", {}),
                "is_active": item.get("enabled", True),
            },
        )


def _apply_rules(items: list[dict]) -> None:
    from shopman.shop.models import Channel, RuleConfig

    for item in items:
        config = item.get("config", {})
        required = {"rule_path", "label", "params", "channels", "priority"}
        if set(config) != required:
            raise ValueError(f"rule {item['ref']} requires {sorted(required)}")
        rule, _created = _get_or_update(
            RuleConfig,
            lookup={"ref": item["ref"]},
            defaults={
                "rule_path": config["rule_path"],
                "label": config["label"],
                "enabled": item.get("enabled", True),
                "params": config["params"],
                "priority": config["priority"],
            },
        )
        channel_refs = config["channels"]
        channels = list(Channel.objects.filter(ref__in=channel_refs).order_by("ref"))
        if [channel.ref for channel in channels] != sorted(channel_refs):
            raise ValueError(f"rule {item['ref']} references unknown channel")
        current_channel_ids = set(rule.channels.values_list("pk", flat=True))
        desired_channel_ids = {channel.pk for channel in channels}
        if current_channel_ids != desired_channel_ids:
            rule.channels.set(channels)


def sync_personas(items: list[dict]) -> list[dict]:
    """Make each declared group hold exactly the declared permissions.

    Returns one report per persona: ``name``, ``created``, ``granted`` and
    ``revoked`` (``app_label.codename``), so a release log says what changed.
    Groups absent from the descriptor are left alone: the descriptor owns the
    personas it declares, not every group an operator may create.
    """
    reports = []
    for item in items:
        if slugify(item["name"]) != item["ref"]:
            raise ValueError(
                f"persona ref {item['ref']} does not match name {item['name']!r}"
            )
        group, created = Group.objects.get_or_create(name=item["name"])
        permissions = [_permission(ref) for ref in item["permissions"]]
        current = {
            f"{app_label}.{codename}"
            for app_label, codename in group.permissions.values_list(
                "content_type__app_label", "codename"
            )
        }
        desired = set(item["permissions"])
        if current != desired:
            group.permissions.set(permissions)
        reports.append({
            "name": group.name,
            "created": created,
            "granted": sorted(desired - current),
            "revoked": sorted(current - desired),
        })
    return reports


def _apply_personas(items: list[dict]) -> None:
    sync_personas(items)


def _apply_templates(items: list[dict]) -> None:
    from shopman.backstage.models import (
        OperationChecklistTemplate,
        OperationChecklistTemplateTask,
        OperationTaskTemplate,
    )

    for item in items:
        config = item.get("config", {})
        required = {"title", "description", "moment", "sort_order", "tasks"}
        if set(config) != required:
            raise ValueError(f"template {item['ref']} requires {sorted(required)}")
        template, _created = _get_or_update(
            OperationChecklistTemplate,
            lookup={"ref": item["ref"]},
            defaults={
                "title": config["title"],
                "description": config["description"],
                "moment": config["moment"],
                "is_active": item.get("enabled", True),
                "sort_order": config["sort_order"],
            },
        )
        for task_data in config["tasks"]:
            task, _task_created = _get_or_update(
                OperationTaskTemplate,
                lookup={"ref": task_data["ref"]},
                defaults={
                    "title": task_data["title"],
                    "description": task_data["description"],
                    "moment": task_data["moment"],
                    "area": task_data["area"],
                    "evidence_required": task_data["evidence_required"],
                    "expected_role": task_data["expected_role"],
                    "is_required": task_data["required"],
                    "is_active": task_data["enabled"],
                    "is_system": task_data["system"],
                    "sort_order": task_data["task_sort_order"],
                    "config": task_data["config"],
                },
            )
            _get_or_update(
                OperationChecklistTemplateTask,
                lookup={
                    "checklist_template": template,
                    "task_template": task,
                },
                defaults={
                    "sort_order": task_data["sort_order"],
                    "is_required_override": task_data["required"],
                },
            )


def _summary(changes: list[dict]) -> dict:
    summary: dict[str, int] = {}
    for change in changes:
        summary[change["action"]] = summary.get(change["action"], 0) + 1
    return dict(sorted(summary.items()))


WRITING_ACTIONS = frozenset({"create", "add", "update", "remove", "overwritten"})


def _apply_customer_groups(items: list[dict]) -> None:
    """Cria só o grupo ausente: depois de criado, o cadastro é do gestor."""
    from config.management.commands.setup_commercial_groups import ensure_commercial_groups

    ensure_commercial_groups(items)


@transaction.atomic
def apply_to_database(
    descriptor: dict,
    *,
    actor: str,
    on_drift: str = "refuse",
    dry_run: bool = False,
) -> dict:
    """Aplica a configuração declarada, atômico e idempotente, e relata o diff.

    ``on_drift`` decide o valor que o banco tem diferente da última versão
    aplicada: ``refuse`` (padrão) recusa o apply inteiro listando os caminhos;
    ``keep`` preserva o valor do banco; ``overwrite`` grava o declarado. O estado
    operacional nunca entra nessa conta: o apply não o toca.

    ``dry_run`` devolve o mesmo relatório sem escrever nada.
    """
    from shopman.shop.models import InstanceApplyRecord, Shop

    if not actor or not str(actor).strip():
        raise ValueError("apply exige actor (quem está aplicando)")
    bootstrap = descriptor["bootstrap"]
    assert_export_safe(bootstrap)
    assert_no_operational_state(descriptor)
    unsupported = {
        section: bootstrap[section]
        for section in UNOWNED_SECTIONS
        if bootstrap[section]
    }
    if unsupported:
        raise UnsupportedInstanceSection(
            f"no proven DB owner for: {', '.join(sorted(unsupported))}"
        )

    plan = plan_apply(descriptor, on_drift=on_drift)
    changes = plan["changes"]
    sha = descriptor_sha256(descriptor)
    report = {
        "instance": descriptor["instance"]["ref"],
        "descriptor_sha256": sha,
        "base_sha256": plan["base_sha256"],
        "dry_run": dry_run,
        "on_drift": on_drift,
        "actor": actor,
        "shop_created": plan["shop_missing"] and not dry_run,
        "summary": _summary(changes),
        "changes": changes,
    }
    conflicts = [change for change in changes if change["action"] == "conflict"]
    if dry_run:
        return report
    if conflicts:
        raise InstanceDriftConflict(conflicts)

    target = plan["target"]
    shop = the_shop(required=False)
    if shop is None:
        shop = Shop.objects.create(name=target["instance"]["display_name"])
    elif shop.name != target["instance"]["display_name"]:
        shop.name = target["instance"]["display_name"]
        shop.save(update_fields=["name"])

    _apply_channels(target["bootstrap"]["channels"], shop)
    _apply_rules(target["bootstrap"]["rule_configs"])
    _apply_personas(target["bootstrap"]["rbac_personas"])
    _apply_templates(target["bootstrap"]["templates"])
    _apply_customer_groups(target["bootstrap"]["customer_groups"])

    wrote = any(change["action"] in WRITING_ACTIONS for change in changes)
    if wrote or plan["base_sha256"] != sha:
        InstanceApplyRecord.objects.create(
            instance_ref=descriptor["instance"]["ref"],
            schema_version=descriptor["schema_version"],
            descriptor_sha256=sha,
            descriptor=copy.deepcopy(descriptor),
            changes=changes,
            actor=str(actor),
            on_drift=on_drift,
        )
    return report
