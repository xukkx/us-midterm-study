"""LH-054 FEC source-metadata 纯核心的离线攻击测试。"""

from __future__ import annotations

import copy
import json
import math
import sys
import unittest
import urllib.error
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from midterms.fec_source_metadata import (  # noqa: E402
    DEFAULT_MAX_HTML_BYTES,
    EXPECTED_HREFS,
    EXPECTED_OBJECT_HEADERS,
    FINAL_OBJECT_URLS,
    LANDING_URLS,
    NUMBERED_OBJECT_URLS,
    OOXML_SPREADSHEET_MIME,
    FetchResult,
    FecMetadataError,
    HeadValidationError,
    HtmlLinkError,
    HttpResponse,
    RequestPolicyError,
    ResponseValidationError,
    audit_sources,
    audit_year,
    canonical_json_bytes,
    extract_unique_xlsx_href,
    fetch_final_head,
    fetch_landing,
    fetch_numbered_head,
    sha256_hex,
    validate_final_head,
    validate_landing_document,
    validate_numbered_head,
    validate_request,
)
import midterms.fec_source_metadata as fec_core  # noqa: E402


def landing_html(year: int, *, href: str | None = None, extra: str = "") -> bytes:
    actual = EXPECTED_HREFS[year] if href is None else href
    return (
        "<!doctype html><html><body>"
        f'<a class="download" data-year="{year}" href="{actual}">'
        f"Federal Elections {year} XLSX</a>{extra}</body></html>"
    ).encode("utf-8")


def landing_response(source_key="index", body: bytes | None = None, **changes):
    if body is None:
        body = b"<!doctype html><html><body>FEC</body></html>" if source_key == "index" else landing_html(source_key)
    values = {
        "status": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8", "Content-Length": str(len(body))},
        "final_url": LANDING_URLS[source_key],
        "body": body,
    }
    values.update(changes)
    return HttpResponse(**values)


def numbered_response(year: int, **changes):
    values = {
        "status": 302,
        "headers": {"Location": FINAL_OBJECT_URLS[year]},
        "final_url": NUMBERED_OBJECT_URLS[year],
    }
    values.update(changes)
    return HttpResponse(**values)


def final_response(year: int, **changes):
    values = {
        "status": 200,
        "headers": dict(EXPECTED_OBJECT_HEADERS[year]),
        "final_url": FINAL_OBJECT_URLS[year],
    }
    values.update(changes)
    return HttpResponse(**values)


class FakeTransport:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return self.response


class ExplodingHeadResponse:
    """任何正文 API 一经访问就失败的 HEAD canary。"""

    def __init__(self, status, headers, final_url):
        self.status = status
        self.headers = headers
        self.final_url = final_url

    @property
    def body(self):
        raise AssertionError("HEAD 禁止读取 body")

    def read(self, *args, **kwargs):
        raise AssertionError("HEAD 禁止调用 read")

    def readinto(self, *args, **kwargs):
        raise AssertionError("HEAD 禁止调用 readinto")

    def __iter__(self):
        raise AssertionError("HEAD 禁止迭代正文")


class CanonicalTests(unittest.TestCase):
    def test_001_canonical_keys_sorted(self):
        self.assertEqual(canonical_json_bytes({"z": 1, "a": 2}), b'{"a":2,"z":1}')

    def test_002_canonical_unicode_utf8(self):
        self.assertIn("封印".encode(), canonical_json_bytes({"v": "封印"}))

    def test_003_canonical_rejects_nan(self):
        with self.assertRaises(FecMetadataError):
            canonical_json_bytes({"v": math.nan})

    def test_004_canonical_rejects_non_string_key(self):
        with self.assertRaises(FecMetadataError):
            canonical_json_bytes({1: "bad"})

    def test_005_sha256_known_value(self):
        self.assertEqual(sha256_hex(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_006_sha256_rejects_text(self):
        with self.assertRaises(FecMetadataError):
            sha256_hex("abc")


class RequestPolicyTests(unittest.TestCase):
    def test_007_index_get_allowed(self):
        self.assertEqual(validate_request("GET", LANDING_URLS["index"]).method, "GET")

    def test_008_annual_gets_allowed(self):
        for year in (2018, 2020, 2022):
            with self.subTest(year=year):
                self.assertEqual(validate_request("GET", LANDING_URLS[year]).url, LANDING_URLS[year])

    def test_009_numbered_heads_allowed(self):
        for year in (2018, 2020, 2022):
            self.assertEqual(validate_request("HEAD", NUMBERED_OBJECT_URLS[year]).max_response_bytes, 0)

    def test_010_final_heads_allowed(self):
        for year in (2018, 2020, 2022):
            self.assertEqual(validate_request("HEAD", FINAL_OBJECT_URLS[year]).method, "HEAD")

    def test_011_post_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("POST", LANDING_URLS["index"])

    def test_012_lowercase_method_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("get", LANDING_URLS["index"])

    def test_013_attachment_get_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", NUMBERED_OBJECT_URLS[2018])

    def test_014_landing_head_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("HEAD", LANDING_URLS[2018])

    def test_015_pdf_get_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", "https://www.fec.gov/documents/1/results.pdf")

    def test_016_http_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"].replace("https:", "http:"))

    def test_017_unknown_host_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"].replace("www.fec.gov", "fec.gov.evil.test"))

    def test_018_host_case_drift_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"].replace("www.fec.gov", "WWW.FEC.GOV"))

    def test_019_port_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"].replace(".gov/", ".gov:443/"))

    def test_020_userinfo_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"].replace("https://", "https://user@"))

    def test_021_fragment_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"] + "#download")

    def test_022_query_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"] + "?format=xlsx")

    def test_023_percent_separator_rejected(self):
        url = LANDING_URLS[2018].replace("federal-elections", "federal%2felections")
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", url)

    def test_024_backslash_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS[2018].replace("/federal", "\\federal"))

    def test_025_control_character_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"] + "\n")

    def test_026_range_header_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("HEAD", NUMBERED_OBJECT_URLS[2018], {"Range": "bytes=0-0"})

    def test_027_unknown_header_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"], {"X-Guess": "1"})

    def test_028_bad_accept_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"], {"Accept": "*/*"})

    def test_029_head_nonzero_body_limit_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("HEAD", NUMBERED_OBJECT_URLS[2018], max_response_bytes=1)

    def test_030_get_zero_body_limit_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"], max_response_bytes=0)

    def test_031_bool_limit_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", LANDING_URLS["index"], max_response_bytes=True)

    def test_032_unknown_path_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request("GET", "https://www.fec.gov/introduction-campaign-finance/")


class LandingParserTests(unittest.TestCase):
    def test_033_each_expected_href_passes(self):
        for year in (2018, 2020, 2022):
            self.assertEqual(extract_unique_xlsx_href(year, landing_html(year)), EXPECTED_HREFS[year])

    def test_034_attribute_order_does_not_matter(self):
        raw = f'<a href="{EXPECTED_HREFS[2018]}" id="x" class="y">Excel workbook</a>'.encode()
        self.assertEqual(extract_unique_xlsx_href(2018, raw), EXPECTED_HREFS[2018])

    def test_035_missing_candidate_rejected(self):
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, b"<html><a href='/about/'>About</a></html>")

    def test_036_duplicate_candidate_rejected(self):
        extra = f'<a href="{EXPECTED_HREFS[2018]}">Excel duplicate</a>'
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, landing_html(2018, extra=extra))

    def test_037_extra_xlsx_candidate_rejected(self):
        extra = '<a href="/documents/999/other.xlsx">Other workbook</a>'
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, landing_html(2018, extra=extra))

    def test_038_cross_year_link_rejected(self):
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, landing_html(2018, href=EXPECTED_HREFS[2020]))

    def test_039_uppercase_extension_drift_rejected(self):
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, landing_html(2018, href=EXPECTED_HREFS[2018][:-5] + ".XLSX"))

    def test_040_xls_suffix_drift_rejected(self):
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, landing_html(2018, href=EXPECTED_HREFS[2018][:-5] + ".xls"))

    def test_041_csv_suffix_drift_rejected(self):
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, landing_html(2018, href=EXPECTED_HREFS[2018][:-5] + ".csv"))

    def test_042_pdf_masquerading_as_workbook_rejected(self):
        raw = b'<a href="/documents/2706/federalelections2018.pdf">Download XLSX</a>'
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, raw)

    def test_043_duplicate_href_attribute_rejected(self):
        raw = f'<a href="{EXPECTED_HREFS[2018]}" HREF="/evil.xlsx">Excel</a>'.encode()
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, raw)

    def test_044_invalid_utf8_rejected(self):
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, b"\xff.xlsx")

    def test_045_text_only_xlsx_is_candidate_and_rejected(self):
        with self.assertRaises(HtmlLinkError):
            extract_unique_xlsx_href(2018, b'<a href="/wrong.pdf">Download XLSX</a>')

    def test_046_invalid_year_rejected(self):
        with self.assertRaises(RequestPolicyError):
            extract_unique_xlsx_href(2024, landing_html(2018))

    def test_046a_realistic_pdf_and_xlsx_selects_only_xlsx(self):
        pdf = '<a href="/documents/2705/federalelections2018.pdf">Federal Elections 2018 PDF</a>'
        raw = landing_html(2018, extra=pdf)
        self.assertEqual(extract_unique_xlsx_href(2018, raw), EXPECTED_HREFS[2018])


class LandingResponseTests(unittest.TestCase):
    def test_047_index_document_passes_without_href(self):
        doc = validate_landing_document("index", landing_response())
        self.assertIsNone(doc.expected_xlsx_href)

    def test_048_annual_document_preserves_raw_bytes(self):
        raw = landing_html(2020)
        doc = validate_landing_document(2020, landing_response(2020, raw))
        self.assertEqual(doc.raw_bytes, raw)
        self.assertEqual(doc.sha256, sha256_hex(raw))

    def test_049_status_rejected(self):
        with self.assertRaises(ResponseValidationError):
            validate_landing_document("index", landing_response(status=404))

    def test_050_redirect_rejected(self):
        with self.assertRaises(ResponseValidationError):
            validate_landing_document("index", landing_response(final_url=LANDING_URLS[2018]))

    def test_051_html_mime_required(self):
        with self.assertRaises(ResponseValidationError):
            validate_landing_document("index", landing_response(headers={"Content-Type": "application/pdf"}))

    def test_052_mime_parameters_allowed(self):
        doc = validate_landing_document("index", landing_response())
        self.assertEqual(doc.content_type, "text/html")

    def test_053_empty_body_rejected(self):
        with self.assertRaises(ResponseValidationError):
            validate_landing_document("index", landing_response(body=b"", headers={"Content-Type": "text/html", "Content-Length": "0"}))

    def test_054_oversize_body_rejected(self):
        body = b"x" * 11
        with self.assertRaises(ResponseValidationError):
            validate_landing_document("index", landing_response(body=body), max_response_bytes=10)

    def test_055_non_decimal_content_length_rejected(self):
        with self.assertRaises(ResponseValidationError):
            validate_landing_document("index", landing_response(headers={"Content-Type": "text/html", "Content-Length": "+44"}))

    def test_056_content_length_mismatch_rejected(self):
        with self.assertRaises(ResponseValidationError):
            validate_landing_document("index", landing_response(headers={"Content-Type": "text/html", "Content-Length": "1"}))

    def test_057_non_bytes_body_rejected(self):
        response = HttpResponse(200, {"Content-Type": "text/html"}, LANDING_URLS["index"], "html")
        with self.assertRaises(ResponseValidationError):
            validate_landing_document("index", response)

    def test_058_duplicate_case_headers_rejected(self):
        headers = {"Content-Type": "text/html", "content-type": "text/html"}
        with self.assertRaises(ResponseValidationError):
            validate_landing_document("index", landing_response(headers=headers))

    def test_059_size_ceiling_is_two_mib(self):
        self.assertEqual(DEFAULT_MAX_HTML_BYTES, 2 * 1024 * 1024)


class HeadValidationTests(unittest.TestCase):
    def test_060_numbered_heads_pass(self):
        for year in (2018, 2020, 2022):
            doc = validate_numbered_head(year, numbered_response(year))
            self.assertEqual(doc.safe_headers["Location"], FINAL_OBJECT_URLS[year])

    def test_061_numbered_requires_302(self):
        with self.assertRaises(HeadValidationError):
            validate_numbered_head(2018, numbered_response(2018, status=301))

    def test_062_numbered_wrong_location_rejected(self):
        with self.assertRaises(HeadValidationError):
            validate_numbered_head(2018, numbered_response(2018, headers={"Location": FINAL_OBJECT_URLS[2020]}))

    def test_063_numbered_missing_location_rejected(self):
        with self.assertRaises(ResponseValidationError):
            validate_numbered_head(2018, numbered_response(2018, headers={}))

    def test_064_numbered_auto_redirect_rejected(self):
        with self.assertRaises(HeadValidationError):
            validate_numbered_head(2018, numbered_response(2018, final_url=FINAL_OBJECT_URLS[2018]))

    def test_065_numbered_location_header_case_insensitive(self):
        doc = validate_numbered_head(2018, numbered_response(2018, headers={"location": FINAL_OBJECT_URLS[2018]}))
        self.assertEqual(doc.status, 302)

    def test_066_numbered_duplicate_location_rejected(self):
        headers = {"Location": FINAL_OBJECT_URLS[2018], "location": FINAL_OBJECT_URLS[2018]}
        with self.assertRaises(ResponseValidationError):
            validate_numbered_head(2018, numbered_response(2018, headers=headers))

    def test_067_numbered_head_never_touches_body_canary(self):
        response = ExplodingHeadResponse(302, {"Location": FINAL_OBJECT_URLS[2018]}, NUMBERED_OBJECT_URLS[2018])
        self.assertEqual(validate_numbered_head(2018, response).status, 302)

    def test_068_final_heads_pass(self):
        for year in (2018, 2020, 2022):
            doc = validate_final_head(year, final_response(year))
            self.assertEqual(doc.safe_headers["ETag"], EXPECTED_OBJECT_HEADERS[year]["ETag"])

    def test_069_final_requires_200(self):
        with self.assertRaises(HeadValidationError):
            validate_final_head(2018, final_response(2018, status=304))

    def test_070_final_redirect_rejected(self):
        with self.assertRaises(HeadValidationError):
            validate_final_head(2018, final_response(2018, final_url=NUMBERED_OBJECT_URLS[2018]))

    def test_071_content_type_drift_rejected(self):
        headers = dict(EXPECTED_OBJECT_HEADERS[2018]); headers["Content-Type"] = "application/octet-stream"
        with self.assertRaises(HeadValidationError):
            validate_final_head(2018, final_response(2018, headers=headers))

    def test_072_content_length_drift_rejected(self):
        headers = dict(EXPECTED_OBJECT_HEADERS[2018]); headers["Content-Length"] = "602713"
        with self.assertRaises(HeadValidationError):
            validate_final_head(2018, final_response(2018, headers=headers))

    def test_073_etag_drift_rejected(self):
        headers = dict(EXPECTED_OBJECT_HEADERS[2018]); headers["ETag"] = '"changed"'
        with self.assertRaises(HeadValidationError):
            validate_final_head(2018, final_response(2018, headers=headers))

    def test_074_last_modified_drift_rejected(self):
        headers = dict(EXPECTED_OBJECT_HEADERS[2018]); headers["Last-Modified"] = "Tue, 17 Nov 2020 15:58:38 GMT"
        with self.assertRaises(HeadValidationError):
            validate_final_head(2018, final_response(2018, headers=headers))

    def test_075_version_id_drift_rejected(self):
        headers = dict(EXPECTED_OBJECT_HEADERS[2018]); headers["X-Amz-Version-Id"] = "changed"
        with self.assertRaises(HeadValidationError):
            validate_final_head(2018, final_response(2018, headers=headers))

    def test_076_each_required_header_missing_is_rejected(self):
        for name in EXPECTED_OBJECT_HEADERS[2018]:
            headers = dict(EXPECTED_OBJECT_HEADERS[2018]); headers.pop(name)
            with self.subTest(name=name), self.assertRaises(ResponseValidationError):
                validate_final_head(2018, final_response(2018, headers=headers))

    def test_077_final_headers_case_insensitive(self):
        headers = {key.swapcase(): value for key, value in EXPECTED_OBJECT_HEADERS[2018].items()}
        self.assertEqual(validate_final_head(2018, final_response(2018, headers=headers)).status, 200)

    def test_078_final_duplicate_case_header_rejected(self):
        headers = dict(EXPECTED_OBJECT_HEADERS[2018]); headers["etag"] = headers["ETag"]
        with self.assertRaises(ResponseValidationError):
            validate_final_head(2018, final_response(2018, headers=headers))

    def test_079_final_head_never_touches_body_canary(self):
        response = ExplodingHeadResponse(200, dict(EXPECTED_OBJECT_HEADERS[2022]), FINAL_OBJECT_URLS[2022])
        self.assertEqual(validate_final_head(2022, response).status, 200)

    def test_080_ooxml_mime_is_exact(self):
        self.assertEqual(OOXML_SPREADSHEET_MIME, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class FetchAndFailureTests(unittest.TestCase):
    def test_081_fetch_landing_calls_transport_once(self):
        transport = FakeTransport(landing_response(2018))
        result = fetch_landing(2018, transport=transport)
        self.assertTrue(result.ok)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0][0].method, "GET")

    def test_082_fetch_numbered_head_calls_transport_once(self):
        transport = FakeTransport(numbered_response(2018))
        result = fetch_numbered_head(2018, transport=transport)
        self.assertTrue(result.ok)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0][0].method, "HEAD")

    def test_083_fetch_final_head_calls_transport_once(self):
        transport = FakeTransport(final_response(2018))
        self.assertTrue(fetch_final_head(2018, transport=transport).ok)
        self.assertEqual(len(transport.calls), 1)

    def test_084_invalid_source_fails_before_transport(self):
        transport = FakeTransport(landing_response())
        result = fetch_landing("winner=secret", transport=transport)
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.attempt_count, 0)
        self.assertEqual(result.failure.source_key, "REDACTED_INVALID_SOURCE")
        self.assertEqual(transport.calls, [])

    def test_085_timeout_is_structured_without_retry(self):
        transport = FakeTransport(error=TimeoutError())
        result = fetch_landing("index", transport=transport)
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "TRANSPORT_ERROR")
        self.assertEqual(len(transport.calls), 1)

    def test_086_network_error_is_structured_without_detail_leak(self):
        transport = FakeTransport(error=OSError("winner=secret"))
        result = fetch_landing("index", transport=transport)
        rendered = json.dumps(result.failure.as_dict(), ensure_ascii=False)
        self.assertNotIn("winner", rendered)
        self.assertEqual(len(transport.calls), 1)

    def test_087_bad_landing_body_not_echoed(self):
        body = b"winner=secret"
        response = landing_response(headers={"Content-Type": "winner/secret", "Content-Length": str(len(body))}, body=body)
        result = fetch_landing("index", transport=FakeTransport(response))
        rendered = json.dumps(result.failure.as_dict(), ensure_ascii=False)
        self.assertNotIn("winner", rendered)
        self.assertNotIn("secret", rendered)
        self.assertEqual(result.failure.content_type, "invalid/redacted")

    def test_088_bad_content_type_parameter_not_echoed(self):
        body = b"x"
        response = landing_response(headers={"Content-Type": "application/pdf; winner=secret", "Content-Length": "1"}, body=body)
        result = fetch_landing("index", transport=FakeTransport(response))
        self.assertNotIn("secret", json.dumps(result.failure.as_dict(), ensure_ascii=False))

    def test_089_head_failure_does_not_touch_canary_body(self):
        response = ExplodingHeadResponse(302, {"Location": FINAL_OBJECT_URLS[2020]}, NUMBERED_OBJECT_URLS[2018])
        result = fetch_numbered_head(2018, transport=FakeTransport(response))
        self.assertFalse(result.ok)

    def test_090_failure_retry_permission_is_false(self):
        result = fetch_numbered_head(2018, transport=FakeTransport(numbered_response(2018, status=301)))
        self.assertFalse(result.failure.as_dict()["retry_permitted_in_same_contract"])

    def test_090a_http_error_is_closed_after_head_metadata(self):
        class BodyCanary:
            def __init__(self):
                self.closed = False

            def read(self, *args):
                raise AssertionError("HEAD 不得读取 HTTPError body")

            def close(self):
                self.closed = True

        canary = BodyCanary()
        error = urllib.error.HTTPError(
            NUMBERED_OBJECT_URLS[2018], 302, "Found",
            {"Location": FINAL_OBJECT_URLS[2018]}, canary,
        )

        class Opener:
            def open(self, request, timeout):
                raise error

        request = validate_request("HEAD", NUMBERED_OBJECT_URLS[2018])
        with mock.patch.object(fec_core.urllib.request, "build_opener", return_value=Opener()):
            response = fec_core._default_transport(request, 1.0)
        self.assertEqual(response.status, 302)
        self.assertTrue(canary.closed)


class AuditTests(unittest.TestCase):
    def documents(self, year):
        return (
            validate_landing_document(year, landing_response(year)),
            validate_numbered_head(year, numbered_response(year)),
            validate_final_head(year, final_response(year)),
        )

    def results(self, year):
        landing, numbered, final = self.documents(year)
        return {
            "landing": FetchResult(document=landing),
            "numbered_head": FetchResult(document=numbered),
            "final_head": FetchResult(document=final),
        }

    def test_091_audit_year_seals_transport_identity(self):
        value = audit_year(2018, *self.documents(2018))
        self.assertEqual(value["activation"], "fec_transport_object_metadata_sealed")

    def test_092_audit_marks_content_checks_pending(self):
        value = audit_year(2020, *self.documents(2020))
        self.assertTrue(all(v == "PENDING_SEPARATE_INGEST_CONTRACT" for v in value["content_integrity"].values()))

    def test_093_etag_is_not_content_hash(self):
        value = audit_year(2022, *self.documents(2022))
        self.assertEqual(value["etag_role"], "opaque_http_validator_not_content_hash")
        self.assertFalse(value["official_content_sha256_verified"])

    def test_094_version_and_last_modified_roles_are_limited(self):
        value = audit_year(2018, *self.documents(2018))
        self.assertIn("not_content_integrity", value["version_id_role"])
        self.assertIn("not_publication_vintage", value["last_modified_role"])

    def test_095_cross_year_documents_rejected(self):
        landing, numbered, final = self.documents(2020)
        with self.assertRaises(FecMetadataError):
            audit_year(2018, landing, numbered, final)

    def test_096_audit_bytes_ignore_mapping_insertion_order(self):
        left = {year: self.results(year) for year in (2018, 2020, 2022)}
        right = {year: left[year] for year in (2022, 2020, 2018)}
        self.assertEqual(canonical_json_bytes(audit_sources(left)), canonical_json_bytes(audit_sources(right)))

    def test_097_one_bad_year_does_not_erase_other_audits(self):
        values = {year: self.results(year) for year in (2018, 2020, 2022)}
        values[2020]["final_head"] = fetch_final_head(2020, transport=FakeTransport(final_response(2020, status=500)))
        report = audit_sources(values)
        self.assertEqual(report["activation"], "blocked_fec_object_metadata")
        self.assertEqual(report["sources"]["2018"]["activation"], "fec_transport_object_metadata_sealed")
        self.assertEqual(report["sources"]["2020"]["activation"], "blocked_fec_object_metadata")
        self.assertEqual(report["sources"]["2022"]["activation"], "fec_transport_object_metadata_sealed")

    def test_098_all_sources_seal_only_when_complete(self):
        report = audit_sources({year: self.results(year) for year in (2018, 2020, 2022)})
        self.assertEqual(report["activation"], "fec_transport_object_metadata_sealed")
        self.assertFalse(report["data_ingested"])

    def test_099_missing_bundle_blocks(self):
        with self.assertRaises(FecMetadataError):
            audit_sources({2018: self.results(2018)})

    def test_100_audit_dict_has_driver_schema(self):
        landing, numbered, final = self.documents(2018)
        self.assertTrue({"year", "url", "status", "content_type", "byte_count", "sha256", "expected_href"} <= landing.audit_dict().keys())
        self.assertTrue({"year", "request_role", "url", "status", "final_url", "headers"} <= numbered.audit_dict().keys())
        self.assertTrue({"year", "request_role", "url", "status", "final_url", "headers"} <= final.audit_dict().keys())

    def test_100a_extra_source_year_fails_closed(self):
        values = {year: self.results(year) for year in (2018, 2020, 2022)}
        values[2024] = self.results(2022)
        with self.assertRaises(FecMetadataError):
            audit_sources(values)

    def test_100b_bool_source_key_fails_closed(self):
        values = {year: self.results(year) for year in (2018, 2020, 2022)}
        values[True] = self.results(2018)
        with self.assertRaises(FecMetadataError):
            audit_sources(values)

    def test_100c_extra_bundle_role_blocks_year(self):
        values = {year: self.results(year) for year in (2018, 2020, 2022)}
        values[2020]["guessed_pdf"] = values[2020]["landing"]
        report = audit_sources(values)
        self.assertEqual(report["activation"], "blocked_fec_object_metadata")
        self.assertEqual(report["sources"]["2020"]["failures"][0]["code"], "SOURCE_BUNDLE_ROLES_INVALID")

    def test_100d_forged_landing_hash_cannot_seal(self):
        landing, numbered, final = self.documents(2018)
        object.__setattr__(landing, "sha256", "0" * 64)
        with self.assertRaises(FecMetadataError):
            audit_year(2018, landing, numbered, final)

    def test_100e_forged_numbered_location_cannot_seal(self):
        landing, numbered, final = self.documents(2018)
        object.__setattr__(numbered, "safe_headers", {"Location": FINAL_OBJECT_URLS[2020]})
        with self.assertRaises(FecMetadataError):
            audit_year(2018, landing, numbered, final)

    def test_100f_forged_final_header_cannot_seal(self):
        landing, numbered, final = self.documents(2018)
        forged = dict(final.safe_headers); forged["ETag"] = '"forged"'
        object.__setattr__(final, "safe_headers", forged)
        with self.assertRaises(FecMetadataError):
            audit_year(2018, landing, numbered, final)

    def test_100g_seal_has_all_negative_activation_flags(self):
        report = audit_sources({year: self.results(year) for year in (2018, 2020, 2022)})
        for key in (
            "contains_2026_probability", "data_ingested",
            "official_content_sha256_verified", "predictions_emitted", "scores_emitted",
        ):
            self.assertIs(report[key], False)
        self.assertEqual(report["model_activation"], "unchanged")


class IsolationTests(unittest.TestCase):
    def test_101_core_has_no_model_imports(self):
        source = (SRC / "midterms" / "fec_source_metadata.py").read_text(encoding="utf-8")
        for forbidden in ("senate_balancing", "senate_m0", "benchmark", "scoring"):
            self.assertNotIn(f"import {forbidden}", source)

    def test_102_core_has_no_result_directory_scan(self):
        source = (SRC / "midterms" / "fec_source_metadata.py").read_text(encoding="utf-8")
        for forbidden in ("os.walk", "rglob(", "glob(", "raw/", "processed/", "sealed/"):
            self.assertNotIn(forbidden, source)

    def test_103_only_standard_library_imports(self):
        source = (SRC / "midterms" / "fec_source_metadata.py").read_text(encoding="utf-8")
        for forbidden in ("requests", "httpx", "pandas", "openpyxl"):
            self.assertNotIn(forbidden, source)

    def test_104_default_head_branch_contains_no_read_expression(self):
        source = (SRC / "midterms" / "fec_source_metadata.py").read_text(encoding="utf-8")
        start = source.index("def _default_transport")
        end = source.index("\n\nTransport =", start)
        block = source[start:end]
        self.assertNotIn('if request.method == "HEAD":\n                body =', block)


if __name__ == "__main__":
    unittest.main()
