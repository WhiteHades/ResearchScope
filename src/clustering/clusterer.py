"""
Topic clusterer: groups papers by tag into Topic objects with trend scores,
starter/frontier packs, and gap summaries.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from src.normalization.schema import Paper, ResearchGap, Topic

_CURRENT_YEAR = datetime.now(timezone.utc).year

# ── Static topic metadata ─────────────────────────────────────────────────────

_TOPIC_DIFFICULTY: dict[str, str] = {
    # ── L1: Beginner — broad / introductory topics ────────────────────────────
    "Machine Learning": "L1", "Artificial Intelligence": "L1",
    "NLP": "L1", "Natural Language Generation": "L1",
    "Question Answering": "L1", "QA": "L1",
    "Text Summarization": "L1", "Summarization": "L1",
    "Machine Translation": "L1", "Translation": "L1",
    "Sentiment & Opinion Analysis": "L1", "Sentiment Analysis": "L1",
    "Text Classification": "L1",
    "Prompting & In-Context Learning": "L1", "Prompting": "L1",
    "Benchmarking & Evaluation": "L1",
    "Information Extraction": "L1", "IE": "L1",

    # ── L2: Intermediate — requires solid ML foundations ─────────────────────
    "Large Language Models": "L2", "LLMs": "L2",
    "Transformer Architectures": "L2", "Transformers": "L2",
    "Deep Learning": "L2", "Neural Networks": "L2",
    "Computer Vision": "L2",
    "Multimodal Learning": "L2", "Multimodal": "L2",
    "Vision-Language Models": "L2",
    "Retrieval-Augmented Generation": "L2", "RAG": "L2",
    "Code Generation & Synthesis": "L2", "Code Generation": "L2",
    "Fine-Tuning & PEFT": "L2",
    "Model Compression & Efficiency": "L2", "Model Compression": "L2",
    "AI Safety & Alignment": "L2",
    "AI Agents & Tool Use": "L2", "AI Agents": "L2",
    "Reasoning & Chain-of-Thought": "L2",
    "Factuality & Hallucination": "L2",
    "Interpretability & Explainability": "L2",
    "Bias, Fairness & Ethics": "L2",
    "Dialogue Systems": "L2",
    "Speech Recognition": "L2", "Speech Synthesis": "L2", "Speech": "L2",
    "Robotics": "L2", "Robotics & Embodied AI": "L2",
    "Information Retrieval": "L2",
    "Text-to-Image Generation": "L2", "Image Generation": "L2",
    "Video Understanding & Generation": "L2",
    "Object Detection & Segmentation": "L2",
    "Self-Supervised & Contrastive Learning": "L2",
    "Knowledge Graphs & Representation": "L2",
    "Long-Context Modeling": "L2",
    "Document Understanding": "L2",
    "Text Embeddings & Semantic Similarity": "L2",
    "Human-Computer Interaction": "L2",
    "Adversarial Robustness": "L2",
    "Biomedical & Clinical AI": "L2",
    "3D Vision & Scene Understanding": "L2",
    "Structured Data & Tables": "L2",
    "Legal AI": "L2",
    "Software Engineering": "L2",

    # ── L3: Advanced — requires strong math/systems background ───────────────
    "Diffusion Models": "L3",
    "Reinforcement Learning": "L3", "RL": "L3",
    "RLHF & Preference Alignment": "L3",   # DPO, GRPO, RLAIF, PPO-based alignment
    "Graph Neural Networks": "L3", "GNN": "L3",
    "Mixture of Experts": "L3",
    "State Space Models": "L3",             # Mamba, SSM, S4
    "Continual Learning": "L3",
    "Federated & Privacy-Preserving Learning": "L3", "Federated Learning": "L3",
    "Multi-Agent Systems": "L3",
    "Optimization": "L3",
    "Cryptography & Security": "L3",
    "Databases": "L3",

    # ── L4: Frontier — cutting-edge, active research frontier ────────────────
    # (new tags from future pipeline runs will land here as they emerge)
}

_LEVEL_TO_LABEL: dict[str, str] = {
    "L1": "beginner", "L2": "intermediate", "L3": "advanced", "L4": "frontier"
}

_PREREQUISITES: dict[str, list[str]] = {
    "Transformer Architectures":          ["Deep Learning"],
    "Large Language Models":              ["Transformer Architectures"],
    "Diffusion Models":                   ["Deep Learning", "Text-to-Image Generation"],
    "Reinforcement Learning":             ["Machine Learning"],
    "Graph Neural Networks":              ["Deep Learning", "Machine Learning"],
    "Retrieval-Augmented Generation":     ["Large Language Models", "Information Retrieval"],
    "Federated & Privacy-Preserving Learning": ["Machine Learning"],
    "Continual Learning":                 ["Machine Learning", "Deep Learning"],
    "AI Safety & Alignment":              ["Large Language Models", "Reinforcement Learning"],
    "AI Agents & Tool Use":               ["Large Language Models", "Reinforcement Learning"],
    "Multimodal Learning":                ["Transformer Architectures", "Computer Vision"],
    "Code Generation & Synthesis":        ["Large Language Models"],
}

_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "LLMs": ["large language model", "llm", "gpt", "instruction tuning"],
    "Transformers": ["transformer", "self-attention", "bert", "attention mechanism"],
    "Diffusion Models": ["diffusion", "score-based", "denoising", "ddpm"],
    "RL": ["reinforcement learning", "policy gradient", "reward", "rlhf"],
    "RAG": ["retrieval-augmented", "dense retrieval", "rag"],
    "Multimodal": ["multimodal", "vision-language", "clip", "vqa"],
    "Computer Vision": ["image classification", "object detection", "vision"],
    "NLP": ["natural language processing", "text", "language"],
}

# ── Trend keywords: topics that signal cutting-edge / trending work ───────────
_TRENDING_TOPICS = {
    "Large Language Models", "Diffusion Models", "Retrieval-Augmented Generation",
    "Multimodal Learning", "AI Safety & Alignment", "AI Agents & Tool Use",
    "Code Generation & Synthesis",
}


def _slug(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")


class TopicClusterer:
    """Group papers by tag into enriched Topic objects."""

    def cluster(
        self, papers: list[Paper], gaps: list[ResearchGap] | None = None
    ) -> list[Topic]:
        tag_to_papers: dict[str, list[Paper]] = {}
        for paper in papers:
            for tag in paper.tags:
                tag_to_papers.setdefault(tag, []).append(paper)

        topics: list[Topic] = []
        all_tags = list(tag_to_papers.keys())

        for tag, tag_papers in tag_to_papers.items():
            level = _TOPIC_DIFFICULTY.get(tag, "L2")
            diff_label = _LEVEL_TO_LABEL.get(level, "intermediate")

            # related topics by paper-count proximity
            related = sorted(
                [t for t in all_tags if t != tag],
                key=lambda t: -len(tag_to_papers[t])
            )[:5]

            # starter pack: L1/L2 papers sorted by read_first_score
            starter = sorted(
                [p for p in tag_papers if p.difficulty_level in ("L1", "L2")],
                key=lambda p: -p.read_first_score,
            )[:5]

            # frontier pack: L3/L4 papers sorted by paper_score
            frontier = sorted(
                [p for p in tag_papers if p.difficulty_level in ("L3", "L4")],
                key=lambda p: -p.paper_score,
            )[:5]

            trend_score = self._trend_score(tag, tag_papers)
            gap_summary = self._gap_summary(tag, tag_papers, gaps)

            topics.append(Topic(
                id=_slug(tag),
                name=tag,
                keywords=_TOPIC_KEYWORDS.get(tag, [tag.lower()]),
                paper_ids=[p.id for p in tag_papers],
                trend_score=trend_score,
                gap_summary=gap_summary,
                starter_pack_ids=[p.id for p in starter],
                frontier_pack_ids=[p.id for p in frontier],
                difficulty=diff_label,
                prerequisites=_PREREQUISITES.get(tag, []),
                related_topics=related,
            ))

        topics.sort(key=lambda t: (-t.trend_score, -len(t.paper_ids)))
        return topics

    @staticmethod
    def _trend_score(tag: str, papers: list[Paper]) -> float:
        recent = sum(1 for p in papers if _CURRENT_YEAR - p.year <= 2)
        total = len(papers) or 1
        recency_ratio = recent / total
        base = 10.0 if tag in _TRENDING_TOPICS else 5.0
        return round(min(base * recency_ratio + len(papers) * 0.01, 10.0), 2)

    @staticmethod
    def _gap_summary(
        tag: str, papers: list[Paper], gaps: list[ResearchGap] | None = None
    ) -> str:
        if gaps is None:
            limitation_count = sum(1 for p in papers if p.limitations)
            future_count = sum(1 for p in papers if p.future_work)
            if limitation_count == 0 and future_count == 0:
                return f"No limitation or future work cues were found for {tag}. No novelty search was done."
            return (
                f"{limitation_count} papers in {tag} have stored limitation cues and "
                f"{future_count} have stored future work cues. Check these cues in the "
                f"original papers. No novelty search was done."
            )

        explicit_ids = {
            paper_id
            for gap in gaps
            if gap.topic == tag and gap.gap_type == "explicit"
            for paper_id in gap.evidence_paper_ids
        }
        explicit_ids.update(
            paper.id for paper in papers if paper.limitations or paper.future_work
        )
        pattern_count = sum(
            1 for gap in gaps if gap.topic == tag and gap.gap_type == "pattern"
        )
        if not explicit_ids and not pattern_count:
            return f"No limitation or future work cues were found for {tag}. No novelty search was done."
        if not pattern_count:
            return (
                f"{len(explicit_ids)} papers have limitation or future work cues for {tag}. "
                f"Check these cues in the original papers. No novelty search was done."
            )
        return (
            f"{len(explicit_ids)} papers have limitation or future work cues. "
            "Recurring cues also need review in the original papers. "
            "No novelty search was done."
        )
