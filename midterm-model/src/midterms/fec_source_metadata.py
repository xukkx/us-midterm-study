"""LH-054 FEC 官方发布对象元数据封印的纯核心。

本模块只验证四个 HTML 落地页以及三个 XLSX 对象的两段 HEAD 身份。
它绝不下载 PDF/XLSX 正文，不解析工作簿，也不触碰模型、评分或历史结果目录。
所有网络函数均允许注入 transport，以便离线证明 URL 门禁、禁止自动重定向和
HEAD 零正文读取。
"""

from __future__ import annotations

import hashlib
import html.parser
import json
import math
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


FEC_HOST = "www.fec.gov"
DEFAULT_MAX_HTML_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 20.0
OOXML_SPREADSHEET_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
PENDING_INGEST = "PENDING_SEPARATE_INGEST_CONTRACT"

INDEX_URL = (
    "https://www.fec.gov/introduction-campaign-finance/"
    "election-results-and-voting-information/"
)
LANDING_URLS = MappingProxyType({
    "index": INDEX_URL,
    2018: INDEX_URL + "federal-elections-2018/",
    2020: INDEX_URL + "federal-elections-2020/",
    2022: INDEX_URL + "federal-elections-2022/",
})
NUMBERED_OBJECT_URLS = MappingProxyType({
    2018: "https://www.fec.gov/documents/2706/federalelections2018.xlsx",
    2020: "https://www.fec.gov/documents/4228/federalelections2020.xlsx",
    2022: "https://www.fec.gov/documents/5676/federalelections2022.xlsx",
})
FINAL_OBJECT_URLS = MappingProxyType({
    year: (
        "https://www.fec.gov/resources/cms-content/documents/"
        f"federalelections{year}.xlsx"
    )
    for year in (2018, 2020, 2022)
})
EXPECTED_HREFS = MappingProxyType({
    year: urllib.parse.urlsplit(url).path
    for year, url in NUMBERED_OBJECT_URLS.items()
})
EXPECTED_OBJECT_HEADERS = MappingProxyType({
    2018: MappingProxyType({
        "Content-Type": OOXML_SPREADSHEET_MIME,
        "Content-Length": "602712",
        "ETag": '"dae569593e446d0b7d1e0aee2d1fc79b"',
        "Last-Modified": "Mon, 16 Nov 2020 15:58:38 GMT",
        "X-Amz-Version-Id": "RscdKx0U9aNiVivIBaiRM_CIOacHSPuA",
    }),
    2020: MappingProxyType({
        "Content-Type": OOXML_SPREADSHEET_MIME,
        "Content-Length": "6251110",
        "ETag": '"ed533051916a6d12b1dbec5dee92eb84"',
        "Last-Modified": "Mon, 19 Dec 2022 15:00:14 GMT",
        "X-Amz-Version-Id": "YfisdWWqox88OUjsiKw6FgKKl4qYk1Zd",
    }),
    2022: MappingProxyType({
        "Content-Type": OOXML_SPREADSHEET_MIME,
        "Content-Length": "3179722",
        "ETag": '"c87371c7736e7f8f4136f96ce0b6327e"',
        "Last-Modified": "Tue, 11 Feb 2025 19:04:47 GMT",
        "X-Amz-Version-Id": "..MeSjsdI32DPkok_mF0IfDuLItgMZSC",
    }),
})

_YEARS = (2018, 2020, 2022)
_SAFE_FAILURE_MIME = frozenset({"text/html", OOXML_SPREADSHEET_MIME})
_CANDIDATE_EXTENSIONS = frozenset({".xlsx", ".xls", ".csv"})


class FecMetadataError(ValueError):
    """可预期、可结构化的 LH-054 元数据失败。"""

    code = "FEC_METADATA_ERROR"


class RequestPolicyError(FecMetadataError):
    """请求在 transport 前违反精确 allowlist。"""

    code = "REQUEST_POLICY_REJECTED"


class ResponseValidationError(FecMetadataError):
    """HTTP 状态、MIME、大小或重定向不合格。"""

    code = "RESPONSE_VALIDATION_FAILED"


class HtmlLinkError(FecMetadataError):
    """年度 landing 没有唯一、逐字匹配的冻结 XLSX href。"""

    code = "LANDING_HREF_INVALID"


class HeadValidationError(FecMetadataError):
    """编号重定向或最终对象 HEAD 与预注册身份不一致。"""

    code = "HEAD_METADATA_INVALID"


def _json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FecMetadataError(f"{path} 含非有限浮点数")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise FecMetadataError(f"{path} 含非字符串 JSON key")
            _json_value(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _json_value(item, f"{path}[{index}]")
        return
    raise FecMetadataError(f"{path} 含非 JSON 类型 {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """返回无时间戳、无 NaN、键序确定的 UTF-8 JSON 字节。"""

    _json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(raw: bytes) -> str:
    if not isinstance(raw, bytes):
        raise FecMetadataError("sha256_hex 只接受 bytes")
    return hashlib.sha256(raw).hexdigest()


def _source_key(value: Any) -> str | int:
    if value == "index":
        return "index"
    if isinstance(value, bool) or not isinstance(value, int) or value not in _YEARS:
        raise RequestPolicyError("source key 必须是 index、2018、2020 或 2022")
    return value


def _year(value: Any) -> int:
    key = _source_key(value)
    if key == "index":
        raise RequestPolicyError("该操作只接受 2018、2020 或 2022")
    return key


def _safe_source(value: Any) -> str:
    try:
        key = _source_key(value)
    except RequestPolicyError:
        return "REDACTED_INVALID_SOURCE"
    return str(key)


def _validate_url_shape(url: Any) -> str:
    if not isinstance(url, str) or not url or url != url.strip():
        raise RequestPolicyError("URL 必须是无首尾空白的非空字符串")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in url):
        raise RequestPolicyError("URL 禁止控制字符")
    if "\\" in url:
        raise RequestPolicyError("URL 禁止反斜杠")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise RequestPolicyError("URL 无法规范解析") from error
    if parsed.scheme != "https" or parsed.hostname != FEC_HOST:
        raise RequestPolicyError("URL 必须使用 FEC 精确 HTTPS host")
    if parsed.username is not None or parsed.password is not None or port is not None:
        raise RequestPolicyError("URL 禁止 userinfo 与显式端口")
    if parsed.fragment or parsed.query:
        raise RequestPolicyError("URL 禁止 query 与 fragment")
    if "%" in parsed.path:
        raise RequestPolicyError("URL path 禁止 percent 编码分隔符绕过")
    if parsed.netloc != FEC_HOST:
        raise RequestPolicyError("URL host 必须逐字等于冻结 host")
    return url


def _normalize_request_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise RequestPolicyError("请求 headers 必须是 mapping")
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise RequestPolicyError("请求 header 名和值必须是字符串")
        lowered = key.lower()
        if lowered in normalized:
            raise RequestPolicyError("请求 header 禁止大小写重复")
        if lowered == "range":
            raise RequestPolicyError("本合同禁止 Range")
        if lowered not in {"accept", "accept-encoding", "user-agent"}:
            raise RequestPolicyError("请求 header 不在最小 allowlist")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
            raise RequestPolicyError("请求 header 值禁止控制字符")
        normalized[lowered] = value
    return normalized


@dataclass(frozen=True)
class MetadataRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    max_response_bytes: int


@dataclass(frozen=True)
class HttpResponse:
    """可注入 transport 的响应值。

    HEAD 验证逻辑绝不访问 ``body``；测试可传入带抛错 body/read 的鸭子对象，
    从而证明正文访问不是 HEAD 控制流的一部分。
    """

    status: int
    headers: Mapping[str, str]
    final_url: str
    body: bytes = b""


@dataclass(frozen=True)
class LandingDocument:
    source_key: str | int
    url: str
    status: int
    content_type: str
    raw_bytes: bytes
    sha256: str
    expected_xlsx_href: str | None
    attempt_count: int = 1

    def audit_dict(self) -> dict[str, Any]:
        return {
            "attempt_count": self.attempt_count,
            "byte_count": len(self.raw_bytes),
            "content_type": self.content_type,
            "expected_href": self.expected_xlsx_href,
            "expected_xlsx_href": self.expected_xlsx_href,
            "method": "GET",
            "response_bytes": len(self.raw_bytes),
            "response_sha256": self.sha256,
            "sha256": self.sha256,
            "source_key": str(self.source_key),
            "status": self.status,
            "url": self.url,
            "year": self.source_key,
        }


@dataclass(frozen=True)
class HeadDocument:
    year: int
    role: str
    url: str
    status: int
    final_url: str
    safe_headers: Mapping[str, str]
    attempt_count: int = 1

    def audit_dict(self) -> dict[str, Any]:
        return {
            "attempt_count": self.attempt_count,
            "body_bytes_read": 0,
            "final_url": self.final_url,
            "headers": dict(sorted(self.safe_headers.items())),
            "method": "HEAD",
            "request_role": self.role,
            "role": self.role,
            "status": self.status,
            "url": self.url,
            "year": self.year,
        }


@dataclass(frozen=True)
class FailureRecord:
    source_key: str
    code: str
    stage: str
    method: str
    url: str
    detail: str
    attempt_count: int
    status: int | None = None
    content_type: str | None = None
    response_bytes: int | None = None
    response_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "attempt_count": self.attempt_count,
            "code": self.code,
            "detail": self.detail,
            "method": self.method,
            "retry_permitted_in_same_contract": False,
            "source_key": self.source_key,
            "stage": self.stage,
            "url": self.url,
        }
        for key, item in (
            ("content_type", self.content_type),
            ("response_bytes", self.response_bytes),
            ("response_sha256", self.response_sha256),
            ("status", self.status),
        ):
            if item is not None:
                value[key] = item
        return value


@dataclass(frozen=True)
class FetchResult:
    document: LandingDocument | HeadDocument | None = None
    failure: FailureRecord | None = None

    def __post_init__(self) -> None:
        if (self.document is None) == (self.failure is None):
            raise FecMetadataError("FetchResult 必须且只能含 document 或 failure")

    @property
    def ok(self) -> bool:
        return self.document is not None


def validate_request(
    method: Any,
    url: Any,
    headers: Mapping[str, str] | None = None,
    *,
    max_response_bytes: int | None = None,
) -> MetadataRequest:
    """在 transport 前验证 method、完整 URL 与请求 headers。"""

    if method not in {"GET", "HEAD"}:
        raise RequestPolicyError("method 必须逐字为 GET 或 HEAD")
    safe_url = _validate_url_shape(url)
    if method == "GET":
        if safe_url not in LANDING_URLS.values():
            raise RequestPolicyError("GET 只能访问四个冻结 HTML 页面")
        maximum = DEFAULT_MAX_HTML_BYTES if max_response_bytes is None else max_response_bytes
    else:
        if safe_url not in set(NUMBERED_OBJECT_URLS.values()) | set(FINAL_OBJECT_URLS.values()):
            raise RequestPolicyError("HEAD 只能访问六个冻结 XLSX 对象 URL")
        maximum = 0 if max_response_bytes is None else max_response_bytes
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
        raise RequestPolicyError("max_response_bytes 必须是非负整数")
    if method == "GET" and maximum <= 0:
        raise RequestPolicyError("GET 的 max_response_bytes 必须为正")
    if method == "HEAD" and maximum != 0:
        raise RequestPolicyError("HEAD 的 max_response_bytes 必须为 0")
    supplied = _normalize_request_headers(headers)
    if method == "GET":
        fixed = {
            "Accept": "text/html",
            "Accept-Encoding": "identity",
            "User-Agent": "LongHorizon-LH054-metadata-head-only/1.0",
        }
    else:
        fixed = {
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "User-Agent": "LongHorizon-LH054-metadata-head-only/1.0",
        }
    for name, value in supplied.items():
        canonical_name = next(key for key in fixed if key.lower() == name)
        if value != fixed[canonical_name]:
            raise RequestPolicyError("请求 header 值必须逐字等于冻结值")
    return MetadataRequest(method, safe_url, MappingProxyType(fixed), maximum)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _default_transport(request: MetadataRequest, timeout: float) -> HttpResponse:
    """单次 urllib 请求；HEAD 分支没有任何 body/read/readinto/iter 调用。"""

    opener = urllib.request.build_opener(_NoRedirect)
    network_request = urllib.request.Request(
        request.url,
        headers=dict(request.headers),
        method=request.method,
    )
    try:
        with opener.open(network_request, timeout=timeout) as response:
            if request.method == "GET":
                body = response.read(request.max_response_bytes + 1)
                return HttpResponse(
                    int(response.status),
                    dict(response.headers.items()),
                    response.geturl(),
                    body,
                )
            return HttpResponse(
                int(response.status),
                dict(response.headers.items()),
                response.geturl(),
            )
    except urllib.error.HTTPError as error:
        try:
            if request.method == "GET":
                body = error.read(request.max_response_bytes + 1)
                return HttpResponse(
                    int(error.code), dict(error.headers.items()), error.geturl(), body
                )
            return HttpResponse(int(error.code), dict(error.headers.items()), error.geturl())
        finally:
            error.close()


Transport = Callable[[MetadataRequest, float], Any]


def _response_fields(response: Any, *, include_body: bool) -> tuple[int, Mapping[str, str], str, bytes | None]:
    """读取安全响应字段；HEAD 调用令 include_body=False，绝不求值 body。"""

    try:
        status = response.status
        headers = response.headers
        final_url = response.final_url
        body = response.body if include_body else None
    except (AttributeError, TypeError) as error:
        raise ResponseValidationError("transport 响应字段缺失") from error
    if isinstance(status, bool) or not isinstance(status, int):
        raise ResponseValidationError("transport status 必须是整数")
    if not isinstance(headers, Mapping):
        raise ResponseValidationError("transport headers 必须是 mapping")
    if not isinstance(final_url, str):
        raise ResponseValidationError("transport final_url 必须是字符串")
    if include_body and not isinstance(body, bytes):
        raise ResponseValidationError("GET transport body 必须是 bytes")
    return status, headers, final_url, body


def _response_headers(headers: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    normalized: dict[str, tuple[str, str]] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ResponseValidationError("响应 header 名和值必须是字符串")
        lowered = key.lower()
        if lowered in normalized:
            raise ResponseValidationError("响应 header 禁止大小写重复")
        normalized[lowered] = (key, value)
    return normalized


def _required_header(headers: Mapping[str, tuple[str, str]], name: str) -> str:
    item = headers.get(name.lower())
    if item is None:
        raise ResponseValidationError(f"响应缺少冻结 header {name}")
    return item[1]


def _safe_content_type(headers: Any) -> str | None:
    if not isinstance(headers, Mapping):
        return None
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == "content-type" and isinstance(value, str):
            main = value.split(";", 1)[0].strip().lower()
            return main if main in _SAFE_FAILURE_MIME else "invalid/redacted"
    return None


def _failure(
    source_key: Any,
    method: str,
    error: Exception,
    *,
    stage: str,
    url: str,
    attempt_count: int,
    response: Any | None = None,
    include_body_audit: bool = False,
) -> FetchResult:
    status: int | None = None
    content_type: str | None = None
    response_bytes: int | None = None
    response_sha256: str | None = None
    if response is not None:
        candidate_status = getattr(response, "status", None)
        if isinstance(candidate_status, int) and not isinstance(candidate_status, bool):
            status = candidate_status
        content_type = _safe_content_type(getattr(response, "headers", None))
        if include_body_audit:
            candidate_body = getattr(response, "body", None)
            if isinstance(candidate_body, bytes):
                response_bytes = len(candidate_body)
                response_sha256 = sha256_hex(candidate_body)
    code = error.code if isinstance(error, FecMetadataError) else "TRANSPORT_ERROR"
    detail = str(error) if isinstance(error, FecMetadataError) else f"transport 失败：{type(error).__name__}"
    return FetchResult(failure=FailureRecord(
        source_key=_safe_source(source_key),
        code=code,
        stage=stage,
        method=method,
        url=url,
        detail=detail,
        attempt_count=attempt_count,
        status=status,
        content_type=content_type,
        response_bytes=response_bytes,
        response_sha256=response_sha256,
    ))


@dataclass(frozen=True)
class _Anchor:
    href: str
    text: str


class _LandingParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[_Anchor] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        hrefs = [value for name, value in attrs if name.lower() == "href"]
        if len(hrefs) > 1:
            raise HtmlLinkError("anchor 含重复 href 属性")
        self._href = hrefs[0] if hrefs and isinstance(hrefs[0], str) else None
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append(_Anchor(self._href, "".join(self._text)))
            self._href = None
            self._text = []

    def close(self) -> None:
        super().close()
        if self._href is not None:
            self.anchors.append(_Anchor(self._href, "".join(self._text)))
            self._href = None
            self._text = []


def _is_workbook_candidate(anchor: _Anchor) -> bool:
    href_lower = anchor.href.lower()
    try:
        path = urllib.parse.urlsplit(anchor.href).path
    except ValueError:
        path = anchor.href
    suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    text_lower = anchor.text.lower()
    return (
        suffix in _CANDIDATE_EXTENSIONS
        or ".xlsx" in href_lower
        or "xlsx" in text_lower
        or "excel" in text_lower
    )


def extract_unique_xlsx_href(year: Any, html_bytes: bytes) -> str:
    """从年度 landing 原始 HTML 中选出唯一、逐字匹配的冻结 href。"""

    safe_year = _year(year)
    if not isinstance(html_bytes, bytes):
        raise HtmlLinkError("HTML 必须是原始 bytes")
    try:
        text = html_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise HtmlLinkError("HTML 不是严格 UTF-8") from error
    parser = _LandingParser()
    try:
        parser.feed(text)
        parser.close()
    except HtmlLinkError:
        raise
    except Exception as error:
        raise HtmlLinkError("HTML parser 失败") from error
    candidates = [anchor for anchor in parser.anchors if _is_workbook_candidate(anchor)]
    if not candidates:
        raise HtmlLinkError("landing 缺少 XLSX 候选")
    if len(candidates) != 1:
        raise HtmlLinkError("landing 的 XLSX 候选不唯一")
    href = candidates[0].href
    if href != EXPECTED_HREFS[safe_year]:
        raise HtmlLinkError("landing XLSX href 与冻结值不一致")
    return href


def validate_landing_document(
    source_key: Any,
    response: Any,
    *,
    max_response_bytes: int = DEFAULT_MAX_HTML_BYTES,
) -> LandingDocument:
    key = _source_key(source_key)
    if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int) or max_response_bytes <= 0:
        raise ResponseValidationError("HTML 大小上限必须是正整数")
    status, raw_headers, final_url, body = _response_fields(response, include_body=True)
    assert body is not None
    headers = _response_headers(raw_headers)
    expected_url = LANDING_URLS[key]
    if final_url != expected_url:
        raise ResponseValidationError("landing 禁止自动或手动重定向")
    if status != 200:
        raise ResponseValidationError("landing HTTP status 必须为 200")
    content_type = _required_header(headers, "Content-Type")
    if content_type.split(";", 1)[0].strip().lower() != "text/html":
        raise ResponseValidationError("landing Content-Type 必须是 text/html")
    content_length_item = headers.get("content-length")
    if content_length_item is not None:
        raw_length = content_length_item[1]
        if not raw_length.isascii() or not raw_length.isdigit():
            raise ResponseValidationError("landing Content-Length 必须是十进制整数")
        if int(raw_length) != len(body):
            raise ResponseValidationError("landing Content-Length 与原始字节数不一致")
    if not body:
        raise ResponseValidationError("landing HTML 不能为空")
    if len(body) > max_response_bytes:
        raise ResponseValidationError("landing HTML 超过 2 MiB 上限")
    href = None if key == "index" else extract_unique_xlsx_href(key, body)
    return LandingDocument(
        key,
        expected_url,
        status,
        "text/html",
        body,
        sha256_hex(body),
        href,
    )


def validate_numbered_head(year: Any, response: Any) -> HeadDocument:
    safe_year = _year(year)
    status, raw_headers, final_url, _ = _response_fields(response, include_body=False)
    headers = _response_headers(raw_headers)
    url = NUMBERED_OBJECT_URLS[safe_year]
    if final_url != url:
        raise HeadValidationError("编号 URL HEAD 禁止自动重定向")
    if status != 302:
        raise HeadValidationError("编号 URL HEAD status 必须为 302")
    location = _required_header(headers, "Location")
    if location != FINAL_OBJECT_URLS[safe_year]:
        raise HeadValidationError("302 Location 与冻结最终 URL 不一致")
    return HeadDocument(
        safe_year,
        "numbered_redirect",
        url,
        status,
        final_url,
        MappingProxyType({"Location": location}),
    )


def validate_final_head(year: Any, response: Any) -> HeadDocument:
    safe_year = _year(year)
    status, raw_headers, final_url, _ = _response_fields(response, include_body=False)
    headers = _response_headers(raw_headers)
    url = FINAL_OBJECT_URLS[safe_year]
    if final_url != url:
        raise HeadValidationError("最终 URL HEAD 禁止重定向")
    if status != 200:
        raise HeadValidationError("最终 URL HEAD status 必须为 200")
    expected = EXPECTED_OBJECT_HEADERS[safe_year]
    safe_headers: dict[str, str] = {}
    for name, expected_value in expected.items():
        actual = _required_header(headers, name)
        if actual != expected_value:
            raise HeadValidationError(f"最终对象 header {name} 与冻结值不一致")
        safe_headers[name] = actual
    return HeadDocument(
        safe_year,
        "final_object",
        url,
        status,
        final_url,
        MappingProxyType(safe_headers),
    )


def _timeout(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RequestPolicyError("timeout_seconds 必须是正有限数值")
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise RequestPolicyError("timeout_seconds 必须是正有限数值")
    return timeout


def _fetch(
    source_key: Any,
    request: MetadataRequest,
    validator: Callable[[Any, Any], LandingDocument | HeadDocument],
    *,
    transport: Transport | None,
    timeout_seconds: float,
) -> FetchResult:
    try:
        timeout = _timeout(timeout_seconds)
    except RequestPolicyError as error:
        return _failure(
            source_key, request.method, error,
            stage="before_transport", url="REDACTED_REJECTED_URL", attempt_count=0,
        )
    active_transport = transport or _default_transport
    try:
        response = active_transport(request, timeout)
    except (TimeoutError, socket.timeout, OSError, urllib.error.URLError) as error:
        return _failure(
            source_key, request.method, error,
            stage="transport", url=request.url, attempt_count=1,
        )
    try:
        document = validator(source_key, response)
    except FecMetadataError as error:
        return _failure(
            source_key,
            request.method,
            error,
            stage="response",
            url=request.url,
            attempt_count=1,
            response=response,
            include_body_audit=request.method == "GET",
        )
    return FetchResult(document=document)


def fetch_landing(
    source_key: Any,
    *,
    transport: Transport | None = None,
    max_response_bytes: int = DEFAULT_MAX_HTML_BYTES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> FetchResult:
    try:
        key = _source_key(source_key)
        request = validate_request(
            "GET", LANDING_URLS[key], max_response_bytes=max_response_bytes
        )
    except FecMetadataError as error:
        return _failure(
            source_key, "GET", error,
            stage="before_transport", url="REDACTED_REJECTED_URL", attempt_count=0,
        )
    return _fetch(
        key,
        request,
        lambda value, response: validate_landing_document(
            value, response, max_response_bytes=max_response_bytes
        ),
        transport=transport,
        timeout_seconds=timeout_seconds,
    )


def fetch_numbered_head(
    year: Any,
    *,
    transport: Transport | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> FetchResult:
    try:
        safe_year = _year(year)
        request = validate_request("HEAD", NUMBERED_OBJECT_URLS[safe_year])
    except FecMetadataError as error:
        return _failure(
            year, "HEAD", error,
            stage="before_transport", url="REDACTED_REJECTED_URL", attempt_count=0,
        )
    return _fetch(
        safe_year,
        request,
        validate_numbered_head,
        transport=transport,
        timeout_seconds=timeout_seconds,
    )


def fetch_final_head(
    year: Any,
    *,
    transport: Transport | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> FetchResult:
    try:
        safe_year = _year(year)
        request = validate_request("HEAD", FINAL_OBJECT_URLS[safe_year])
    except FecMetadataError as error:
        return _failure(
            year, "HEAD", error,
            stage="before_transport", url="REDACTED_REJECTED_URL", attempt_count=0,
        )
    return _fetch(
        safe_year,
        request,
        validate_final_head,
        transport=transport,
        timeout_seconds=timeout_seconds,
    )


def audit_year(
    year: Any,
    landing: LandingDocument,
    numbered_head: HeadDocument,
    final_head: HeadDocument,
) -> dict[str, Any]:
    """把一个年份的三个已验证文档组装成职责准确的确定性审计。"""

    safe_year = _year(year)
    if not isinstance(landing, LandingDocument) or landing.source_key != safe_year:
        raise FecMetadataError("landing 文档年份不匹配")
    if (
        landing.url != LANDING_URLS[safe_year]
        or isinstance(landing.status, bool)
        or landing.status != 200
        or landing.content_type != "text/html"
        or not isinstance(landing.raw_bytes, bytes)
        or not landing.raw_bytes
        or len(landing.raw_bytes) > DEFAULT_MAX_HTML_BYTES
        or landing.sha256 != sha256_hex(landing.raw_bytes)
        or landing.expected_xlsx_href != EXPECTED_HREFS[safe_year]
    ):
        raise FecMetadataError("landing 文档身份或原始字节封印无效")
    if not isinstance(numbered_head, HeadDocument) or (
        numbered_head.year != safe_year or numbered_head.role != "numbered_redirect"
    ):
        raise FecMetadataError("编号 HEAD 文档年份或职责不匹配")
    if (
        numbered_head.url != NUMBERED_OBJECT_URLS[safe_year]
        or numbered_head.final_url != NUMBERED_OBJECT_URLS[safe_year]
        or isinstance(numbered_head.status, bool)
        or numbered_head.status != 302
        or not isinstance(numbered_head.safe_headers, Mapping)
        or dict(numbered_head.safe_headers) != {"Location": FINAL_OBJECT_URLS[safe_year]}
    ):
        raise FecMetadataError("编号 HEAD 文档身份或 Location 封印无效")
    if not isinstance(final_head, HeadDocument) or (
        final_head.year != safe_year or final_head.role != "final_object"
    ):
        raise FecMetadataError("最终 HEAD 文档年份或职责不匹配")
    if (
        final_head.url != FINAL_OBJECT_URLS[safe_year]
        or final_head.final_url != FINAL_OBJECT_URLS[safe_year]
        or isinstance(final_head.status, bool)
        or final_head.status != 200
        or not isinstance(final_head.safe_headers, Mapping)
        or dict(final_head.safe_headers) != dict(EXPECTED_OBJECT_HEADERS[safe_year])
    ):
        raise FecMetadataError("最终 HEAD 文档身份或 header 封印无效")
    return {
        "activation": "fec_transport_object_metadata_sealed",
        "content_integrity": {
            "content_sha256": PENDING_INGEST,
            "ooxml_magic": PENDING_INGEST,
            "result_coverage": PENDING_INGEST,
            "sheet_schema": PENDING_INGEST,
            "vote_conservation": PENDING_INGEST,
        },
        "contains_2026_probability": False,
        "data_ingested": False,
        "etag_role": "opaque_http_validator_not_content_hash",
        "final_object_head": final_head.audit_dict(),
        "landing": landing.audit_dict(),
        "last_modified_role": "transport_object_modification_time_not_publication_vintage",
        "numbered_redirect_head": numbered_head.audit_dict(),
        "official_content_sha256_verified": False,
        "predictions_emitted": False,
        "scores_emitted": False,
        "model_activation": "unchanged",
        "version_id_role": "object_version_identity_not_content_integrity",
        "year": safe_year,
    }


def audit_sources(
    values: Mapping[int, Mapping[str, FetchResult]],
) -> dict[str, Any]:
    """逐年份审计；坏年份被局部封锁，不会删除其他年份的证据。"""

    if not isinstance(values, Mapping):
        raise FecMetadataError("逐源审计输入必须是 mapping")
    actual_keys = tuple(values.keys())
    if (
        any(isinstance(key, bool) or not isinstance(key, int) for key in actual_keys)
        or set(actual_keys) != set(_YEARS)
        or len(actual_keys) != len(_YEARS)
    ):
        raise FecMetadataError("逐源审计 key 必须精确为 2018、2020、2022")
    sources: dict[str, Any] = {}
    all_sealed = True
    for year in _YEARS:
        bundle = values.get(year)
        failures: list[dict[str, Any]] = []
        documents: dict[str, Any] = {}
        if not isinstance(bundle, Mapping):
            failures.append({"code": "SOURCE_BUNDLE_MISSING", "stage": "assembly"})
        else:
            if set(bundle.keys()) != {"landing", "numbered_head", "final_head"} or len(bundle) != 3:
                failures.append({"code": "SOURCE_BUNDLE_ROLES_INVALID", "stage": "assembly"})
            for role in ("landing", "numbered_head", "final_head"):
                result = bundle.get(role)
                if not isinstance(result, FetchResult):
                    failures.append({"code": "FETCH_RESULT_MISSING", "role": role, "stage": "assembly"})
                elif result.failure is not None:
                    failures.append(result.failure.as_dict())
                else:
                    documents[role] = result.document
        if failures:
            all_sealed = False
            sources[str(year)] = {
                "activation": "blocked_fec_object_metadata",
                "failures": failures,
                "year": year,
            }
            continue
        try:
            sources[str(year)] = audit_year(
                year,
                documents["landing"],
                documents["numbered_head"],
                documents["final_head"],
            )
        except FecMetadataError as error:
            all_sealed = False
            sources[str(year)] = {
                "activation": "blocked_fec_object_metadata",
                "failures": [{"code": error.code, "detail": str(error), "stage": "assembly"}],
                "year": year,
            }
    return {
        "activation": (
            "fec_transport_object_metadata_sealed"
            if all_sealed else "blocked_fec_object_metadata"
        ),
        "contains_2026_probability": False,
        "data_ingested": False,
        "model_activation": "unchanged",
        "official_content_sha256_verified": False,
        "predictions_emitted": False,
        "scores_emitted": False,
        "sources": sources,
    }


__all__ = [
    "DEFAULT_MAX_HTML_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "EXPECTED_HREFS",
    "EXPECTED_OBJECT_HEADERS",
    "FINAL_OBJECT_URLS",
    "FEC_HOST",
    "FecMetadataError",
    "FailureRecord",
    "FetchResult",
    "HeadDocument",
    "HeadValidationError",
    "HtmlLinkError",
    "HttpResponse",
    "INDEX_URL",
    "LANDING_URLS",
    "LandingDocument",
    "MetadataRequest",
    "NUMBERED_OBJECT_URLS",
    "OOXML_SPREADSHEET_MIME",
    "PENDING_INGEST",
    "RequestPolicyError",
    "ResponseValidationError",
    "audit_sources",
    "audit_year",
    "canonical_json_bytes",
    "extract_unique_xlsx_href",
    "fetch_final_head",
    "fetch_landing",
    "fetch_numbered_head",
    "sha256_hex",
    "validate_final_head",
    "validate_landing_document",
    "validate_numbered_head",
    "validate_request",
]
