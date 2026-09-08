"""来源侦察共用的响应安全校验。

侦察层把重复或大小写异形的响应 header 当作传输事实记录，不把它们当作
失败条件。HTTPS、允许状态码、最终 URL、内容类型和正文尺寸仍是硬约束。
本模块只把正文交给调用方提供的元数据解析器，绝不持久化响应正文。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from email.message import Message
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit


FAILURE_BY_CONSTRAINT = {
    "url_https": "PROBE_URL_NOT_ALLOWED",
    "transport_execution": "PROBE_TRANSPORT_ERROR",
    "status_allowed": "PROBE_STATUS_NOT_ALLOWED",
    "final_url_exact": "PROBE_FINAL_URL_MISMATCH",
    "header_container": "PROBE_HEADER_CONTAINER_INVALID",
    "header_value_string": "PROBE_HEADER_VALUE_INVALID",
    "content_type_expected": "PROBE_CONTENT_TYPE_MISMATCH",
    "content_length_valid": "PROBE_CONTENT_LENGTH_INVALID",
    "body_limit": "PROBE_BODY_LIMIT_EXCEEDED",
    "body_read": "PROBE_BODY_READ_ERROR",
    "metadata_parser": "PROBE_METADATA_STRUCTURE_INVALID",
}

DIAGNOSTIC_FIELDS = {
    "constraint_name",
    "exception_class",
    "hop",
    "request_id",
    "route_id",
    "status_code",
}

HEADER_CANONICAL = {
    "content-length": "Content-Length",
    "content-type": "Content-Type",
    "etag": "ETag",
    "last-modified": "Last-Modified",
    "location": "Location",
    "x-github-media-type": "X-GitHub-Media-Type",
    "x-ratelimit-limit": "X-RateLimit-Limit",
    "x-ratelimit-remaining": "X-RateLimit-Remaining",
    "x-ratelimit-reset": "X-RateLimit-Reset",
}


class MetadataParseError(ValueError):
    """元数据响应结构不满足白名单解析契约。"""


@dataclass(frozen=True)
class HttpResponse:
    """不依赖具体 HTTP 客户端的最小响应容器。"""

    status: int
    headers: Any
    final_url: str
    body: Any = b""


def failure(request_spec: Mapping[str, Any], constraint: str, **diagnostic: Any) -> dict[str, Any]:
    """生成脱敏且稳定的失败对象。"""

    safe = {
        "request_id": request_spec["request_id"],
        "constraint_name": constraint,
    }
    for key in ("route_id", "hop"):
        if key in request_spec:
            safe[key] = request_spec[key]
    for key, value in diagnostic.items():
        if key in DIAGNOSTIC_FIELDS:
            safe[key] = value
    return {"code": FAILURE_BY_CONSTRAINT[constraint], "diagnostic": safe}


def _header_pairs(headers: Any) -> Iterable[tuple[Any, Any]]:
    if isinstance(headers, Message):
        return headers.items()
    if isinstance(headers, Mapping):
        return headers.items()
    if isinstance(headers, (list, tuple)):
        return headers
    raise TypeError("header 容器必须是 Message、Mapping 或键值序列")


def normalize_recon_headers(
    headers: Any,
    request_spec: Mapping[str, Any],
    allowed_headers: Iterable[str],
) -> tuple[dict[str, list[str]] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """白名单化 header，并把重复和大小写差异作为事实列表返回。"""

    allowed = {name.lower() for name in allowed_headers}
    values: dict[str, list[str]] = {}
    raw_names: dict[str, list[str]] = {}
    pair_count = 0
    try:
        for item in _header_pairs(headers):
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                return None, None, failure(request_spec, "header_container")
            raw_key, raw_value = item
            if not isinstance(raw_key, str) or not isinstance(raw_value, str):
                return None, None, failure(request_spec, "header_value_string")
            lowered = raw_key.lower()
            if lowered not in allowed:
                continue
            canonical = HEADER_CANONICAL.get(lowered, raw_key)
            values.setdefault(canonical, []).append(raw_value)
            raw_names.setdefault(canonical, []).append(raw_key)
            pair_count += 1
    except (TypeError, ValueError):
        return None, None, failure(request_spec, "header_container")

    duplicates = []
    case_conflicts = []
    for canonical, recorded_values in values.items():
        names = raw_names[canonical]
        if len(recorded_values) > 1:
            duplicates.append(
                {
                    "name": canonical,
                    "occurrences": len(recorded_values),
                    "raw_names": names,
                    "values": recorded_values,
                }
            )
        if len(set(names)) > 1:
            case_conflicts.append({"name": canonical, "raw_names": list(dict.fromkeys(names))})
    observations = {
        "allowed_pair_count": pair_count,
        "duplicates": duplicates,
        "case_conflicts": case_conflicts,
        "duplicates_are_facts_not_failures": True,
    }
    return values, observations, None


def _valid_https_url(url: Any) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        return bool(
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
            and not parsed.fragment
        )
    except ValueError:
        return False


def _read_body(
    body: Any,
    limit: int,
    request_spec: Mapping[str, Any],
) -> tuple[bytes | None, dict[str, Any] | None]:
    try:
        if isinstance(body, bytes):
            payload = body
        elif isinstance(body, bytearray):
            payload = bytes(body)
        elif hasattr(body, "read"):
            payload = body.read(limit + 1)
            if not isinstance(payload, bytes):
                return None, failure(request_spec, "body_read")
        else:
            return None, failure(request_spec, "body_read")
    except Exception as error:  # 异常消息可能含秘密，只记录异常类名
        return None, failure(request_spec, "body_read", exception_class=type(error).__name__)
    if len(payload) > limit:
        return None, failure(request_spec, "body_limit")
    return payload, None


def probe_json_response(
    request_spec: Mapping[str, Any],
    policy: Mapping[str, Any],
    transport: Callable[[Mapping[str, Any], float], HttpResponse],
    parser: Callable[[bytes], Mapping[str, Any]],
) -> dict[str, Any]:
    """执行一次小型 JSON 元数据请求并应用侦察级安全校验。"""

    base = {
        "request_id": request_spec["request_id"],
        "route_id": request_spec.get("route_id"),
        "hop": request_spec.get("hop"),
        "method": request_spec["method"],
        "requested_url": request_spec["url"],
        "body_bytes_read": 0,
    }
    if request_spec["method"] != "GET" or not _valid_https_url(request_spec["url"]):
        return {**base, "outcome": "failure", "failure": failure(request_spec, "url_https")}
    try:
        response = transport(request_spec, float(policy["network_policy"]["timeout_seconds"]))
    except Exception as error:  # 异常消息可能含凭据，绝不记录
        return {
            **base,
            "outcome": "failure",
            "failure": failure(request_spec, "transport_execution", exception_class=type(error).__name__),
        }
    if response.status not in policy["network_policy"]["allowed_statuses"]:
        return {
            **base,
            "outcome": "failure",
            "failure": failure(request_spec, "status_allowed", status_code=response.status),
        }
    if response.final_url != request_spec["url"]:
        return {
            **base,
            "outcome": "failure",
            "failure": failure(request_spec, "final_url_exact", status_code=response.status),
        }

    headers, observations, header_failure = normalize_recon_headers(
        response.headers,
        request_spec,
        policy["network_policy"]["allowed_response_headers"],
    )
    if header_failure:
        return {**base, "outcome": "failure", "failure": header_failure}
    assert headers is not None and observations is not None

    length_values = headers.get("Content-Length", [])
    if any(re.fullmatch(r"0|[1-9][0-9]*", value) is None for value in length_values):
        return {**base, "outcome": "failure", "failure": failure(request_spec, "content_length_valid")}
    hard_limit = int(policy["network_policy"]["get_response_hard_limit_bytes"])
    request_limit = int(request_spec["max_response_bytes"])
    limit = min(hard_limit, request_limit)
    if any(int(value) > limit for value in length_values):
        return {
            **base,
            "outcome": "failure",
            "failure": failure(request_spec, "body_limit", status_code=response.status),
        }

    expected_types = {value.lower() for value in request_spec["expected_content_types"]}
    actual_types = {
        value.split(";", 1)[0].strip().lower()
        for value in headers.get("Content-Type", [])
    }
    if not actual_types.intersection(expected_types):
        return {
            **base,
            "outcome": "failure",
            "failure": failure(request_spec, "content_type_expected", status_code=response.status),
        }

    payload, body_failure = _read_body(response.body, limit, request_spec)
    if body_failure:
        return {**base, "outcome": "failure", "failure": body_failure}
    assert payload is not None
    try:
        metadata = dict(parser(payload))
    except (MetadataParseError, UnicodeDecodeError, ValueError, TypeError, KeyError):
        return {
            **base,
            "body_bytes_read": len(payload),
            "outcome": "failure",
            "failure": failure(request_spec, "metadata_parser"),
        }
    return {
        **base,
        "body_bytes_read": len(payload),
        "outcome": "success",
        "status": response.status,
        "headers": headers,
        "header_observations": observations,
        "metadata_evidence": metadata,
        "response_body_persisted": False,
    }


__all__ = [
    "DIAGNOSTIC_FIELDS",
    "FAILURE_BY_CONSTRAINT",
    "HttpResponse",
    "MetadataParseError",
    "failure",
    "normalize_recon_headers",
    "probe_json_response",
]
