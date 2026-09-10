"""Inventário de receitas — API headless (``/api/v1/backstage/recipes/*``).

A porta HTTP do RECIPE-INVENTORY-PLAN §8, consumida pelo app de Produção
(``surfaces/production-nuxt``, telas ``/recipes``). Cada view lê o corpo,
chama a orquestração fina (``services.recipe_book``) e devolve a projection
(``projections.recipe_book``) já formatada.

Permissão: **ler** é o gate do app de Produção (``backstage.operate_production``,
ou ver a ficha); **escrever** é ``shop.manage_production`` (ou mudar a ficha),
a mesma régua de "mexer acontece no app de Produção". A régua vive em
``resolve_recipe_book_access``; aqui só se pergunta.

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

from shopman.backstage.projections.recipe_book import (
    build_capture_draft,
    build_formula_lens,
    build_ingredient_options,
    build_recipe_book,
    build_recipe_compare,
    build_recipe_entry,
    build_recipe_reference,
    resolve_recipe_book_access,
    wire_formula,
)
from shopman.backstage.services import recipe_book as recipe_book_service
from shopman.backstage.services.exceptions import (
    RecipeBookServiceError,
    RecipeEntryNotFound,
    RecipeVersionNotFound,
)
from shopman.backstage.services.recipe_capture import RecipeCaptureError, RecipeCaptureNotConfigured

from .permissions import HasBackstagePermission
from .projections import projection_data

_MSG_VIEW = "O inventário de receitas exige backstage.operate_production."
_MSG_EDIT = "Alterar o inventário de receitas exige shop.manage_production."

#: Códigos do Craftsman que são conflito de ESTADO, não de campo: 409, não 400.
_STATE_CONFLICT_CODES = ("VERSION_NOT_DRAFT", "ENTRY_ARCHIVED")

_KINDS = ("bread", "viennoiserie", "sweet_dough", "filling", "cream", "sauce", "beverage", "other")


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
        return projection_data(build_recipe_entry(ref))

    def _entry_and_version_payload(self, ref: str, number: int) -> dict:
        entry = build_recipe_entry(ref)
        version = next((v for v in entry.versions if v.number == number), None)
        return {"entry": projection_data(entry), "version": projection_data(version)}


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
class RecipeBookListView(_RecipeBookBase):
    def get(self, request):
        kind = str(request.query_params.get("kind") or "").strip()
        if kind and kind not in _KINDS:
            return Response(
                {"detail": f"Tipo de receita desconhecido; use um de: {', '.join(_KINDS)}.", "field": "kind",
                 "errors": {"kind": ["Tipo de receita desconhecido."]}},
                status=400,
            )
        book = build_recipe_book(
            query=request.query_params.get("q", ""),
            kind=kind,
            archived=request.query_params.get("archived", "") in ("1", "true", "yes"),
        )
        return Response({"book": projection_data(book), "access": projection_data(self.access)})

    def post(self, request):
        if not self.access.can_edit:
            raise PermissionDenied(_MSG_EDIT)
        try:
            entry, _version = recipe_book_service.create_entry_from_payload(request.data, actor=_actor(request))
        except RecipeVersionNotFound as exc:
            raise NotFound(str(exc)) from exc
        except RecipeBookServiceError as exc:
            return _service_error_response(exc)
        return Response({"entry": self._entry_payload(entry.ref)}, status=201)


# ── Receita ──────────────────────────────────────────────────────────────────


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Recipe entry detail (all versions, newest first)",
        responses={200: OpenApiResponse(description="Entry, versions with lens, access.")},
    ),
    patch=extend_schema(
        tags=["backstage"],
        summary="Edit a recipe entry (name, kind, SKU, notes, archive)",
        responses={200: OpenApiResponse(description="The entry with its versions.")},
    ),
)
class RecipeEntryView(_RecipeBookBase):
    def get(self, request, ref: str):
        try:
            entry = build_recipe_entry(ref)
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
        try:
            version = recipe_book_service.create_version_from_payload(entry, request.data, actor=_actor(request))
        except RecipeVersionNotFound as exc:
            raise NotFound(str(exc)) from exc
        except RecipeBookServiceError as exc:
            return _service_error_response(exc)
        return Response(self._entry_and_version_payload(entry.ref, version.number), status=201)


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
        try:
            recipe_book_service.publish(version, actor=_actor(request))
        except RecipeBookServiceError as exc:
            return _service_error_response(exc)
        return Response({"entry": self._entry_payload(entry.ref)})


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
