"""Extract abstract cues, recurring cues, and generated project ideas.

The cues need review in the original papers. The project ideas are suggestions,
not findings from the papers. No novelty search is done.
"""
from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict

from src.normalization.schema import Paper, ResearchGap

# ── Layer 1: Explicit gap sentence patterns ───────────────────────────────────

_EXPLICIT_PATTERN = re.compile(
    r"(?:"
    r"limitation|future work|open problem|open challenge|open question|"
    r"remains to be|yet to be|not address|unsolved|we leave|"
    r"promising direction|future direction|further research needed|"
    r"our approach does not|we do not handle|we cannot|"
    r"cannot handle|fails? to|struggles? with|does not scale|"
    r"challenging to|difficult to|out of scope"
    r")[^.!?]{5,200}[.!?]",
    re.IGNORECASE,
)

# ── Layer 2: Pattern gap signals ─────────────────────────────────────────────
# Each label groups similar text matches across papers.

_PATTERN_SIGNALS: list[tuple[str, re.Pattern[str]]] = [
    ("Benchmark overfitting",
     re.compile(r"\b(overfit(?:ting)? (?:to|on)|overfitting remains|fails? to generaliz\w*|does not generaliz\w*|not generaliz\w*|narrow benchmark coverage)\b", re.IGNORECASE)),
    ("Weak robustness testing",
     re.compile(r"\b(lack of robustness|not robust|poor robustness|no adversarial (?:testing|evaluation)|not tested under distribution shift|distribution shift (?:is|remains) untested|out.of.domain performance (?:is|remains) limited)\b", re.IGNORECASE)),
    ("Missing low-resource coverage",
     re.compile(r"\b(lack of low.resource coverage|low.resource coverage (?:is|remains) limited|does not include low.resource|no (?:low.resource|underrepresented) languages?)\b", re.IGNORECASE)),
    ("Narrow evaluation domains",
     re.compile(r"\b(only (?:evaluates?|tests?) (?:in )?English|limited to (?:one|a single) domain|single.domain evaluation|limited domain coverage)\b", re.IGNORECASE)),
    ("High compute cost",
     re.compile(r"\b(computationally expensive|high computational cost|resource.intensive|GPU.intensive)\b", re.IGNORECASE)),
    ("Lack of interpretability",
     re.compile(r"\b(lack(?:s|ing)? of interpret\w*|not interpretable|opaque model|black.box model)\b", re.IGNORECASE)),
    ("Missing long-form evaluation",
     re.compile(r"\b(lack of long.form evaluation|not evaluated on long.documents?|no extended.context evaluation|long.context evaluation is missing)\b", re.IGNORECASE)),
    ("Dataset bias / fairness",
     re.compile(r"\b(dataset bias remains|biased dataset|gender bias remains|racial bias remains|fairness is not evaluated|fairness is not addressed|lack of fairness evaluation)\b", re.IGNORECASE)),
    ("Limited multilinguality",
     re.compile(r"\b(lack of multilingual coverage|not evaluated in non.English|does not cover non.English|only English(?: data| evaluation)?|limited cross.lingual evaluation)\b", re.IGNORECASE)),
    ("Hallucination / factuality",
     re.compile(r"\b(hallucinations? (?:remain|persist|occur)|factual errors? (?:remain|occur)|hallucination (?:is|remains) unresolved|factuality (?:is|remains) limited|cannot ensure factuality|confabulations? remain)\b", re.IGNORECASE)),
]

# ── Layer 3: Starter idea templates ──────────────────────────────────────────

_STARTER_TEMPLATES: dict[str, list[str]] = {
    "Large Language Models": [
        "Fine-tune an open-source LLM on a domain-specific dataset and evaluate factuality.",
        "Build a RAG pipeline and compare retrieval strategies on a small test set.",
        "Measure LLM calibration: does the model know what it doesn't know?",
    ],
    "Transformer Architectures": [
        "Implement a Transformer from scratch in PyTorch.",
        "Visualise attention heads on your own text samples.",
        "Compare different positional encoding schemes on a text classification task.",
    ],
    "Diffusion Models": [
        "Train a small diffusion model on a custom image dataset (e.g. 64x64 icons).",
        "Evaluate how conditioning signal quality affects generation diversity.",
    ],
    "Reinforcement Learning": [
        "Train a DQN agent on a simple OpenAI Gym environment.",
        "Add reward shaping to reduce sample inefficiency on a gridworld task.",
        "Compare PPO and REINFORCE on a continuous-action environment.",
    ],
    "Computer Vision": [
        "Train a classifier on a small custom dataset using transfer learning.",
        "Implement data augmentation techniques and measure their impact.",
        "Reproduce a CIFAR-10 baseline with a modern architecture.",
    ],
    "Multimodal Learning": [
        "Fine-tune a CLIP model on a domain-specific image-caption dataset.",
        "Evaluate vision-language models on your own image set.",
    ],
    "Code Generation & Synthesis": [
        "Evaluate open-source code LLMs on a custom set of algorithmic problems.",
        "Build a test-case generator to evaluate code correctness automatically.",
    ],
    "Retrieval-Augmented Generation": [
        "Build a RAG pipeline and compare different chunking and retrieval strategies.",
        "Evaluate how knowledge freshness affects LLM answer quality in a RAG setup.",
    ],
    "AI Safety & Alignment": [
        "Red-team a small open-source LLM with structured adversarial prompts.",
        "Measure refusal rates across different safety-sensitive categories.",
    ],
    "AI Agents & Tool Use": [
        "Build a simple tool-using agent and evaluate it on a benchmark task.",
        "Compare ReAct and plan-then-execute prompting strategies.",
    ],
    "_default": [
        "Reproduce the paper's baseline experiment.",
        "Apply the method to a new domain dataset.",
        "Write a blog post explaining the gap and possible directions.",
        "Run an ablation study removing one component of the method.",
    ],
}

# Aliases — short tag forms point to the same templates as their full names
_STARTER_ALIASES: dict[str, str] = {
    "LLMs":           "Large Language Models",
    "Transformers":   "Transformer Architectures",
    "RL":             "Reinforcement Learning",
    "RAG":            "Retrieval-Augmented Generation",
    "Multimodal":     "Multimodal Learning",
    "AI Agents":      "AI Agents & Tool Use",
    "Code Generation":"Code Generation & Synthesis",
}
_STARTER_ALIASES = {tag.casefold(): topic for tag, topic in _STARTER_ALIASES.items()}

def _starter_projects(tags: list[str]) -> list[str]:
    for tag in tags:
        resolved = _STARTER_ALIASES.get(tag.casefold(), tag)
        if resolved in _STARTER_TEMPLATES:
            return _STARTER_TEMPLATES[resolved]
    return _STARTER_TEMPLATES["_default"]


def _gap_id(gap_type: str, topic: str, title: str) -> str:
    key = "\0".join((gap_type, topic, title))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"researchscope/gap/{key}"))



# ── GapExtractor ─────────────────────────────────────────────────────────────

class GapExtractor:
    """Extract review cues and generated project ideas."""

    def extract(self, papers: list[Paper]) -> list[ResearchGap]:
        papers = sorted(papers, key=lambda p: (p.id, p.title, p.abstract))
        gaps: list[ResearchGap] = []
        gaps.extend(self._layer1_explicit(papers))
        gaps.extend(self._layer2_patterns(papers))
        gaps.extend(self._layer3_starters(papers))

        # Deduplicate by the full public identity, not a truncated title.
        seen: dict[tuple[str, str, str], ResearchGap] = {}
        for g in gaps:
            key = (g.topic, g.gap_type, g.title)
            if key not in seen or g.frequency > seen[key].frequency:
                seen[key] = g

        result = sorted(
            seen.values(),
            key=lambda g: (-g.frequency, g.gap_type, g.topic.casefold(), g.title.casefold(), g.gap_id),
        )
        return result

    # ── Layer 1 ───────────────────────────────────────────────────────────────

    def _layer1_explicit(self, papers: list[Paper]) -> list[ResearchGap]:
        topic_buckets: dict[str, dict] = defaultdict(
            lambda: {"examples": [], "paper_ids": [], "tags": set()}
        )
        topic_totals: Counter[str] = Counter(
            paper.tags[0] if paper.tags else "General AI" for paper in papers
        )

        for paper in papers:
            text = paper.abstract
            if not text:
                continue
            matches = _EXPLICIT_PATTERN.findall(text)
            if not matches:
                continue

            topic = paper.tags[0] if paper.tags else "General AI"
            bucket = topic_buckets[topic]
            bucket["paper_ids"].append(paper.id)
            bucket["tags"].update(paper.tags)
            for m in matches:
                clean = m.strip()
                example = (paper.id, clean)
                if clean and example not in bucket["examples"]:
                    bucket["examples"].append(example)

        gaps = []
        for topic, bucket in topic_buckets.items():
            paper_ids = sorted(set(bucket["paper_ids"]))
            freq = len(paper_ids)
            if freq < 3:          # require at least 3 papers for an explicit gap
                continue
            examples_by_paper: dict[str, str] = {}
            for paper_id, excerpt in bucket["examples"]:
                examples_by_paper.setdefault(paper_id, excerpt)
            examples = list(examples_by_paper.items())[:3]
            title = f"Abstract cues in {topic}"
            description = (
                f"Abstract text has limitation or future work cues in {freq} of "
                f"{topic_totals[topic]} input papers whose first tag is {topic}. "
                f"Check these cues in the original papers. No novelty search was done. "
                f"Examples:\n"
                + "\n".join(f'{paper_id}: "{excerpt}"' for paper_id, excerpt in examples)
            )
            starter_projects = _starter_projects(
                sorted(bucket["tags"], key=lambda tag: (tag.casefold(), tag))
            )
            gaps.append(ResearchGap(
                gap_id=_gap_id("explicit", topic, title),
                topic=topic,
                title=title,
                description=description,
                evidence_paper_ids=paper_ids,
                gap_type="explicit",
                # Kept for compatibility. The basis marker defines the value as coverage.
                confidence=round(freq / topic_totals[topic], 2),
                confidence_basis="evidence_coverage_v1",
                coverage_denominator=topic_totals[topic],
                starter_idea=starter_projects[0],
                frequency=freq,
                suggested_projects=starter_projects,
            ))
        return gaps

    # ── Layer 2 ───────────────────────────────────────────────────────────────

    def _layer2_patterns(self, papers: list[Paper]) -> list[ResearchGap]:
        signal_buckets: dict[str, dict] = defaultdict(
            lambda: {"paper_ids": [], "tags": Counter()}
        )

        for paper in papers:
            text = f"{paper.title} {paper.abstract}"
            for label, pattern in _PATTERN_SIGNALS:
                if pattern.search(text):
                    signal_buckets[label]["paper_ids"].append(paper.id)
                    signal_buckets[label]["tags"].update(set(paper.tags))

        gaps = []
        for label, bucket in signal_buckets.items():
            paper_ids = sorted(set(bucket["paper_ids"]))
            freq = len(paper_ids)
            if freq < 2:
                continue  # require at least 2 papers for a pattern gap
            tags = sorted(bucket["tags"], key=lambda tag: (-bucket["tags"][tag], tag.casefold(), tag))
            topic = tags[0] if tags else "General AI"
            gaps.append(ResearchGap(
                gap_id=_gap_id("pattern", topic, label),
                topic=topic,
                title=label,
                description=(
                    f"The signal '{label}' matched in titles or abstracts for {freq} of "
                    f"{len(papers)} input papers. It is a cue for review, not proof of a "
                    f"limitation or an unstudied area. Check the cues in the original "
                    f"papers. No novelty search was done. At most 10 paper IDs are attached."
                ),
                evidence_paper_ids=paper_ids[:10],
                gap_type="pattern",
                # Kept for compatibility. The basis marker defines the value as coverage.
                confidence=round(freq / len(papers), 2) if papers else 0.0,
                confidence_basis="evidence_coverage_v1",
                coverage_denominator=len(papers),
                starter_idea=_starter_projects(tags)[0] if tags else _STARTER_TEMPLATES["_default"][0],
                frequency=freq,
                suggested_projects=_starter_projects(tags),
            ))
        return sorted(gaps, key=lambda g: -g.frequency)

    # ── Layer 3 ───────────────────────────────────────────────────────────────

    def _layer3_starters(self, papers: list[Paper]) -> list[ResearchGap]:
        """Suggest projects based on frequent topic tags."""
        tag_count: dict[str, list[str]] = defaultdict(list)
        for paper in papers:
            for tag in dict.fromkeys(paper.tags):
                tag_count[tag].append(paper.id)

        gaps = []
        for tag, paper_ids in sorted(
            tag_count.items(), key=lambda x: (-len(x[1]), x[0].casefold(), x[0])
        ):
            resolved = _STARTER_ALIASES.get(tag.casefold(), tag)
            if resolved not in _STARTER_TEMPLATES:
                continue
            ideas = _STARTER_TEMPLATES[resolved]
            for i, idea in enumerate(ideas[:2]):
                gaps.append(ResearchGap(
                    gap_id=_gap_id("starter", tag, f"Starter idea: {idea}"),
                    topic=tag,
                    title=f"Starter idea: {idea}",
                    description=(
                        f"Suggested project for {tag}, which appears in {len(set(paper_ids))} "
                        f"tracked papers. The first five paper IDs are attached as examples. "
                        f"This is a generated suggestion, not a finding from the papers. "
                        f"No novelty search was done."
                    ),
                    evidence_paper_ids=sorted(set(paper_ids))[:5],
                    gap_type="starter",
                    # Kept for compatibility. The basis marker defines the value as coverage.
                    confidence=round(len(set(paper_ids)) / len(papers), 2) if papers else 0.0,
                    confidence_basis="evidence_coverage_v1",
                    coverage_denominator=len(papers),
                    starter_idea=idea,
                    frequency=len(set(paper_ids)),
                    suggested_projects=ideas,
                ))
        return gaps
