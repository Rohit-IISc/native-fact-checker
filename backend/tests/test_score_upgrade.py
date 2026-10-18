from app.agents import score_upgrade
from app.models import (
    Claim,
    ClaimType,
    Evidence,
    JudgeVerdict,
    Label,
    PanelOutcome,
    ScoreUpgradeReview,
    SourceTier,
    Stance,
    TimeSensitivity,
)

T1, T2, T3 = SourceTier.TIER_1, SourceTier.TIER_2, SourceTier.TIER_3


class StubLLM:
    def __init__(self, review):
        self.review, self.calls = review, 0

    async def generate(self, **kw):
        self.calls += 1
        return self.review

    async def embed(self, texts, *, timeout_s):
        return [[float(i == j) for j in range(len(texts))] for i in range(len(texts))]  # all distinct


def ev(eid, tier, publisher, title):
    return Evidence(evidence_id=eid, agent="web_search", claim_id="c1", publisher=publisher, title=title,
                    snippet_en="It happened.", stance=Stance.SUPPORTS, tier=tier)


CLAIM = Claim(claim_id="c1", claim_original="x", claim_en="A singer opened a restaurant", claim_type=ClaimType.OTHER,
              time_sensitivity=TimeSensitivity.EVERGREEN, checkable=True)


def nee(for_ids):
    return JudgeVerdict(claim_id="c1", label=Label.NOT_ENOUGH_EVIDENCE, confidence=0, what_is_true_en="unclear",
                        evidence_for_ids=for_ids, evidence_against_ids=[], cited_ids=[], reasoning_en="thin")


async def test_upgrade_accepted_passes_policy():
    pack = [ev("a", T2, "Hindustan Times", "Opened"), ev("b", T2, "The Hindu", "Restaurant opens")]
    llm = StubLLM(ScoreUpgradeReview(accept=True, kept_ids=["a", "b"], what_is_true_en="It opened.", reason_en="ok"))
    up = await score_upgrade.run(llm, CLAIM, nee(["a", "b"]), PanelOutcome.POLICY_DOWNGRADE, pack, 20)
    assert up and up[0].label == Label.TRUE and up[0].cited_ids == ["a", "b"] and llm.calls == 1


async def test_critic_declines():
    pack = [ev("a", T2, "Hindustan Times", "Opened"), ev("b", T2, "The Hindu", "Restaurant opens")]
    llm = StubLLM(ScoreUpgradeReview(accept=False, reason_en="older event"))
    assert await score_upgrade.run(llm, CLAIM, nee(["a", "b"]), PanelOutcome.AGREED, pack, 20) is None


async def test_low_harm_upgrade_satisfies_policy_high_harm_does_not():
    # 1 tier 2 + tier 3s (Mahadevan): enough for a low-harm claim, not for a high-harm one
    pack = [ev("a", T2, "Hindustan Times", "Opened"), ev("b", T3, "The Print", "Malgudi"),
            ev("c", T3, "Business Today", "Dream"), ev("d", T3, "Big News", "Other words")]
    llm = StubLLM(ScoreUpgradeReview(accept=True, kept_ids=["a", "b", "c", "d"], reason_en="ok"))
    up = await score_upgrade.run(llm, CLAIM, nee(["a", "b", "c", "d"]), PanelOutcome.AGREED, pack, 20)
    assert up and up[0].label == Label.TRUE
    health = CLAIM.model_copy(update={"claim_type": ClaimType.HEALTH})
    assert await score_upgrade.run(llm, health, nee(["a", "b", "c", "d"]), PanelOutcome.AGREED, pack, 20) is None


async def test_never_for_split_or_other_labels():
    pack = [ev("a", T1, "Reuters", "One"), ev("b", T1, "AP", "Two")]
    llm = StubLLM(ScoreUpgradeReview(accept=True, kept_ids=["a", "b"]))
    assert await score_upgrade.run(llm, CLAIM, nee(["a", "b"]), PanelOutcome.SPLIT, pack, 20) is None
    false_v = nee(["a", "b"]).model_copy(update={"label": Label.FALSE})
    assert await score_upgrade.run(llm, CLAIM, false_v, PanelOutcome.AGREED, pack, 20) is None
    assert llm.calls == 0
