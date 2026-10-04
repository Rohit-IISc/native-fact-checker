import pytest

from app.models import SourceTier
from app.verify.source_tiers import tier_for_url


@pytest.mark.parametrize("url,tier", [
    ("https://pib.gov.in/PressRelease.aspx?id=1", SourceTier.TIER_1),
    ("https://www.mohfw.gov.in/", SourceTier.TIER_1),
    ("https://some-ministry.nic.in/page", SourceTier.TIER_1),
    ("https://www.reuters.com/world/india/x", SourceTier.TIER_1),
    ("https://factcheck.afp.com/x", SourceTier.TIER_1),
    ("https://www.indiatoday.in/fact-check/story/x", SourceTier.TIER_1),
    ("https://www.indiatoday.in/india/story/x", SourceTier.TIER_3),
    ("https://www.thequint.com/news/webqoof/x", SourceTier.TIER_1),
    ("https://cekfakta.tempo.co/x", SourceTier.TIER_1),
    ("https://tempo.co/x", SourceTier.TIER_2),
    ("https://www.thehindu.com/news/x", SourceTier.TIER_2),
    ("https://x.com/someone/status/1", SourceTier.NOT_A_SOURCE),
    ("https://m.facebook.com/post", SourceTier.NOT_A_SOURCE),
    ("https://someblog.blogspot.com/2024/x", SourceTier.NOT_A_SOURCE),
    ("https://youtu.be/abc", SourceTier.NOT_A_SOURCE),
    ("https://randomnews.example/x", SourceTier.TIER_3),
    ("https://ndtv-news.co/x", SourceTier.TIER_3),
    ("https://notreuters.com/x", SourceTier.TIER_3),
])
def test_tiers(url, tier):
    assert tier_for_url(url) == tier


def test_missing_url_is_not_a_source():
    assert tier_for_url(None) == SourceTier.NOT_A_SOURCE
