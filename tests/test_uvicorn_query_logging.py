"""Regression coverage for Uvicorn access and WebSocket token log exposure.

Uses only the standard library, so these security tests also run in a minimal
deployment/build environment without a configured database or API credentials.
"""

import json
import logging
import unittest

from lyo_app.core.url_log_sanitizer import (
    RequestURLQueryFilter,
    install_request_url_query_filter,
    strip_request_url_queries,
)


class RequestURLQueryLoggingTests(unittest.TestCase):
    def setUp(self):
        self.filter = RequestURLQueryFilter()

    def record(self, message, arguments=(), *, logger="uvicorn.error", exc_info=None):
        return logging.LogRecord(
            logger, logging.INFO, __file__, 1, message, arguments, exc_info
        )

    def test_classroom_websocket_accepted_log_strips_entire_query(self):
        record = self.record(
            '%s - "WebSocket %s" [accepted]',
            ("192.0.2.10:5123", "/api/v1/classroom/ws/connect?token=SYNTHETIC.JWT.VALUE&feature=1"),
        )
        self.filter.filter(record)
        result = logging.Formatter().format(record)

        self.assertEqual(
            result,
            '192.0.2.10:5123 - "WebSocket /api/v1/classroom/ws/connect" [accepted]',
        )
        self.assertNotIn("SYNTHETIC", result)
        self.assertNotIn("token=", result)
        self.assertNotIn("feature=", result)

    def test_sync_websocket_quoted_log_strips_entire_query(self):
        record = self.record(
            '"WebSocket /api/v1/sync/ws?session=synthetic-private&token=SYNTHETIC.JWT.VALUE" [accepted]'
        )
        self.filter.filter(record)
        self.assertEqual(
            record.getMessage(), '"WebSocket /api/v1/sync/ws" [accepted]'
        )

    def test_http_access_log_preserves_method_route_client_status(self):
        record = self.record(
            '%s - "%s %s HTTP/%s" %d',
            ("192.0.2.12:5780", "GET", "/api/v1/sync/ws?token=SYNTHETIC.JWT.VALUE", "1.1", 401),
            logger="uvicorn.access",
        )
        self.filter.filter(record)
        result = record.getMessage()
        self.assertEqual(result, '192.0.2.12:5780 - "GET /api/v1/sync/ws HTTP/1.1" 401')

    def test_url_sanitizer_handles_full_ws_https_urls_without_partial_masking(self):
        self.assertEqual(
            strip_request_url_queries(
                "Connected wss://example.test/api/v1/classroom/ws/connect?token=SYNTHETIC.JWT.VALUE&x=1"
            ),
            "Connected wss://example.test/api/v1/classroom/ws/connect",
        )
        self.assertEqual(
            strip_request_url_queries(
                "GET https://example.test/api/v1/sync/ws?token=SYNTHETIC.JWT.VALUE (denied)"
            ),
            "GET https://example.test/api/v1/sync/ws (denied)",
        )

    def test_nested_formatted_arguments_are_sanitized_before_json_formatting(self):
        record = self.record(
            "connection %s", ({"path": "/api/v1/sync/ws?token=SYNTHETIC.JWT.VALUE"},)
        )
        self.filter.filter(record)
        json_result = json.dumps({"message": record.getMessage(), "args": record.args})
        self.assertIn("/api/v1/sync/ws", json_result)
        self.assertNotIn("SYNTHETIC", json_result)
        self.assertNotIn("token=", json_result)

    def test_url_in_exception_message_and_chained_exception_is_sanitized(self):
        try:
            try:
                raise RuntimeError(
                    "upstream wss://example.test/api/v1/sync/ws?token=SYNTHETIC.CAUSE.VALUE"
                )
            except RuntimeError as cause:
                raise ValueError(
                    "failed /api/v1/classroom/ws/connect?token=SYNTHETIC.JWT.VALUE"
                ) from cause
        except ValueError:
            import sys
            record = self.record("WebSocket failure", exc_info=sys.exc_info())
        self.filter.filter(record)
        result = logging.Formatter().format(record)
        self.assertIn("ValueError", result)
        self.assertIn("/api/v1/classroom/ws/connect", result)
        self.assertNotIn("SYNTHETIC", result)
        self.assertNotIn("token=", result)

    def test_only_chained_exception_contains_query(self):
        try:
            try:
                raise RuntimeError(
                    "upstream /api/v1/sync/ws?token=SYNTHETIC.CAUSE.VALUE"
                )
            except RuntimeError as cause:
                raise ValueError("WebSocket could not connect") from cause
        except ValueError:
            import sys
            record = self.record("Connection failure", exc_info=sys.exc_info())
        self.filter.filter(record)
        result = logging.Formatter().format(record)
        self.assertIn("ValueError: WebSocket could not connect", result)
        self.assertNotIn("SYNTHETIC", result)
        self.assertNotIn("token=", result)

    def test_unrelated_data_and_paths_remain_unchanged(self):
        record = self.record(
            '%s - "%s %s HTTP/%s" %d',
            ("192.0.2.13:4001", "GET", "/api/v1/health", "1.1", 200),
        )
        original = record.getMessage()
        self.filter.filter(record)
        self.assertEqual(record.getMessage(), original)

    def test_bytes_query_argument_cannot_escape_filter(self):
        record = self.record(
            "path %r", (b"/api/v1/sync/ws?token=SYNTHETIC.JWT.VALUE",)
        )
        self.filter.filter(record)
        self.assertEqual(record.getMessage(), "path b'/api/v1/sync/ws'")

    def test_installer_covers_error_access_and_websockets_without_duplicates(self):
        install_request_url_query_filter()
        install_request_url_query_filter()
        for name in (
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
            "uvicorn.asgi",
            "websockets.server",
            "websockets.protocol",
        ):
            filters = [
                item for item in logging.getLogger(name).filters
                if isinstance(item, RequestURLQueryFilter)
            ]
            self.assertEqual(len(filters), 1, msg=name)


if __name__ == "__main__":
    unittest.main()
