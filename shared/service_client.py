"""
A small wrapper around httpx for calling other RideFlow services.

Its main job is to turn low-level network failures into two clear errors
that the calling service can map to proper HTTP responses:

  * ServiceUnavailableError -> the other service is down or too slow (we return 503)
  * UpstreamServiceError    -> it answered, but with an unexpected error (we return 502)

We deliberately do NOT retry automatically. Retrying a non-idempotent call
like "reserve a driver" could reserve two drivers if the first response was
merely lost on the way back. Safe retries need idempotency keys, which is a
good "next step" topic but more than this project needs.
"""

from typing import Any

import httpx


class ServiceUnavailableError(Exception):
    def __init__(self, service: str, reason: str):
        self.service = service
        self.reason = reason
        super().__init__(f"{service} is unavailable: {reason}")


class UpstreamServiceError(Exception):
    def __init__(self, service: str, status_code: int, detail: Any = None):
        self.service = service
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{service} returned HTTP {status_code}: {detail}")


class ServiceClient:
    def __init__(
        self,
        service_name: str,
        base_url: str | None = None,
        *,
        timeout: float = 5.0,
        default_headers: dict[str, str] | None = None,
        http_client: httpx.Client | None = None,
    ):
        """
        `http_client` can be injected (e.g. FastAPI's TestClient, or an httpx
        client with a mock transport) so tests can exercise the real code path
        without opening network connections.
        """
        if http_client is None:
            if not base_url:
                raise ValueError("base_url is required when no http_client is given")
            http_client = httpx.Client(base_url=base_url, timeout=timeout)
        self.service_name = service_name
        self._http = http_client
        self._default_headers = default_headers or {}

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        merged_headers = {**self._default_headers, **(headers or {})}
        try:
            return self._http.request(method, path, json=json, headers=merged_headers)
        except httpx.TimeoutException as exc:
            raise ServiceUnavailableError(self.service_name, "request timed out") from exc
        except httpx.RequestError as exc:
            raise ServiceUnavailableError(self.service_name, "could not connect") from exc

    @staticmethod
    def error_detail(response: httpx.Response) -> Any:
        try:
            return response.json().get("detail")
        except (ValueError, AttributeError):
            return response.text[:200]
