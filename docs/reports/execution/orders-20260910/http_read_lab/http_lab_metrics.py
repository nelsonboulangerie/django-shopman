"""Lab-only headers, measured around the actual Django request/serialization."""
import time

import psutil
from django.db import connection
from django.test.utils import CaptureQueriesContext


class ReadMetrics:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start, cpu = time.perf_counter(), time.process_time()
        with CaptureQueriesContext(connection) as queries:
            response = self.get_response(request)
        response["X-Lab-Backend-Ms"] = f"{(time.perf_counter() - start) * 1000:.3f}"
        response["X-Lab-Cpu-Ms"] = f"{(time.process_time() - cpu) * 1000:.3f}"
        response["X-Lab-Queries"] = str(len(queries))
        response["X-Lab-Hold-Queries"] = str(sum("stockman_hold" in item["sql"] for item in queries))
        response["X-Lab-Rss-Bytes"] = str(psutil.Process().memory_info().rss)
        return response
