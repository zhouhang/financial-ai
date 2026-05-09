"""支付宝平台 connector。"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import requests

from platforms.base import BasePlatformConnector, PlatformShopProfile, PlatformTokenBundle

logger = logging.getLogger(__name__)

ALIPAY_GATEWAY_URL = "https://openapi.alipay.com/gateway.do"
ALIPAY_AUTH_URL = "https://openauth.alipay.com/oauth2/appToAppAuth.htm"
ALIPAY_TZ = timezone(timedelta(hours=8))
ALIPAY_BILL_METHOD = "alipay.data.dataservice.bill.downloadurl.query"
ALIPAY_TOKEN_METHOD = "alipay.open.auth.token.app"
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")
ROW_KEY_FIELDS = (
    "业务基础订单号",
    "业务订单号",
    "商户订单号",
    "商户订单号/商家订单号",
    "支付宝交易号",
    "支付宝流水号",
    "账务流水号",
)
ALIPAY_BILL_SUMMARY_MARKERS = (
    "账务明细列表结束",
    "账务汇总列表",
    "账务汇总列表结束",
    "支出合计",
    "收入合计",
    "合计",
    "导出时间",
)
CSV_HEADER_HINTS = {
    "商户订单号",
    "支付宝交易号",
    "业务订单号",
    "账务流水号",
    "金额",
    "收入",
    "支出",
    "发生金额",
    "入账时间",
}
CSV_DETAIL_HEADER_HINTS = {
    "商户订单号",
    "支付宝交易号",
    "支付宝流水号",
    "账务流水号",
    "业务流水号",
    "业务基础订单号",
    "业务订单号",
}
TOKEN_SECRET_KEYS = {"app_auth_token", "app_refresh_token", "access_token", "refresh_token"}
ALIPAY_HTTP_BILL_DOWNLOAD_HOSTS = {"dwbillcenter.alipay.com"}


def _alipay_response_key(method: str) -> str:
    return f"{str(method or '').replace('.', '_')}_response"


def _extract_json_value_text(raw_text: str, key: str) -> str:
    if not raw_text or not key:
        return ""
    quoted_key = json.dumps(key, ensure_ascii=False)
    key_index = raw_text.find(quoted_key)
    if key_index < 0:
        return ""
    colon_index = raw_text.find(":", key_index + len(quoted_key))
    if colon_index < 0:
        return ""
    value_start = colon_index + 1
    while value_start < len(raw_text) and raw_text[value_start].isspace():
        value_start += 1
    try:
        _, value_end = json.JSONDecoder().raw_decode(raw_text[value_start:])
    except ValueError:
        return ""
    return raw_text[value_start : value_start + value_end]


def _extract_gateway_sign_content(raw_text: str, *, response_key: str) -> str:
    return _extract_json_value_text(raw_text, response_key)


def _is_trusted_alipay_bill_download_url(url: str) -> bool:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = str(parsed.hostname or "").lower()
    if scheme == "https":
        return True
    return scheme == "http" and hostname in ALIPAY_HTTP_BILL_DOWNLOAD_HOSTS


def _load_pem_certificates(cert_text: str):
    from cryptography import x509

    pem_blocks = re.findall(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        str(cert_text or ""),
        flags=re.DOTALL,
    )
    if not pem_blocks:
        raise ValueError("certificate PEM block not found")
    return [x509.load_pem_x509_certificate(block.encode("utf-8")) for block in pem_blocks]


def _alipay_cert_sn(cert_text: str, *, root: bool = False) -> str:
    certs = _load_pem_certificates(cert_text)
    serials: list[str] = []
    for cert in certs:
        if root and not cert.signature_algorithm_oid.dotted_string.startswith("1.2.840.113549.1.1"):
            continue
        issuer = cert.issuer.rfc4514_string()
        source = f"{issuer}{cert.serial_number}"
        serials.append(hashlib.md5(source.encode("utf-8")).hexdigest())
    return "_".join(serials)


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    return parsed


def _safe_token_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        normalized_key = str(key or "").strip()
        if normalized_key.lower() in TOKEN_SECRET_KEYS:
            cleaned[normalized_key] = "***REDACTED***"
        else:
            cleaned[normalized_key] = value
    return cleaned


def _download_error_message(exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code:
        return f"支付宝账单文件下载失败: HTTP {status_code}"
    return "支付宝账单文件下载失败"


def _alipay_business_error_message(data: dict[str, Any], *, response_key: str = "") -> str:
    response = data.get(response_key) if response_key else None
    if not isinstance(response, dict):
        response = data.get("error_response") if isinstance(data.get("error_response"), dict) else {}
    code = str(response.get("code") or "").strip()
    sub_code = str(response.get("sub_code") or "").strip()
    sub_msg = str(response.get("sub_msg") or "").strip()
    msg = str(response.get("msg") or "").strip()
    if not response or code in {"", "10000"}:
        return ""
    detail = sub_msg or msg or "支付宝网关返回业务错误"
    if sub_code:
        return f"{detail}（{sub_code}）"
    if code:
        return f"{detail}（{code}）"
    return detail


def _gateway_error_message(exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code:
        return f"支付宝网关请求失败: HTTP {status_code}"
    return "支付宝网关请求失败"


def _decode_csv(content: bytes) -> str:
    last_error: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"支付宝账单 CSV 解码失败: {last_error}") from last_error


def _preferred_row_identifier(row: dict[str, Any]) -> str:
    for key in ROW_KEY_FIELDS:
        text = _first_text(row, key)
        if text:
            return text
    return ""


def build_alipay_row_key(
    *,
    bill_type: str,
    bill_date: str,
    source_file_name: str,
    source_row_number: int,
    row: dict[str, Any],
) -> str:
    normalized_row = {
        str(key or "").strip(): str(value or "").strip()
        for key, value in row.items()
        if str(key or "").strip()
    }
    raw = json.dumps(normalized_row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    preferred_id = _preferred_row_identifier(normalized_row)
    source = f"{bill_type}|{bill_date}|{source_file_name}|{source_row_number}|{preferred_id}|{raw}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _is_summary_or_footer_bill_row(row: dict[str, Any]) -> bool:
    values = [str(value or "").strip() for value in row.values()]
    non_empty_values = [value for value in values if value]
    if not non_empty_values:
        return True
    if any(value.startswith("#") for value in non_empty_values):
        return True
    if len(non_empty_values) == 1 and non_empty_values[0] in {"类型", "合计"}:
        return True
    joined = " ".join(non_empty_values)
    return any(marker in joined for marker in ALIPAY_BILL_SUMMARY_MARKERS)


def _csv_header_and_rows(text: str) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    physical_rows = list(csv.reader(io.StringIO(text)))
    header_index = 0
    for index, row in enumerate(physical_rows):
        normalized = {str(cell or "").strip() for cell in row}
        if normalized & CSV_HEADER_HINTS:
            header_index = index
            break
    while header_index < len(physical_rows) and not any(
        str(cell or "").strip() for cell in physical_rows[header_index]
    ):
        header_index += 1
    if header_index >= len(physical_rows):
        return [], []
    headers = [str(cell or "").strip() for cell in physical_rows[header_index]]
    if not (set(headers) & CSV_DETAIL_HEADER_HINTS):
        return [], []
    parsed_rows: list[tuple[int, dict[str, str]]] = []
    for physical_index, row in enumerate(physical_rows[header_index + 1 :], start=header_index + 2):
        if not any(str(cell or "").strip() for cell in row):
            continue
        values = [str(cell or "").strip() for cell in row]
        row_dict = {
            header: values[column_index] if column_index < len(values) else ""
            for column_index, header in enumerate(headers)
            if header
        }
        if not any(row_dict.values()):
            continue
        if _is_summary_or_footer_bill_row(row_dict):
            continue
        parsed_rows.append((physical_index, row_dict))
    return [header for header in headers if header], parsed_rows


def _csv_rows_with_header(text: str) -> list[tuple[int, dict[str, str]]]:
    _, parsed_rows = _csv_header_and_rows(text)
    return parsed_rows


class AlipayConnector(BasePlatformConnector):
    platform_code = "alipay"

    def _auth_url(self) -> str:
        return str(self.app_config.auth_base_url or ALIPAY_AUTH_URL)

    def _gateway_url(self) -> str:
        return str(self.app_config.token_url or self.app_config.refresh_url or ALIPAY_GATEWAY_URL)

    def build_auth_url(self, *, state: str) -> str:
        if self.is_mock:
            return ""
        query = urlencode(
            {
                "app_id": self.app_config.app_key,
                "redirect_uri": self.app_config.redirect_uri,
                "state": state,
            }
        )
        return f"{self._auth_url()}?{query}"

    def exchange_code_for_token(
        self,
        *,
        code: str,
        auth_session: dict[str, Any] | None = None,
        callback_payload: dict[str, Any] | None = None,
    ) -> PlatformTokenBundle:
        if self.is_mock:
            suffix = str(code or "mock")[-8:]
            return PlatformTokenBundle(
                access_token=f"mock_alipay_access_{suffix}",
                refresh_token=f"mock_alipay_refresh_{suffix}",
                expires_in=31536000,
                refresh_expires_in=32140800,
                raw_payload={"mode": "mock", "code": code},
            )
        callback = callback_payload or {}
        resolved_code = str(
            callback.get("app_auth_code") or callback.get("code") or code or ""
        ).strip()
        data = self._post_alipay_request(
            method=ALIPAY_TOKEN_METHOD,
            app_auth_token="",
            biz_content={"grant_type": "authorization_code", "code": resolved_code},
        )
        return self._token_bundle_from_response(data)

    def refresh_token(self, *, refresh_token: str) -> PlatformTokenBundle:
        if self.is_mock:
            suffix = str(refresh_token or "mock")[-8:]
            return PlatformTokenBundle(
                access_token=f"mock_alipay_access_{suffix}",
                refresh_token=f"mock_alipay_refresh_{suffix}",
                expires_in=31536000,
                refresh_expires_in=32140800,
                raw_payload={"mode": "mock", "refresh_token": refresh_token},
            )
        current_refresh_token = str(refresh_token or "").strip()
        if not current_refresh_token:
            raise RuntimeError("支付宝 refresh token 为空，请重新授权")
        data = self._post_alipay_request(
            method=ALIPAY_TOKEN_METHOD,
            app_auth_token="",
            biz_content={"grant_type": "refresh_token", "refresh_token": current_refresh_token},
        )
        return self._token_bundle_from_response(data)

    def fetch_shop_profile(
        self,
        *,
        token_bundle: PlatformTokenBundle,
        auth_session: dict[str, Any] | None = None,
        callback_payload: dict[str, Any] | None = None,
    ) -> PlatformShopProfile:
        if self.is_mock:
            session_id = str((auth_session or {}).get("id") or "")[-6:] or "000001"
            shop_name = str((callback_payload or {}).get("mock_shop_name") or f"支付宝测试商户{session_id}")
            return PlatformShopProfile(
                external_shop_id=f"alipay_shop_{session_id}",
                external_shop_name=shop_name,
                external_seller_id=f"alipay_seller_{session_id}",
                auth_subject_name=shop_name,
                shop_type="merchant",
                metadata={"mode": "mock", "platform": "alipay"},
            )
        payload = token_bundle.raw_payload
        session_extra = (auth_session or {}).get("extra") if isinstance(auth_session, dict) else {}
        session_extra = session_extra if isinstance(session_extra, dict) else {}
        callback = callback_payload or {}
        shop_id = str(payload.get("user_id") or payload.get("auth_user_id") or "").strip()
        seller_id = str(payload.get("auth_app_id") or "").strip()
        shop_name = str(
            session_extra.get("merchant_display_name")
            or callback.get("merchant_display_name")
            or payload.get("merchant_display_name")
            or shop_id
        ).strip()
        if not shop_id:
            raise RuntimeError("支付宝 token 响应缺少 user_id，无法绑定商户")
        return PlatformShopProfile(
            external_shop_id=shop_id,
            external_shop_name=shop_name or shop_id,
            external_seller_id=seller_id,
            auth_subject_name=shop_name or shop_id,
            shop_type="merchant",
            metadata={
                "mode": "real",
                "platform": "alipay",
                "source": "app_auth_token",
            },
        )

    def query_bill_download_url(
        self,
        *,
        app_auth_token: str,
        bill_type: str,
        bill_date: str,
    ) -> str:
        data = self._post_alipay_request(
            method=ALIPAY_BILL_METHOD,
            app_auth_token=app_auth_token,
            biz_content={"bill_type": bill_type, "bill_date": bill_date},
        )
        response = data.get("alipay_data_dataservice_bill_downloadurl_query_response")
        response_payload = response if isinstance(response, dict) else {}
        download_url = str(response_payload.get("bill_download_url") or "").strip()
        if not download_url:
            raise RuntimeError("支付宝账单下载地址响应为空")
        return download_url

    def download_bill_file(self, *, bill_download_url: str) -> bytes:
        safe_url = str(bill_download_url or "").strip()
        if not safe_url:
            raise RuntimeError("支付宝账单下载地址为空")
        if not _is_trusted_alipay_bill_download_url(safe_url):
            message = "支付宝账单文件下载失败"
            logger.error(message)
            raise RuntimeError(message)
        try:
            response = requests.get(safe_url, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            message = _download_error_message(exc)
            logger.error(message)
            raise RuntimeError(message) from exc
        return response.content

    def fetch_bill_rows(
        self,
        *,
        app_auth_token: str,
        bill_type: str,
        bill_date: str,
        merchant_display_name: str,
        shop_connection_id: str,
        output_dir: str | Path | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        download_url = self.query_bill_download_url(
            app_auth_token=app_auth_token,
            bill_type=bill_type,
            bill_date=bill_date,
        )
        content = self.download_bill_file(bill_download_url=download_url)
        file_name = "download.zip" if zipfile.is_zipfile(io.BytesIO(content)) else "download.csv"
        files: list[dict[str, Any]] = []
        if output_dir:
            target_dir = Path(output_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / file_name
            target_path.write_bytes(content)
            files.append(
                {
                    "file_name": file_name,
                    "path": str(target_path),
                    "size_bytes": len(content),
                }
            )
        parsed_bill = self.parse_bill_file(
            content=content,
            file_name=file_name,
            bill_type=bill_type,
            bill_date=bill_date,
            merchant_display_name=merchant_display_name,
            shop_connection_id=shop_connection_id,
        )
        return parsed_bill if not output_dir else {
            "success": True,
            "rows": parsed_bill["rows"],
            "columns": parsed_bill["columns"],
            "files": files,
        }

    def parse_bill_file(
        self,
        *,
        content: bytes,
        file_name: str,
        bill_type: str,
        bill_date: str,
        merchant_display_name: str,
        shop_connection_id: str,
    ) -> dict[str, Any]:
        if zipfile.is_zipfile(io.BytesIO(content)):
            rows: list[dict[str, Any]] = []
            columns: list[dict[str, str]] = []
            seen_columns: set[str] = set()
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for member in zf.infolist():
                    if member.is_dir() or not member.filename.lower().endswith(".csv"):
                        continue
                    parsed = self.parse_bill_csv(
                        content=zf.read(member),
                        file_name=member.filename,
                        bill_type=bill_type,
                        bill_date=bill_date,
                        merchant_display_name=merchant_display_name,
                        shop_connection_id=shop_connection_id,
                    )
                    rows.extend(parsed["rows"])
                    for column in parsed["columns"]:
                        name = str(column.get("name") or "").strip()
                        if not name or name in seen_columns:
                            continue
                        seen_columns.add(name)
                        columns.append(column)
            return {"rows": rows, "columns": columns}
        return self.parse_bill_csv(
            content=content,
            file_name=file_name,
            bill_type=bill_type,
            bill_date=bill_date,
            merchant_display_name=merchant_display_name,
            shop_connection_id=shop_connection_id,
        )

    def parse_bill_csv(
        self,
        *,
        content: bytes,
        file_name: str,
        bill_type: str,
        bill_date: str,
        merchant_display_name: str,
        shop_connection_id: str,
    ) -> dict[str, Any]:
        text = _decode_csv(content)
        headers, row_items = _csv_header_and_rows(text)
        columns = [
            {"name": header, "data_type": "text", "nullable": True}
            for header in headers
            if header
        ]
        rows = self._parse_csv_row_items(
            row_items=row_items,
            file_name=file_name,
            bill_type=bill_type,
            bill_date=bill_date,
            merchant_display_name=merchant_display_name,
            shop_connection_id=shop_connection_id,
        )
        return {"rows": rows, "columns": columns}

    def _parse_csv_rows(
        self,
        *,
        content: bytes,
        file_name: str,
        bill_type: str,
        bill_date: str,
        merchant_display_name: str,
        shop_connection_id: str,
    ) -> list[dict[str, Any]]:
        parsed = self.parse_bill_csv(
            content=content,
            file_name=file_name,
            bill_type=bill_type,
            bill_date=bill_date,
            merchant_display_name=merchant_display_name,
            shop_connection_id=shop_connection_id,
        )
        return list(parsed["rows"])

    def _parse_csv_row_items(
        self,
        *,
        row_items: list[tuple[int, dict[str, str]]],
        file_name: str,
        bill_type: str,
        bill_date: str,
        merchant_display_name: str,
        shop_connection_id: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row_number, raw_row in row_items:
            cleaned_row = {
                str(key or "").strip(): str(value or "").strip()
                for key, value in raw_row.items()
                if key is not None
            }
            if not any(cleaned_row.values()):
                continue
            row_key = build_alipay_row_key(
                bill_type=bill_type,
                bill_date=bill_date,
                source_file_name=file_name,
                source_row_number=row_number,
                row=cleaned_row,
            )
            rows.append(
                {
                    "platform_code": self.platform_code,
                    "shop_connection_id": shop_connection_id,
                    "merchant_display_name": merchant_display_name,
                    "bill_type": bill_type,
                    "bill_date": bill_date,
                    "source_file_name": file_name,
                    "source_row_number": row_number,
                    "source_row_key": row_key,
                    "alipay_trade_no": _first_text(
                        cleaned_row,
                        "支付宝交易号",
                        "支付宝流水号",
                        "账务流水号",
                    ),
                    "merchant_order_no": _first_text(
                        cleaned_row,
                        "商户订单号",
                        "商户订单号/商家订单号",
                    ),
                    "business_order_no": _first_text(
                        cleaned_row,
                        "业务基础订单号",
                        "业务订单号",
                        "业务流水号",
                    ),
                    "raw": cleaned_row,
                }
            )
        return rows

    def _token_bundle_from_response(self, data: dict[str, Any]) -> PlatformTokenBundle:
        if "error_response" in data:
            error = data["error_response"] if isinstance(data.get("error_response"), dict) else {}
            raise RuntimeError(str(error.get("sub_msg") or error.get("msg") or error))
        response = data.get("alipay_open_auth_token_app_response")
        payload = response if isinstance(response, dict) else data
        access_token = str(payload.get("app_auth_token") or "").strip()
        if not access_token:
            raise RuntimeError("支付宝 token 响应缺少 app_auth_token")
        return PlatformTokenBundle(
            access_token=access_token,
            refresh_token=str(payload.get("app_refresh_token") or ""),
            expires_in=_safe_int(payload.get("expires_in")),
            refresh_expires_in=_safe_int(payload.get("re_expires_in")),
            raw_payload=_safe_token_payload(payload),
        )

    def _post_alipay_request(
        self,
        *,
        method: str,
        app_auth_token: str,
        biz_content: dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._build_signed_params(
            method=method,
            app_auth_token=app_auth_token,
            biz_content=biz_content,
        )
        try:
            response = requests.post(self._gateway_url(), data=payload, timeout=30)
            response.raise_for_status()
            response_text = str(getattr(response, "text", "") or "")
            data = response.json()
        except requests.RequestException as exc:
            message = _gateway_error_message(exc)
            logger.error(f"{message} method={method}")
            raise RuntimeError(message) from exc
        except ValueError as exc:
            message = "支付宝网关响应格式错误"
            logger.error(f"{message} method={method}")
            raise RuntimeError(message) from exc
        if not isinstance(data, dict):
            raise RuntimeError("支付宝网关响应格式错误")
        response_key = _alipay_response_key(method)
        business_error = _alipay_business_error_message(data, response_key=response_key)
        try:
            self._verify_gateway_response_signature(
                data,
                raw_text=response_text,
                response_key=response_key,
            )
        except RuntimeError:
            if business_error:
                logger.warning(
                    "支付宝业务错误响应验签未通过，按业务错误返回: method=%s error=%s",
                    method,
                    business_error,
                )
                raise RuntimeError(business_error) from None
            raise
        if business_error:
            raise RuntimeError(business_error)
        return data

    def _verify_gateway_response_signature(
        self,
        data: dict[str, Any],
        *,
        raw_text: str = "",
        response_key: str = "",
    ) -> bool:
        signature_text = str(data.get("sign") or "").strip()
        if not signature_text:
            return True
        public_key_text = str(
            self.app_config.extra.get("alipay_public_key")
            or self.app_config.extra.get("alipay_public_cert")
            or self.app_config.extra.get("alipay_public_cert_path")
            or ""
        ).strip()
        if not public_key_text:
            raise RuntimeError("支付宝网关响应验签失败")
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            signature = base64.b64decode(signature_text, validate=True)
            try:
                public_key = serialization.load_pem_public_key(public_key_text.encode("utf-8"))
            except ValueError:
                cert = x509.load_pem_x509_certificate(public_key_text.encode("utf-8"))
                public_key = cert.public_key()
            sign_content = _extract_gateway_sign_content(raw_text, response_key=response_key)
            if not sign_content and "error_response" in data:
                sign_content = _extract_gateway_sign_content(raw_text, response_key="error_response")
            if not sign_content:
                raise RuntimeError("支付宝网关响应验签失败")
            public_key.verify(
                signature,
                sign_content.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except Exception as exc:
            public_key_fingerprint = hashlib.sha256(public_key_text.encode("utf-8")).hexdigest()[:16]
            current_sign_content = str(locals().get("sign_content") or "")
            logger.error(
                "支付宝网关响应验签失败: response_key=%s sign_content_len=%s "
                "sign_content_sha256=%s public_key_sha256=%s",
                response_key,
                len(current_sign_content),
                hashlib.sha256(current_sign_content.encode("utf-8")).hexdigest()[:16]
                if current_sign_content
                else "",
                public_key_fingerprint,
            )
            raise RuntimeError("支付宝网关响应验签失败") from exc
        return True

    def _build_signed_params(
        self,
        *,
        method: str,
        app_auth_token: str,
        biz_content: dict[str, Any],
    ) -> dict[str, Any]:
        params = {
            "app_id": self.app_config.app_key,
            "method": method,
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now(ALIPAY_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "app_auth_token": app_auth_token,
            "biz_content": json.dumps(biz_content, ensure_ascii=False, separators=(",", ":")),
        }
        if not app_auth_token:
            params.pop("app_auth_token")
        app_public_cert = str(self.app_config.extra.get("app_public_cert") or "").strip()
        alipay_root_cert = str(self.app_config.extra.get("alipay_root_cert") or "").strip()
        if app_public_cert and alipay_root_cert:
            try:
                params["app_cert_sn"] = _alipay_cert_sn(app_public_cert)
                params["alipay_root_cert_sn"] = _alipay_cert_sn(alipay_root_cert, root=True)
            except Exception as exc:
                logger.error("支付宝证书序列号计算失败: %s", exc)
                raise RuntimeError("支付宝证书序列号计算失败") from exc
        params["sign"] = self._sign_params(params)
        return params

    def _sign_params(self, params: dict[str, Any]) -> str:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as exc:
            raise RuntimeError(
                "Alipay RSA2 signing requires cryptography; install it in finance-mcp requirements"
            ) from exc

        items = sorted(
            (key, value) for key, value in params.items() if key != "sign" and value is not None
        )
        sign_content = "&".join(f"{key}={value}" for key, value in items)
        private_key = serialization.load_pem_private_key(
            self.app_config.app_secret.encode("utf-8"),
            password=None,
        )
        signature = private_key.sign(
            sign_content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")
