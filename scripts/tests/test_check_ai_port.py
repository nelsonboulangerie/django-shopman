from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_ai_port", Path(__file__).resolve().parent.parent / "check_ai_port.py"
)
check = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check)


def test_cliente_do_sdk_fora_da_porta_reprova():
    found = check.violations_in(Path("shopman/x.py"), "import anthropic\nc = anthropic.Anthropic(api_key='k')\n")
    assert len(found) == 1 and "Anthropic" in found[0]


def test_endereco_de_api_fora_da_porta_reprova():
    found = check.violations_in(Path("shopman/x.py"), "URL = 'https://api.deepseek.com/anthropic'\n")
    assert len(found) == 1 and "api.deepseek.com" in found[0]


def test_importar_para_pegar_erro_passa():
    source = "import anthropic\ntry:\n    pass\nexcept anthropic.APIError:\n    pass\n"
    assert check.violations_in(Path("shopman/x.py"), source) == []


def test_o_repositorio_esta_limpo():
    assert check.scan() == []
