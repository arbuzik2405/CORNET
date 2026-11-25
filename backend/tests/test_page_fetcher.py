import unittest

from backend.app.core.page_fetcher import validate_url


class ValidateURLTests(unittest.TestCase):

    def test_rejects_non_http_scheme(self):
        with self.assertRaises(ValueError):
            validate_url("file:///etc/passwd")

    def test_rejects_credentials(self):
        with self.assertRaises(ValueError):
            validate_url("https://user:password@example.com")

    def test_rejects_missing_hostname(self):
        with self.assertRaises(ValueError):
            validate_url("https:///")

    def test_rejects_invalid_port(self):
        with self.assertRaises(ValueError):
            validate_url("https://example.com:99999")

    def test_allows_public_http_url(self):
        validate_url("http://example.com")

    def test_allows_public_https_url(self):
        validate_url("https://example.com")

    def test_allows_custom_port(self):
        validate_url("https://example.com:8443")


if __name__ == "__main__":
    unittest.main()
