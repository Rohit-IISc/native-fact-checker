"""Review panel model calls: Judge, Critic and Judge revision (prompts/08, 08b, 09). Gemini Pro.

The Judge sees only the EvidencePack, never the post. Merge rules live in pipeline/panel.py.
"""
from __future__ import annotations

from app.llm import LLM
from app.models import CriticOutput, EvidencePack, JudgeOutput
from app.prompts import load_block, load_prompt


def _pack_json(pack: EvidencePack) -> str:
    return pack.model_dump_json(indent=1, exclude={"check_id"})


async def judge(llm: LLM, pack: EvidencePack, timeout_s: float) -> JudgeOutput:
    prompt = load_prompt("08_judge.md")
    text = prompt.render(revision_block="", evidence_pack_json=_pack_json(pack))
    return await llm.generate(stage="judge", prompt=text, prompt_version=prompt.version, schema=JudgeOutput,
                              timeout_s=timeout_s)


async def critic(llm: LLM, pack: EvidencePack, judged: JudgeOutput, timeout_s: float) -> CriticOutput:
    prompt = load_prompt("09_critic.md")
    text = prompt.render(evidence_pack_json=_pack_json(pack), judge_output_json=judged.model_dump_json(indent=1))
    return await llm.generate(stage="critic", prompt=text, prompt_version=prompt.version, schema=CriticOutput,
                              timeout_s=timeout_s)


async def revise(llm: LLM, pack: EvidencePack, judged: JudgeOutput, criticised: CriticOutput,
                 timeout_s: float) -> JudgeOutput:
    prompt, block = load_prompt("08_judge.md"), load_block("08b_judge_revision_block.md")
    revision = block.render(judge_output_json=judged.model_dump_json(indent=1),
                            critic_output_json=criticised.model_dump_json(indent=1))
    text = prompt.render(revision_block=revision, evidence_pack_json=_pack_json(pack))
    return await llm.generate(stage="judge_revision", prompt=text, prompt_version=f"{prompt.version}+{block.version}",
                              schema=JudgeOutput, timeout_s=timeout_s)
