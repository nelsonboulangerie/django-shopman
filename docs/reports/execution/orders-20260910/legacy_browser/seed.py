import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from shopman.orderman.models import Order, OrderItem

ref = f"LAB-OLD-BROWSER-{uuid4().hex[:8]}"
with patch("shopman.orderman.dispatch._on_commit_callback"):
    order = Order.objects.create(ref=ref, channel_ref="lab", status="accepted", total_q=500,
        session_key=ref, data={"fulfillment_type": "pickup", "payment": {"method": "cash"}, "customer": {"name": ref}})
    OrderItem.objects.create(order=order, line_id=f"{ref}-line", sku="LAB-PROD",
        name="Produto laboratório", qty="0.500", unit_price_q=1000, line_total_q=500)
Path(".orders-lab/legacy-manifest.json").write_text(json.dumps({"ref": ref}))
print("Synthetic legacy browser order seeded; no transport invoked.")
