from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Mapping

import requests


class PlatformAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, url: str | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.body = body


@dataclass(frozen=True)
class PlatformRequestConfig:
    timeout_seconds: float = 15.0
    max_retries: int = 3
    retry_backoff_base_seconds: float = 0.4
    retry_backoff_factor: float = 2.0
    jitter_ratio: float = 0.2
    retry_on_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)


class PlatformAPIRequestBuilder:
    """
    Shared HTTP request builder for the devsper platform API.

    Defaults can be supplied by env vars:
    - DEVSPER_PLATFORM_API_URL (base URL, e.g. http://localhost:8080)
    - DEVSPER_PLATFORM_ORG (org slug)
    - DEVSPER_PLATFORM_TOKEN (JWT for Authorization: Bearer ...)
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        org_slug: str | None = None,
        token: str | None = None,
        config: PlatformRequestConfig | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("DEVSPER_PLATFORM_API_URL", "")).rstrip("/")
        self.org_slug = org_slug or os.environ.get("DEVSPER_PLATFORM_ORG", "")
        self.token = token or os.environ.get("DEVSPER_PLATFORM_TOKEN", "")
        self.config = config or PlatformRequestConfig()
        self._session = requests.Session()

    def enabled(self) -> bool:
        return bool(self.base_url and self.org_slug)

    def build_url(self, path: str) -> str:
        if not path:
            return self.base_url
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def build_headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra:
            h.update({str(k): str(v) for k, v in extra.items()})
        return h

    def _should_retry(self, status_code: int) -> bool:
        return status_code in self.config.retry_on_statuses

    def _sleep_before_retry(self, attempt: int) -> None:
        # attempt is 0-based
        backoff = self.config.retry_backoff_base_seconds * (self.config.retry_backoff_factor**attempt)
        jitter = backoff * self.config.jitter_ratio * random.random()
        time.sleep(backoff + jitter)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> requests.Response:
        if not self.base_url:
            raise PlatformAPIError("Platform API base_url is not configured", url=self.base_url)

        url = self.build_url(path)
        timeout = timeout_seconds if timeout_seconds is not None else self.config.timeout_seconds

        merged_headers = self.build_headers(extra=headers)

        last_exc: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    headers=merged_headers,
                    json=json_body,
                    timeout=timeout,
                )
                if resp.ok:
                    return resp
                if self._should_retry(resp.status_code) and attempt < self.config.max_retries - 1:
                    self._sleep_before_retry(attempt)
                    continue

                body = None
                try:
                    body = resp.text[:10_000]
                except Exception:
                    body = None

                raise PlatformAPIError(
                    f"Platform API request failed with status {resp.status_code}",
                    status_code=resp.status_code,
                    url=url,
                    body=body,
                )
            except (requests.RequestException, PlatformAPIError) as e:
                # PlatformAPIError is raised above for non-retriable 4xx or exhausted retries.
                # For network exceptions, decide whether to retry.
                if isinstance(e, PlatformAPIError) and e.status_code is not None:
                    # It's already a status failure; if it is retryable, we'd have handled it.
                    raise
                last_exc = e
                if attempt < self.config.max_retries - 1:
                    self._sleep_before_retry(attempt)
                    continue
                raise PlatformAPIError(f"Platform API request error: {e}", url=url) from e

        # Should be unreachable
        if last_exc:
            raise PlatformAPIError(f"Platform API request error: {last_exc}", url=url) from last_exc
        raise PlatformAPIError("Platform API request error", url=url)

    def get_json(self, path: str, *, params: Mapping[str, Any] | None = None, headers: Mapping[str, str] | None = None) -> Any:
        resp = self.request("GET", path, params=params, headers=headers, json_body=None)
        if not resp.text:
            return None
        return resp.json()

    def post_json(
        self,
        path: str,
        *,
        json_body: Any,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        resp = self.request("POST", path, params=params, headers=headers, json_body=json_body)
        if not resp.text:
            return None
        return resp.json()

    # ---- Platform run endpoints (optional helpers) ----

    def create_run(
        self,
        task: str,
        *,
        project_id: str | None = None,
        config: Mapping[str, Any] | None = None,
        manifest: Mapping[str, Any] | None = None,
        manifest_version: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled():
            raise PlatformAPIError("Platform API is not enabled (missing base_url or org_slug).")
        body: dict[str, Any] = {"task": task, "project_id": project_id or "", "config": dict(config or {}), "manifest": dict(manifest or {})}
        extra_headers: dict[str, str] = {}
        if manifest_version:
            extra_headers["x-devsper-run-manifest-version"] = manifest_version
        return self.post_json(f"/orgs/{self.org_slug}/runs", json_body=body, headers=extra_headers)

    def get_run(self, run_id: str) -> dict[str, Any]:
        if not self.enabled():
            raise PlatformAPIError("Platform API is not enabled (missing base_url or org_slug).")
        data = self.get_json(f"/orgs/{self.org_slug}/runs/{run_id}")
        # API returns `result` as either a JSON object or string depending on server version.
        return data or {}

    def poll_run(
        self,
        run_id: str,
        *,
        interval_seconds: float = 2.0,
        timeout_seconds: float = 120.0,
        terminal_statuses: tuple[str, ...] = ("completed", "failed", "cancelled", "timeout"),
    ) -> dict[str, Any]:
        start = time.time()
        while True:
            payload = self.get_run(run_id)
            status = str(payload.get("status") or "")
            if status in terminal_statuses:
                return payload
            if time.time() - start >= timeout_seconds:
                raise TimeoutError(f"Timed out waiting for run {run_id}. Last status: {status}")
            time.sleep(interval_seconds)

