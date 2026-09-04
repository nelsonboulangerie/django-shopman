"""
Substitutes module — find replacement products for unavailable SKUs.

Usage:
    from shopman.offerman.contrib.substitutes import find_substitutes

    subs = find_substitutes("SKU-001")                 # só os produtos
    scored = score_substitutes("SKU-001")              # com pontuação e motivos
"""

__all__ = ["ScoredSubstitute", "find_substitutes", "score_substitutes"]


def __getattr__(name: str):
    if name in __all__:
        from shopman.offerman.contrib.substitutes import substitutes as _module

        globals().update({n: getattr(_module, n) for n in __all__})
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
