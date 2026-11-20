"""AI SOP 开放平台 Python SDK（零依赖，仅用标准库）。

用法::

    from ai_sop_client import AiSopClient

    client = AiSopClient("http://localhost:8000", api_key="sk_xxx")
    for sop in client.list_sop():
        print(sop["name"])

    for record in client.list_execution(status="completed", limit=10):
        print(record["id"], record["sop_name"])
"""

import json
import urllib.error
import urllib.request
from typing import Dict, Iterator, List, Optional


class AiSopError(RuntimeError):
    """开放接口返回非 2xx 时抛出。"""


class AiSopClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    # ---------- 底层请求 ----------
    def _request(self, path: str, params: Optional[Dict] = None) -> dict:
        url = "{}/api/v1/open{}".format(self.base_url, path)
        if params:
            query = "&".join(
                "{}={}".format(key, value)
                for key, value in params.items()
                if value is not None
            )
            if query:
                url = "{}?{}".format(url, query)

        request = urllib.request.Request(url, headers={"X-API-Key": self.api_key})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")
            raise AiSopError("HTTP {}: {}".format(exc.code, detail)) from exc
        except urllib.error.URLError as exc:
            raise AiSopError("无法连接 {}: {}".format(url, exc.reason)) from exc

    # ---------- 业务接口 ----------
    def list_sop(self) -> List[dict]:
        return self._request("/sop")["sops"]

    def list_execution(
        self, status: Optional[str] = None, page: int = 1, limit: int = 20
    ) -> List[dict]:
        return self._request(
            "/execution", {"status": status, "page": page, "limit": limit}
        )["records"]

    def iter_execution(self, limit: int = 20) -> Iterator[dict]:
        page = 1
        while True:
            records = self.list_execution(page=page, limit=limit)
            if not records:
                return
            for record in records:
                yield record
            page += 1

    def get_execution(self, record_id: int) -> dict:
        return self._request("/execution/{}".format(record_id))

    def mes_payload(self, record_id: int) -> dict:
        return self._request("/mes/execution/{}".format(record_id))

    def analytics_overview(self, days: int = 7) -> dict:
        return self._request("/analytics/overview", {"days": days})
