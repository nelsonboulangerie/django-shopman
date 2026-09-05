"""Gate da meia-correção — o gate roda como código, estes testes provam.

Um gate que reprova demais é desligado no primeiro dia; um que reprova de
menos não guarda nada. Então os testes vêm em dois blocos simétricos: o que
DEVE reprovar e o que DEVE passar. O segundo bloco é o que mantém a ferramenta
viva.

O script mora fora da árvore do pacote, então o módulo é carregado por caminho.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_silent_swallow.py"
_spec = importlib.util.spec_from_file_location("check_silent_swallow", _SCRIPT)
check_silent_swallow = importlib.util.module_from_spec(_spec)
# O registro em `sys.modules` vem ANTES do exec: `@dataclass` resolve as
# anotações olhando `sys.modules[cls.__module__]`, e sem esta linha o módulo
# ainda não está lá quando a classe é construída — a importação estoura com
# um AttributeError que não tem nada a ver com o gate.
sys.modules["check_silent_swallow"] = check_silent_swallow
_spec.loader.exec_module(check_silent_swallow)


def scan_py(source: str):
    return check_silent_swallow.scan_python("shopman/shop/services/exemplo.py", textwrap.dedent(source))


def scan_ts(source: str):
    return check_silent_swallow.scan_surface("surfaces/pos-nuxt/app/exemplo.ts", textwrap.dedent(source))


# ---------------------------------------------------------------------------
# Python — deve REPROVAR
# ---------------------------------------------------------------------------


def test_grita_no_estorno_e_cala_no_authorize():
    """O caso canônico: dinheiro saindo alerta, dinheiro entrando é silêncio."""
    verdict = scan_py(
        """
        def refund(ref):
            try:
                PaymentService.refund(ref)
            except PaymentError:
                record_payment_reconciliation_failure(ref, "refund")

        def authorize(ref):
            try:
                PaymentService.authorize(ref)
            except PaymentError:
                pass
        """
    )
    assert verdict.contradictory
    assert [s.kind for s in verdict.mute] == ["except_pass"]


def test_logger_debug_conta_como_mudez():
    """Com DJANGO_LOG_LEVEL=INFO, logger.debug não emite nada em produção.

    É `pass` com aparência de cuidado — e passa despercebido na revisão
    justamente por parecer tratado.
    """
    verdict = scan_py(
        """
        def notify(order):
            try:
                send(order)
            except Exception:
                logger.error("notify.failed order=%s", order.ref)

        def notify_sibling(order):
            try:
                send(order)
            except Exception:
                logger.debug("notify.failed order=%s", order.ref)
        """
    )
    assert verdict.contradictory
    assert [s.kind for s in verdict.mute] == ["except_debug"]


def test_reticencias_sao_mudez_como_pass():
    verdict = scan_py(
        """
        def emit(order):
            try:
                fiscal.emit(order)
            except FiscalError:
                create_operator_alert("fiscal.failed")

        def emit_sibling(order):
            try:
                fiscal.emit(order)
            except FiscalError:
                ...
        """
    )
    assert verdict.contradictory


def test_raise_de_erro_de_dominio_conta_como_grito():
    verdict = scan_py(
        """
        def charge(ref):
            if not ref:
                raise PaymentError("sem referência")
            try:
                gateway.charge(ref)
            except PaymentError:
                pass
        """
    )
    assert verdict.contradictory
    assert verdict.loud[0].kind == "raise:PaymentError"


# ---------------------------------------------------------------------------
# Python — deve PASSAR
# ---------------------------------------------------------------------------


def test_marcador_na_linha_do_except_isenta():
    verdict = scan_py(
        """
        def charge(ref):
            try:
                gateway.charge(ref)
            except PaymentError:
                record_payment_reconciliation_failure(ref, "charge")
            try:
                cache.warm(ref)
            except CacheError:  # silêncio-deliberado: cache frio não é falha de negócio
                pass
        """
    )
    assert not verdict.contradictory
    assert verdict.mute == []


def test_marcador_no_corpo_do_handler_isenta():
    """A razão costuma não caber depois de dois-pontos sem estourar a linha.

    Aí ela desce para o corpo, que é onde o leitor do `pass` está olhando.
    """
    verdict = scan_py(
        """
        def charge(ref):
            try:
                gateway.charge(ref)
            except PaymentError:
                logger.error("charge.failed ref=%s", ref)
            try:
                lock.release(ref)
            except LockError:
                # silêncio-deliberado: corrida benigna com o worker, que relê no ciclo seguinte
                pass
        """
    )
    assert not verdict.contradictory


def test_marcador_sem_acento_tambem_vale():
    verdict = scan_py(
        """
        def charge(ref):
            try:
                gateway.charge(ref)
            except PaymentError:
                logger.error("charge.failed")
            try:
                lock.release(ref)
            except LockError:  # silencio-deliberado: teclado sem acento é realidade
                pass
        """
    )
    assert not verdict.contradictory


def test_arquivo_que_so_engole_nao_reprova():
    """Sem contradição interna não há meia-correção — há uma escolha uniforme.

    Reprovar isto seria transformar o gate num caçador de `except: pass` em
    geral, que é outra briga (e a que faz a ferramenta ser desligada).
    """
    verdict = scan_py(
        """
        def warm(ref):
            try:
                cache.warm(ref)
            except Exception:
                pass
        """
    )
    assert not verdict.contradictory


def test_arquivo_que_so_grita_nao_reprova():
    verdict = scan_py(
        """
        def charge(ref):
            try:
                gateway.charge(ref)
            except PaymentError:
                create_operator_alert("charge.failed")
                raise
        """
    )
    assert not verdict.contradictory


def test_except_que_trata_de_verdade_nao_e_mudez():
    verdict = scan_py(
        """
        def charge(ref):
            try:
                gateway.charge(ref)
            except PaymentError:
                logger.error("charge.failed")
            try:
                gateway.settle(ref)
            except PaymentError:
                return fallback(ref)
        """
    )
    assert verdict.mute == []


def test_raise_de_builtin_generico_nao_conta_como_grito():
    """`raise ValueError` conferindo argumento defende a função de quem a chamou.

    Não é o mesmo gesto que relatar que o negócio falhou. Contar assim faria
    quase todo arquivo parecer alto — e o gate viraria ruído.
    """
    verdict = scan_py(
        """
        def charge(ref):
            if not ref:
                raise ValueError("ref vazio")
            try:
                gateway.charge(ref)
            except PaymentError:
                pass
        """
    )
    assert not verdict.contradictory


def test_docstring_no_except_nao_impede_deteccao_de_mudez():
    verdict = scan_py(
        '''
        def charge(ref):
            try:
                gateway.charge(ref)
            except PaymentError:
                logger.error("charge.failed")
            try:
                gateway.settle(ref)
            except PaymentError:
                """Nada a fazer."""
                pass
        '''
    )
    assert verdict.contradictory


def test_arquivo_que_nao_parseia_vira_no_op():
    """O gate nunca pode ser o motivo de um PR travar por algo que outro pega."""
    verdict = scan_py("def quebrado(:\n    pass\n")
    assert not verdict.contradictory


# ---------------------------------------------------------------------------
# TS / Vue — deve REPROVAR
# ---------------------------------------------------------------------------


def test_catch_arrow_vazio_com_throw_no_mesmo_arquivo():
    verdict = scan_ts(
        """
        export function useSale() {
          function open(tab) {
            if (tab.taken) throw new Error("Esta comanda já possui pedido.");
          }
          function refresh() {
            return fetchTab().catch(() => {});
          }
          return { open, refresh };
        }
        """
    )
    assert verdict.contradictory
    assert [s.kind for s in verdict.mute] == ["catch_arrow"]


@pytest.mark.parametrize(
    "engolimento",
    [
        ".catch(() => {})",
        ".catch(() => null)",
        ".catch(() => undefined)",
        ".catch((e) => {})",
        ".catch(err => null)",
    ],
)
def test_todas_as_formas_de_catch_mudo(engolimento):
    verdict = scan_ts(
        f"""
        export function useSale() {{
          console.error("falhou");
          return fetchTab(){engolimento};
        }}
        """
    )
    assert verdict.contradictory


def test_catch_block_vazio():
    verdict = scan_ts(
        """
        export async function save() {
          console.error("autosave falhou");
          try {
            await persist();
          } catch {}
        }
        """
    )
    assert verdict.contradictory
    assert [s.kind for s in verdict.mute] == ["catch_block"]


# ---------------------------------------------------------------------------
# TS / Vue — deve PASSAR
# ---------------------------------------------------------------------------


def test_catch_mudo_dentro_de_comentario_nao_conta():
    """A prova de que o regex não lê comentário.

    Em `usePosSale.ts` existe um comentário contando que o erro ERA engolido
    com `.catch(() => {})`. Um gate que lesse comentário reprovaria o arquivo
    justamente pelo relato do conserto.
    """
    verdict = scan_ts(
        """
        export function useSale() {
          console.error("falhou");
          // Antes o erro era engolido (.catch(() => {})) e o operador seguia.
          return fetchTab().catch((e) => reportError(e));
        }
        """
    )
    assert verdict.mute == []


def test_catch_mudo_dentro_de_string_nao_conta():
    verdict = scan_ts(
        """
        export function useSale() {
          console.error("falhou");
          const exemplo = "use .catch(() => {}) nunca";
          return exemplo;
        }
        """
    )
    assert verdict.mute == []


def test_marcador_ts_isenta():
    verdict = scan_ts(
        """
        export function useSale() {
          console.error("autosave falhou");
          // silêncio-deliberado: refresh oportunista, o SSE reconcilia depois
          void refreshCart().catch(() => null);
        }
        """
    )
    assert not verdict.contradictory


def test_catch_que_trata_nao_e_mudez():
    verdict = scan_ts(
        """
        export async function save() {
          console.error("boot");
          try {
            await persist();
          } catch (e) {
            unsaved.value = true;
          }
        }
        """
    )
    assert verdict.mute == []


def test_linha_reportada_e_a_linha_real():
    """Offset preservado na limpeza de comentário: linha errada é pior que nenhuma."""
    verdict = scan_ts(
        """
        // um comentário
        /* e um bloco
           de várias linhas */
        console.error("grito");
        void refresh().catch(() => {});
        """
    )
    assert verdict.mute[0].line == 6


# ---------------------------------------------------------------------------
# Escopo — o gate só olha código de produção
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "shopman/shop/services/payment.py",
        "packages/payman/shopman/payman/services/write.py",
        "config/settings.py",
        "surfaces/pos-nuxt/app/composables/usePosSale.ts",
        "surfaces/pos-nuxt/app/components/PosPaymentWorkspace.vue",
    ],
)
def test_producao_esta_no_escopo(path):
    assert check_silent_swallow.in_scope(path)


@pytest.mark.parametrize(
    "path",
    [
        "shopman/shop/tests/test_payment.py",
        "shopman/shop/migrations/0002_algo.py",
        "surfaces/pos-nuxt/node_modules/foo/index.ts",
        "surfaces/pos-nuxt/app/composables/usePosSale.spec.ts",
        "surfaces/storefront-nuxt/tests/e2e/alpha/helpers.ts",
        "scripts/check_silent_swallow.py",
        "docs/reference/silencio-inventario.md",
    ],
)
def test_fora_do_escopo(path):
    """Teste exercita caminho de erro de propósito; migração roda uma vez.

    E o próprio gate fica de fora: ele fala de `except: pass` o tempo todo.
    """
    assert not check_silent_swallow.in_scope(path)
