"""Formato da suíte de conformidade: o decorador, o arnês de forma das portas e a matriz.

Especificação: ``spec/11-conformance.md``.
"""

from .catalog import K_BY_ID, K_TESTS, SCOPES, ConformanceTest
from .decorator import ConformanceMark, conformance

__all__ = ["K_BY_ID", "K_TESTS", "SCOPES", "ConformanceMark", "ConformanceTest", "conformance"]
