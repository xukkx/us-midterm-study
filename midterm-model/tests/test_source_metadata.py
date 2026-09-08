"""LH-053 来源元数据纯核心的离线失败关闭测试。

测试只使用内存 JSON/HTTP fixture；不读取 raw、processed、sealed 或任何结果文件。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from midterms.source_metadata import (  # noqa: E402
    HttpResponse,
    MetadataError,
    MetadataRequest,
    PinValidationError,
    PRESIDENT_DOI,
    RequestPolicyError,
    SENATE_DOI,
    build_guestbook_url,
    build_original_data_url_template,
    build_version_metadata_url,
    build_versions_url,
    canonical_json_bytes,
    decide_activation,
    decide_coverage,
    fetch_json_metadata,
    pin_from_dataverse_version,
    sha256_hex,
    validate_dataverse_envelope,
    validate_official_pin,
    validate_pin,
    validate_request_url,
)


def valid_pin(source_id: str = "senate", through: int = 2022, *, guestbook: int | None = 17):
    doi = SENATE_DOI if source_id == "senate" else PRESIDENT_DOI
    target = "Senate" if source_id == "senate" else "President"
    file_id = 731 if source_id == "senate" else 941
    start = 1976 if source_id == "senate" else 1972
    return {
        "source_id": source_id,
        "pin_status": "officially_pinned",
        "doi": doi,
        "dataset_id": 101 if source_id == "senate" else 202,
        "version": "3.1",
        "release_time": "2025-01-02T03:04:05Z",
        "dataset_title": f"{target} election metadata {start}-{through}",
        "dataset_scope": f"Official {target} files from {start} through {through}",
        "license": {"name": "CC0 1.0", "uri": "https://creativecommons.org/publicdomain/zero/1.0/"},
        "guestbook_id": guestbook,
        "metadata_url": build_version_metadata_url(doi, "3.1"),
        "files": [{
            "file_id": file_id,
            "filename": f"{source_id}_{start}_{through}.csv",
            "filesize": 12345,
            "checksum_type": "SHA-256",
            "checksum_value": "a" * 64,
            "content_type": "text/csv",
            "restricted": False,
            "guestbook_id": guestbook,
            "datafile_url_template": build_original_data_url_template(file_id),
            "representation": "original",
            "representation_evidence": {
                "source": "official_metadata",
                "file_identity": "uploaded_original",
                "checksum_scope": "uploaded_original",
                "original_filename": f"{source_id}_{start}_{through}.csv",
            },
        }],
        "coverage_evidence": {
            "source": "official_metadata",
            "fields": [
                f"dataset_title={target} election metadata {start}-{through}",
                f"dataset_scope=Official {target} files from {start} through {through}",
                f"filename={source_id}_{start}_{through}.csv",
            ],
        },
    }


def dataverse_envelope(source_id: str = "senate", through: int = 2022):
    pin = valid_pin(source_id, through)
    file_row = pin["files"][0]
    return {
        "status": "OK",
        "data": {
            "datasetVersion": {
                "datasetId": pin["dataset_id"],
                "versionNumber": 3,
                "versionMinorNumber": 1,
                "versionState": "RELEASED",
                "releaseTime": pin["release_time"],
                "datasetScope": pin["dataset_scope"],
                "license": pin["license"],
                "guestbookId": pin["guestbook_id"],
                "metadataBlocks": {"citation": {"fields": [
                    {"typeName": "title", "value": pin["dataset_title"]},
                ]}},
                "files": [{
                    "restricted": False,
                    "originalFile": {
                        "filename": file_row["filename"],
                        "filesize": file_row["filesize"],
                        "contentType": file_row["content_type"],
                        "checksum": {"type": "SHA-256", "value": "a" * 64},
                    },
                    "dataFile": {
                        "id": file_row["file_id"],
                        "filename": file_row["filename"],
                        "filesize": file_row["filesize"],
                        "contentType": file_row["content_type"],
                        "checksum": {"type": "SHA-256", "value": "a" * 64},
                        "guestbookId": pin["guestbook_id"],
                    },
                }],
            },
        },
    }


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


def json_response(payload=None, **changes):
    if payload is None:
        payload = {"status": "OK", "data": {"id": 1}}
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    values = {
        "status": 200,
        "headers": {"Content-Type": "application/json", "Content-Length": str(len(body))},
        "body": body,
        "final_url": build_versions_url(SENATE_DOI),
    }
    values.update(changes)
    return HttpResponse(**values)


class CanonicalBytesTests(unittest.TestCase):
    def test_01_key_order_is_canonical(self):
        self.assertEqual(canonical_json_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}')

    def test_02_unicode_is_not_ascii_escaped(self):
        self.assertIn("元数据".encode(), canonical_json_bytes({"说明": "元数据"}))

    def test_03_nan_is_rejected(self):
        with self.assertRaises(MetadataError):
            canonical_json_bytes({"x": math.nan})

    def test_04_non_string_key_is_rejected(self):
        with self.assertRaises(MetadataError):
            canonical_json_bytes({1: "x"})

    def test_05_unsupported_object_is_rejected(self):
        with self.assertRaises(MetadataError):
            canonical_json_bytes({"x": object()})

    def test_06_sha256_matches_hand_calculation(self):
        self.assertEqual(sha256_hex(b"abc"), hashlib.sha256(b"abc").hexdigest())

    def test_07_sha256_rejects_text(self):
        with self.assertRaises(MetadataError):
            sha256_hex("abc")


class UrlPolicyTests(unittest.TestCase):
    def test_08_versions_builder_round_trip(self):
        url = build_versions_url(SENATE_DOI)
        self.assertEqual(validate_request_url(url), url)

    def test_09_version_builder_is_numeric(self):
        url = build_version_metadata_url(PRESIDENT_DOI, "12.3")
        self.assertEqual(validate_request_url(url), url)

    def test_10_latest_version_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            build_version_metadata_url(SENATE_DOI, ":latest")

    def test_11_draft_version_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            build_version_metadata_url(SENATE_DOI, ":draft")

    def test_12_unknown_doi_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            build_versions_url("10.7910/DVN/AAAAAA")

    def test_13_http_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request_url(build_versions_url(SENATE_DOI).replace("https:", "http:"))

    def test_14_wrong_host_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request_url(build_versions_url(SENATE_DOI).replace("dataverse.harvard.edu", "evil.test"))

    def test_15_userinfo_is_rejected(self):
        url = build_versions_url(SENATE_DOI).replace("https://", "https://user@")
        with self.assertRaises(RequestPolicyError):
            validate_request_url(url)

    def test_16_explicit_port_is_rejected(self):
        url = build_versions_url(SENATE_DOI).replace(".edu/", ".edu:443/")
        with self.assertRaises(RequestPolicyError):
            validate_request_url(url)

    def test_17_fragment_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request_url(build_versions_url(SENATE_DOI) + "#x")

    def test_18_duplicate_query_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request_url(build_versions_url(SENATE_DOI) + "&persistentId=doi:x")

    def test_19_extra_query_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request_url(build_versions_url(SENATE_DOI) + "&key=x")

    def test_20_access_datafile_is_rejected_before_open(self):
        with self.assertRaises(RequestPolicyError):
            validate_request_url(build_original_data_url_template(3))

    def test_21_guestbook_builder_round_trip(self):
        url = build_guestbook_url(17)
        self.assertEqual(validate_request_url(url, "guestbook"), url)

    def test_22_guestbook_query_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request_url(build_guestbook_url(17) + "?x=1", "guestbook")

    def test_23_bad_guestbook_id_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            build_guestbook_url(True)

    def test_24_official_explanation_page_is_allowed(self):
        url = "https://guides.dataverse.org/en/latest/api/native-api.html"
        self.assertEqual(validate_request_url(url, "explanation"), url)

    def test_25_explanation_pdf_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request_url("https://www.fec.gov/files/results.pdf", "explanation")

    def test_26_explanation_download_query_is_rejected(self):
        with self.assertRaises(RequestPolicyError):
            validate_request_url("https://www.archives.gov/help?download=1", "explanation")

    def test_27_original_template_is_exact(self):
        self.assertEqual(
            build_original_data_url_template(9),
            "https://dataverse.harvard.edu/api/access/datafile/9?format=original",
        )

    def test_27a_uppercase_host_is_noncanonical(self):
        url = build_versions_url(SENATE_DOI).replace(
            "dataverse.harvard.edu", "DATAVERSE.HARVARD.EDU"
        )
        with self.assertRaises(RequestPolicyError):
            validate_request_url(url)

    def test_27b_percent_encoded_path_cannot_bypass_route_gate(self):
        url = build_versions_url(SENATE_DOI).replace("/api/", "/%61pi/")
        with self.assertRaises(RequestPolicyError):
            validate_request_url(url)

    def test_27c_noncanonical_query_encoding_is_rejected(self):
        url = build_versions_url(SENATE_DOI).replace("%3A", "%3a")
        with self.assertRaises(RequestPolicyError):
            validate_request_url(url)

    def test_27d_malformed_query_is_policy_error(self):
        with self.assertRaises(RequestPolicyError):
            validate_request_url(build_versions_url(SENATE_DOI) + "&")

    def test_27e_invalid_port_is_policy_error(self):
        url = build_versions_url(SENATE_DOI).replace(".edu/", ".edu:bad/")
        with self.assertRaises(RequestPolicyError):
            validate_request_url(url)

    def test_27f_unregistered_metadata_suffix_is_rejected(self):
        url = build_version_metadata_url(SENATE_DOI, "1.0").replace("1.0?", "1.0/metadata?")
        with self.assertRaises(RequestPolicyError):
            validate_request_url(url)

    def test_27g_uppercase_guestbook_host_is_noncanonical(self):
        url = build_guestbook_url(17).replace(
            "dataverse.harvard.edu", "DATAVERSE.HARVARD.EDU"
        )
        with self.assertRaises(RequestPolicyError):
            validate_request_url(url, "guestbook")


class FetchGateTests(unittest.TestCase):
    def setUp(self):
        self.url = build_versions_url(SENATE_DOI)

    def test_28_valid_json_preserves_raw_bytes_and_hash(self):
        response = json_response()
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(response))
        self.assertTrue(result.ok)
        self.assertEqual(result.document.raw_bytes, response.body)
        self.assertEqual(result.document.sha256, sha256_hex(response.body))

    def test_29_request_has_json_accept_and_limit(self):
        transport = FakeTransport(json_response())
        fetch_json_metadata(self.url, "senate", transport=transport, max_response_bytes=123)
        request, _ = transport.calls[0]
        self.assertIsInstance(request, MetadataRequest)
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(request.max_response_bytes, 123)

    def test_30_forbidden_url_never_calls_transport(self):
        transport = FakeTransport(json_response())
        result = fetch_json_metadata(build_original_data_url_template(1), "senate", transport=transport)
        self.assertEqual(transport.calls, [])
        self.assertEqual(result.failure.stage, "before_open")
        self.assertEqual(result.failure.attempt_count, 0)

    def test_30a_source_id_must_match_metadata_doi_before_open(self):
        transport = FakeTransport(json_response())
        result = fetch_json_metadata(
            build_versions_url(SENATE_DOI), "president", transport=transport
        )
        self.assertEqual(result.failure.code, "SOURCE_DOI_MISMATCH")
        self.assertEqual(result.failure.stage, "before_open")
        self.assertEqual(result.failure.attempt_count, 0)
        self.assertEqual(transport.calls, [])

    def test_30b_unknown_metadata_source_id_is_rejected_before_open(self):
        transport = FakeTransport(json_response())
        result = fetch_json_metadata(
            build_versions_url(SENATE_DOI), "unknown", transport=transport
        )
        self.assertEqual(result.failure.code, "SOURCE_ID_REJECTED")
        self.assertEqual(result.failure.attempt_count, 0)
        self.assertEqual(transport.calls, [])

    def test_30c_rejected_url_query_is_redacted_from_failure(self):
        transport = FakeTransport(json_response())
        rejected = build_versions_url(SENATE_DOI) + "&winner=secret"
        result = fetch_json_metadata(rejected, "senate", transport=transport)
        rendered = canonical_json_bytes(result.failure.as_dict()).decode("utf-8")
        self.assertEqual(result.failure.url, "REDACTED_REJECTED_URL")
        self.assertNotIn("winner", rendered)
        self.assertNotIn("secret", rendered)
        self.assertEqual(result.failure.attempt_count, 0)
        self.assertEqual(transport.calls, [])

    def test_31_redirect_is_rejected(self):
        response = json_response(final_url=build_version_metadata_url(SENATE_DOI, "1.0"))
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(response))
        self.assertEqual(result.failure.code, "REDIRECT_REJECTED")

    def test_32_http_400_is_rejected(self):
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(json_response(status=400)))
        self.assertEqual(result.failure.code, "HTTP_STATUS_REJECTED")

    def test_33_http_401_is_rejected(self):
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(json_response(status=401)))
        self.assertEqual(result.failure.status, 401)

    def test_34_http_403_is_rejected(self):
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(json_response(status=403)))
        self.assertEqual(result.failure.attempt_count, 1)

    def test_35_html_waf_is_rejected_without_body_in_failure(self):
        response = json_response(headers={"Content-Type": "text/html"}, body=b"<html>challenge</html>")
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(response))
        self.assertEqual(result.failure.code, "NON_JSON_CONTENT_TYPE")
        self.assertNotIn("body", result.failure.as_dict())
        self.assertNotIn("challenge", json.dumps(result.failure.as_dict()))

    def test_36_json_202_challenge_is_rejected_by_status(self):
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(json_response(status=202)))
        self.assertEqual(result.failure.code, "HTTP_STATUS_REJECTED")

    def test_37_malformed_json_is_rejected(self):
        response = json_response(body=b"{", headers={"Content-Type": "application/json"})
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(response))
        self.assertEqual(result.failure.code, "INVALID_JSON_METADATA")

    def test_38_non_ok_envelope_is_rejected(self):
        response = json_response({"status": "ERROR", "data": {}})
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(response))
        self.assertEqual(result.failure.code, "INVALID_JSON_METADATA")

    def test_39_missing_envelope_data_is_rejected(self):
        response = json_response({"status": "OK"})
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(response))
        self.assertFalse(result.ok)

    def test_40_declared_oversize_is_rejected(self):
        response = json_response(headers={"Content-Type": "application/json", "Content-Length": "1000"})
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(response), max_response_bytes=10)
        self.assertEqual(result.failure.code, "RESPONSE_TOO_LARGE")

    def test_41_actual_oversize_is_rejected(self):
        response = json_response(headers={"Content-Type": "application/json"})
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(response), max_response_bytes=2)
        self.assertEqual(result.failure.code, "RESPONSE_TOO_LARGE")

    def test_42_invalid_content_length_is_rejected(self):
        response = json_response(headers={"Content-Type": "application/json", "Content-Length": "many"})
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(response))
        self.assertEqual(result.failure.code, "INVALID_CONTENT_LENGTH")

    def test_43_timeout_is_structured_and_not_retried(self):
        transport = FakeTransport(error=TimeoutError())
        result = fetch_json_metadata(self.url, "senate", transport=transport)
        self.assertEqual(result.failure.code, "METADATA_TIMEOUT")
        self.assertEqual(len(transport.calls), 1)

    def test_44_network_error_is_structured(self):
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(error=OSError("offline")))
        self.assertEqual(result.failure.code, "METADATA_NETWORK_ERROR")

    def test_45_transport_wrong_type_is_rejected(self):
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport({"status": 200}))
        self.assertEqual(result.failure.code, "TRANSPORT_PROTOCOL_ERROR")

    def test_46_timeout_parameter_must_be_positive(self):
        with self.assertRaises(MetadataError):
            fetch_json_metadata(self.url, "senate", transport=FakeTransport(json_response()), timeout_seconds=0)

    def test_47_max_bytes_must_be_positive_integer(self):
        with self.assertRaises(MetadataError):
            fetch_json_metadata(self.url, "senate", transport=FakeTransport(json_response()), max_response_bytes=True)

    def test_47a_malformed_query_is_structured_before_open(self):
        transport = FakeTransport(json_response())
        result = fetch_json_metadata(self.url + "&", "senate", transport=transport)
        self.assertEqual(result.failure.code, "URL_POLICY_REJECTED")
        self.assertEqual(result.failure.stage, "before_open")
        self.assertEqual(result.failure.attempt_count, 0)
        self.assertEqual(transport.calls, [])

    def test_47b_invalid_port_is_structured_before_open(self):
        transport = FakeTransport(json_response())
        url = self.url.replace(".edu/", ".edu:bad/")
        result = fetch_json_metadata(url, "senate", transport=transport)
        self.assertEqual(result.failure.code, "URL_POLICY_REJECTED")
        self.assertEqual(transport.calls, [])

    def test_47c_malformed_http_response_headers_are_structured(self):
        malformed = HttpResponse(200, [], b"{}", self.url)
        result = fetch_json_metadata(self.url, "senate", transport=FakeTransport(malformed))
        self.assertEqual(result.failure.code, "TRANSPORT_PROTOCOL_ERROR")
        self.assertEqual(result.failure.stage, "response")


class PinSchemaTests(unittest.TestCase):
    def mutate(self, action):
        value = copy.deepcopy(valid_pin())
        action(value)
        return value

    def test_48_complete_official_pin_is_accepted(self):
        self.assertEqual(validate_official_pin(valid_pin())["pin_status"], "officially_pinned")

    def test_49_metadata_candidate_is_distinct(self):
        pin = valid_pin()
        pin["pin_status"] = "metadata_candidate"
        self.assertEqual(validate_pin(pin)["pin_status"], "metadata_candidate")
        with self.assertRaises(PinValidationError):
            validate_official_pin(pin)

    def test_50_missing_field_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p.pop("license")))

    def test_51_extra_result_field_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p.update({"winner": "X"})))

    def test_52_source_doi_mismatch_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p.update({"doi": PRESIDENT_DOI})))

    def test_53_non_numeric_version_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p.update({"version": ":latest"})))

    def test_54_naive_release_time_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p.update({"release_time": "2025-01-01T00:00:00"})))

    def test_55_empty_title_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p.update({"dataset_title": ""})))

    def test_56_empty_scope_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p.update({"dataset_scope": ""})))

    def test_57_license_name_is_required(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["license"].update({"name": ""})))

    def test_58_license_uri_must_be_https(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["license"].update({"uri": "http://example.test"})))

    def test_59_restricted_file_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["files"][0].update({"restricted": True})))

    def test_60_unknown_checksum_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["files"][0].update({"checksum_type": "CRC32"})))

    def test_61_checksum_length_is_checked(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["files"][0].update({"checksum_value": "a" * 63})))

    def test_62_archival_representation_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["files"][0].update({"representation": "archival"})))

    def test_63_original_format_is_mandatory(self):
        def action(pin):
            pin["files"][0]["datafile_url_template"] = pin["files"][0]["datafile_url_template"].split("?")[0]
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(action))

    def test_64_template_file_id_must_match(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["files"][0].update({"datafile_url_template": build_original_data_url_template(999)})))

    def test_65_multiple_candidate_files_are_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["files"].append(copy.deepcopy(p["files"][0]))))

    def test_66_zero_candidate_files_are_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p.update({"files": []})))

    def test_67_guestbook_absent_is_explicitly_valid(self):
        normalized = validate_pin(valid_pin(guestbook=None))
        self.assertIsNone(normalized["guestbook_id"])

    def test_68_guestbook_mismatch_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["files"][0].update({"guestbook_id": 18})))

    def test_69_non_official_coverage_source_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["coverage_evidence"].update({"source": "search_snippet"})))

    def test_70_duplicate_coverage_fields_are_rejected(self):
        def action(pin):
            pin["coverage_evidence"]["fields"].append(pin["coverage_evidence"]["fields"][0])
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(action))

    def test_71_wrong_metadata_version_url_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p.update({"metadata_url": build_versions_url(SENATE_DOI)})))

    def test_72_html_candidate_file_is_rejected(self):
        with self.assertRaises(PinValidationError):
            validate_pin(self.mutate(lambda p: p["files"][0].update({"content_type": "text/html"})))


class ExtractionAndCoverageTests(unittest.TestCase):
    def test_73_envelope_requires_ok_status(self):
        with self.assertRaises(Exception):
            validate_dataverse_envelope({"status": "ERROR", "data": {}})

    def test_74_official_version_extracts_pin(self):
        envelope = dataverse_envelope()
        pin = pin_from_dataverse_version(
            envelope, source_id="senate", doi=SENATE_DOI, version="3.1",
            candidate_filenames=("senate_1976_2022.csv",),
        )
        self.assertEqual(pin["files"][0]["representation"], "original")

    def test_75_missing_numeric_version_is_rejected(self):
        with self.assertRaises(PinValidationError):
            pin_from_dataverse_version(
                dataverse_envelope(), source_id="senate", doi=SENATE_DOI, version="4.0",
                candidate_filenames=("senate_1976_2022.csv",),
            )

    def test_76_draft_version_is_rejected(self):
        envelope = dataverse_envelope()
        envelope["data"]["datasetVersion"]["versionState"] = "DRAFT"
        with self.assertRaises(PinValidationError):
            pin_from_dataverse_version(
                envelope, source_id="senate", doi=SENATE_DOI, version="3.1",
                candidate_filenames=("senate_1976_2022.csv",),
            )

    def test_77_multiple_matching_files_are_rejected(self):
        envelope = dataverse_envelope()
        envelope["data"]["datasetVersion"]["files"].append(
            copy.deepcopy(envelope["data"]["datasetVersion"]["files"][0])
        )
        with self.assertRaises(PinValidationError):
            pin_from_dataverse_version(
                envelope, source_id="senate", doi=SENATE_DOI, version="3.1",
                candidate_filenames=("senate_1976_2022.csv",),
            )

    def test_78_unlisted_candidate_file_is_rejected(self):
        with self.assertRaises(PinValidationError):
            pin_from_dataverse_version(
                dataverse_envelope(), source_id="senate", doi=SENATE_DOI, version="3.1",
                candidate_filenames=("guess.csv",),
            )

    def test_79_senate_2022_is_confirmed(self):
        decision = decide_coverage("senate", valid_pin("senate", 2022))
        self.assertEqual((decision.status, decision.ingest_cycles), ("confirmed", (2018, 2022)))

    def test_80_senate_2020_is_insufficient(self):
        decision = decide_coverage("senate", valid_pin("senate", 2020))
        self.assertEqual(decision.code, "SOURCE_COVERAGE_INSUFFICIENT")

    def test_81_senate_unknown_is_unverified(self):
        pin = valid_pin("senate", 2022)
        pin["coverage_evidence"]["fields"] = ["dataset_title=Senate data", "filename=senate.csv"]
        decision = decide_coverage("senate", pin)
        self.assertEqual(decision.code, "SOURCE_COVERAGE_UNVERIFIED")

    def test_82_senate_2024_is_isolated(self):
        decision = decide_coverage("senate", valid_pin("senate", 2024))
        self.assertEqual(decision.isolated_cycles, (2024,))
        self.assertEqual(decision.ingest_cycles, (2018, 2022))

    def test_83_president_2020_is_confirmed(self):
        self.assertEqual(decide_coverage("president", valid_pin("president", 2020)).status, "confirmed")

    def test_84_president_missing_2020_is_unverified(self):
        self.assertEqual(decide_coverage("president", valid_pin("president", 2016)).status, "unverified")

    def test_84a_planned_2022_does_not_confirm_coverage(self):
        pin = valid_pin("senate", 2022)
        pin["coverage_evidence"]["fields"][1] += " update planned"
        self.assertEqual(decide_coverage("senate", pin).code, "SOURCE_COVERAGE_UNVERIFIED")

    def test_84b_excluded_2022_does_not_confirm_coverage(self):
        pin = valid_pin("senate", 2022)
        pin["coverage_evidence"]["fields"][1] += " but 2022 excluded"
        self.assertEqual(decide_coverage("senate", pin).code, "SOURCE_COVERAGE_UNVERIFIED")

    def test_85_both_complete_activate_separate_contract_only(self):
        decision = decide_activation({
            "senate": valid_pin("senate", 2022),
            "president": valid_pin("president", 2020),
        })
        self.assertEqual(decision.activation, "metadata_ready_for_separate_ingest_contract")
        self.assertEqual(decision.next_permitted_action, "open_separate_ingest_contract")

    def test_86_missing_source_blocks_activation(self):
        decision = decide_activation({"senate": valid_pin("senate", 2022)})
        self.assertEqual(decision.activation, "blocked_source_metadata")
        self.assertEqual(decision.reason_code, "OFFICIAL_PIN_INCOMPLETE")

    def test_87_candidate_status_blocks_activation(self):
        president = valid_pin("president", 2020)
        president["pin_status"] = "metadata_candidate"
        decision = decide_activation({"senate": valid_pin(), "president": president})
        self.assertEqual(decision.reason_code, "OFFICIAL_PIN_INVALID")

    def test_88_insufficient_senate_blocks_activation(self):
        decision = decide_activation({
            "senate": valid_pin("senate", 2020),
            "president": valid_pin("president", 2020),
        })
        self.assertEqual(decision.reason_code, "SOURCE_COVERAGE_INSUFFICIENT")

    def test_89_activation_bytes_are_repeatable(self):
        pins_a = {"senate": valid_pin("senate", 2022), "president": valid_pin("president", 2020)}
        pins_b = {"president": copy.deepcopy(pins_a["president"]), "senate": copy.deepcopy(pins_a["senate"])}
        self.assertEqual(
            canonical_json_bytes(decide_activation(pins_a).as_dict()),
            canonical_json_bytes(decide_activation(pins_b).as_dict()),
        )


class IsolationTests(unittest.TestCase):
    def test_90_module_source_has_no_model_imports(self):
        source = (SRC / "midterms" / "source_metadata.py").read_text(encoding="utf-8")
        for forbidden in ("senate_balancing", "senate_m0", "benchmark", "scoring", "ingest"):
            self.assertNotIn(f"import {forbidden}", source)

    def test_91_module_has_no_result_directory_scan(self):
        source = (SRC / "midterms" / "source_metadata.py").read_text(encoding="utf-8")
        for forbidden in ("os.walk", "rglob(", "glob(", "raw/", "processed/", "sealed/"):
            self.assertNotIn(forbidden, source)

    def test_92_failure_record_is_result_value_free(self):
        response = json_response(headers={"Content-Type": "text/html"}, body=b"winner=secret")
        result = fetch_json_metadata(build_versions_url(SENATE_DOI), "senate", transport=FakeTransport(response))
        rendered = canonical_json_bytes(result.failure.as_dict()).decode()
        self.assertNotIn("secret", rendered)
        self.assertNotIn("winner", rendered)


class FailureSanitizationRegressionTests(unittest.TestCase):
    def test_rejected_query_value_is_not_echoed(self):
        called = []
        url = build_versions_url(SENATE_DOI) + "&winner=secret"
        result = fetch_json_metadata(
            url, "senate", transport=lambda request, timeout: called.append(request)
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.url, "REDACTED_REJECTED_URL")
        self.assertNotIn("secret", json.dumps(result.failure.as_dict(), ensure_ascii=False))
        self.assertEqual(called, [])

    def test_failure_content_type_parameters_are_not_echoed(self):
        body = b"<html>blocked</html>"
        response = HttpResponse(
            200,
            {"Content-Type": "text/html; winner=secret", "Content-Length": str(len(body))},
            body,
            build_versions_url(SENATE_DOI),
        )
        result = fetch_json_metadata(
            build_versions_url(SENATE_DOI),
            "senate",
            transport=lambda request, timeout: response,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.content_type, "text/html")
        self.assertNotIn("secret", json.dumps(result.failure.as_dict(), ensure_ascii=False))

    def test_unknown_mime_main_type_is_redacted(self):
        body = b"blocked"
        response = HttpResponse(
            200,
            {"Content-Type": "winner/secret", "Content-Length": str(len(body))},
            body,
            build_versions_url(SENATE_DOI),
        )
        result = fetch_json_metadata(
            build_versions_url(SENATE_DOI), "senate",
            transport=lambda request, timeout: response,
        )
        self.assertEqual(result.failure.content_type, "invalid/redacted")
        self.assertNotIn("secret", json.dumps(result.failure.as_dict(), ensure_ascii=False))

    def test_invalid_source_id_is_redacted(self):
        result = fetch_json_metadata(build_versions_url(SENATE_DOI), "winner=secret")
        self.assertEqual(result.failure.source_id, "REDACTED_INVALID_SOURCE")
        self.assertNotIn("secret", json.dumps(result.failure.as_dict(), ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
