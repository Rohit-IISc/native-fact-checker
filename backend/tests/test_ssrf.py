import pytest

from app.intake.ssrf import BlockedURL, check_url_shape, ip_is_public, resolve_public


@pytest.mark.parametrize("ip,public", [
    ("8.8.8.8", True),
    ("142.250.183.14", True),
    ("2606:4700:4700::1111", True),
    ("10.0.0.1", False),
    ("172.16.5.4", False),
    ("192.168.1.1", False),
    ("127.0.0.1", False),
    ("169.254.169.254", False),   # metadata server
    ("100.64.0.1", False),        # carrier-grade NAT
    ("0.0.0.0", False),
    ("::1", False),
    ("fe80::1", False),
    ("fc00::1", False),
    ("::ffff:127.0.0.1", False),  # IPv4-mapped loopback
    ("224.0.0.1", False),
])
def test_ip_is_public(ip, public):
    assert ip_is_public(ip) is public


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/x", "gopher://x", "http://localhost/admin",
    "http://metadata.google.internal/computeMetadata/v1/", "http://user:pw@example.com/",
    "http:///nohost",
])
def test_bad_shapes_blocked(url):
    with pytest.raises(BlockedURL):
        check_url_shape(url)


async def test_literal_private_ip_blocked():
    with pytest.raises(BlockedURL):
        await resolve_public("http://169.254.169.254/latest/meta-data")
    with pytest.raises(BlockedURL):
        await resolve_public("http://[::1]:8080/")


async def test_dns_rebinding_any_private_answer_blocks():
    async def resolver(host, port):
        return ["93.184.216.34", "10.1.2.3"]

    with pytest.raises(BlockedURL):
        await resolve_public("https://evil.example/", resolver=resolver)


async def test_public_dns_passes():
    async def resolver(host, port):
        assert (host, port) == ("example.com", 443)
        return ["93.184.216.34"]

    assert await resolve_public("https://example.com/a", resolver=resolver) == ["93.184.216.34"]
