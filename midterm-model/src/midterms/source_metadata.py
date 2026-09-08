"""LH-053 官方来源元数据封印的纯核心。

本模块只处理来源身份、HTTP 元数据包络、固定版本、文件表示层与覆盖范围。
它不导入模型或评分模块，不扫描本地数据目录，也不请求任何结果内容端点。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any


DATAVERSE_HOST = "dataverse.harvard.edu"
SENATE_DOI = "10.7910/DVN/PEJ5QU"
PRESIDENT_DOI = "10.7910/DVN/42MVDX"
DOI_BY_SOURCE = {"senate": SENATE_DOI, "president": PRESIDENT_DOI}
DEFAULT_MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_TIMEOUT_SECONDS = 20.0

_DOI_RE = re.compile(r"^10\.7910/DVN/[A-Z0-9]{6}$")
_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_VERSION_PATH_RE = re.compile(
    r"^/api/datasets/:persistentId/versions(?:/(0|[1-9][0-9]*)\.(0|[1-9][0-9]*))?$"
)
_GUESTBOOK_PATH_RE = re.compile(r"^/api/guestbooks/([1-9][0-9]*)$")
_HEX_LENGTHS = {"MD5": 32, "SHA-1": 40, "SHA-256": 64, "SHA-512": 128}
_FORBIDDEN_RESULT_KEYS = {
    "candidate", "candidates", "winner", "winners", "vote", "votes",
    "vote_count", "margin", "actual_margin", "brier", "crps", "delta",
    "probability", "probabilities", "score", "scores", "election_results",
}
EXPLANATION_URLS = frozenset({
    "https://guides.dataverse.org/en/latest/api/native-api.html",
    "https://www.fec.gov/legal-resources/",
    "https://www.archives.gov/electoral-college/about",
})


class MetadataError(ValueError):
    """LH-053 元数据核心的可预期失败基类。"""


class RequestPolicyError(MetadataError):
    """URL 在网络 open 之前违反 allowlist。"""


class ResponseValidationError(MetadataError):
    """HTTP 响应不是合格的 Dataverse JSON 元数据。"""


class PinValidationError(MetadataError):
    """候选 pin 缺字段、含歧义或混淆表示层。"""


class CoverageError(MetadataError):
    """覆盖判定的来源身份或输入非法。"""


def _strict_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PinValidationError(f"{field} 必须是无首尾空白的非空字符串")
    return value


def _positive_int(value: Any, field: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PinValidationError(f"{field} 必须是整数且不能是 bool")
    lower = 0 if allow_zero else 1
    if value < lower:
        raise PinValidationError(f"{field} 必须不小于 {lower}")
    return value


def _instant(value: Any, field: str) -> str:
    text = _strict_text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise PinValidationError(f"{field} 必须是 ISO-8601 时间") from error
    if parsed.tzinfo is None:
        raise PinValidationError(f"{field} 必须含时区")
    return text


def _json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MetadataError(f"{path} 含非有限浮点数")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise MetadataError(f"{path} 含非字符串 JSON key")
            _json_value(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _json_value(item, f"{path}[{index}]")
        return
    raise MetadataError(f"{path} 含非 JSON 类型 {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """返回无时间戳、无 NaN、键序确定的 UTF-8 JSON 字节。"""

    _json_value(value)
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha256_hex(raw: bytes) -> str:
    if not isinstance(raw, bytes):
        raise MetadataError("sha256_hex 只接受 bytes")
    return hashlib.sha256(raw).hexdigest()


def _validate_doi(doi: Any) -> str:
    if not isinstance(doi, str) or not _DOI_RE.fullmatch(doi):
        raise RequestPolicyError("DOI 必须是冻结的 Dataverse DOI 形式")
    if doi not in DOI_BY_SOURCE.values():
        raise RequestPolicyError("DOI 不在 LH-053 冻结 allowlist")
    return doi


def _query_doi(query: str) -> str:
    try:
        pairs = urllib.parse.parse_qsl(query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise RequestPolicyError("metadata query 不是规范键值对") from error
    if len(pairs) != 1 or pairs[0][0] != "persistentId":
        raise RequestPolicyError("metadata query 必须且只能含一个 persistentId")
    value = pairs[0][1]
    if not value.startswith("doi:"):
        raise RequestPolicyError("persistentId 必须使用 doi: 前缀")
    doi = _validate_doi(value[4:])
    canonical = urllib.parse.urlencode({"persistentId": f"doi:{doi}"})
    if query != canonical:
        raise RequestPolicyError("metadata query 必须使用规范编码且不得重排")
    return doi


def build_versions_url(doi: str) -> str:
    doi = _validate_doi(doi)
    query = urllib.parse.urlencode({"persistentId": f"doi:{doi}"})
    return f"https://{DATAVERSE_HOST}/api/datasets/:persistentId/versions?{query}"


def build_version_metadata_url(doi: str, version: str) -> str:
    doi = _validate_doi(doi)
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise RequestPolicyError("版本必须是数字 MAJOR.MINOR，禁止 latest/draft")
    query = urllib.parse.urlencode({"persistentId": f"doi:{doi}"})
    return (
        f"https://{DATAVERSE_HOST}/api/datasets/:persistentId/versions/"
        f"{version}?{query}"
    )


def build_guestbook_url(guestbook_id: int) -> str:
    if isinstance(guestbook_id, bool) or not isinstance(guestbook_id, int) or guestbook_id <= 0:
        raise RequestPolicyError("guestbook_id 必须是正整数")
    return f"https://{DATAVERSE_HOST}/api/guestbooks/{guestbook_id}"


def build_original_data_url_template(file_id: int) -> str:
    """只构造未来合同可用的模板；本函数绝不发起请求。"""

    if isinstance(file_id, bool) or not isinstance(file_id, int) or file_id <= 0:
        raise PinValidationError("file_id 必须是正整数")
    return f"https://{DATAVERSE_HOST}/api/access/datafile/{file_id}?format=original"


def validate_request_url(url: Any, purpose: str = "metadata") -> str:
    """在 transport/open 之前验证完整 URL，返回逐字相同的合格 URL。"""

    if not isinstance(url, str) or not url or url != url.strip():
        raise RequestPolicyError("URL 必须是无首尾空白的非空字符串")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in url):
        raise RequestPolicyError("URL 禁止控制字符")
    if "\\" in url:
        raise RequestPolicyError("URL 禁止反斜杠")
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as error:
        raise RequestPolicyError("URL 无法解析") from error
    if parsed.scheme != "https" or not parsed.hostname:
        raise RequestPolicyError("只允许 HTTPS URL")
    try:
        port = parsed.port
    except ValueError as error:
        raise RequestPolicyError("URL 端口非法") from error
    if parsed.username is not None or parsed.password is not None or port is not None:
        raise RequestPolicyError("URL 禁止凭证和显式端口")
    if parsed.fragment:
        raise RequestPolicyError("URL 禁止 fragment")
    host = parsed.hostname.lower()
    if "%" in parsed.path:
        raise RequestPolicyError("URL path 禁止 percent 编码，防止路由解码绕过")
    path_lower = parsed.path.lower()
    query_lower = parsed.query.lower()
    if "/api/access/datafile/" in path_lower or "format=original" in query_lower:
        raise RequestPolicyError("结果内容端点必须在 open 前拒绝")
    if purpose == "metadata":
        match = _VERSION_PATH_RE.fullmatch(parsed.path)
        if host != DATAVERSE_HOST or match is None:
            raise RequestPolicyError("metadata URL 的 host/path 不在精确 allowlist")
        doi = _query_doi(parsed.query)
        if match.group(1) is None:
            canonical = build_versions_url(doi)
        else:
            canonical = build_version_metadata_url(doi, f"{match.group(1)}.{match.group(2)}")
        if url != canonical:
            raise RequestPolicyError("metadata URL 必须逐字等于规范 builder 输出")
    elif purpose == "guestbook":
        match = _GUESTBOOK_PATH_RE.fullmatch(parsed.path)
        if host != DATAVERSE_HOST or match is None:
            raise RequestPolicyError("guestbook URL 的 host/path 不在精确 allowlist")
        if parsed.query:
            raise RequestPolicyError("guestbook URL 禁止 query")
        if url != build_guestbook_url(int(match.group(1))):
            raise RequestPolicyError("guestbook URL 必须逐字等于规范 builder 输出")
    elif purpose == "explanation":
        if url not in EXPLANATION_URLS:
            raise RequestPolicyError("说明页必须逐字命中冻结的三个精确 URL")
    else:
        raise RequestPolicyError("purpose 必须是 metadata、guestbook 或 explanation")
    return url


@dataclass(frozen=True)
class MetadataRequest:
    url: str
    headers: Mapping[str, str]
    max_response_bytes: int


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


@dataclass(frozen=True)
class MetadataDocument:
    source_id: str
    url: str
    status: int
    content_type: str
    raw_bytes: bytes
    sha256: str
    payload: Mapping[str, Any]
    attempt_count: int = 1

    def audit_dict(self) -> dict[str, Any]:
        return {
            "attempt_count": self.attempt_count,
            "content_type": self.content_type,
            "response_bytes": len(self.raw_bytes),
            "response_sha256": self.sha256,
            "source_id": self.source_id,
            "status": self.status,
            "url": self.url,
        }


@dataclass(frozen=True)
class FailureRecord:
    source_id: str
    code: str
    stage: str
    url: str
    detail: str
    attempt_count: int
    status: int | None = None
    content_type: str | None = None
    response_bytes: int | None = None
    response_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "attempt_count": self.attempt_count,
            "code": self.code,
            "detail": self.detail,
            "retry_permitted_in_same_contract": False,
            "source_id": self.source_id,
            "stage": self.stage,
            "url": self.url,
        }
        for key, value in (
            ("content_type", self.content_type),
            ("response_bytes", self.response_bytes),
            ("response_sha256", self.response_sha256),
            ("status", self.status),
        ):
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class FetchResult:
    document: MetadataDocument | None = None
    failure: FailureRecord | None = None

    def __post_init__(self) -> None:
        if (self.document is None) == (self.failure is None):
            raise MetadataError("FetchResult 必须且只能含 document 或 failure")

    @property
    def ok(self) -> bool:
        return self.document is not None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _default_transport(request: MetadataRequest, timeout: float) -> HttpResponse:
    opener = urllib.request.build_opener(_NoRedirect)
    network_request = urllib.request.Request(request.url, headers=dict(request.headers), method="GET")
    try:
        with opener.open(network_request, timeout=timeout) as response:
            body = response.read(request.max_response_bytes + 1)
            return HttpResponse(
                int(response.status), dict(response.headers.items()), body, response.geturl()
            )
    except urllib.error.HTTPError as error:
        body = error.read(request.max_response_bytes + 1)
        return HttpResponse(int(error.code), dict(error.headers.items()), body, error.geturl())


Transport = Callable[[MetadataRequest, float], HttpResponse]


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if str(key).lower() == name.lower():
            return str(value)
    return None


def _audit_content_type(headers: Mapping[str, str]) -> str | None:
    """失败回执只保留 MIME 主类型，禁止把任意参数带入审计产物。"""

    value = _header(headers, "Content-Type")
    if value is None:
        return None
    main_type = value.split(";", 1)[0].strip().lower()
    if main_type not in {"application/json", "text/html", "application/xhtml+xml"}:
        return "invalid/redacted"
    return main_type


def _failure(
    source_id: str,
    code: str,
    stage: str,
    url: str,
    detail: str,
    attempt_count: int,
    response: HttpResponse | None = None,
) -> FetchResult:
    audited_source_id = source_id if source_id in DOI_BY_SOURCE else "REDACTED_INVALID_SOURCE"
    body = response.body if response is not None and isinstance(response.body, bytes) else b""
    content_type = _audit_content_type(response.headers) if response is not None else None
    return FetchResult(failure=FailureRecord(
        source_id=audited_source_id,
        code=code,
        stage=stage,
        url=url,
        detail=detail,
        attempt_count=attempt_count,
        status=response.status if response is not None else None,
        content_type=content_type,
        response_bytes=len(body) if response is not None else None,
        response_sha256=sha256_hex(body) if response is not None else None,
    ))


def validate_dataverse_envelope(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResponseValidationError("JSON 顶层必须是对象")
    if value.get("status") != "OK":
        raise ResponseValidationError("Dataverse envelope status 必须为 OK")
    if "data" not in value or not isinstance(value["data"], (Mapping, list)):
        raise ResponseValidationError("Dataverse envelope 缺合法 data")
    return value


def fetch_json_metadata(
    url: str,
    source_id: str,
    *,
    purpose: str = "metadata",
    transport: Transport | None = None,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> FetchResult:
    """单次读取策略允许的元数据或说明页；内容类型契约随 purpose 分段。"""

    if not isinstance(source_id, str) or not source_id or source_id != source_id.strip():
        raise MetadataError("source_id 必须是无首尾空白的非空字符串")
    if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int) or max_response_bytes <= 0:
        raise MetadataError("max_response_bytes 必须是正整数")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise MetadataError("timeout_seconds 必须是正有限数值")
    timeout = float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0:
        raise MetadataError("timeout_seconds 必须是正有限数值")
    try:
        safe_url = validate_request_url(url, purpose)
    except RequestPolicyError as error:
        return _failure(
            source_id,
            "URL_POLICY_REJECTED",
            "before_open",
            "REDACTED_REJECTED_URL",
            str(error),
            0,
        )
    if purpose == "metadata":
        if source_id not in DOI_BY_SOURCE:
            return _failure(
                source_id,
                "SOURCE_ID_REJECTED",
                "before_open",
                "REDACTED_REJECTED_URL",
                "metadata source_id 必须是 senate 或 president",
                0,
            )
        try:
            request_doi = _query_doi(urllib.parse.urlsplit(safe_url).query)
        except (RequestPolicyError, ValueError):
            return _failure(
                source_id,
                "URL_POLICY_REJECTED",
                "before_open",
                "REDACTED_REJECTED_URL",
                "metadata URL 无法提取规范 DOI",
                0,
            )
        if request_doi != DOI_BY_SOURCE[source_id]:
            return _failure(
                source_id,
                "SOURCE_DOI_MISMATCH",
                "before_open",
                "REDACTED_REJECTED_URL",
                "source_id 与 persistentId DOI 不匹配",
                0,
            )
    expected_accept = (
        "text/html,application/xhtml+xml" if purpose == "explanation" else "application/json"
    )
    request = MetadataRequest(
        safe_url,
        {"Accept": expected_accept, "User-Agent": "LongHorizon-LH053-metadata-only/1.0"},
        max_response_bytes,
    )
    active_transport = transport or _default_transport
    try:
        response = active_transport(request, timeout)
    except (TimeoutError, socket.timeout):
        return _failure(source_id, "METADATA_TIMEOUT", "transport", safe_url, "metadata 请求超时", 1)
    except (OSError, urllib.error.URLError) as error:
        return _failure(
            source_id, "METADATA_NETWORK_ERROR", "transport", safe_url,
            f"metadata 网络失败：{type(error).__name__}", 1,
        )
    if not isinstance(response, HttpResponse):
        return _failure(source_id, "TRANSPORT_PROTOCOL_ERROR", "response", safe_url, "transport 返回类型非法", 1)
    if (
        isinstance(response.status, bool)
        or not isinstance(response.status, int)
        or not isinstance(response.headers, Mapping)
        or any(not isinstance(key, str) or not isinstance(value, str) for key, value in response.headers.items())
        or not isinstance(response.body, bytes)
        or not isinstance(response.final_url, str)
    ):
        return _failure(
            source_id, "TRANSPORT_PROTOCOL_ERROR", "response", safe_url,
            "HttpResponse 字段类型非法", 1,
        )
    if response.final_url != safe_url:
        return _failure(source_id, "REDIRECT_REJECTED", "response", safe_url, "metadata 响应发生重定向", 1, response)
    if response.status != 200:
        return _failure(source_id, "HTTP_STATUS_REJECTED", "response", safe_url, "metadata HTTP 状态非 200", 1, response)
    content_length = _header(response.headers, "Content-Length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            return _failure(source_id, "INVALID_CONTENT_LENGTH", "response", safe_url, "Content-Length 非整数", 1, response)
        if declared < 0 or declared > max_response_bytes:
            return _failure(source_id, "RESPONSE_TOO_LARGE", "response", safe_url, "metadata 响应超过大小上限", 1, response)
    if len(response.body) > max_response_bytes:
        return _failure(source_id, "RESPONSE_TOO_LARGE", "response", safe_url, "metadata 响应超过大小上限", 1, response)
    content_type = _header(response.headers, "Content-Type") or ""
    main_content_type = content_type.split(";", 1)[0].strip().lower()
    allowed_content_types = (
        {"text/html", "application/xhtml+xml"}
        if purpose == "explanation"
        else {"application/json"}
    )
    if main_content_type not in allowed_content_types:
        if purpose == "explanation":
            return _failure(source_id, "NON_HTML_CONTENT_TYPE", "response", safe_url, "说明页响应不是 HTML", 1, response)
        return _failure(source_id, "NON_JSON_CONTENT_TYPE", "response", safe_url, "metadata 响应不是 application/json", 1, response)
    if purpose == "explanation":
        try:
            response.body.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            return _failure(
                source_id, "INVALID_HTML_EXPLANATION", "parse", safe_url,
                f"说明页不是 UTF-8：{type(error).__name__}", 1, response,
            )
        raw_hash = sha256_hex(response.body)
        return FetchResult(document=MetadataDocument(
            source_id,
            safe_url,
            200,
            content_type,
            response.body,
            raw_hash,
            {"document_kind": "html_explanation", "purpose": "explanation"},
        ))
    try:
        decoded = response.body.decode("utf-8", errors="strict")
        payload = json.loads(decoded)
        envelope = validate_dataverse_envelope(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ResponseValidationError) as error:
        return _failure(
            source_id, "INVALID_JSON_METADATA", "parse", safe_url,
            f"metadata JSON 无效：{type(error).__name__}", 1, response,
        )
    raw_hash = sha256_hex(response.body)
    return FetchResult(document=MetadataDocument(
        source_id, safe_url, 200, content_type, response.body, raw_hash, envelope
    ))


_PIN_FIELDS = frozenset({
    "source_id", "pin_status", "doi", "dataset_id", "version", "release_time",
    "dataset_title", "dataset_scope", "license", "guestbook_id", "metadata_url",
    "files", "coverage_evidence",
})
_FILE_FIELDS = frozenset({
    "file_id", "filename", "filesize", "checksum_type", "checksum_value",
    "content_type", "restricted", "guestbook_id", "datafile_url_template",
    "representation", "representation_evidence",
})
_LICENSE_FIELDS = frozenset({"name", "uri"})
_COVERAGE_FIELDS = frozenset({"source", "fields"})
_REPRESENTATION_FIELDS = frozenset({
    "source", "file_identity", "checksum_scope", "original_filename",
})


def _reject_result_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_RESULT_KEYS:
                raise PinValidationError(f"{path}.{key} 是禁止的结果字段")
            _reject_result_keys(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_result_keys(item, f"{path}[{index}]")


def _license(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _LICENSE_FIELDS:
        raise PinValidationError("license 必须且只能含 name/uri")
    name = _strict_text(value["name"], "license.name")
    uri = _strict_text(value["uri"], "license.uri")
    parsed = urllib.parse.urlsplit(uri)
    if parsed.scheme != "https" or not parsed.hostname:
        raise PinValidationError("license.uri 必须是 HTTPS")
    return {"name": name, "uri": uri}


def _guestbook_id(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, field)


def _file_pin(value: Any, dataset_guestbook_id: int | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FILE_FIELDS:
        raise PinValidationError("files[] 字段不完整或越权")
    file_id = _positive_int(value["file_id"], "file_id")
    filename = _strict_text(value["filename"], "filename")
    filesize = _positive_int(value["filesize"], "filesize", allow_zero=True)
    checksum_type = _strict_text(value["checksum_type"], "checksum_type").upper()
    if checksum_type not in _HEX_LENGTHS:
        raise PinValidationError("checksum_type 未知")
    checksum_value = _strict_text(value["checksum_value"], "checksum_value").lower()
    if not re.fullmatch(r"[0-9a-f]+", checksum_value) or len(checksum_value) != _HEX_LENGTHS[checksum_type]:
        raise PinValidationError("checksum_value 与 checksum_type 不匹配")
    content_type = _strict_text(value["content_type"], "content_type")
    if content_type.split(";", 1)[0].strip().lower() in {"text/html", "application/xhtml+xml"}:
        raise PinValidationError("候选数据文件不能是 HTML")
    if value["restricted"] is not False:
        raise PinValidationError("restricted 必须明确为 false")
    guestbook = _guestbook_id(value["guestbook_id"], "files[].guestbook_id")
    if dataset_guestbook_id is not None and guestbook != dataset_guestbook_id:
        raise PinValidationError("文件与数据集 guestbook ID 不一致")
    if value["representation"] != "original":
        raise PinValidationError("representation 必须严格为 original")
    evidence = value["representation_evidence"]
    if not isinstance(evidence, Mapping) or set(evidence) != _REPRESENTATION_FIELDS:
        raise PinValidationError("representation_evidence 字段不完整或越权")
    if evidence.get("source") != "official_metadata":
        raise PinValidationError("表示层证据只能来自 official_metadata")
    if evidence.get("file_identity") != "uploaded_original":
        raise PinValidationError("官方元数据未证明文件身份是上传原件")
    if evidence.get("checksum_scope") != "uploaded_original":
        raise PinValidationError("官方元数据未证明 checksum 适用于上传原件")
    if evidence.get("original_filename") != filename:
        raise PinValidationError("原件证据 filename 与 pin 不一致")
    expected_template = build_original_data_url_template(file_id)
    if value["datafile_url_template"] != expected_template:
        raise PinValidationError("原件 URL 模板缺 format=original 或 file ID 不匹配")
    return {
        "checksum_type": checksum_type,
        "checksum_value": checksum_value,
        "content_type": content_type,
        "datafile_url_template": expected_template,
        "file_id": file_id,
        "filename": filename,
        "filesize": filesize,
        "guestbook_id": guestbook,
        "representation": "original",
        "representation_evidence": {
            "checksum_scope": "uploaded_original",
            "file_identity": "uploaded_original",
            "original_filename": filename,
            "source": "official_metadata",
        },
        "restricted": False,
    }


def _coverage_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _COVERAGE_FIELDS:
        raise PinValidationError("coverage_evidence 必须且只能含 source/fields")
    if value["source"] != "official_metadata":
        raise PinValidationError("coverage 只能来自 official_metadata")
    fields = value["fields"]
    if isinstance(fields, (str, bytes, Mapping)) or not isinstance(fields, Sequence) or not fields:
        raise PinValidationError("coverage_evidence.fields 必须是非空字符串序列")
    normalized = [_strict_text(item, f"coverage_evidence.fields[{i}]") for i, item in enumerate(fields)]
    if len(set(normalized)) != len(normalized):
        raise PinValidationError("coverage_evidence.fields 不得重复")
    return {"fields": normalized, "source": "official_metadata"}


def validate_pin(pin: Any, *, require_official: bool = False) -> dict[str, Any]:
    """严格规范化候选/官方 pin；多个文件即视为未消歧。"""

    if not isinstance(pin, Mapping) or set(pin) != _PIN_FIELDS:
        raise PinValidationError("pin 字段不完整或越权")
    _reject_result_keys(pin)
    source_id = pin["source_id"]
    if source_id not in DOI_BY_SOURCE:
        raise PinValidationError("source_id 必须是 senate 或 president")
    expected_doi = DOI_BY_SOURCE[source_id]
    if pin["doi"] != expected_doi:
        raise PinValidationError("source_id 与冻结 DOI 不匹配")
    status = pin["pin_status"]
    if status not in {"metadata_candidate", "officially_pinned"}:
        raise PinValidationError("pin_status 非法")
    if require_official and status != "officially_pinned":
        raise PinValidationError("activation 只接受 officially_pinned")
    dataset_id = _positive_int(pin["dataset_id"], "dataset_id")
    version = _strict_text(pin["version"], "version")
    if not _VERSION_RE.fullmatch(version):
        raise PinValidationError("version 必须是数字 MAJOR.MINOR")
    release_time = _instant(pin["release_time"], "release_time")
    title = _strict_text(pin["dataset_title"], "dataset_title")
    scope = _strict_text(pin["dataset_scope"], "dataset_scope")
    license_value = _license(pin["license"])
    guestbook = _guestbook_id(pin["guestbook_id"], "guestbook_id")
    metadata_url = _strict_text(pin["metadata_url"], "metadata_url")
    try:
        validate_request_url(metadata_url, "metadata")
    except RequestPolicyError as error:
        raise PinValidationError("metadata_url 不合格") from error
    if metadata_url != build_version_metadata_url(expected_doi, version):
        raise PinValidationError("metadata_url 必须固定到同 DOI 的数字版本")
    files = pin["files"]
    if isinstance(files, (str, bytes, Mapping)) or not isinstance(files, Sequence) or len(files) != 1:
        raise PinValidationError("必须且只能有一个已消歧候选文件")
    file_pin = _file_pin(files[0], guestbook)
    coverage = _coverage_evidence(pin["coverage_evidence"])
    return {
        "coverage_evidence": coverage,
        "dataset_id": dataset_id,
        "dataset_scope": scope,
        "dataset_title": title,
        "doi": expected_doi,
        "files": [file_pin],
        "guestbook_id": guestbook,
        "license": license_value,
        "metadata_url": metadata_url,
        "pin_status": status,
        "release_time": release_time,
        "source_id": source_id,
        "version": version,
    }


def validate_official_pin(pin: Any) -> dict[str, Any]:
    return validate_pin(pin, require_official=True)


def _metadata_field(version_record: Mapping[str, Any], name: str) -> Any:
    direct = version_record.get(name)
    if direct not in (None, "", [], {}):
        return direct
    blocks = version_record.get("metadataBlocks", {})
    citation = blocks.get("citation", {}) if isinstance(blocks, Mapping) else {}
    fields = citation.get("fields", []) if isinstance(citation, Mapping) else []
    if isinstance(fields, Sequence) and not isinstance(fields, (str, bytes, Mapping)):
        for field in fields:
            if isinstance(field, Mapping) and field.get("typeName") == name:
                return field.get("value")
    return None


def _scope_text(value: Any) -> str:
    if isinstance(value, str):
        return _strict_text(value, "dataset_scope")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, Mapping)):
        texts: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                texts.append(item.strip())
            elif isinstance(item, Mapping):
                for inner in item.values():
                    if isinstance(inner, Mapping):
                        for candidate in inner.values():
                            if isinstance(candidate, str) and candidate.strip():
                                texts.append(candidate.strip())
                    elif isinstance(inner, str) and inner.strip():
                        texts.append(inner.strip())
        if texts:
            return " | ".join(texts)
    raise PinValidationError("官方 metadata 缺可解释 dataset scope")


def _version_records(envelope: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    validated = validate_dataverse_envelope(envelope)
    data = validated["data"]
    if isinstance(data, list):
        records = data
    elif isinstance(data, Mapping) and isinstance(data.get("datasetVersion"), Mapping):
        records = [data["datasetVersion"]]
    elif isinstance(data, Mapping):
        records = [data]
    else:
        records = []
    if not records or any(not isinstance(item, Mapping) for item in records):
        raise PinValidationError("官方 envelope 不含版本对象")
    return list(records)


def pin_from_dataverse_version(
    envelope: Mapping[str, Any],
    *,
    source_id: str,
    doi: str,
    version: str,
    candidate_filenames: Sequence[str],
) -> dict[str, Any]:
    """从官方版本 JSON 建立严格 pin；候选文件名必须由合同预先给出。"""

    if source_id not in DOI_BY_SOURCE or doi != DOI_BY_SOURCE[source_id]:
        raise PinValidationError("source_id/DOI 不匹配")
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise PinValidationError("version 必须是数字 MAJOR.MINOR")
    if isinstance(candidate_filenames, (str, bytes, Mapping)) or not isinstance(candidate_filenames, Sequence):
        raise PinValidationError("candidate_filenames 必须是序列")
    names = tuple(_strict_text(item, f"candidate_filenames[{i}]") for i, item in enumerate(candidate_filenames))
    if not names or len(set(names)) != len(names):
        raise PinValidationError("candidate_filenames 必须非空且唯一")
    major, minor = (int(part) for part in version.split("."))
    matches = [
        record for record in _version_records(envelope)
        if record.get("versionNumber") == major and record.get("versionMinorNumber") == minor
    ]
    if len(matches) != 1:
        raise PinValidationError("数字版本缺失或无法唯一消歧")
    record = matches[0]
    if record.get("versionState") != "RELEASED":
        raise PinValidationError("versionState 必须由官方元数据明确为 RELEASED")
    dataset_id = record.get("datasetId")
    title = _metadata_field(record, "title")
    scope_raw = (
        _metadata_field(record, "datasetScope")
        or _metadata_field(record, "dsDescription")
        or _metadata_field(record, "subtitle")
    )
    license_raw = record.get("license")
    if not isinstance(license_raw, Mapping):
        raise PinValidationError("官方版本缺结构化 license name/uri")
    files_raw = record.get("files")
    if isinstance(files_raw, (str, bytes, Mapping)) or not isinstance(files_raw, Sequence):
        raise PinValidationError("官方版本缺 files")
    selected: list[Mapping[str, Any]] = []
    for wrapper in files_raw:
        if not isinstance(wrapper, Mapping):
            continue
        data_file = wrapper.get("dataFile", wrapper)
        if isinstance(data_file, Mapping):
            original = wrapper.get("originalFile", data_file.get("originalFile"))
            identities = {data_file.get("filename")}
            if isinstance(original, Mapping):
                identities.add(original.get("filename"))
            if identities.intersection(names):
                selected.append({"wrapper": wrapper, "data": data_file})
    if len(selected) != 1:
        raise PinValidationError("候选数据文件缺失或有多个无法消歧")
    wrapper = selected[0]["wrapper"]
    data_file = selected[0]["data"]
    original = wrapper.get("originalFile", data_file.get("originalFile"))
    if not isinstance(original, Mapping):
        raise PinValidationError("官方元数据未独立证明上传原件及其 checksum；不得把 archival 表示冒充原件")
    checksum = original.get("checksum")
    if not isinstance(checksum, Mapping):
        raise PinValidationError("上传原件证据缺独立 checksum")
    guestbook_raw = data_file.get("guestbookId", record.get("guestbookId"))
    pin = {
        "coverage_evidence": {
            "fields": [
                f"dataset_title={_strict_text(title, 'dataset_title')}",
                f"dataset_scope={_scope_text(scope_raw)}",
                f"filename={_strict_text(original.get('filename'), 'original.filename')}",
            ],
            "source": "official_metadata",
        },
        "dataset_id": dataset_id,
        "dataset_scope": _scope_text(scope_raw),
        "dataset_title": title,
        "doi": doi,
        "files": [{
            "checksum_type": checksum.get("type"),
            "checksum_value": checksum.get("value"),
            "content_type": original.get("contentType"),
            "datafile_url_template": build_original_data_url_template(data_file.get("id")),
            "file_id": data_file.get("id"),
            "filename": original.get("filename"),
            "filesize": original.get("filesize"),
            "guestbook_id": guestbook_raw,
            "representation": "original",
            "representation_evidence": {
                "checksum_scope": "uploaded_original",
                "file_identity": "uploaded_original",
                "original_filename": original.get("filename"),
                "source": "official_metadata",
            },
            "restricted": wrapper.get("restricted", data_file.get("restricted")),
        }],
        "guestbook_id": guestbook_raw,
        "license": {"name": license_raw.get("name"), "uri": license_raw.get("uri")},
        "metadata_url": build_version_metadata_url(doi, version),
        "pin_status": "officially_pinned",
        "release_time": record.get("releaseTime"),
        "source_id": source_id,
        "version": version,
    }
    return validate_official_pin(pin)


@dataclass(frozen=True)
class CoverageDecision:
    source_id: str
    status: str
    code: str
    confirmed_through: int | None
    ingest_cycles: tuple[int, ...]
    isolated_cycles: tuple[int, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "confirmed_through": self.confirmed_through,
            "ingest_cycles": list(self.ingest_cycles),
            "isolated_cycles": list(self.isolated_cycles),
            "reason": self.reason,
            "source_id": self.source_id,
            "status": self.status,
        }


def _coverage_claims(fields: Sequence[str]) -> tuple[list[tuple[int, int]], set[int], bool]:
    """只接受明确区间/上界；孤立年份不能自动成为覆盖证据。"""

    intervals: list[tuple[int, int]] = []
    all_years: set[int] = set()
    claimed_years: set[int] = set()
    ambiguous_language = False
    for field in fields:
        if re.search(
            r"\b(?:planned|forthcoming|expected|anticipated|provisional|pending|future|"
            r"exclude|excludes|excluded|excluding|not\s+included|not\s+covered|"
            r"will\s+include)\b",
            field,
            flags=re.IGNORECASE,
        ):
            ambiguous_language = True
        all_years.update(int(value) for value in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", field))
        found = [
            (int(start), int(end))
            for start, end in re.findall(
                r"(?<!\d)((?:19|20)\d{2})\s*(?:-|_|–|—|to|through|至)\s*((?:19|20)\d{2})(?!\d)",
                field,
                flags=re.IGNORECASE,
            )
            if int(start) <= int(end)
        ]
        intervals.extend(found)
        for start, end in found:
            claimed_years.update((start, end))
    # 明确区间以外出现更晚年份（例如“2022 update planned”）是语义冲突，必须关闭。
    highest_claim = max((end for _, end in intervals), default=None)
    stray_future = highest_claim is not None and any(year > highest_claim for year in all_years - claimed_years)
    endpoints = {end for _, end in intervals}
    conflicting_endpoints = len(endpoints) > 1
    return (
        intervals,
        all_years - claimed_years,
        ambiguous_language or stray_future or conflicting_endpoints,
    )


def decide_coverage(source_id: str, pin: Mapping[str, Any]) -> CoverageDecision:
    normalized = validate_official_pin(pin)
    if source_id != normalized["source_id"]:
        raise CoverageError("source_id 与 pin 不一致")
    fields = normalized["coverage_evidence"]["fields"]
    ranges, _isolated_years, ambiguous = _coverage_claims(fields)

    def covered(year: int) -> bool:
        return not ambiguous and any(start <= year <= end for start, end in ranges)

    endpoints = {end for _, end in ranges}
    upper = max(endpoints) if endpoints else None
    if source_id == "senate":
        if covered(2022):
            isolated = (2024,) if covered(2024) or (upper is not None and upper >= 2024) else ()
            return CoverageDecision(
                source_id, "confirmed", "COVERAGE_CONFIRMED", upper,
                (2018, 2022), isolated, "官方 metadata 明确覆盖 2022",
            )
        if not ambiguous and upper == 2020:
            return CoverageDecision(
                source_id, "insufficient", "SOURCE_COVERAGE_INSUFFICIENT", upper,
                (), (), "Senate 官方 metadata 上界仅到 2020",
            )
        return CoverageDecision(
            source_id, "unverified", "SOURCE_COVERAGE_UNVERIFIED", upper,
            (), (), "Senate 官方 metadata 未明确证明覆盖 2022",
        )
    if source_id == "president":
        if covered(2020):
            return CoverageDecision(
                source_id, "confirmed", "COVERAGE_CONFIRMED", upper,
                (2020,), tuple(year for year in (2024,) if covered(year)),
                "官方 metadata 明确覆盖 2020",
            )
        return CoverageDecision(
            source_id, "unverified", "SOURCE_COVERAGE_UNVERIFIED", upper,
            (), (), "President 官方 metadata 未明确证明覆盖 2020",
        )
    raise CoverageError("未知 source_id")


@dataclass(frozen=True)
class ActivationDecision:
    activation: str
    official_pin_complete: bool
    reason_code: str
    next_permitted_action: str
    coverage: Mapping[str, Mapping[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "activation": self.activation,
            "coverage": dict(self.coverage),
            "next_permitted_action": self.next_permitted_action,
            "official_pin_complete": self.official_pin_complete,
            "reason_code": self.reason_code,
        }


def decide_activation(pins: Mapping[str, Mapping[str, Any]]) -> ActivationDecision:
    if not isinstance(pins, Mapping):
        raise PinValidationError("pins 必须是 mapping")
    decisions: dict[str, Mapping[str, Any]] = {}
    normalized_pins: dict[str, Mapping[str, Any]] = {}
    # 先完整验证两源，之后才判断任一源的 coverage，避免缺源却误报 pin complete。
    for source_id in ("senate", "president"):
        if source_id not in pins:
            return ActivationDecision(
                "blocked_source_metadata", False, "OFFICIAL_PIN_INCOMPLETE",
                "retry_metadata_in_new_contract", decisions,
            )
        try:
            normalized_pins[source_id] = validate_official_pin(pins[source_id])
        except (MetadataError, KeyError, TypeError):
            return ActivationDecision(
                "blocked_source_metadata", False, "OFFICIAL_PIN_INVALID",
                "retry_metadata_in_new_contract", decisions,
            )
    for source_id in ("senate", "president"):
        decision = decide_coverage(source_id, normalized_pins[source_id])
        decisions[source_id] = decision.as_dict()
        if decision.status != "confirmed":
            return ActivationDecision(
                "blocked_source_metadata", True, decision.code,
                "retry_metadata_in_new_contract", decisions,
            )
    return ActivationDecision(
        "metadata_ready_for_separate_ingest_contract", True, "METADATA_READY",
        "open_separate_ingest_contract", decisions,
    )


__all__ = [
    "ActivationDecision", "CoverageDecision", "CoverageError", "DATAVERSE_HOST",
    "DEFAULT_MAX_RESPONSE_BYTES", "DEFAULT_TIMEOUT_SECONDS", "DOI_BY_SOURCE",
    "FailureRecord", "FetchResult", "HttpResponse", "MetadataDocument", "MetadataError",
    "MetadataRequest", "PRESIDENT_DOI", "PinValidationError", "RequestPolicyError",
    "ResponseValidationError", "SENATE_DOI", "Transport", "build_guestbook_url",
    "build_original_data_url_template", "build_version_metadata_url", "build_versions_url",
    "canonical_json_bytes", "decide_activation", "decide_coverage", "fetch_json_metadata",
    "pin_from_dataverse_version", "sha256_hex", "validate_dataverse_envelope",
    "validate_official_pin", "validate_pin", "validate_request_url",
]
