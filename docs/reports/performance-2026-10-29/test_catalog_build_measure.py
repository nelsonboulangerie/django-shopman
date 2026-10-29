"""Comparação controlada: executar explicitamente com BASELINE_ADAPTER_FILE e MEASURE_OUTPUT.

O baseline vem de git show do commit anterior, nunca de download. Usa somente o
banco de testes. Alterna a ordem e compara o JSON inteiro, não só a quantidade.
"""

import hashlib
import json
import os
import statistics
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.adapters.sku_validator import SkuValidator
from shopman.offerman.models import Collection, Listing
from shopman.stockman.models import Position

from shopman.shop.projections import catalog_context
from shopman.shop.request_memo import request_memo_scope, stock_reads_scope
from shopman.storefront.api.projections import projection_data
from shopman.storefront.presentation import product_detail as pdp_module
from shopman.storefront.presentation.catalog import build_catalog
from shopman.storefront.presentation.product_detail import build_product_detail
from shopman.storefront.tests.web.test_catalog_nplus1_measure import _extra_products, _seed_catalog

pytestmark = pytest.mark.django_db


def test_measure_catalog_and_pdp():
    _seed_catalog()
    _extra_products(
        Listing.objects.get(ref="web"), {c.ref: c for c in Collection.objects.all()},
        Position.objects.get(ref="loja"), n=24, start=100,
    )
    namespace = {"__name__": "catalog_baseline"}
    source = Path(os.environ["BASELINE_ADAPTER_FILE"])
    exec(compile(source.read_text(), str(source), "exec"), namespace)
    baseline = namespace["SkuValidator"]
    methods = {
        "before": (baseline.get_sku_info, baseline.get_sku_infos),
        "after": (SkuValidator.get_sku_info, SkuValidator.get_sku_infos),
    }
    availability = {
        "before": lambda sku, channel_ref: catalog_context.availability_for_sku(sku, channel_ref=channel_ref),
        "after": pdp_module._availability,
    }
    output = {}
    for name, build in {
        "catalog": lambda: build_catalog(channel_ref="web"),
        "pdp": lambda: build_product_detail(sku="PAO-FRANCES", channel_ref="web"),
    }.items():
        samples = {key: [] for key in methods}
        bodies = {}
        for index in range(12):
            for key in (list(methods) if index % 2 else list(reversed(methods))):
                single, bulk = methods[key]
                with patch.object(SkuValidator, "get_sku_info", single), patch.object(SkuValidator, "get_sku_infos", bulk), patch.object(pdp_module, "_availability", availability[key]):
                    with request_memo_scope(), stock_reads_scope(), CaptureQueriesContext(connection) as queries:
                        start = time.perf_counter()
                        data = projection_data(build())
                        elapsed = (time.perf_counter() - start) * 1000
                    body = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    bodies[key] = body
                    if index >= 2:  # duas voltas de aquecimento por variante
                        samples[key].append({"ms": round(elapsed, 3), "queries": len(queries)})
        assert bodies["before"] == bodies["after"]
        output[name] = {
            "samples": samples,
            "p50_ms": {key: statistics.median(x["ms"] for x in rows) for key, rows in samples.items()},
            "sha256": hashlib.sha256(bodies["after"].encode()).hexdigest(),
            "bytes": len(bodies["after"].encode()),
            "json_equal": True,
        }
        assert max(x["queries"] for x in samples["after"]) < min(x["queries"] for x in samples["before"])
    Path(os.environ["MEASURE_OUTPUT"]).write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
