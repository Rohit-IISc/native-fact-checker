from app.models import Evidence, JudgeVerdict, Label, SourceTier, Stance


def ev(eid: str, tier: SourceTier, publisher: str | None = None, url: str | None = None,
       stance: Stance = Stance.CONTRADICTS, claim_id: str = "c1") -> Evidence:
    return Evidence(evidence_id=eid, agent="web_search", claim_id=claim_id, url=url, publisher=publisher,
                    snippet_en="snippet", stance=stance, tier=tier)


def verdict(label: Label, cited: list[str], confidence: int = 90, against: list[str] | None = None,
            for_ids: list[str] | None = None) -> JudgeVerdict:
    return JudgeVerdict(claim_id="c1", label=label, confidence=confidence, what_is_true_en="x",
                        evidence_for_ids=for_ids or [], evidence_against_ids=against if against is not None else cited,
                        cited_ids=cited, reasoning_en="because")
