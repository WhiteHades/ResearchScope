"""Estimate a reading level from paper text and type cues.

The estimates are not validated against reader studies or prerequisite checks.
Papers without a clear cue remain Unknown.
"""
from __future__ import annotations

import re

from src.normalization.schema import Paper

# ── Level patterns ────────────────────────────────────────────────────────────

_L1_POSITIVE = re.compile(
    r"\b(survey|overview|tutorial|introduction to|beginners?|primer|"
    r"getting started|hands.on|explainer|we explain|"
    r"accessible|no prior|from scratch)\b",
    re.IGNORECASE,
)

_L4_POSITIVE = re.compile(
    r"\b(theorem|proof|lemma|corollary|convergence guarantee|"
    r"variational inference|bayesian|stochastic|manifold|topology|"
    r"eigenvalue|information.theoretic|pac.learning|regret bound|"
    r"neural architecture search|nas\b|causal inference|"
    r"adversarial robustness|certified defense)\b",
    re.IGNORECASE,
)

_L3_POSITIVE = re.compile(
    r"\b(novel architecture|architecture design|custom (loss|objective)|"
    r"attention variant|gradient descent|backpropagation|"
    r"adversarial training|generative adversarial|"
    r"variational autoencoder|vae\b|latent space|"
    r"pretraining|self.supervised|contrastive|"
    r"hyperparameter|ablation study|cross.entropy|"
    r"multi.task|continual|catastrophic)\b",
    re.IGNORECASE,
)

class DifficultyAssessor:
    """Estimate paper difficulty from text and type cues.

    This estimate has not been validated against reader studies.
    """

    def assess(self, paper: Paper) -> Paper:
        text = f"{paper.title} {paper.abstract}"
        level, reason = self._classify(text, paper.paper_type)
        paper.difficulty_level = level
        paper.difficulty_reason = reason
        return paper

    @staticmethod
    def _classify(text: str, paper_type: str) -> tuple[str, str]:
        paper_type = str(paper_type or "").strip().lower()

        # Advanced text cues take priority over survey or tutorial framing.
        match = _L4_POSITIVE.search(text)
        if match:
            return (
                "L4",
                f"Title or abstract contains the cue '{match.group(0)}'. "
                "This is an unvalidated level estimate.",
            )

        match = _L3_POSITIVE.search(text)
        if match:
            return (
                "L3",
                f"Title or abstract contains the cue '{match.group(0)}'. "
                "This is an unvalidated level estimate.",
            )

        match = _L1_POSITIVE.search(text)
        if match:
            return (
                "L1",
                f"Title or abstract contains the cue '{match.group(0)}'. "
                "This is an unvalidated level estimate.",
            )

        if paper_type in ("survey", "tutorial"):
            return "L1", f"Paper type is '{paper_type}'. This is an unvalidated level estimate."

        return (
            "Unknown",
            "The title, abstract, and paper type provide no level cue. "
            "A level cannot be estimated.",
        )
