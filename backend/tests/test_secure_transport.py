import socket
import httpcore
import unittest
from unittest.mock import patch

from backend.app.core.secure_transport import (
    resolve_public_addresses,
    SecureNetworkBackend,
    SecureSocketStream,
)


class ResolvePublicAddressesTests(unittest.TestCase):

    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_allows_public_ipv4(self, mock_dns):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
        ]
        result = resolve_public_addresses("example.com", 80)
        self.assertEqual(len(result), 1)

    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_raises_value_error_on_dns_failure(self, mock_dns):
        mock_dns.side_effect = socket.gaierror("DNS lookup failed")

        with self.assertRaisesRegex(
            ValueError,
            "Unable to resolve hostname",
        ):
            resolve_public_addresses("nonexistent.example", 80)

    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_rejects_empty_dns_result(self, mock_dns):
        mock_dns.return_value = []

        with self.assertRaisesRegex(
            ValueError,
            "Hostname has no addresses",
        ):
            resolve_public_addresses("example.com", 80)

    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_keeps_all_public_addresses(self, mock_dns):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 80)),
        ]

        result = resolve_public_addresses("example.com", 80)

        self.assertEqual(len(result), 2)
        self.assertEqual(
            {item[3][0] for item in result},
            {"93.184.216.34", "1.1.1.1"},
        )

    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_blocks_loopback(self, mock_dns):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))
        ]
        with self.assertRaises(ValueError):
            resolve_public_addresses("example.com", 80)

    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_blocks_private_ipv4(self, mock_dns):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 80))
        ]
        with self.assertRaises(ValueError):
            resolve_public_addresses("example.com", 80)

    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_blocks_mixed_public_and_private(self, mock_dns):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 80)),
        ]
        with self.assertRaises(ValueError):
            resolve_public_addresses("example.com", 80)

    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_blocks_ipv4_mapped_ipv6(self, mock_dns):
        mock_dns.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 80, 0, 0))
        ]
        with self.assertRaises(ValueError):
            resolve_public_addresses("example.com", 80)


    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_blocks_nat64_address(self, mock_dns):
        mock_dns.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("64:ff9b::7f00:1", 80, 0, 0))
        ]
        with self.assertRaises(ValueError):
            resolve_public_addresses("example.com", 80)

    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_blocks_orchid_ipv6_address(self, mock_dns):
        mock_dns.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:20::1", 80, 0, 0))
        ]
        with self.assertRaises(ValueError):
            resolve_public_addresses("example.com", 80)


class SecureNetworkBackendTests(unittest.TestCase):

    @patch("backend.app.core.secure_transport.socket.socket")
    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_tries_next_resolved_ip_after_connection_failure(
        self,
        mock_dns,
        mock_socket,
    ):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 80)),
        ]

        first_socket = unittest.mock.MagicMock()
        first_socket.connect.side_effect = OSError("Connection failed")

        second_socket = unittest.mock.MagicMock()

        mock_socket.side_effect = [first_socket, second_socket]

        stream = SecureNetworkBackend().connect_tcp(
            "example.com",
            80,
        )

        first_socket.connect.assert_called_once_with(
            ("93.184.216.34", 80)
        )
        second_socket.connect.assert_called_once_with(
            ("1.1.1.1", 80)
        )
        first_socket.close.assert_called_once()
        self.assertIsInstance(stream, SecureSocketStream)
        mock_dns.assert_called_once()

        stream.close()


    @patch("backend.app.core.secure_transport.socket.socket")
    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_raises_connect_error_when_all_ips_fail(
        self,
        mock_dns,
        mock_socket,
    ):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 80)),
        ]

        first_socket = unittest.mock.MagicMock()
        first_socket.connect.side_effect = OSError("First connection failed")

        second_socket = unittest.mock.MagicMock()
        second_socket.connect.side_effect = OSError("Second connection failed")

        mock_socket.side_effect = [first_socket, second_socket]

        with self.assertRaises(httpcore.ConnectError):
            SecureNetworkBackend().connect_tcp(
                "example.com",
                80,
            )

        first_socket.close.assert_called_once()
        second_socket.close.assert_called_once()
        mock_dns.assert_called_once()


    @patch("backend.app.core.secure_transport.socket.socket")
    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_raises_connect_timeout_and_closes_socket(
        self,
        mock_dns,
        mock_socket,
    ):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
        ]

        fake_socket = mock_socket.return_value
        fake_socket.connect.side_effect = socket.timeout(
            "Connection timed out"
        )

        with self.assertRaises(httpcore.ConnectTimeout):
            SecureNetworkBackend().connect_tcp(
                "example.com",
                80,
                timeout=5,
            )

        fake_socket.settimeout.assert_called_once_with(5)
        fake_socket.close.assert_called_once()
        mock_dns.assert_called_once()


    @patch("backend.app.core.secure_transport.socket.socket")
    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_binds_ipv4_local_address(
        self,
        mock_dns,
        mock_socket,
    ):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
        ]

        fake_socket = mock_socket.return_value

        stream = SecureNetworkBackend().connect_tcp(
            "example.com",
            80,
            local_address="192.0.2.10",
        )

        fake_socket.bind.assert_called_once_with(("192.0.2.10", 0))
        fake_socket.connect.assert_called_once_with(("93.184.216.34", 80))

        stream.close()


    @patch("backend.app.core.secure_transport.socket.socket")
    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_binds_ipv6_local_address(
        self,
        mock_dns,
        mock_socket,
    ):
        mock_dns.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 80, 0, 0))
        ]

        fake_socket = mock_socket.return_value

        stream = SecureNetworkBackend().connect_tcp(
            "example.com",
            80,
            local_address="2001:db8::10",
        )

        fake_socket.bind.assert_called_once_with(
            ("2001:db8::10", 0, 0, 0)
        )
        fake_socket.connect.assert_called_once_with(
            ("2606:4700:4700::1111", 80, 0, 0)
        )

        stream.close()


    @patch("backend.app.core.secure_transport.socket.socket")
    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_applies_socket_options_before_connect(
        self,
        mock_dns,
        mock_socket,
    ):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
        ]

        fake_socket = mock_socket.return_value
        option = (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        stream = SecureNetworkBackend().connect_tcp(
            "example.com",
            80,
            socket_options=[option],
        )

        fake_socket.setsockopt.assert_any_call(*option)

        calls = [
            call[0]
            for call in fake_socket.method_calls
        ]

        self.assertLess(
            calls.index("setsockopt"),
            calls.index("connect"),
        )

        stream.close()


    @patch("backend.app.core.secure_transport.socket.socket")
    @patch("backend.app.core.secure_transport.socket.getaddrinfo")
    def test_connects_directly_to_resolved_ip(
        self,
        mock_dns,
        mock_socket,
    ):
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
        ]

        fake_socket = mock_socket.return_value

        stream = SecureNetworkBackend().connect_tcp(
            "example.com",
            80,
        )

        self.assertIsInstance(stream, SecureSocketStream)
        fake_socket.connect.assert_called_once_with(
            ("93.184.216.34", 80)
        )
        mock_dns.assert_called_once()

        stream.close()


if __name__ == "__main__":
    unittest.main()


class SecureSocketStreamTests(unittest.TestCase):

    @patch("backend.app.core.secure_transport.ssl")
    def test_start_tls_preserves_server_hostname(self, mock_ssl):
        fake_socket = unittest.mock.MagicMock()
        fake_tls_socket = unittest.mock.MagicMock()
        fake_ssl_context = unittest.mock.MagicMock()
        fake_ssl_context.wrap_socket.return_value = fake_tls_socket

        stream = SecureSocketStream(fake_socket)
        result = stream.start_tls(
            fake_ssl_context,
            server_hostname="example.com",
            timeout=5,
        )

        fake_socket.settimeout.assert_called_once_with(5)
        fake_ssl_context.wrap_socket.assert_called_once_with(
            fake_socket,
            server_hostname="example.com",
        )
        self.assertIsInstance(result, SecureSocketStream)
        self.assertIs(result._sock, fake_tls_socket)


    def test_start_tls_closes_socket_on_ssl_error(self):
        import ssl

        fake_socket = unittest.mock.MagicMock()
        fake_ssl_context = unittest.mock.MagicMock()
        fake_ssl_context.wrap_socket.side_effect = ssl.SSLError(
            "TLS handshake failed"
        )

        stream = SecureSocketStream(fake_socket)

        with self.assertRaises(httpcore.ConnectError) as context:
            stream.start_tls(
                fake_ssl_context,
                server_hostname="example.com",
            )

        fake_socket.close.assert_called_once()
        self.assertIsInstance(context.exception.__cause__, ssl.SSLError)

    @patch("backend.app.core.secure_transport.ssl")
    def test_start_tls_closes_socket_on_timeout(self, mock_ssl):
        fake_socket = unittest.mock.MagicMock()
        fake_ssl_context = unittest.mock.MagicMock()
        fake_ssl_context.wrap_socket.side_effect = socket.timeout(
            "TLS handshake timed out"
        )

        stream = SecureSocketStream(fake_socket)

        with self.assertRaises(httpcore.ConnectTimeout) as context:
            stream.start_tls(
                fake_ssl_context,
                server_hostname="example.com",
                timeout=5,
            )

        fake_socket.close.assert_called_once()
        self.assertIsInstance(context.exception.__cause__, socket.timeout)
