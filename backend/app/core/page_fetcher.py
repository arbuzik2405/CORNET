from urllib.parse import urlparse

import httpx

from .secure_transport import SecureHTTPTransport


MAX_RESPONSE_SIZE = 2 * 1024 * 1024
TIMEOUT = 10.0

USER_AGENT = "CORNET/0.1 (+web monitoring)"


def validate_url(url: str) -> None:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS URLs are allowed")

    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid URL")

    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid port")


def fetch_page(url: str) -> str:
    validate_url(url)

    headers = {"User-Agent": USER_AGENT}

    with httpx.Client(
        transport=SecureHTTPTransport(),
        timeout=TIMEOUT,
        follow_redirects=False,
        trust_env=False,
        headers=headers,
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()

            content_type = response.headers.get(
                "content-type", ""
            ).lower()

            if not any(
                item in content_type
                for item in ("text/html", "application/xhtml+xml")
            ):
                raise ValueError("URL does not return HTML")

            chunks = []
            total_size = 0

            for chunk in response.iter_bytes():
                total_size += len(chunk)

                if total_size > MAX_RESPONSE_SIZE:
                    raise ValueError("Response exceeds 2 MB limit")

                chunks.append(chunk)

            encoding = response.encoding or "utf-8"

            return b"".join(chunks).decode(
                encoding,
                errors="replace",
            )
