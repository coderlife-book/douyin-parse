import hashlib
import unittest

from douyin_video_parser import (
    WEB_SIGN_SALT,
    build_websigned_request,
    encode_query_pairs,
    extract_uifid,
)


class ExtractUifidTests(unittest.TestCase):
    def test_prefers_uifid_over_uifid_temp(self):
        cookie = "ttwid=1; UIFID_TEMP=temp-value; UIFID=full-value; other=2"

        self.assertEqual(extract_uifid(cookie), "full-value")

    def test_falls_back_to_temp_spelling(self):
        cookie = "ttwid=1; UIFID_TEMP=temp-value"

        self.assertEqual(extract_uifid(cookie), "temp-value")

    def test_returns_none_without_uifid(self):
        self.assertIsNone(extract_uifid("ttwid=1; sessionid=abc"))
        self.assertIsNone(extract_uifid(""))


class EncodeQueryPairsTests(unittest.TestCase):
    def test_encodes_like_url_search_params(self):
        query = encode_query_pairs([("a", "1"), ("b", "x/y"), ("c", "d+e"), ("f", "g*-._")])

        self.assertEqual(query, "a=1&b=x%2Fy&c=d%2Be&f=g*-._")


class BuildWebsignedRequestTests(unittest.TestCase):
    def test_signs_query_and_headers(self):
        headers = {"User-Agent": "ua"}

        url, signed_headers = build_websigned_request(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aid": "6383", "aweme_id": "123", "a_bogus": "ab/c"},
            headers,
            cookie="ttwid=1; UIFID=uid123",
            timestamp=1700000000,
        )

        query = "aid=6383&aweme_id=123&a_bogus=ab%2Fc&uifid=uid123&timestamp=1700000000"
        signature = hashlib.md5(
            f"uid123_1700000000_{WEB_SIGN_SALT}_{query}".encode()
        ).hexdigest()

        self.assertEqual(
            url,
            "https://www.douyin.com/aweme/v1/web/aweme/detail/"
            f"?{query}&x-secsdk-web-signature={signature}",
        )
        self.assertEqual(signed_headers["uifid"], "uid123")
        self.assertEqual(signed_headers["x-secsdk-web-signature"], signature)
        self.assertEqual(signed_headers["x-secsdk-web-expire"], "1700000000")

    def test_does_not_mutate_input_headers_or_duplicate_uifid(self):
        headers = {"User-Agent": "ua"}

        url, _signed_headers = build_websigned_request(
            "https://www.douyin.com/x/",
            {"uifid": "already", "a": "1"},
            headers,
            cookie="UIFID=uid123",
            timestamp=1700000000,
        )

        self.assertEqual(url.count("uifid="), 1)
        self.assertNotIn("uifid", headers)

    def test_returns_none_without_uifid(self):
        result = build_websigned_request(
            "https://www.douyin.com/x/",
            {"a": "1"},
            {},
            cookie="ttwid=1",
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
