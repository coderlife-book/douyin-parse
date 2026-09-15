import json
import unittest
from unittest.mock import patch

import requests

from douyin_video_parser import DouyinParseError, DouyinVideoParser


def _make_response(status_code=200, text="", json_data=None):
    resp = requests.Response()
    resp.status_code = status_code
    if json_data is not None:
        resp._content = json.dumps(json_data).encode("utf-8")
    else:
        resp._content = text.encode("utf-8")
    return resp


class ResponseClassificationTests(unittest.TestCase):
    def setUp(self):
        self.parser = DouyinVideoParser()
        self.parser.set_cookie("UIFID=uid")
        self.params = {"aid": "6383", "aweme_id": "123"}

    def _classify(self, resp, data_key="aweme_detail"):
        return DouyinVideoParser._classify_response(resp, data_key)

    def test_argus_403_mentions_risk_control(self):
        resp = _make_response(403, text="Blocked by ArgusSecurityPlugin Uifid Not Found")

        with self.assertRaises(DouyinParseError) as ctx:
            self._classify(resp)

        self.assertIn("风控", str(ctx.exception))
        self.assertIn("签名", str(ctx.exception))

    def test_rate_limited_429(self):
        with self.assertRaises(DouyinParseError) as ctx:
            self._classify(_make_response(429))

        self.assertIn("限流", str(ctx.exception))

    def test_login_required_status_code(self):
        resp = _make_response(200, json_data={"status_code": 2483})

        with self.assertRaises(DouyinParseError) as ctx:
            self._classify(resp)

        self.assertIn("扫码登录", str(ctx.exception))

    def test_nonzero_status_code_mentions_missing_work(self):
        resp = _make_response(200, json_data={"status_code": 8})

        with self.assertRaises(DouyinParseError) as ctx:
            self._classify(resp)

        self.assertIn("status_code=8", str(ctx.exception))

    def test_successful_detail_returns_data(self):
        resp = _make_response(200, json_data={"status_code": 0, "aweme_detail": {"aweme_id": "1"}})

        self.assertEqual(self._classify(resp)["aweme_detail"]["aweme_id"], "1")

    def test_empty_list_is_success_for_list_endpoint(self):
        resp = _make_response(200, json_data={"aweme_list": [], "has_more": False})

        data = self._classify(resp, data_key="aweme_list")

        self.assertEqual(data["aweme_list"], [])

    def test_non_json_200_mentions_captcha(self):
        resp = _make_response(200, text="<html>captcha</html>")

        with self.assertRaises(DouyinParseError) as ctx:
            self._classify(resp)

        self.assertIn("验证码", str(ctx.exception))

    def test_other_http_status(self):
        with self.assertRaises(DouyinParseError) as ctx:
            self._classify(_make_response(502))

        self.assertIn("HTTP 502", str(ctx.exception))


class RequestJsonNetworkTests(unittest.TestCase):
    def setUp(self):
        self.parser = DouyinVideoParser()
        self.parser.set_cookie("UIFID=uid")

    def test_timeout_raises_network_message(self):
        with patch("douyin_video_parser.requests.get", side_effect=requests.Timeout("t")):
            with self.assertRaises(DouyinParseError) as ctx:
                self.parser._request_json(
                    "https://www.douyin.com/x/", {"a": "1"}, {}
                )

        self.assertIn("超时", str(ctx.exception))

    def test_request_error_raises_network_message(self):
        with patch("douyin_video_parser.requests.get", side_effect=requests.ConnectionError("c")):
            with self.assertRaises(DouyinParseError) as ctx:
                self.parser._request_json(
                    "https://www.douyin.com/x/", {"a": "1"}, {}
                )

        self.assertIn("网络", str(ctx.exception))


class GetVideoIdErrorTests(unittest.TestCase):
    def setUp(self):
        self.parser = DouyinVideoParser()

    def test_garbage_input_raises_link_error(self):
        with self.assertRaises(DouyinParseError) as ctx:
            self.parser.get_video_id("完全不是链接的文本")

        self.assertIn("无法识别", str(ctx.exception))

    def test_unknown_url_raises_link_error(self):
        # URL 合法但匹配不到任何 ID 模式时，不应误报为网络错误
        resp = _make_response(200, text="<html>empty</html>")
        resp.url = "https://example.com/nope"
        with patch("douyin_video_parser.requests.Session.get", return_value=resp):
            with self.assertRaises(DouyinParseError) as ctx:
                self.parser.get_video_id("https://example.com/nope")

        self.assertIn("无法识别", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
