"""Inventário de receitas — API headless (``/api/v1/backstage/recipes/*``).

A porta HTTP do RECIPE-INVENTORY-PLAN §8, consumida pelo app de Produção
(``surfaces/production-nuxt``, telas ``/recipes``). Cada view lê o corpo,
chama a orquestração fina (``services.recipe_book``) e devolve a projection
(``projections.recipe_book``) já formatada.

Permissão: **ler** é o gate do app de Produção (``backstage.operate_production``,
ou ver a ficha); **escrever** é ``shop.manage_production`` (ou mudar a ficha),
a mesma régua de "mexer acontece no app de Produção". A régua vive em
``resolve_recipe_book_access``; aqui só se pergunta.

A estrela (``recipes/<ref>/favorite/``) é preferência do operador, não edição
da receita: marcar e desmarcar pedem só a leitura, e a resposta de leitura
traz ``is_favorite`` de quem pediu (o ``username``, o mesmo de ``_actor``).
A nota (``recipes/<ref>/versions/<n>/rating/``) segue a mesma régua: é a
opinião de quem prova, não edição da receita, então basta a leitura.

As referências externas (livros, vídeos, artigos) vão no ``PATCH`` da receita
(``external_references``, a lista inteira), com a régua de escrita.

Erros no dialeto canônico ``{detail, field, errors}``: campo inválido é 400
com ``field``; estado (versão que não é rascunho, receita arquivada) é 409;
receita ou versão inexistente é 404; leitura por IA sem credencial é 503 e
provedor em falha é 502 (o mesmo mapeamento do ``CatalogAiAssistView``).
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.craftsman.models import ProductionMode

from shopman.backstage.projections.recipe_book import (
    build_capture_draft,
    build_formula_lens,
    build_ingredient_options,
    build_recipe_book,
    build_recipe_compare,
    build_recipe_entry,
    build_recipe_reference,
    build_recipe_review_queue,
    build_recipe_sheet,
    build_recipe_sheet_list,
    resolve_recipe_book_access,
    wire_formula,
)
from shopman.backstage.services import recipe_book as recipe_book_service
from shopman.backstage.services import recipe_favorites, recipe_ratings, recipe_review
from shopman.backstage.services.exceptions import (
    RecipeBookServiceError,
    RecipeEntryNotFound,
    RecipeSheetNotFound,
    RecipeVersionNotFound,
)
from shopman.backstage.services.recipe_capture import RecipeCaptureError, RecipeCaptureNotConfigured
from shopman.shop.observability import ServerTimingMixin
from shopman.shop.services.remote_mutations import (
    RemoteMutationConflict,
    RemoteMutationInProgress,
    mutation_fingerprint,
    run_idempotent_mutation,
)

from .permissions import HasBackstagePermission
from .projections import projection_data

_MSG_VIEW = "O inventário de receitas exige backstage.operate_production."
_MSG_EDIT = "Alterar o inventário de receitas exige shop.manage_production."

#: Códigos do Craftsman que são conflito de ESTADO, não de campo: 409, não 400.
_STATE_CONFLICT_CODES = (
    "VERSION_NOT_DRAFT",
    "ENTRY_ARCHIVED",
    "NO_ACTIVE_CRITERIA",
    "RECIPE_CHANGED",
    "REVIEW_NOT_CURRENT",
)

_KINDS = ("bread", "viennoiserie", "sweet_dough", "cookie", "filling", "cream", "sauce", "beverage", "other")
_RECIPE_SORTS = ("updated", "name", "kind")
#: Ordenação do cadastro direto da ficha de execução.
_RECIPE_SHEET_SORTS = ("updated", "name", "output", "active")
#: ``?mode=`` do inventário e das fichas: os valores de ``ProductionMode``.
_PRODUCTION_MODES = tuple(str(value) for value in ProductionMode.values)


def _positive_int(value, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def _actor(request) -> str:
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "operator"


def _service_error_response(exc: RecipeBookServiceError) -> Response:
    """``RecipeBookServiceError`` no dialeto canônico: 409 para estado, 400 com ``field`` para campo."""
    if exc.code in _STATE_CONFLICT_CODES:
        return Response({"detail": exc.detail, "error": {"code": exc.code.lower()}}, status=409)
    payload: dict = {"detail": exc.detail}
    if exc.field:
        payload["field"] = exc.field
        payload["errors"] = {exc.field: [exc.detail]}
    return Response(payload, status=400)


def _kind_of(value) -> str:
    kind = str(value or "").strip()
    return kind if kind in _KINDS else "other"


class _RecipeBookBase(APIView):
    """Gate do inventário: da casa (``HasBackstagePermission``) e com leitura; escrita pede mais.

    ``requires_edit = True`` nas views que escrevem ou que são ferramenta do
    editor (prévia da lente, padronizar, leitura por IA): quem não pode editar
    não tem o editor para abrir.
    """

    permission_classes = [HasBackstagePermission]
    requires_edit = False
    enforce_view = True

    def check_permissions(self, request) -> None:
        super().check_permissions(request)
        access = resolve_recipe_book_access(request.user)
        if self.enforce_view and not access.can_view:
            raise PermissionDenied(_MSG_VIEW)
        if self.requires_edit and not access.can_edit:
            raise PermissionDenied(_MSG_EDIT)
        self.access = access

    def _entry(self, ref: str):
        try:
            return recipe_book_service.get_entry(ref)
        except RecipeEntryNotFound as exc:
            raise NotFound(str(exc)) from exc

    def _version(self, entry, number: int):
        try:
            return recipe_book_service.get_version(entry, number)
        except RecipeVersionNotFound as exc:
            raise NotFound(str(exc)) from exc

    def _entry_payload(self, ref: str) -> dict:
        return projection_data(build_recipe_entry(ref, operator_ref=_actor(self.request)))

    def _entry_and_version_payload(self, ref: str, number: int) -> dict:
        entry = build_recipe_entry(ref, operator_ref=_actor(self.request))
        version = next((v for v in entry.versions if v.number == number), None)
        return {"entry": projection_data(entry), "version": projection_data(version)}

    def _sheet(self, ref: str):
        """A ficha de execução pelo ref, ou 404 — o cadastro direto, fora do inventário."""
        try:
            return recipe_book_service.get_sheet(ref)
        except RecipeSheetNotFound as exc:
            raise NotFound(str(exc)) from exc

    def _sheet_payload(self, ref: str) -> dict:
        return projection_data(build_recipe_sheet(ref))


# ── Acesso ───────────────────────────────────────────────────────────────────


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Recipe book access probe",
        responses={200: OpenApiResponse(description="can_view / can_edit / capture_available.")},
    ),
)
class RecipeBookAccessView(_RecipeBookBase):
    """A sonda do rail: responde o que o operador pode, sem recusar quem não pode ver."""

    enforce_view = False

    def get(self, request):
        return Response({"access": projection_data(self.access)})


# ── Inventário ───────────────────────────────────────────────────────────────


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Recipe book inventory",
        responses={200: OpenApiResponse(description="Entry cards, kind options and access.")},
    ),
    post=extend_schema(
        tags=["backstage"],
        summary="Create a recipe entry (optionally with a first draft)",
        responses={201: OpenApiResponse(description="The entry with its versions.")},
    ),
)
class RecipeBookListView(ServerTimingMixin, _RecipeBookBase):
    def get(self, request):
        kind = str(request.query_params.get("kind") or "").strip()
        if kind and kind not in _KINDS:
            return Response(
                {"detail": f"Tipo de receita desconhecido; use um de: {', '.join(_KINDS)}.", "field": "kind",
                 "errors": {"kind": ["Tipo de receita desconhecido."]}},
                status=400,
            )
        sort = str(request.query_params.get("sort") or "updated").strip()
        if sort not in _RECIPE_SORTS:
            return Response(
                {"detail": "Ordenação desconhecida.", "field": "sort", "errors": {"sort": ["Ordenação desconhecida."]}},
                status=400,
            )
        mode = str(request.query_params.get("mode") or "").strip()
        if mode and mode not in _PRODUCTION_MODES:
            return Response(
                {"detail": "Modo de produção desconhecido.", "field": "mode", "errors": {"mode": ["Modo de produção desconhecido."]}},
                status=400,
            )
        book = build_recipe_book(
            query=request.query_params.get("q", ""),
            kind=kind,
            archived=request.query_params.get("archived", "") in ("1", "true", "yes"),
            operator_ref=_actor(request),
            only_without_sku=request.query_params.get("without_sku", "") in ("1", "true", "yes"),
            only_with_draft=request.query_params.get("with_draft", "") in ("1", "true", "yes"),
            only_favorites=request.query_params.get("favorites", "") in ("1", "true", "yes"),
            only_unreviewed=request.query_params.get("unreviewed", "") in ("1", "true", "yes"),
            production_mode=mode,
            sort=sort,
            page=_positive_int(request.query_params.get("page"), default=1, maximum=100000),
            page_size=_positive_int(request.query_params.get("page_size"), default=48, maximum=100),
        )
        return Response({"book": projection_data(book), "access": projection_data(self.access)})

    def post(self, request):
        if not self.access.can_edit:
            raise PermissionDenied(_MSG_EDIT)
        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize o cadastro e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({"version": 1, "actor": request.user.pk, "operation": "recipe-create"})
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                entry, _version = recipe_book_service.create_entry_from_payload(data, actor=_actor(request))
            except RecipeVersionNotFound as exc:
                return {"detail": str(exc), "outcome": "not_applied"}, 404
            except RecipeBookServiceError as exc:
                response = _service_error_response(exc)
                return {**dict(response.data), "outcome": "not_applied"}, response.status_code
            return {
                "ok": True,
                "outcome": "applied",
                "entry": self._entry_payload(entry.ref),
                "resource": {"kind": "recipe", "ref": entry.ref},
            }, 201

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outro cadastro.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Cadastro em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


# ── Receita ──────────────────────────────────────────────────────────────────


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Recipe entry detail (all versions, newest first)",
        responses={200: OpenApiResponse(description="Entry, versions with lens, access.")},
    ),
    patch=extend_schema(
        tags=["backstage"],
        summary="Edit a recipe entry (name, kind, SKU, notes, archive, external references)",
        responses={200: OpenApiResponse(description="The entry with its versions.")},
    ),
)
class RecipeEntryView(_RecipeBookBase):
    def get(self, request, ref: str):
        try:
            entry = build_recipe_entry(ref, operator_ref=_actor(request))
        except RecipeEntryNotFound as exc:
            raise NotFound(str(exc)) from exc
        return Response({"entry": projection_data(entry), "access": projection_data(self.access)})

    def patch(self, request, ref: str):
        if not self.access.can_edit:
            raise PermissionDenied(_MSG_EDIT)
        entry = self._entry(ref)
        try:
            recipe_book_service.patch_entry(entry, request.data)
        except RecipeBookServiceError as exc:
            return _service_error_response(exc)
        return Response({"entry": self._entry_payload(entry.ref)})


class RecipeExecutionView(_RecipeBookBase):
    """Configuração operacional da ficha; fórmula e ingredientes não passam aqui."""

    requires_edit = True

    def patch(self, request, ref: str):
        entry = self._entry(ref)
        try:
            recipe_book_service.update_execution(entry, request.data, actor=_actor(request))
        except RecipeEntryNotFound as exc:
            raise NotFound(str(exc)) from exc
        except RecipeBookServiceError as exc:
            return _service_error_response(exc)
        return Response({"entry": self._entry_payload(entry.ref)})


class RecipeDuplicateView(_RecipeBookBase):
    """Duplica uma versão para um rascunho novo, uma vez por intenção."""

    requires_edit = True

    def post(self, request, ref: str):
        entry = self._entry(ref)
        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a receita e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({"version": 1, "actor": request.user.pk, "operation": f"recipe-duplicate:{ref}"})
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                copied, _version = recipe_book_service.duplicate_entry(entry, data, actor=_actor(request))
            except RecipeVersionNotFound as exc:
                return {"detail": str(exc), "outcome": "not_applied"}, 404
            except RecipeBookServiceError as exc:
                response = _service_error_response(exc)
                return {**dict(response.data), "outcome": "not_applied"}, response.status_code
            return {
                "ok": True,
                "outcome": "applied",
                "entry": self._entry_payload(copied.ref),
                "resource": {"kind": "recipe", "ref": copied.ref},
            }, 201

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outra cópia.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Cópia em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Mark a recipe entry as a favorite of the current operator (idempotent)",
        responses={200: OpenApiResponse(description="ref and is_favorite.")},
    ),
    delete=extend_schema(
        tags=["backstage"],
        summary="Unmark a favorite recipe entry of the current operator (idempotent)",
        responses={200: OpenApiResponse(description="ref and is_favorite.")},
    ),
)
class RecipeFavoriteView(_RecipeBookBase):
    """A estrela do operador: marcar e desmarcar, os dois idempotentes.

    É preferência de quem lê, então pede só a leitura do inventário (quem não
    edita também escolhe as suas). Receita inexistente é 404; arquivada aceita a
    estrela, porque arquivar não apaga o gosto de ninguém.
    """

    def post(self, request, ref: str):
        entry = self._entry(ref)
        return Response({"ref": entry.ref, "is_favorite": recipe_favorites.mark(_actor(request), entry.ref)})

    def delete(self, request, ref: str):
        entry = self._entry(ref)
        return Response({"ref": entry.ref, "is_favorite": recipe_favorites.unmark(_actor(request), entry.ref)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="The baker's check queue: current versions not confirmed yet, best sellers first",
        responses={200: OpenApiResponse(description="queue + access.")},
    ),
)
class RecipeReviewQueueView(_RecipeBookBase):
    """A fila do padeiro (WP-RECEITAS-DA-CASA F2). Leitura do inventário basta para ver."""

    def get(self, request):
        return Response({
            "queue": projection_data(build_recipe_review_queue()),
            "access": projection_data(self.access),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Confirm the version in use was checked by someone from the house",
        responses={200: OpenApiResponse(description="The entry with the signed check.")},
    ),
)
class RecipeVersionReviewView(_RecipeBookBase):
    """"Está certa": assina a conferência da versão em uso (``meta["review"]``).

    Pede a escrita do inventário: conferir é declarar a receita da casa. Repetir
    renova o carimbo, então não precisa de chave de intenção.
    """

    requires_edit = True

    def post(self, request, ref: str, number: int):
        entry = self._entry(ref)
        version = self._version(entry, number)
        user = request.user
        name = (user.get_full_name() if hasattr(user, "get_full_name") else "") or _actor(request)
        try:
            recipe_review.confirm(version, actor=_actor(request), actor_name=name)
        except RecipeBookServiceError as exc:
            return _service_error_response(exc)
        return Response({"entry": self._entry_payload(entry.ref), "ok": True})


@extend_schema_view(
    put=extend_schema(
        tags=["backstage"],
        summary="Rate a closed version 0 to 5 per active criterion (one rating per operator, replaced on re-rate)",
        responses={200: OpenApiResponse(description="The entry with its versions and ratings.")},
    ),
)
class RecipeVersionRatingView(_RecipeBookBase):
    """A nota do operador para uma versão FECHADA: ``{"scores": {"<id do critério>": 0..5}}``.

    Uma nota para cada critério ativo, nem mais nem menos (400 com ``field``).
    Rascunho é 409: ainda muda. Avaliar de novo substitui a avaliação anterior
    do mesmo operador. Pede só a leitura, como a estrela.
    """

    def put(self, request, ref: str, number: int):
        entry = self._entry(ref)
        version = self._version(entry, number)
        data = request.data if isinstance(request.data, dict) else {}
        try:
            recipe_ratings.rate(_actor(request), version, data.get("scores"))
        except RecipeBookServiceError as exc:
            return _service_error_response(exc)
        return Response({"entry": self._entry_payload(entry.ref)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Create a draft version (from scratch or copied from another version)",
        responses={201: OpenApiResponse(description="Entry and the new draft.")},
    ),
)
class RecipeVersionCreateView(_RecipeBookBase):
    requires_edit = True

    def post(self, request, ref: str):
        entry = self._entry(ref)
        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a receita e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({"version": 1, "actor": request.user.pk, "operation": f"recipe-version-create:{ref}"})
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                version = recipe_book_service.create_version_from_payload(entry, data, actor=_actor(request))
            except RecipeVersionNotFound as exc:
                return {"detail": str(exc), "outcome": "not_applied"}, 404
            except RecipeBookServiceError as exc:
                response = _service_error_response(exc)
                return {**dict(response.data), "outcome": "not_applied"}, response.status_code
            return {
                **self._entry_and_version_payload(entry.ref, version.number),
                "ok": True,
                "outcome": "applied",
                "resource": {"kind": "recipe-version", "ref": version.version_ref},
            }, 201

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outra versão.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Versão em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


@extend_schema_view(
    patch=extend_schema(
        tags=["backstage"],
        summary="Edit a draft version",
        responses={200: OpenApiResponse(description="Entry and the edited draft.")},
    ),
)
class RecipeVersionView(_RecipeBookBase):
    requires_edit = True

    def patch(self, request, ref: str, number: int):
        entry = self._entry(ref)
        version = self._version(entry, number)
        try:
            recipe_book_service.update_draft_from_payload(version, request.data)
        except RecipeBookServiceError as exc:
            return _service_error_response(exc)
        return Response(self._entry_and_version_payload(entry.ref, version.number))


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Publish a draft version (writes the execution sheet)",
        responses={200: OpenApiResponse(description="The entry with its versions.")},
    ),
)
class RecipeVersionPublishView(_RecipeBookBase):
    requires_edit = True

    def post(self, request, ref: str, number: int):
        entry = self._entry(ref)
        version = self._version(entry, number)
        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a receita e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({
            "version": 1,
            "actor": request.user.pk,
            "operation": f"recipe-version-publish:{ref}:{number}",
        })
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                recipe_book_service.publish(version, data, actor=_actor(request))
            except RecipeBookServiceError as exc:
                response = _service_error_response(exc)
                return {**dict(response.data), "outcome": "not_applied"}, response.status_code
            return {
                "entry": self._entry_payload(entry.ref),
                "ok": True,
                "outcome": "applied",
                "resource": {"kind": "recipe-version", "ref": version.version_ref},
            }, 200

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outra publicação.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Publicação em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


# ── Lente e padronização ─────────────────────────────────────────────────────


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Formula lens preview (baker's percentages, metrics, parts, final mix, BOM)",
        responses={200: OpenApiResponse(description="The lens over the given formula.")},
    ),
)
class FormulaLensView(_RecipeBookBase):
    requires_edit = True

    def post(self, request):
        formula = request.data.get("formula") if isinstance(request.data, dict) else None
        if not isinstance(formula, dict):
            return Response(
                {"detail": "A fórmula precisa ser um objeto.", "field": "formula",
                 "errors": {"formula": ["A fórmula precisa ser um objeto."]}},
                status=400,
            )
        kind = _kind_of(request.data.get("kind"))
        try:
            lens = build_formula_lens(formula, kind)
        except (TypeError, ValueError, AttributeError):
            return Response(
                {"detail": "Não foi possível ler a fórmula.", "field": "formula",
                 "errors": {"formula": ["Não foi possível ler a fórmula."]}},
                status=400,
            )
        return Response({"lens": projection_data(lens)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Standardize a formula to the house basis (anchor = basis_g)",
        responses={200: OpenApiResponse(description="The rewritten formula and its lens.")},
    ),
)
class FormulaStandardizeView(_RecipeBookBase):
    requires_edit = True

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        try:
            formula = recipe_book_service.standardize_formula(data.get("formula"), data.get("basis_g"))
        except RecipeBookServiceError as exc:
            return _service_error_response(exc)
        kind = _kind_of(data.get("kind"))
        return Response({
            "formula": wire_formula(formula),
            "lens": projection_data(build_formula_lens(formula, kind)),
        })


# ── Comparação, referência, insumos ──────────────────────────────────────────


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Compare two versions (a=<ref>@<n>, b=<ref>@<n>)",
        responses={200: OpenApiResponse(description="Rows and metrics side by side.")},
    ),
)
class RecipeCompareView(_RecipeBookBase):
    def get(self, request):
        a = str(request.query_params.get("a") or "").strip()
        b = str(request.query_params.get("b") or "").strip()
        for field, value in (("a", a), ("b", b)):
            if not value:
                return Response(
                    {"detail": f"Informe as duas versões a comparar ({field} ausente).", "field": field,
                     "errors": {field: ["Informe a versão no formato <ref>@<n>."]}},
                    status=400,
                )
        try:
            compare = build_recipe_compare(a, b)
        except ValueError as exc:
            return Response({"detail": str(exc), "field": "a", "errors": {"a": [str(exc)]}}, status=400)
        except (RecipeEntryNotFound, RecipeVersionNotFound) as exc:
            raise NotFound(str(exc)) from exc
        return Response({"compare": projection_data(compare)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Reference ranges from the literature for a recipe kind",
        responses={200: OpenApiResponse(description="Ranges per metric.")},
    ),
)
class RecipeReferenceView(_RecipeBookBase):
    def get(self, request):
        raw = str(request.query_params.get("kind") or "").strip()
        if raw and raw not in _KINDS:
            return Response(
                {"detail": f"Tipo de receita desconhecido; use um de: {', '.join(_KINDS)}.", "field": "kind",
                 "errors": {"kind": ["Tipo de receita desconhecido."]}},
                status=400,
            )
        return Response({"reference": projection_data(build_recipe_reference(raw or "other"))})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Ingredient options (materials and recipe entries with a formula)",
        responses={200: OpenApiResponse(description="Options for the ingredient picker.")},
    ),
)
class IngredientOptionsView(_RecipeBookBase):
    def get(self, request):
        options = build_ingredient_options(str(request.query_params.get("q") or ""))
        return Response({"options": projection_data(options)})


# ── Captura ──────────────────────────────────────────────────────────────────


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Read a recipe from a note or a photo (AI capture)",
        responses={
            200: OpenApiResponse(description="Structured draft with matched ingredients."),
            502: OpenApiResponse(description="The AI provider failed."),
            503: OpenApiResponse(description="No AI credential in this deployment."),
        },
    ),
)
class RecipeCaptureView(_RecipeBookBase):
    """Lê uma anotação ou foto e devolve o rascunho. Nada é gravado aqui.

    503 sem ``AI_ASSIST_API_KEY``: a tela mostra "sem leitura automática neste
    ambiente" e aponta a porta manual, não um erro.
    """

    requires_edit = True

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        text = str(data.get("text") or "").strip()
        image = data.get("image") if isinstance(data.get("image"), dict) else {}
        if not text and not str(image.get("data_base64") or "").strip():
            return Response(
                {"detail": "Envie uma anotação ou uma foto da receita.", "field": "text",
                 "errors": {"text": ["Envie uma anotação ou uma foto da receita."]}},
                status=400,
            )
        try:
            captured = recipe_book_service.capture(
                text=text, image=image, language_hint=str(data.get("language_hint") or ""),
            )
        except RecipeCaptureNotConfigured as exc:
            return Response({"detail": str(exc)}, status=503)
        except RecipeCaptureError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response({"draft": projection_data(build_capture_draft(captured))})


# ── Ficha de execução (craftsman.Recipe + RecipeItem) ────────────────────────


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Execution sheets inventory",
        responses={200: OpenApiResponse(description="Sheet cards, paging and access.")},
    ),
    post=extend_schema(
        tags=["backstage"],
        summary="Create an execution sheet (Recipe + RecipeItem)",
        responses={201: OpenApiResponse(description="The created sheet.")},
    ),
)
class RecipeSheetListView(_RecipeBookBase):
    """A lista de fichas de execução do zero; o cadastro que o inventário publica. """

    def get(self, request):
        sort = str(request.query_params.get("sort") or "updated").strip()
        if sort not in _RECIPE_SHEET_SORTS:
            return Response(
                {"detail": "Ordenação desconhecida.", "field": "sort", "errors": {"sort": ["Ordenação desconhecida."]}},
                status=400,
            )
        mode = str(request.query_params.get("mode") or "").strip()
        if mode and mode not in _PRODUCTION_MODES:
            return Response(
                {"detail": "Modo de produção desconhecido.", "field": "mode", "errors": {"mode": ["Modo de produção desconhecido."]}},
                status=400,
            )
        sheets = build_recipe_sheet_list(
            query=request.query_params.get("q", ""),
            active=request.query_params.get("active", ""),
            production_mode=mode,
            sort=sort,
            page=_positive_int(request.query_params.get("page"), default=1, maximum=100000),
            page_size=_positive_int(request.query_params.get("page_size"), default=48, maximum=100),
        )
        return Response({"sheets": projection_data(sheets), "access": projection_data(self.access)})

    def post(self, request):
        if not self.access.can_edit:
            raise PermissionDenied(_MSG_EDIT)
        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize o cadastro e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint({"version": 1, "actor": request.user.pk, "operation": "recipe-sheet-create"})
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                recipe = recipe_book_service.create_sheet_from_payload(data, actor=_actor(request))
            except RecipeBookServiceError as exc:
                response = _service_error_response(exc)
                return {**dict(response.data), "outcome": "not_applied"}, response.status_code
            return {
                "ok": True,
                "outcome": "applied",
                "sheet": self._sheet_payload(recipe.ref),
                "resource": {"kind": "recipe-sheet", "ref": recipe.ref},
            }, 201

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outro cadastro.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Cadastro em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Execution sheet detail",
        responses={200: OpenApiResponse(description="The sheet with items, mass balance and operation.")},
    ),
    patch=extend_schema(
        tags=["backstage"],
        summary="Edit an execution sheet (identity, items and operation)",
        responses={200: OpenApiResponse(description="The edited sheet.")},
    ),
)
class RecipeSheetView(_RecipeBookBase):
    """O detalhe da ficha e a edição: identidade, itens e operação numa gravação."""

    def get(self, request, ref: str):
        try:
            sheet = build_recipe_sheet(ref)
        except RecipeSheetNotFound as exc:
            raise NotFound(str(exc)) from exc
        return Response({"sheet": projection_data(sheet), "access": projection_data(self.access)})

    def patch(self, request, ref: str):
        if not self.access.can_edit:
            raise PermissionDenied(_MSG_EDIT)
        sheet = self._sheet(ref)
        try:
            recipe_book_service.update_sheet_from_payload(sheet, request.data, actor=_actor(request))
        except RecipeBookServiceError as exc:
            return _service_error_response(exc)
        return Response({"sheet": self._sheet_payload(ref)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Duplicate an execution sheet as an inactive copy",
        responses={201: OpenApiResponse(description="The copied sheet.")},
    ),
)
class RecipeSheetDuplicateView(_RecipeBookBase):
    """Duplica a ficha inteira como cópia inativa, uma vez por intenção."""

    requires_edit = True

    def post(self, request, ref: str):
        sheet = self._sheet(ref)
        data = dict(request.data or {})
        key = request.headers.get("Idempotency-Key") or data.pop("idempotencyKey", None)
        if not isinstance(key, str) or not key or len(key) > 128:
            return Response(
                {"detail": "Atualize a ficha e tente novamente.", "error": {"code": "intention_required"}},
                status=400,
            )
        scope = mutation_fingerprint(
            {"version": 1, "actor": request.user.pk, "operation": f"recipe-sheet-duplicate:{ref}"}
        )
        fingerprint = mutation_fingerprint({"scope": scope, "payload": data})

        def execute():
            try:
                copied = recipe_book_service.duplicate_sheet(sheet, data, actor=_actor(request))
            except RecipeBookServiceError as exc:
                response = _service_error_response(exc)
                return {**dict(response.data), "outcome": "not_applied"}, response.status_code
            return {
                "ok": True,
                "outcome": "applied",
                "sheet": self._sheet_payload(copied.ref),
                "resource": {"kind": "recipe-sheet", "ref": copied.ref},
            }, 201

        try:
            result = run_idempotent_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
            return Response(result.response_body, status=result.response_code)
        except RemoteMutationConflict:
            return Response(
                {"detail": "Esta tentativa já representa outra cópia.", "error": {"code": "intention_conflict"}},
                status=409,
            )
        except RemoteMutationInProgress:
            return Response(
                {"detail": "Cópia em processamento. Tente novamente em instantes.", "outcome": "unknown"},
                status=202,
            )
