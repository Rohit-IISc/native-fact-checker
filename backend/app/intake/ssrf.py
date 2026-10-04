"""SSRF guard for link fetching: http(s) only, public IPs only at every redirect hop."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class BlockedURL(Exception):
    pass


_METADATA_HOSTS = {"metadata.google.internal", "metadata", "metadata.goog"}


def ip_is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or (isinstance(addr, ipaddress.IPv4Address) and addr in ipaddress.ip_network("100.64.0.0/10"))
    )


def check_url_shape(url: str) -> tuple[str, int]:
    """Validate scheme and host syntax. Returns (host, port)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise BlockedURL(f"scheme not allowed: {parts.scheme!r}")
    if parts.username or parts.password:
        raise BlockedURL("credentials in URL")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise BlockedURL("no host")
    if host in _METADATA_HOSTS or host == "localhost" or host.endswith(".localhost"):
        raise BlockedURL(f"host not allowed: {host}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return host, port


async def resolve_public(url: str, resolver=None) -> list[str]:
    """Resolve the URL's host and require every address to be public. Returns the IPs.

    Call before every hop (including redirects). `resolver(host, port)` returns a list of IPs;
    it is injectable for tests.
    """
    host, port = check_url_shape(url)
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        if resolver is not None:
            ips = await resolver(host, port)
        else:
            infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
            ips = list({info[4][0] for info in infos})
    if not ips:
        raise BlockedURL(f"no addresses for {host}")
    for ip in ips:
        if not ip_is_public(ip):
            raise BlockedURL(f"non-public address {ip} for {host}")
    return ips
