"""AST-backed import boundary guardrails.

These tests enforce the architectural direction that is easy to regress:

* kernel packages do not import host/orchestrator/surface apps;
* surfaces do not import each other;
* shop imports surfaces only through adapters;
* framework code does not import protected kernel internals.

The checks intentionally parse Python imports instead of using line regexes so
both ``import x.y`` and ``from x.y import z`` are covered.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FRAMEWORK_ROOT = REPO_ROOT / "shopman"
PACKAGES_ROOT = REPO_ROOT / "packages"

SHOP_ROOT = FRAMEWORK_ROOT / "shop"
STOREFRONT_ROOT = FRAMEWORK_ROOT / "storefront"
BACKSTAGE_ROOT = FRAMEWORK_ROOT / "backstage"

SURFACE_ROOTS = (SHOP_ROOT, STOREFRONT_ROOT, BACKSTAGE_ROOT)

# Data read-side (Projection) and the surface Presentation layers — targets of
# the ADR-014 §4.2 semantic cut (rules R-A/R-B/R-C/R-D).
PROJECTIONS_ROOT = SHOP_ROOT / "projections"
PRESENTATION_ROOTS = (
    STOREFRONT_ROOT / "presentation",
    BACKSTAGE_ROOT / "presentation",
)
READ_SIDE_ROOTS = (
    SHOP_ROOT / "projections",
    BACKSTAGE_ROOT / "projections",
    STOREFRONT_ROOT / "presentation",
)
API_ROOTS = (
    BACKSTAGE_ROOT / "api",
    STOREFRONT_ROOT / "api",
)

# Command modules are delivery-visible, but never callable from GET handlers.
# Keep this list small and explicit; mutation-shaped calls are caught as a
# second line of defence even when they live outside these modules.
COMMAND_SERVICE_MODULES = (
    "shopman.backstage.services.blind_prep_codes",
)
MUTATION_CALL_PREFIXES = (
    "add_",
    "allocate_",
    "consume_",
    "create_",
    "delete_",
    "ensure_",
    "issue_",
    "mark_",
    "mutate_",
    "process_",
    "reconcile_",
    "record_",
    "save_",
    "send_",
    "set_",
    "update_",
)
ORM_MUTATION_METHODS = {
    "bulk_create",
    "bulk_update",
    "create",
    "get_or_create",
    "update",
    "update_or_create",
}

HOST_PREFIXES = (
    "config",
    "shopman.shop",
    "shopman.storefront",
    "shopman.backstage",
)

DOMAIN_KERNEL_PACKAGES = {
    "buyman",
    "cashman",
    "craftsman",
    "doorman",
    "fiscalman",
    "guestman",
    "offerman",
    "orderman",
    "payman",
    "stockman",
}

# O que a rede TRANSITIVA (abaixo) achou no dia em que nasceu, além das sete
# chamadas que a A8-1 tirou dos GETs (acompanhamento, sino, etiqueta, menu): GET
# que alcança uma escrita por um serviço sem nome de comando. É dívida, com
# catraca nos dois sentidos: escrita NOVA reprova, e linha que ficou velha
# (escrita resolvida, linha esquecida) também. Cada grupo é uma frente própria.
# Chave: (arquivo, chamada no GET) -> quantas vezes.
GET_WRITE_FOUND_BY_TRANSITIVE_GATE = {
    # Exportação da conta: o download (GET) abre e fecha o recibo LGPD.
    ("shopman/storefront/api/account.py", "account_privacy.begin_export"): 1,
    ("shopman/storefront/api/account.py", "account_export.prepare_account_export"): 1,
    ("shopman/storefront/api/account.py", "account_privacy.fail_export"): 1,
    # Continuum: a leitura materializa a cabeça do snapshot do catálogo.
    ("shopman/storefront/api/continuum.py", "current_or_build_head"): 1,
    ("shopman/storefront/api/surface.py", "compare_shadow"): 1,
    # Recuperação do checkout por GET: concede acesso na sessão e refaz efeitos pós-commit.
    ("shopman/storefront/api/views.py", "order_service.grant_order_access"): 1,
    ("shopman/storefront/api/views.py", "checkout_service.recover_committed_checkout"): 1,
    # Gestor/PDV: o detalhe do pedido pergunta ao gateway do cartão (e carimba a pergunta).
    ("shopman/backstage/api/operations.py", "_reconcile_payment_if_due"): 2,
    # ESC/POS: compor o papel carimba a "primeira via" no pedido.
    ("shopman/backstage/api/operations.py", "_stamp_first_print"): 5,
    # Pulso da gaveta: a leitura grava o veredito do relógio e fecha o livro-caixa.
    ("shopman/backstage/api/operations.py", "drawer_pulse.pulse_state"): 1,
}
KNOWN_NON_MUTATING_GET_CALLS = {"response.add_post_render_callback"}

PROTECTED_KERNEL_PACKAGES = (
    "refs",
    "utils",
    "stockman",
    "offerman",
    "craftsman",
    "orderman",
    "doorman",
    "payman",
    "cashman",
)


def _py_files(root: Path, *, skip_parts: set[str] | None = None) -> Iterable[Path]:
    skip_parts = skip_parts or set()
    for path in sorted(root.rglob("*.py")):
        rel_parts = set(path.relative_to(root).parts)
        if "__pycache__" in rel_parts:
            continue
        if skip_parts & rel_parts:
            continue
        yield path


def _imports(path: Path) -> Iterable[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except UnicodeDecodeError:
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


def _matches_prefix(module: str, prefixes: Iterable[str]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def _format_violations(violations: list[tuple[Path, int, str]]) -> str:
    return "\n".join(
        f"  {path.relative_to(REPO_ROOT)}:{line}: {module}"
        for path, line, module in violations
    )


def _get_handler_write_calls(path: Path) -> list[tuple[Path, int, str]]:
    """Return command/write calls made inside HTTP ``get`` handlers."""
    tree = ast.parse(path.read_text(), filename=str(path))
    imported_command_names: set[str] = set()
    imported_command_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _matches_prefix(
            node.module, COMMAND_SERVICE_MODULES
        ):
            imported_command_names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _matches_prefix(alias.name, COMMAND_SERVICE_MODULES):
                    imported_command_modules.add(alias.asname or alias.name)

    violations: list[tuple[Path, int, str]] = []
    for handler in ast.walk(tree):
        if not isinstance(handler, (ast.FunctionDef, ast.AsyncFunctionDef)) or handler.name != "get":
            continue
        for node in ast.walk(handler):
            if not isinstance(node, ast.Call):
                continue
            label = ast.unparse(node.func)
            if isinstance(node.func, ast.Name):
                if node.func.id in imported_command_names or node.func.id.startswith(MUTATION_CALL_PREFIXES):
                    violations.append((path, node.lineno, label))
            elif isinstance(node.func, ast.Attribute):
                owner = ast.unparse(node.func.value)
                if node.func.attr in ORM_MUTATION_METHODS and ".objects" in owner:
                    violations.append((path, node.lineno, label))
                elif node.func.attr in {"save", "delete"}:
                    violations.append((path, node.lineno, label))
                elif node.func.attr.startswith(MUTATION_CALL_PREFIXES):
                    violations.append((path, node.lineno, label))
                elif any(owner == module or owner.startswith(f"{module}.") for module in imported_command_modules):
                    violations.append((path, node.lineno, label))
    return violations


# ── Escrita transitiva: GET/projeção que chama um serviço de comando ─────────
#
# O detector acima vê só a chamada que tem cara de escrita (prefixo de mutação,
# ``.objects.create``). Um GET que chama ``tidy(order)``, e ``tidy`` grava,
# passava. O grafo abaixo indexa toda função do framework (shop, storefront,
# backstage), marca quem grava DIRETO e propaga pela chamada até o ponto fixo:
# quem chama quem grava, grava. Um GET ou uma função da camada de leitura que
# alcança uma escritora reprova.

FRAMEWORK_GRAPH_ROOTS = (SHOP_ROOT, STOREFRONT_ROOT, BACKSTAGE_ROOT)
_GRAPH_SKIP_PARTS = {"tests", "migrations", "__pycache__"}
# Escrita que não depende de quem é o dono da chamada.
_ALWAYS_WRITE_METHODS = {"bulk_create", "bulk_update", "get_or_create", "update_or_create", "transition_status"}
# Escrita só quando o dono é um queryset/manager (``dict.update`` não é).
_QUERYSET_WRITE_METHODS = {"create", "update", "delete"}
_QUERYSET_OWNER_MARKERS = ("objects", "filter(", "exclude(", "all(", "select_for_update(", "_set")


def _module_name(path: Path, *, base: Path) -> str:
    parts = list(path.relative_to(base).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _direct_write(nodes: Iterable[ast.AST]) -> str | None:
    """A primeira escrita que o corpo da função faz por conta própria, ou ``None``."""
    for node in nodes:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = ast.unparse(node.func.value)
            attr = node.func.attr
            if attr in _ALWAYS_WRITE_METHODS:
                return f"{owner}.{attr}"
            if attr in _QUERYSET_WRITE_METHODS and any(marker in owner for marker in _QUERYSET_OWNER_MARKERS):
                return f"{owner}.{attr}"
            # ``instance.save()``/``.delete()`` de model não recebe posicional;
            # ``workbook.save(stream)`` e ``image.save(buffer)`` recebem.
            if attr in {"save", "delete"} and not node.args and "cache" not in owner:
                return f"{owner}.{attr}"
            if attr == "pop" and owner.endswith("session"):
                return f"{owner}.pop"
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and ast.unparse(target.value).endswith("session"):
                    return f"{ast.unparse(target.value)}[...] ="
                if isinstance(target, ast.Attribute) and target.attr == "modified" and ast.unparse(
                    target.value
                ).endswith("session"):
                    return "session.modified ="
    return None


class _FrameworkWriteGraph:
    """Funções do framework, quem cada uma chama e quem grava (transitivo)."""

    def __init__(self, roots: Iterable[Path], *, base: Path = REPO_ROOT):
        self.paths: dict[str, Path] = {}
        trees: dict[str, ast.Module] = {}
        for root in roots:
            for path in sorted(root.rglob("*.py")):
                if _GRAPH_SKIP_PARTS & set(path.relative_to(root).parts):
                    continue
                module = _module_name(path, base=base)
                try:
                    trees[module] = ast.parse(path.read_text(), filename=str(path))
                except (SyntaxError, UnicodeDecodeError):
                    continue
                self.paths[module] = path
        self.functions: dict[tuple[str, str], ast.AST] = {}
        module_imports: dict[str, dict[str, tuple[str, ...]]] = {}
        for module, tree in trees.items():
            module_imports[module] = self._import_map(
                [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))], {}
            )
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.functions[(module, node.name)] = node
                elif isinstance(node, ast.ClassDef):
                    for member in node.body:
                        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            self.functions[(module, f"{node.name}.{member.name}")] = member
        # Um passeio só por função: é a parte cara do gate.
        self.calls: dict[tuple[str, str], list[tuple[int, ast.expr, tuple[str, str]]]] = {}
        # Escritora -> o que a faz escritora: a escrita direta (``str``) ou a
        # função que ela chama e que grava (``tuple``).
        self.writers: dict[tuple[str, str], str | tuple[str, str]] = {}
        for key, fn in self.functions.items():
            nodes = list(ast.walk(fn))
            local = self._import_map(
                [node for node in nodes if isinstance(node, (ast.Import, ast.ImportFrom))],
                module_imports[key[0]],
            )
            self.calls[key] = [
                (node.lineno, node.func, target)
                for node in nodes
                if isinstance(node, ast.Call) and (target := self._resolve(node, key[0], local))
            ]
            if write := _direct_write(nodes):
                self.writers[key] = write
        changed = True
        while changed:
            changed = False
            for key, calls in self.calls.items():
                if key in self.writers:
                    continue
                for _line, _label, target in calls:
                    if target in self.writers:
                        self.writers[key] = target
                        changed = True
                        break

    def _import_map(self, nodes, base: dict) -> dict[str, tuple[str, ...]]:
        mapping = dict(base)
        for node in nodes:
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for alias in node.names:
                    full = f"{node.module}.{alias.name}"
                    mapping[alias.asname or alias.name] = (
                        ("module", full) if full in self.paths else ("function", node.module, alias.name)
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        mapping[alias.asname] = ("module", alias.name)
        return mapping

    @staticmethod
    def _resolve(call: ast.Call, module: str, imports: dict) -> tuple[str, str] | None:
        func = call.func
        if isinstance(func, ast.Name):
            target = imports.get(func.id)
            if target is None:
                return (module, func.id)
            return (target[1], target[2]) if target[0] == "function" else None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            target = imports.get(func.value.id)
            if target is not None and target[0] == "module":
                return (target[1], func.attr)
        return None

    def chain(self, key: tuple[str, str]) -> str:
        """Do ponto de chamada até a escrita direta: ``mod.a -> mod.b -> obj.save``."""
        steps = [f"{key[0].rsplit('.', 1)[-1]}.{key[1]}"]
        while isinstance(via := self.writers.get(key), tuple):
            key = via
            steps.append(f"{key[0].rsplit('.', 1)[-1]}.{key[1]}")
        steps.append(str(via))
        return " -> ".join(steps)

    def get_handler_writes(self, roots: Iterable[Path]) -> list[tuple[Path, int, str]]:
        """Chamadas, dentro de ``get`` HTTP, que alcançam uma escritora."""
        violations = []
        for (module, name), _fn in self.functions.items():
            path = self.paths[module]
            if not name.endswith(".get") or not any(path.is_relative_to(root) for root in roots):
                continue
            for line, func, target in self.calls[(module, name)]:
                if target in self.writers:
                    violations.append((path, line, f"{ast.unparse(func)} [{self.chain(target)}]"))
        return violations

    def read_side_writers(self, roots: Iterable[Path]) -> list[tuple[Path, int, str]]:
        """Funções da camada de leitura que gravam, direto ou por quem chamam."""
        return [
            (self.paths[module], fn.lineno, f"{name} [{self.chain((module, name))}]")
            for (module, name), fn in self.functions.items()
            if (module, name) in self.writers
            and any(self.paths[module].is_relative_to(root) for root in roots)
        ]


_FRAMEWORK_GRAPH: _FrameworkWriteGraph | None = None


def _framework_graph() -> _FrameworkWriteGraph:
    global _FRAMEWORK_GRAPH
    if _FRAMEWORK_GRAPH is None:
        _FRAMEWORK_GRAPH = _FrameworkWriteGraph(FRAMEWORK_GRAPH_ROOTS)
    return _FRAMEWORK_GRAPH


def test_offerman_is_the_only_list_tier_price_owner():
    """Named orchestrator consumers cannot grow a second tier algorithm."""
    guarded = (
        SHOP_ROOT / "handlers" / "pricing.py",
        SHOP_ROOT / "services" / "customer_orders.py",
        SHOP_ROOT / "services" / "display_prices.py",
        SHOP_ROOT / "services" / "substitutes.py",
        SHOP_ROOT / "projections" / "suggestions.py",
        BACKSTAGE_ROOT / "projections" / "pos.py",
    )
    forbidden = ('order_by("-min_qty")', "bulk_listing_tiers", "find_listing_tiers")
    violations = [
        f"{path.relative_to(REPO_ROOT)}: {token}"
        for path in guarded
        for token in forbidden
        if token in path.read_text()
    ]
    assert not violations, "Duplicate list/tier price decisions:\n" + "\n".join(violations)


def test_contextual_quote_has_no_flattened_surface_contract():
    """The public catalog/PDP price is one typed quote, not parallel fields."""
    assert not (SHOP_ROOT / "services" / "pricing.py").exists()
    guarded = (
        STOREFRONT_ROOT / "presentation" / "catalog.py",
        STOREFRONT_ROOT / "presentation" / "product_detail.py",
    )
    forbidden = ("has_promotion", "promotion_label", "original_price_display")
    violations = [
        f"{path.relative_to(REPO_ROOT)}: {token}"
        for path in guarded
        for token in forbidden
        if token in path.read_text()
    ]
    serializers = (STOREFRONT_ROOT / "api" / "serializers.py").read_text()
    public_catalog = serializers.split("class ProductListItemSerializer", 1)[1].split("class CollectionSerializer", 1)[
        0
    ]
    types = (REPO_ROOT / "surfaces" / "storefront-nuxt" / "app" / "types" / "shopman.ts").read_text()
    public_types = types.split("export interface CatalogItemProjection", 1)[1].split(
        "export interface CatalogSectionProjection", 1
    )[0]
    public_forbidden = (*forbidden, "base_price_q", "price_display")
    violations.extend(
        f"public catalog contract: {token}"
        for token in public_forbidden
        if token in public_catalog or token in public_types
    )
    assert not violations, "Legacy flattened quote fields:\n" + "\n".join(violations)


def test_kernel_packages_do_not_import_host_layers():
    """Kernel packages must remain standalone and never import host layers."""
    violations = []

    for package_root in sorted(p for p in PACKAGES_ROOT.iterdir() if p.is_dir()):
        for path in _py_files(package_root, skip_parts={"tests"}):
            for line, module in _imports(path):
                if _matches_prefix(module, HOST_PREFIXES):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Kernel packages imported host/orchestrator/surface modules:\n"
            f"{_format_violations(violations)}\n\n"
            "Move host-specific behavior behind an optional integration resolved "
            "through Django's app registry, settings, or a protocol adapter."
        )


def test_domain_kernels_do_not_import_each_other_outside_bridges():
    """Cross-kernel imports are opt-in bridges, never domain implementation."""
    violations = []
    for owner in sorted(DOMAIN_KERNEL_PACKAGES):
        package_root = PACKAGES_ROOT / owner
        for path in _py_files(package_root, skip_parts={"tests"}):
            relative_parts = set(path.relative_to(package_root).parts)
            if relative_parts & {"adapters", "contrib"}:
                continue
            for line, module in _imports(path):
                parts = module.split(".")
                if len(parts) < 2 or parts[0] != "shopman" or parts[1] not in DOMAIN_KERNEL_PACKAGES - {owner}:
                    continue
                violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Domain kernels imported another kernel outside adapters/contrib:\n"
            f"{_format_violations(violations)}\n\n"
            "Move the integration to an optional adapter/contrib bridge or to the orchestrator."
        )


def test_doorman_identity_port_has_no_legacy_contract_residue():
    """The identity cut is atomic: old names cannot silently become a second API."""
    roots = (
        PACKAGES_ROOT / "doorman" / "shopman" / "doorman",
        PACKAGES_ROOT / "guestman" / "shopman" / "guestman" / "adapters" / "auth.py",
    )
    forbidden = (
        "AuthCustomerInfo",
        "CustomerResolver",
        "CUSTOMER_RESOLVER_CLASS",
        "get_by_phone",
        "get_by_email",
        "get_by_identifier",
        "target_kind",
        "lock_active_by_uuid",
        "resolve_customer_by_",
        "normalize_login_target",
        "LEGACY_CROSS_KERNEL_DEBT",
        "backward compat",
        "backward-compat",
        "backward_compat",
        "protocols.customer",
    )
    violations: list[str] = []
    for root in roots:
        paths = (root,) if root.is_file() else _py_files(root, skip_parts={"tests"})
        for path in paths:
            text = path.read_text()
            violations.extend(
                f"{path.relative_to(REPO_ROOT)}: {token}"
                for token in forbidden
                if token in text
            )
    assert not violations, "Legacy Doorman identity contract residue:\n" + "\n".join(violations)


def test_concierge_identity_paths_import_only_host_composition():
    """WP-4 identity paths in the storefront cannot import Guestman directly."""
    guarded = (
        STOREFRONT_ROOT / "concierge" / "tools.py",
        STOREFRONT_ROOT / "concierge" / "transport.py",
    )
    violations = [
        (path, line, module)
        for path in guarded
        for line, module in _imports(path)
        if _matches_prefix(module, ("shopman.guestman",))
    ]
    assert not violations, (
        "Concierge identity must cross the shop composition facade:\n"
        + _format_violations(violations)
    )


def test_surfaces_do_not_import_each_other():
    """storefront and backstage are sibling surfaces and must not cross-import."""
    checks = (
        (STOREFRONT_ROOT, ("shopman.backstage",)),
        (BACKSTAGE_ROOT, ("shopman.storefront",)),
    )
    violations = []
    for root, forbidden in checks:
        for path in _py_files(root, skip_parts={"tests"}):
            for line, module in _imports(path):
                if _matches_prefix(module, forbidden):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Cross-surface imports found:\n"
            f"{_format_violations(violations)}\n\n"
            "Use shop-level orchestration or a shared kernel contract instead."
        )


def test_shop_imports_surfaces_only_through_adapters():
    """The orchestrator core may touch surfaces only in shop/adapters/."""
    violations = []
    for path in _py_files(SHOP_ROOT, skip_parts={"adapters", "tests"}):
        for line, module in _imports(path):
            if _matches_prefix(module, ("shopman.storefront", "shopman.backstage")):
                violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Direct surface imports found in shop outside adapters:\n"
            f"{_format_violations(violations)}\n\n"
            "Keep surface integration inside shop/adapters/."
        )


def test_framework_does_not_import_protected_kernel_internals():
    """Framework code should consume kernel package APIs, not internals."""
    violations = []
    for root in SURFACE_ROOTS:
        for path in _py_files(root, skip_parts={"tests"}):
            for line, module in _imports(path):
                parts = module.split(".")
                if (
                    len(parts) >= 4
                    and parts[0] == "shopman"
                    and parts[1] in PROTECTED_KERNEL_PACKAGES
                    and parts[2] in {"models", "contrib"}
                ):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Framework imported protected kernel internals:\n"
            f"{_format_violations(violations)}\n\n"
            "Use package-level exports, public services, settings, or protocol "
            "adapters instead of models.<submodule> or contrib.<submodule> imports."
        )


def test_surfaces_do_not_import_orderman_write_primitives():
    """Surfaces must create/modify/commit sessions through shop services."""
    forbidden = (
        "shopman.orderman.ids",
        "shopman.orderman.services.commit",
        "shopman.orderman.services.modify",
    )
    violations = []
    for root in (STOREFRONT_ROOT, BACKSTAGE_ROOT):
        for path in _py_files(root, skip_parts={"tests", "presentation"}):
            for line, module in _imports(path):
                if _matches_prefix(module, forbidden):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Surfaces imported Orderman write primitives directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Use shopman.shop.services.sessions or shopman.shop.services.checkout "
            "so session writes have one canonical orchestration path."
        )


def test_backstage_views_do_not_drive_order_lifecycle_directly():
    """Backstage HTTP views must delegate order lifecycle mutations to shop services."""
    violations = []
    forbidden_imports = (
        "shopman.orderman",
        "shopman.shop.lifecycle",
        "shopman.craftsman.services",
        "shopman.stockman",
    )

    for path in _py_files(BACKSTAGE_ROOT / "views"):
        for line, module in _imports(path):
            if _matches_prefix(module, forbidden_imports):
                violations.append((path, line, module))

        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "transition_status":
                    violations.append((path, node.lineno, "transition_status"))

    if violations:
        pytest.fail(
            "Backstage views drove order lifecycle directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Move operator/KDS/production mutations into shopman.shop.services and keep "
            "views focused on HTTP, permissions, and rendering."
        )


def test_storefront_api_delegates_kernel_mutations():
    """Storefront public APIs must keep kernel reads/writes behind services."""
    forbidden = (
        "shopman.guestman",
        "shopman.doorman",
        "shopman.orderman",
        "shopman.offerman",
        "shopman.stockman",
        "shopman.payman",
        "shopman.craftsman",
    )
    violations = []

    for path in _py_files(STOREFRONT_ROOT / "api"):
        for line, module in _imports(path):
            if _matches_prefix(module, forbidden):
                violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Storefront APIs imported kernel modules directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Route API reads and mutations through shopman.shop.services.* or "
            "surface-local projection services when no orchestration is needed."
        )


def test_storefront_surface_reads_delegate_kernel_domains():
    """Storefront services/projections/intents must read kernels through shop services."""
    forbidden = (
        "shopman.guestman",
        "shopman.doorman",
        "shopman.orderman",
        "shopman.offerman",
        "shopman.stockman",
        "shopman.payman",
        "shopman.craftsman",
    )
    roots = (
        STOREFRONT_ROOT / "services",
        STOREFRONT_ROOT / "presentation",
        STOREFRONT_ROOT / "intents",
    )
    violations = []

    for root in roots:
        for path in _py_files(root):
            for line, module in _imports(path):
                if _matches_prefix(module, forbidden):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Storefront service/projection/intent modules imported kernel modules directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Route domain reads and mutations through shopman.shop.services.* so "
            "surface modules stay HTTP/template/read-model adapters."
        )


def test_storefront_keeps_customer_auth_mutations_in_shop_services():
    """Customer auth/access/device mutations belong to the orchestrator."""
    forbidden_service_modules = (
        STOREFRONT_ROOT / "services" / "auth.py",
        STOREFRONT_ROOT / "services" / "access.py",
        STOREFRONT_ROOT / "services" / "devices.py",
    )
    violations = [
        (path, 1, "shopman.storefront.services")
        for path in forbidden_service_modules
        if path.exists()
    ]

    if violations:
        pytest.fail(
            "Storefront reintroduced customer auth/access/device mutation services:\n"
            f"{_format_violations(violations)}\n\n"
            "Use shopman.shop.services.auth/access/devices so Doorman and Guestman "
            "coordination has one canonical orchestration path."
        )


def test_storefront_keeps_checkout_mutations_in_shop_services():
    """Checkout commit and post-commit coordination belongs to the orchestrator."""
    forbidden_service_modules = (
        STOREFRONT_ROOT / "services" / "checkout.py",
        STOREFRONT_ROOT / "services" / "checkout_defaults.py",
        STOREFRONT_ROOT / "services" / "ifood_simulation.py",
    )
    violations = [
        (path, 1, "shopman.storefront.services")
        for path in forbidden_service_modules
        if path.exists()
    ]

    if violations:
        pytest.fail(
            "Storefront reintroduced checkout mutation services:\n"
            f"{_format_violations(violations)}\n\n"
            "Use shopman.shop.services.checkout/checkout_defaults/ifood_simulation "
            "so checkout commit, customer persistence, and simulated marketplace "
            "ingest have one canonical orchestration path."
        )


def test_storefront_checkout_intent_delegates_domain_resolution():
    """Checkout intent parsing must not resolve kernel domains directly."""
    path = STOREFRONT_ROOT / "intents" / "checkout.py"
    forbidden = (
        "shopman.guestman",
        "shopman.offerman",
        "shopman.stockman",
        "shopman.orderman",
    )
    violations = []

    for line, module in _imports(path):
        if _matches_prefix(module, forbidden):
            violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Storefront checkout intent imported kernel modules directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Keep request/form interpretation in storefront and route customer, "
            "catalog, stock, and loyalty resolution through "
            "shopman.shop.projections.checkout_context."
        )


def test_storefront_cart_intent_delegates_product_resolution():
    """Cart intent parsing must not resolve catalog/stock domains directly."""
    path = STOREFRONT_ROOT / "intents" / "cart.py"
    forbidden = (
        "shopman.offerman",
        "shopman.stockman",
    )
    violations = []

    for line, module in _imports(path):
        if _matches_prefix(module, forbidden):
            violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Storefront cart intent imported catalog/stock modules directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Keep cart intent parsing in storefront and route product price "
            "resolution through shopman.shop.projections.cart_context."
        )


def test_storefront_cart_delegates_write_mutations():
    """Storefront cart adapter must call shop cart mutations."""
    path = STOREFRONT_ROOT / "cart.py"
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))

    forbidden_names = {
        "modify_session",
        "create_session",
        "abandon_session",
    }
    forbidden_availability = {"reserve", "reconcile"}
    violations: list[tuple[Path, int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "availability"
                and node.func.attr in forbidden_availability
            ):
                violations.append((path, node.lineno, f"availability.{node.func.attr}"))
            if node.func.attr in forbidden_names:
                violations.append((path, node.lineno, node.func.attr))

    if violations:
        pytest.fail(
            "Storefront cart performed write mutations directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Keep request/session adaptation in storefront.cart and route cart mutations "
            "through shopman.shop.services.cart."
        )


# O boundary "POS views delegam writes aos services" saiu com a view POS-HTMX
# (SURFACE-CONVERGENCE-PLAN WP1). O POS agora é o Nuxt sobre api/v1/backstage/pos/*,
# cuja camada de write são os próprios services (contrato headless adr-012/014).


# ──────────────────────────────────────────────────────────────────────
# ADR-014 §4.2 — the data/presentation cut (R-A · R-B · R-C · R-D)
#
# These codify the semantic boundary: data Projections (shop/projections/) carry
# only meaning; each surface's Presentation places appearance. See
# docs/decisions/adr-014-surface-data-presentation-cut.md and
# docs/_archive/redesign/04-architecture.md §4.2.
# ──────────────────────────────────────────────────────────────────────


def _string_constants(tree: ast.AST) -> Iterable[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def test_presentation_reads_only_the_read_side():
    """R-A · ``<surface>/presentation/`` may read ``shop.projections`` but never
    ``shop.services`` (write-side). Mutation stays in views/intents."""
    violations: list[tuple[Path, int, str]] = []
    for root in PRESENTATION_ROOTS:
        if not root.exists():
            continue
        for path in _py_files(root, skip_parts={"tests"}):
            for line, module in _imports(path):
                if _matches_prefix(module, ("shopman.shop.services",)):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Presentation imported the write-side (shop.services):\n"
            f"{_format_violations(violations)}\n\n"
            "Presentation consumes only shop.projections (Projection + Action). "
            "Route mutations through views/intents calling shop.services."
        )


def test_read_side_does_not_write():
    """GET/projection code must be observational, including during SSR/polling."""
    violations: list[tuple[Path, int, str]] = []
    for root in READ_SIDE_ROOTS:
        if not root.exists():
            continue
        for path in _py_files(root, skip_parts={"tests"}):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                chain = ast.unparse(node.func.value)
                if node.func.attr in ORM_MUTATION_METHODS and ".objects" in chain:
                    violations.append((path, node.lineno, f"{chain}.{node.func.attr}()"))
                elif node.func.attr in {"save", "delete"}:
                    violations.append((path, node.lineno, f"{chain}.{node.func.attr}()"))

    if violations:
        pytest.fail(
            "Read-side code performed writes:\n"
            f"{_format_violations(violations)}\n\n"
            "Move allocation/mutation to an explicit command service reached by POST; "
            "GET and Projection builders only read."
        )


def test_get_handlers_do_not_invoke_commands_or_write():
    """HTTP GET/SSE delivery may assemble a read model but never mutate it.

    Duas redes: a chamada com cara de escrita (prefixo de mutação, ORM, módulo
    de comando), sem dívida nenhuma; e a escrita transitiva (o GET chama quem
    grava, a qualquer distância), contra o inventário do dia em que ela nasceu.
    """
    direct = [
        violation
        for root in API_ROOTS
        for path in _py_files(root, skip_parts={"tests"})
        for violation in _get_handler_write_calls(path)
        if violation[2] not in KNOWN_NON_MUTATING_GET_CALLS
    ]
    observed: dict[tuple[str, str], int] = {}
    transitive = []
    for path, line, call in _framework_graph().get_handler_writes(API_ROOTS):
        key = (path.relative_to(REPO_ROOT).as_posix(), call.split(" [", 1)[0])
        observed[key] = observed.get(key, 0) + 1
        if observed[key] > GET_WRITE_FOUND_BY_TRANSITIVE_GATE.get(key, 0):
            transitive.append((path, line, call))
    stale = sorted(
        f"  {path}: {call} (inventário diz {count}, achado {observed.get((path, call), 0)})"
        for (path, call), count in GET_WRITE_FOUND_BY_TRANSITIVE_GATE.items()
        if observed.get((path, call), 0) < count
    )
    violations = [*direct, *transitive]
    if violations:
        pytest.fail(
            "GET handlers invoked command-side code or direct writes:\n"
            f"{_format_violations(violations)}\n\n"
            "Expose an Action in the projection and invoke it through POST/command ingress, "
            "or move the effect to the lifecycle or the worker."
        )
    assert not stale, (
        "GET_WRITE_FOUND_BY_TRANSITIVE_GATE tem linha que não acontece mais; tire-a:\n" + "\n".join(stale)
    )


def test_read_side_never_writes():
    """Projeção e Presentation montam leitura; nenhuma função delas grava."""
    violations = _framework_graph().read_side_writers(READ_SIDE_ROOTS)
    if violations:
        pytest.fail(
            "Read-side functions write (directly or through what they call):\n"
            f"{_format_violations(violations)}"
        )


def test_get_write_detector_rejects_command_service(tmp_path):
    """Negative fixture: the gate catches the BlindPrepCode regression shape."""
    source = tmp_path / "regression.py"
    source.write_text(
        "from shopman.backstage.services.blind_prep_codes import allocate_blind_prep_codes\n"
        "class RegressedView:\n"
        "    def get(self, request):\n"
        "        allocate_blind_prep_codes(recipe_refs=(), selected_date=None)\n",
        encoding="utf-8",
    )

    violations = _get_handler_write_calls(source)
    assert [(line, call) for _, line, call in violations] == [(4, "allocate_blind_prep_codes")]


def _mutant_framework(tmp_path: Path, files: dict[str, str]) -> _FrameworkWriteGraph:
    root = tmp_path / "shopman" / "fake"
    for relative, source in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    return _FrameworkWriteGraph((root,), base=tmp_path)


_MUTANT_COMMAND = (
    "def tidy(order):\n"
    "    order.data['tidied'] = True\n"
    "    order.save(update_fields=['data'])\n"
    "\n"
    "def tidy_later(order):\n"
    "    tidy(order)\n"
    "\n"
    "def describe(order):\n"
    "    return {'ref': order.ref}\n"
)


def test_get_write_detector_catches_a_write_behind_a_service_without_command_name(tmp_path):
    """Mutante: um GET novo que grava por um serviço de nome inocente reprova.

    ``tidy`` não tem prefixo de mutação e o módulo não está em
    ``COMMAND_SERVICE_MODULES``: a rede antiga deixava passar. A transitiva
    pega a chamada direta, a de duas voltas e o import por função, e não acusa
    a leitura pura do mesmo módulo.
    """
    graph = _mutant_framework(
        tmp_path,
        {
            "services/orders.py": _MUTANT_COMMAND,
            "api/views.py": (
                "from shopman.fake.services import orders as order_service\n"
                "from shopman.fake.services.orders import tidy_later\n"
                "\n"
                "class TrackingView:\n"
                "    def get(self, request, ref):\n"
                "        order = request.order\n"
                "        order_service.tidy(order)\n"
                "        tidy_later(order)\n"
                "        return order_service.describe(order)\n"
                "\n"
                "    def post(self, request, ref):\n"
                "        order_service.tidy(request.order)\n"
            ),
        },
    )

    found = [(line, call) for _path, line, call in graph.get_handler_writes((tmp_path / "shopman" / "fake" / "api",))]
    assert found == [
        (7, "order_service.tidy [orders.tidy -> order.save]"),
        (8, "tidy_later [orders.tidy_later -> orders.tidy -> order.save]"),
    ]
    assert _get_handler_write_calls(tmp_path / "shopman" / "fake" / "api" / "views.py") == []


def test_read_side_detector_catches_a_projection_that_writes(tmp_path):
    """Mutante: a projeção que chama quem grava reprova; a que só lê, não."""
    graph = _mutant_framework(
        tmp_path,
        {
            "services/orders.py": _MUTANT_COMMAND,
            "projections/tracking.py": (
                "from shopman.fake.services import orders\n"
                "\n"
                "def build_tracking(order):\n"
                "    orders.tidy_later(order)\n"
                "    return orders.describe(order)\n"
                "\n"
                "def build_summary(order):\n"
                "    return orders.describe(order)\n"
            ),
        },
    )

    found = [call for _path, _line, call in graph.read_side_writers((tmp_path / "shopman" / "fake" / "projections",))]
    assert found == ["build_tracking [tracking.build_tracking -> orders.tidy_later -> orders.tidy -> order.save]"]


def test_session_and_workbook_writes_are_told_apart(tmp_path):
    """A sessão é escrita; ``workbook.save(stream)`` e ``dict.update`` não são."""
    graph = _mutant_framework(
        tmp_path,
        {
            "services/misc.py": (
                "def remember(request):\n"
                "    request.session['k'] = 1\n"
                "\n"
                "def forget(request):\n"
                "    request.session.pop('k', None)\n"
                "\n"
                "def export(book, stream):\n"
                "    book.save(stream)\n"
                "\n"
                "def merge(data, extra):\n"
                "    data.update(extra)\n"
                "    return data\n"
            ),
        },
    )

    assert {name for _module, name in graph.writers} == {"remember", "forget"}


# Tailwind colour/tone design-token classes — appearance, owned by each
# surface's Presentation (rule R-B keeps them out of the data read-side).
_TONE_CLASS_RE = re.compile(
    r"\b(?:bg|text|border)-(?:info|warning|success|danger|muted|surface-alt)\b"
    r"|text-on-surface"
)
# Money/locale formatting and template/HTML helpers are appearance, not data.
_BANNED_PROJECTION_IMPORTS = (
    "shopman.utils.monetary",  # format_money — presentation
    "django.template",
    "django.utils.html",
)


def test_data_projections_carry_no_appearance():
    """R-B · ``shop/projections/`` does not import money/locale/template/HTML
    helpers, nor embed Tailwind colour-token classes (appearance lives in the
    surface Presentation).

    NOTE: the broader "no PT-BR UX copy literal" half of R-B is *not* enforced
    yet — Action labels and confirmation copy still live in
    catalog_context/cart/checkout/payment_status/storefront_context/
    order_tracking. Draining those into OmotenashiCopy is the remaining S7 work
    (see project_wp7_pos_status / docs/_archive/redesign/04-architecture.md §S7).
    """
    violations: list[tuple[Path, int, str]] = []
    for path in _py_files(PROJECTIONS_ROOT, skip_parts={"tests"}):
        for line, module in _imports(path):
            if _matches_prefix(module, _BANNED_PROJECTION_IMPORTS):
                violations.append((path, line, f"import {module}"))
        tree = ast.parse(path.read_text(), filename=str(path))
        for line, value in _string_constants(tree):
            if _TONE_CLASS_RE.search(value):
                violations.append((path, line, f"tailwind colour class: {value!r}"))

    if violations:
        pytest.fail(
            "Data Projections carried appearance (rule R-B):\n"
            f"{_format_violations(violations)}\n\n"
            "Keep shop/projections semantic: emit a Tone enum (mapped to classes "
            "by each surface) and format money/copy in the Presentation."
        )


def test_data_projections_are_frozen_and_channel_agnostic():
    """R-C · ``shop/projections/`` dataclasses are ``frozen=True`` and the
    read-side ignores the HTTP/render channel (no ``django.http``)."""
    violations: list[tuple[Path, int, str]] = []
    for path in _py_files(PROJECTIONS_ROOT, skip_parts={"tests"}):
        for line, module in _imports(path):
            if _matches_prefix(module, ("django.http",)):
                violations.append((path, line, f"import {module}"))
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for deco in node.decorator_list:
                target = deco.func if isinstance(deco, ast.Call) else deco
                if not (isinstance(target, ast.Name) and target.id == "dataclass"):
                    continue
                frozen = isinstance(deco, ast.Call) and any(
                    kw.arg == "frozen"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                    for kw in deco.keywords
                )
                if not frozen:
                    violations.append((path, node.lineno, f"non-frozen dataclass {node.name}"))

    if violations:
        pytest.fail(
            "Data Projections were mutable or channel-aware (rule R-C):\n"
            f"{_format_violations(violations)}\n\n"
            "Mark every shop/projections dataclass frozen=True and keep "
            "django.http out of the read-side."
        )


def test_no_second_card_shape_returns():
    """R-D · the retired second card shape and its parallel template stay gone."""
    forbidden = (
        FRAMEWORK_ROOT / "storefront" / "presentation" / "product_cards.py",
        FRAMEWORK_ROOT / "storefront" / "projections" / "product_cards.py",
        STOREFRONT_ROOT / "templates" / "storefront" / "components" / "availability_preview.html",
    )
    existing = [p for p in forbidden if p.exists()]
    # Belt-and-suspenders: also catch a relocated product_cards.py anywhere.
    existing += [
        p for p in FRAMEWORK_ROOT.rglob("product_cards.py") if "__pycache__" not in p.parts
    ]
    if existing:
        listed = "\n".join(f"  {p.relative_to(REPO_ROOT)}" for p in sorted(set(existing)))
        pytest.fail(
            "A retired second card shape/template reappeared (rule R-D):\n"
            f"{listed}\n\n"
            "There is one card shape; do not reintroduce product_cards.py or "
            "availability_preview.html."
        )
