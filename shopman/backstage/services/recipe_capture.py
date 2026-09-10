"""Ler uma anotação ou uma foto de receita e devolver um rascunho em pt-BR.

É a porta "Anotação" e a porta "Foto" do editor de receitas
(RECIPE-INVENTORY-PLAN §6): o padeiro cola um texto em qualquer língua, ou tira
uma foto do caderno, do livro ou da tela, e recebe de volta um rascunho
estruturado (nome, rendimento, ingredientes com quantidade, unidade e papel,
passos) para conferir e ajustar. Nada é gravado aqui: quem persiste é o editor,
depois que o padeiro olhou.

Três limites escritos:

- **O transporte é o da casa.** Mesma credencial do ``copy_assist``
  (``AI_ASSIST_API_KEY``), mesmo modelo (``AI_ASSIST_MODEL``), mesmo provedor.
  Fala com o SDK direto em vez de passar por ``copy_assist.suggest`` porque a
  foto exige bloco de imagem, e ``suggest`` só transporta texto.
- **JSON estrito, validado, nunca engolido.** Mesmo padrão de
  ``bi/scenarios.py``: cerca de código é tolerada, resto é erro. O que a
  validação consegue corrigir sem inventar (papel fora da lista, unidade fora
  da lista) ela corrige e ANOTA no item; o que não consegue, levanta.
- **Sem credencial é configuração, não falha.** ``RecipeCaptureNotConfigured``
  vira 503 na API e "sem leitura automática neste ambiente" na tela.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from shopman.backstage.services.exceptions import AiAssistError, AiAssistNotConfigured

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"
# Folgado de propósito: o raciocínio do modelo sai do mesmo orçamento que o
# texto, e uma receita com vinte ingredientes e dez passos, transcrita e
# traduzida, passa fácil de 2000 tokens só de resposta.
MAX_TOKENS = 8000

ACCEPTED_IMAGE_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
#: Teto do base64 (~5 MB de imagem decodificada, o limite do provedor). A tela
#: redimensiona a foto para 1600 px antes de enviar; quem passa daqui mandou o
#: arquivo original da câmera.
MAX_IMAGE_BASE64_BYTES = 7_000_000

ROLES = ("flour", "liquid", "salt", "yeast", "fat", "sugar", "egg", "dairy", "inclusion", "other")
KINDS = ("bread", "viennoiserie", "sweet_dough", "filling", "cream", "sauce", "beverage", "other")
UNITS = ("g", "kg", "ml", "L", "un")

#: Apelidos de unidade que o modelo pode devolver apesar da instrução. Grafia,
#: não física: só aponta para uma unidade da lista fechada.
_UNIT_ALIASES = {
    "gr": "g", "grs": "g", "grama": "g", "gramas": "g", "gram": "g", "grams": "g", "gramme": "g",
    "grammes": "g", "グラム": "g",
    "quilo": "kg", "quilos": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
    "kilogramme": "kg", "キロ": "kg",
    "mililitro": "ml", "mililitros": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml",
    "millilitres": "ml", "cc": "ml",
    "unidade": "un", "unidades": "un", "pc": "un", "pcs": "un", "piece": "un", "pieces": "un",
    "piece(s)": "un", "pièce": "un", "pièces": "un", "個": "un", "枚": "un", "本": "un",
}

SYSTEM_PROMPT = (
    "Você é um padeiro-formulista que transcreve receitas para o sistema de uma padaria "
    "artesanal brasileira. Recebe uma anotação colada ou a foto de um caderno, livro ou tela, "
    "em qualquer língua, e devolve a receita estruturada.\n"
    "\n"
    "Responda APENAS com JSON válido, sem cerca de código, sem comentário e sem texto em volta, "
    "exatamente neste formato:\n"
    '{"name": str, "kind": str, "language": str, "yield": {"quantity": number|null, "unit": str}, '
    '"items": [{"name": str, "original_text": str, "quantity": number|null, "unit": str, '
    '"role": str, "note": str}], "steps": [str], "notes": str}\n'
    "\n"
    "Regras:\n"
    "- Traduza nomes de ingrediente, passos e o nome da receita para português do Brasil. "
    "Em cada item, original_text é a linha como está na fonte, sem tradução.\n"
    "- language é o código ISO 639-1 da língua da fonte (pt, fr, en, ja...).\n"
    "- Unidades só entre g, kg, ml, L e un. Xícara, cup, tasse e カップ viram ml (cerca de 240 ml "
    "por xícara); colher de sopa, tbsp, cuillère à soupe e 大さじ viram 15 ml; colher de chá, tsp, "
    "cuillère à café e 小さじ viram 5 ml. Sempre que converter, escreva a conversão feita em note. "
    "Ovos, dentes de alho e itens contados ficam em un.\n"
    '- "q.b.", "a gosto", "to taste", "適量" e afins viram quantity null com a expressão em note.\n'
    "- role classifica o papel do ingrediente na massa: flour (farinhas), liquid (água, leite "
    "vegetal, cerveja), salt, yeast (fermento biológico, levain, poolish), fat (manteiga, azeite, "
    "óleo, banha), sugar (açúcar, mel, malte), egg, dairy (leite, creme, queijo, iogurte), "
    "inclusion (o que se mistura por cima: chocolate, passas, sementes, azeitona) ou other.\n"
    "- kind classifica a receita: bread, viennoiserie, sweet_dough, filling, cream, sauce, "
    "beverage ou other.\n"
    "- Se a fonte está em porcentagem do padeiro (farinha 100%, água 70%...), converta para gramas "
    "sobre 1000 g de farinha total e diga isso em notes.\n"
    "- Não invente ingrediente, quantidade nem passo que não estejam na fonte. O que não dá para "
    "ler, deixe quantity null e explique em note.\n"
    "- Se a fonte tem mais de uma receita, transcreva a primeira e diga em notes que há outras.\n"
    "- Sem travessão e sem emoji nos textos."
)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)
_DATA_URL = re.compile(r"^data:(?P<media>[\w/+.-]+);base64,", re.I)
_LANGUAGE = re.compile(r"^[a-z]{2}$")


class RecipeCaptureNotConfigured(AiAssistNotConfigured):
    """Sem credencial de IA neste ambiente. É configuração, não falha (503 na API)."""


class RecipeCaptureError(AiAssistError):
    """O provedor falhou, recusou, ou a resposta não é uma receita legível (502 na API)."""


# ── Resultado ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CapturedItem:
    name: str
    original_text: str
    quantity: Decimal | None
    unit: str
    role: str
    note: str = ""


@dataclass(frozen=True)
class CapturedRecipe:
    name: str
    kind: str
    language: str
    yield_quantity: Decimal | None
    yield_unit: str
    items: tuple[CapturedItem, ...]
    steps: tuple[str, ...]
    notes: str
    raw_text: str


def is_configured() -> bool:
    """Há credencial para ler receita neste ambiente? Mesmo pino do ``copy_assist``."""
    from shopman.shop.services.copy_assist import is_configured as assist_configured

    return assist_configured()


# ── Validação da resposta ───────────────────────────────────────────────────


def _coerce_quantity(value: Any) -> tuple[Decimal | None, str]:
    """Número, string numérica (com vírgula ou ponto) ou nulo. O resto vira nulo com nota."""
    if value is None or value == "":
        return None, ""
    if isinstance(value, bool):
        return None, f"quantidade '{value}' não reconhecida"
    if isinstance(value, Decimal):
        return value, ""
    if isinstance(value, (int, float)):
        return Decimal(str(value)), ""
    text = str(value).strip().replace(",", ".")
    try:
        return Decimal(text), ""
    except InvalidOperation:
        return None, f"quantidade '{value}' não reconhecida"


def _coerce_unit(value: Any, quantity: Decimal | None) -> tuple[str, Decimal | None, str]:
    """Força a unidade para ``UNITS``. Apelido conhecido é grafia; mg e dz são conversão
    definicional (``shopman.utils.units``); o resto cai em ``g`` com nota."""
    from shopman.utils import units

    raw = str(value or "").strip()
    lowered = raw.lower()
    if raw in UNITS:
        return raw, quantity, ""
    if lowered in _UNIT_ALIASES:
        return _UNIT_ALIASES[lowered], quantity, ""
    canonical = units.normalize(raw)
    if canonical == "l":
        return "L", quantity, ""
    if canonical in UNITS:
        return canonical, quantity, ""
    if canonical == "mg":
        converted = None if quantity is None else units.convert(quantity, "mg", "g")
        return "g", converted, f"{raw} convertido para g"
    if canonical == "dz":
        converted = None if quantity is None else units.convert(quantity, "dz", "un")
        return "un", converted, f"{raw} convertido para un"
    if not raw:
        return "g", quantity, "unidade ausente na fonte; assumida g"
    return "g", quantity, f"unidade '{raw}' não reconhecida; assumida g"


def _coerce_choice(value: Any, allowed: tuple[str, ...], label: str) -> tuple[str, str]:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in allowed:
        return raw, ""
    if not raw:
        return "other", ""
    return "other", f"{label} '{value}' fora da lista; marcado como other"


def _join_notes(*parts: str) -> str:
    return "; ".join(part.strip() for part in parts if part and part.strip())


class CaptureItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    original_text: str = Field(default="", max_length=500)
    quantity: Decimal | None = None
    unit: str = "g"
    role: str = "other"
    note: str = Field(default="", max_length=500)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise ValueError("cada item precisa ser um objeto")
        data = dict(data)
        quantity, quantity_note = _coerce_quantity(data.get("quantity"))
        unit, quantity, unit_note = _coerce_unit(data.get("unit"), quantity)
        role, role_note = _coerce_choice(data.get("role"), ROLES, "papel")
        data["quantity"] = quantity
        data["unit"] = unit
        data["role"] = role
        data["original_text"] = str(data.get("original_text") or "")
        data["note"] = _join_notes(str(data.get("note") or ""), quantity_note, unit_note, role_note)
        return data


class CaptureYield(BaseModel):
    model_config = ConfigDict(extra="ignore")

    quantity: Decimal | None = None
    unit: str = "un"
    note: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: Any) -> Any:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("yield precisa ser um objeto")
        data = dict(data)
        quantity, quantity_note = _coerce_quantity(data.get("quantity"))
        unit, quantity, unit_note = _coerce_unit(data.get("unit") or "un", quantity)
        data["quantity"] = quantity
        data["unit"] = unit
        data["note"] = _join_notes(quantity_note, unit_note)
        return data


class CapturePayload(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    kind: str = "other"
    language: str = ""
    yield_: CaptureYield = Field(default_factory=CaptureYield, alias="yield")
    items: list[CaptureItem] = Field(min_length=1, max_length=80)
    steps: list[str] = Field(default_factory=list, max_length=60)
    notes: str = Field(default="", max_length=2000)

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: Any) -> str:
        return _coerce_choice(value, KINDS, "tipo")[0]

    @field_validator("language", mode="before")
    @classmethod
    def _language(cls, value: Any) -> str:
        code = str(value or "").strip().lower()
        return code if _LANGUAGE.match(code) else ""

    @field_validator("steps", mode="before")
    @classmethod
    def _steps(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("steps precisa ser uma lista de textos")
        return [str(step).strip() for step in value if str(step or "").strip()]

    @field_validator("notes", mode="before")
    @classmethod
    def _notes(cls, value: Any) -> str:
        return str(value or "")


def parse_response(raw: str) -> CapturedRecipe:
    """JSON estrito, com tolerância só para a cerca de código. Qualquer outra coisa levanta."""
    text = _FENCE.sub("", (raw or "").strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RecipeCaptureError(f"O assistente não devolveu JSON: {exc.msg} (posição {exc.pos}).") from exc
    try:
        payload = CapturePayload.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ())) or "resposta"
        raise RecipeCaptureError(
            f"A resposta do assistente não tem o formato esperado em '{where}': {first.get('msg', '')}."
        ) from exc
    return CapturedRecipe(
        name=payload.name,
        kind=payload.kind,
        language=payload.language,
        yield_quantity=payload.yield_.quantity,
        yield_unit=payload.yield_.unit,
        items=tuple(
            CapturedItem(
                name=item.name,
                original_text=item.original_text,
                quantity=item.quantity,
                unit=item.unit,
                role=item.role,
                note=item.note,
            )
            for item in payload.items
        ),
        steps=tuple(payload.steps),
        notes=_join_notes(payload.notes, payload.yield_.note),
        raw_text=raw,
    )


# ── Entrada e chamada ───────────────────────────────────────────────────────


def _clean_image(image_base64: str, image_media_type: str) -> tuple[str, str]:
    """Base64 sem quebra de linha (o provedor recusa com) e sem prefixo de data URL."""
    data = (image_base64 or "").strip()
    media_type = (image_media_type or "").strip().lower()
    match = _DATA_URL.match(data)
    if match:
        data = data[match.end():]
        media_type = media_type or match.group("media").lower()
    data = re.sub(r"\s+", "", data)
    return data, media_type


def _build_content(*, text: str, image_base64: str, image_media_type: str, language_hint: str) -> list[dict]:
    content: list[dict] = []
    if image_base64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": image_media_type, "data": image_base64},
        })
    instruction = ["Transcreva a receita " + ("desta foto." if image_base64 else "desta anotação.")]
    hint = (language_hint or "").strip()
    if hint:
        instruction.append(f"A fonte está provavelmente em '{hint}'.")
    if text:
        instruction.append(f"Anotação:\n<<<\n{text}\n>>>")
    content.append({"type": "text", "text": "\n".join(instruction)})
    return content


def read_recipe(
    *,
    text: str = "",
    image_base64: str = "",
    image_media_type: str = "",
    language_hint: str = "",
) -> CapturedRecipe:
    """Lê uma anotação (``text``) ou uma foto (``image_base64`` + ``image_media_type``).

    Os dois juntos também valem: a anotação vira contexto da foto. Levanta
    ``RecipeCaptureNotConfigured`` sem credencial e ``RecipeCaptureError`` para
    entrada inválida, falha do provedor ou resposta ilegível.
    """
    text = (text or "").strip()
    image_base64, image_media_type = _clean_image(image_base64, image_media_type)
    if not text and not image_base64:
        raise RecipeCaptureError("Envie uma anotação ou uma foto da receita.")
    if image_base64:
        if image_media_type not in ACCEPTED_IMAGE_MEDIA_TYPES:
            raise RecipeCaptureError(
                f"Formato de imagem não aceito: '{image_media_type or 'sem tipo'}'. Use JPEG, PNG, WebP ou GIF."
            )
        if len(image_base64) > MAX_IMAGE_BASE64_BYTES:
            raise RecipeCaptureError("Imagem grande demais (acima de 5 MB). Reduza a foto antes de enviar.")

    api_key = (getattr(settings, "AI_ASSIST_API_KEY", "") or "").strip()
    if not api_key:
        raise RecipeCaptureNotConfigured("Leitura de receita por IA não configurada. Defina AI_ASSIST_API_KEY.")
    provider = getattr(settings, "AI_ASSIST_PROVIDER", "anthropic")
    if provider != "anthropic":
        raise RecipeCaptureError(f"Provedor de IA '{provider}' não suportado.")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    model = getattr(settings, "AI_ASSIST_MODEL", "") or DEFAULT_MODEL
    content = _build_content(
        text=text, image_base64=image_base64, image_media_type=image_media_type, language_hint=language_hint,
    )
    try:
        message = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    # Cadeia da mais específica para a mais ampla: a mensagem ao operador é curta e
    # em português; o detalhe técnico vai para o log (sem a credencial, que o SDK
    # nunca põe na mensagem e nós nunca pomos no log).
    except anthropic.AuthenticationError as exc:
        _log_provider_failure(exc)
        raise RecipeCaptureError("O provedor de IA recusou a credencial configurada.") from exc
    except anthropic.RateLimitError as exc:
        _log_provider_failure(exc)
        raise RecipeCaptureError("O provedor de IA está ocupado. Tente de novo em instantes.") from exc
    except anthropic.APIStatusError as exc:
        _log_provider_failure(exc)
        raise RecipeCaptureError(f"O provedor de IA respondeu com erro ({exc.status_code}).") from exc
    except anthropic.APIConnectionError as exc:
        _log_provider_failure(exc)
        raise RecipeCaptureError("Não foi possível falar com o provedor de IA.") from exc

    stop_reason = getattr(message, "stop_reason", "") or ""
    if stop_reason == "max_tokens":
        raise RecipeCaptureError(
            f"O assistente parou no limite de {MAX_TOKENS} tokens: a leitura veio cortada."
        )
    if stop_reason == "refusal":
        raise RecipeCaptureError("O assistente recusou ler esta fonte.")
    raw = "\n".join(
        block.text for block in getattr(message, "content", ()) if getattr(block, "type", "") == "text"
    ).strip()
    if not raw:
        raise RecipeCaptureError("O assistente devolveu uma resposta vazia.")
    return parse_response(raw)


def _log_provider_failure(exc: Exception) -> None:
    logger.warning(
        "recipe_capture: provedor falhou kind=%s status=%s detail=%s",
        type(exc).__name__,
        getattr(exc, "status_code", ""),
        str(exc)[:300],
    )
