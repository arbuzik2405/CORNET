import ipaddress
import socket


BLOCKED_IPV6_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("2001:10::/28"),
    ipaddress.ip_network("2001:20::/28"),
)


def resolve_public_addresses(host: str, port: int):
    try:
        results = socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("Unable to resolve hostname") from exc

    if not results:
        raise ValueError("Hostname has no addresses")

    addresses = []
    seen = set()

    for family, socktype, proto, canonname, sockaddr in results:
        ip = ipaddress.ip_address(sockaddr[0].split("%")[0])

        if isinstance(ip, ipaddress.IPv6Address):
            if ip.ipv4_mapped is not None:
                ip = ip.ipv4_mapped

        if isinstance(ip, ipaddress.IPv6Address):
            if any(ip in network for network in BLOCKED_IPV6_NETWORKS):
                raise ValueError(
                    "Special-purpose IPv6 addresses are blocked"
                )

        if not ip.is_global:
            raise ValueError(
                "Private or non-public addresses are blocked"
            )

        key = (family, sockaddr)

        if key not in seen:
            seen.add(key)
            addresses.append(
                (family, socktype, proto, sockaddr)
            )

    return addresses


import select
import ssl

import httpcore


class SecureSocketStream(httpcore.NetworkStream):

    def __init__(self, sock):
        self._sock = sock

    def read(self, max_bytes, timeout=None):
        try:
            self._sock.settimeout(timeout)
            return self._sock.recv(max_bytes)
        except socket.timeout as exc:
            raise httpcore.ReadTimeout() from exc
        except OSError as exc:
            raise httpcore.ReadError() from exc

    def write(self, buffer, timeout=None):
        try:
            while buffer:
                self._sock.settimeout(timeout)
                sent = self._sock.send(buffer)

                if sent == 0:
                    raise httpcore.WriteError(
                        "Socket connection closed during write"
                    )

                buffer = buffer[sent:]

        except socket.timeout as exc:
            raise httpcore.WriteTimeout() from exc
        except httpcore.WriteError:
            raise
        except OSError as exc:
            raise httpcore.WriteError() from exc

    def close(self):
        self._sock.close()

    def start_tls(
        self,
        ssl_context,
        server_hostname=None,
        timeout=None,
    ):
        try:
            self._sock.settimeout(timeout)
            tls_socket = ssl_context.wrap_socket(
                self._sock,
                server_hostname=server_hostname,
            )
            return SecureSocketStream(tls_socket)
        except socket.timeout as exc:
            try:
                self.close()
            except OSError:
                pass
            raise httpcore.ConnectTimeout(
                f"TLS handshake timed out: {exc}"
            ) from exc
        except (ssl.SSLError, OSError) as exc:
            try:
                self.close()
            except OSError:
                pass
            raise httpcore.ConnectError(
                f"TLS handshake failed: {exc}"
            ) from exc

    def get_extra_info(self, info):
        try:
            if info == "socket":
                return self._sock

            if info == "client_addr":
                return self._sock.getsockname()

            if info == "server_addr":
                return self._sock.getpeername()

            if info == "ssl_object" and isinstance(
                self._sock,
                ssl.SSLSocket,
            ):
                return self._sock

            if info == "is_readable":
                readable, _, _ = select.select(
                    [self._sock],
                    [],
                    [],
                    0,
                )
                return bool(readable)

        except (OSError, ValueError):
            return None

        return None


import time


class SecureNetworkBackend(httpcore.NetworkBackend):

    def connect_tcp(
        self,
        host,
        port,
        timeout=None,
        local_address=None,
        socket_options=None,
    ):
        try:
            addresses = resolve_public_addresses(host, port)
        except (ValueError, OSError) as exc:
            raise httpcore.ConnectError(
                "Host address validation or resolution failed"
            ) from exc

        last_error = None

        for family, socktype, proto, sockaddr in addresses:
            sock = None

            try:
                sock = socket.socket(family, socktype, proto)
                sock.settimeout(timeout)

                if local_address is not None:
                    if family == socket.AF_INET6:
                        sock.bind((local_address, 0, 0, 0))
                    else:
                        sock.bind((local_address, 0))

                for option in socket_options or ():
                    sock.setsockopt(*option)

                if socktype == socket.SOCK_STREAM:
                    sock.setsockopt(
                        socket.IPPROTO_TCP,
                        socket.TCP_NODELAY,
                        1,
                    )

                sock.connect(sockaddr)

                return SecureSocketStream(sock)

            except OSError as exc:
                last_error = exc

                if sock is not None:
                    sock.close()

        if isinstance(last_error, socket.timeout):
            raise httpcore.ConnectTimeout(
                "TCP connection timed out"
            ) from last_error

        raise httpcore.ConnectError(
            "Unable to connect to any validated address"
        ) from last_error

    def connect_unix_socket(
        self,
        path,
        timeout=None,
        socket_options=None,
    ):
        raise httpcore.ConnectError(
            "Unix sockets are not supported"
        )

    def sleep(self, seconds):
        time.sleep(seconds)


import httpx
from httpx._transports.default import map_httpcore_exceptions


class SecureResponseStream(httpx.SyncByteStream):

    def __init__(self, stream):
        self._stream = stream

    def __iter__(self):
        with map_httpcore_exceptions():
            yield from self._stream

    def close(self):
        close = getattr(self._stream, "close", None)

        if close is not None:
            close()


class SecureHTTPTransport(httpx.BaseTransport):

    def __init__(
        self,
        *,
        verify=True,
        trust_env=False,
        limits=None,
    ):
        if trust_env:
            raise ValueError("Environment proxies are not supported")

        if verify is True:
            ssl_context = httpx.create_ssl_context()
        elif verify is False:
            raise ValueError("TLS certificate verification cannot be disabled")
        elif isinstance(verify, ssl.SSLContext):
            ssl_context = verify
        else:
            raise TypeError("verify must be True or an SSLContext")

        limits = limits or httpx.Limits()

        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl_context,
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            http1=True,
            http2=False,
            network_backend=SecureNetworkBackend(),
        )

    def handle_request(self, request):
        assert isinstance(request.stream, httpx.SyncByteStream)

        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )

        with map_httpcore_exceptions():
            response = self._pool.handle_request(core_request)

        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=SecureResponseStream(response.iter_stream()),
            extensions=response.extensions,
        )

    def close(self):
        self._pool.close()
