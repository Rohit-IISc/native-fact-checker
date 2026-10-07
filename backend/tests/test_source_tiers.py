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
    ("https://www.tempo.co/cekfakta/x", SourceTier.TIER_2),   # not an active IFCN signatory (2026-10-07)
    ("https://www.altnews.in/hindi/x", SourceTier.TIER_2),    # last IFCN verification 2019
    ("https://tempo.co/x", SourceTier.TIER_2),
    # Rohit's additions (2026-10-07)
    ("https://www.voanews.com/a/x", SourceTier.TIER_2),
    ("https://www.pbs.org/newshour/world/x", SourceTier.TIER_2),
    ("https://time.com/6307329/x", SourceTier.TIER_2),
    ("https://www.tribuneindia.com/news/x", SourceTier.TIER_2),
    ("https://in.reuters.com/article/x", SourceTier.TIER_1),
    ("https://apnews.com/hub/india", SourceTier.TIER_1),
    ("https://leadstories.com/hoax-alert/2023/x", SourceTier.TIER_1),
    ("https://www.politifact.com/factchecks/2020/x", SourceTier.TIER_1),
    ("https://telugu.factly.in/x", SourceTier.TIER_1),
    # IFCN active signatories, by their real section paths
    ("https://hindi.boomlive.in/fact-check/x", SourceTier.TIER_1),
    ("https://malayalam.indiatoday.in/fact-check/x", SourceTier.TIER_1),
    ("https://www.telugupost.com/factcheck/x", SourceTier.TIER_1),
    ("https://www.telugupost.com/politics/x", SourceTier.TIER_3),
    ("https://www.newsmobile.in/nm-fact-checker/x", SourceTier.TIER_1),
    ("https://www.thelallantop.com/factcheck/x", SourceTier.TIER_1),
    ("https://kannada.digiteye.in/x", SourceTier.TIER_1),
    ("https://www.liputan6.com/cek-fakta/read/x", SourceTier.TIER_1),
    ("https://www.liputan6.com/news/x", SourceTier.TIER_3),
    ("https://www.kompas.com/cekfakta/read/x", SourceTier.TIER_1),
    ("https://www.kompas.com/tren/read/x", SourceTier.TIER_2),
    ("https://turnbackhoax.id/articles/x", SourceTier.TIER_1),
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
