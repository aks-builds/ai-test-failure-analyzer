# analyzer/parsers/newman_json.py
from __future__ import annotations

import json
from pathlib import Path

from .base import NormalizedFailure, Parser, make_failure_id


class NewmanJsonParser(Parser):
    """Parser for Postman/Newman JSON reporter output.

    Newman invocation:
        newman run collection.json --reporters json --reporter-json-export results.json
    """

    framework = "newman"

    @classmethod
    def can_parse(cls, sample: str | bytes) -> bool:
        if isinstance(sample, bytes):
            try:
                sample = sample.decode("utf-8", errors="replace")
            except Exception:
                return False
        s = sample.lstrip()
        return s.startswith("{") and '"collection"' in s and '"run"' in s and '"executions"' in s

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        collection_name = (
            data.get("collection", {}).get("info", {}).get("name") or "Newman"
        )
        out: list[NormalizedFailure] = []

        for execution in data.get("run", {}).get("executions", []):
            item = execution.get("item") or {}
            item_name = item.get("name", "")

            request = execution.get("request") or {}
            method = (request.get("method") or "").upper()
            url_obj = request.get("url") or {}
            if isinstance(url_obj, dict):
                url = url_obj.get("raw") or ""
            else:
                url = str(url_obj)

            response = execution.get("response") or {}
            status_code = response.get("code")
            response_time = response.get("responseTime")

            http = {
                "method": method or None,
                "url": url or None,
                "status_got": status_code,
                "status_expected": None,
                "response_time_ms": response_time,
            } if (url or status_code is not None) else None

            assertions = execution.get("assertions") or []
            failed = [a for a in assertions if a.get("error") is not None]

            if not failed:
                out.append(NormalizedFailure(
                    id=make_failure_id(cls.framework, collection_name, item_name, ""),
                    framework=cls.framework,
                    suite=collection_name,
                    title=item_name,
                    file="",
                    status="passed",
                    http=http,
                ))
            else:
                for assertion in failed:
                    err = assertion.get("error") or {}
                    err_msg = err.get("message", "") if isinstance(err, dict) else str(err)
                    assertion_name = assertion.get("assertion", "")
                    title = f"{item_name} — {assertion_name}" if assertion_name else item_name
                    out.append(NormalizedFailure(
                        id=make_failure_id(cls.framework, collection_name, title, ""),
                        framework=cls.framework,
                        suite=collection_name,
                        title=title,
                        file="",
                        status="failed",
                        error_message=err_msg,
                        http=http,
                    ))

        return out
