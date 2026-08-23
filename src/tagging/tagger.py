"""
Paper tagger: assigns topic tags and detects paper_type from text.
Topics are loaded from config/topics.yaml when available; the built-in
keyword table is used as fallback so the module works without PyYAML.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.normalization.schema import Paper


# ── Config ────────────────────────────────────────────────────────────────────

def _load_topics() -> dict[str, Any]:
    cfg_path = Path(__file__).parent.parent.parent / "config" / "topics.yaml"
    try:
        import yaml  # type: ignore
        with open(cfg_path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        pass
    return {}


# ── Built-in tag rules (pattern → human-readable topic) ──────────────────────
# Ordered from most specific to most general. Each paper can match multiple.
# Avoid abbreviations — use full names throughout.

_BUILTIN_RULES: list[tuple[str, str]] = [
    # ── Large Language Models ──────────────────────────────────────────────────
    (r"large language model|llm\b|gpt.?\d|chatgpt|chat model|instruction.tun|instruction follow",
     "LLMs"),
    (r"reasoning|chain.of.thought|cot\b|step.by.step reasoning|logical reasoning|math reasoning",
     "Reasoning"),
    (r"in.context learning|few.shot|zero.shot prompting|prompt engineering|prompt tuning",
     "Prompting"),
    (r"hallucination|factuality|grounding|faithfulness|factual consistency",
     "Hallucination"),
    (r"long.context|extended context|context window|long document|context length",
     "Long Context"),
    (r"mixture of experts|moe\b|sparse model|sparse activation",
     "MoE"),
    (r"state space model|mamba\b|ssm\b|linear recurrence|selective state",
     "SSMs"),

    # ── Fine-tuning & Alignment ────────────────────────────────────────────────
    (r"reinforcement learning from human feedback|rlhf\b|rlaif\b|reward model|preference learning|"
     r"dpo\b|grpo\b|ppo\b.*align|direct preference|group relative policy|ai feedback",
     "RLHF"),
    (r"fine.tun|lora\b|peft\b|adapter\b.*train|parameter.efficient",
     "Fine-Tuning"),
    (r"ai safety|alignment|red teaming|constitutional ai|value alignment|jailbreak",
     "AI Safety"),

    # ── Agents & Tool Use ─────────────────────────────────────────────────────
    (r"autonomous agent|ai agent|agent framework|tool use|function calling|react\b.*agent|agentic",
     "AI Agents"),
    (r"retrieval.augmented generation|retrieval augmented|rag\b|passage retrieval",
     "RAG"),

    # ── Multimodal ────────────────────────────────────────────────────────────
    (r"vision.language model|visual language|vqa\b|clip\b|llava\b|visual question|image.text",
     "VLMs"),
    (r"multimodal|cross.modal|audio.visual|video.language|multi.modal",
     "Multimodal"),
    (r"text.to.image|image generation|image synthesis|stable diffusion|dall.e|imagen\b",
     "Text-to-Image"),
    (r"video generation|video understanding|video captioning|video question|temporal visual",
     "Video AI"),

    # ── Computer Vision ───────────────────────────────────────────────────────
    (r"object detection|image classification|semantic segmentation|instance segmentation",
     "Object Detection"),
    (r"3d (understanding|reconstruction|generation|point cloud|scene)|nerf\b|gaussian splatting",
     "3D Vision"),
    (r"diffusion model|denoising diffusion|score.based generative|ddpm\b|latent diffusion",
     "Diffusion"),

    # ── NLP Core Tasks ────────────────────────────────────────────────────────
    (r"machine translation|neural machine translation|nmt\b|low.resource translation",
     "Translation"),
    (r"question answering|reading comprehension|open.domain qa|closed.book qa",
     "QA"),
    (r"summarization|abstractive summarization|extractive summarization|document summarization",
     "Summarization"),
    (r"information extraction|named entity recognition|ner\b|relation extraction|event extraction",
     "Info Extraction"),
    (r"sentiment analysis|opinion mining|stance detection|aspect.based sentiment",
     "Sentiment Analysis"),
    (r"text classification|document classification|intent detection|topic classification",
     "Classification"),
    (r"dialogue|conversation|chatbot|open.domain dialogue|task.oriented dialogue",
     "Dialogue"),
    (r"text generation|natural language generation|nlg\b|story generation|data.to.text",
     "NLG"),
    (r"information retrieval|document ranking|search engine|bm25\b|neural ir",
     "IR"),

    # ── Architectures ─────────────────────────────────────────────────────────
    (r"transformer|self[- ]attention|multi[- ]head attention|attention mechanism",
     "Transformers"),
    (r"graph neural network|graph convolution|gnn\b|gcn\b|gat\b|message passing",
     "GNNs"),

    # ── Training & Efficiency ─────────────────────────────────────────────────
    (r"knowledge distillation|model compression|pruning|quantization|quantised",
     "Model Compression"),
    (r"federated learning|privacy.preserving|differential privacy|secure aggregation",
     "Federated Learning"),
    (r"continual learning|catastrophic forgetting|lifelong learning|incremental learning",
     "Continual Learning"),
    (r"contrastive learning|self.supervised|representation learning|pretraining|pre.training",
     "Self-Supervised"),
    (r"reinforcement learning|reward shaping|policy gradient|q.learning|dqn\b|actor.critic",
     "RL"),

    # ── Speech & Audio ────────────────────────────────────────────────────────
    (r"speech recognition|automatic speech|asr\b|whisper\b|speech transcription",
     "ASR"),
    (r"text.to.speech|speech synthesis|tts\b|voice cloning|neural speech",
     "TTS"),

    # ── Code & Software ───────────────────────────────────────────────────────
    (r"code generation|program synthesis|code completion|codex\b|copilot|software engineer.*agent",
     "Code Generation"),

    # ── Domain Applications ───────────────────────────────────────────────────
    (r"biomedical|clinical|medical nlp|electronic health|drug discovery|genomic|protein",
     "Biomedical AI"),
    (r"legal (nlp|ai|text|document)|contract analysis|legal reasoning",
     "Legal AI"),
    (r"robotic|embodied (ai|agent)|manipulation|navigation.*robot|sim.to.real",
     "Robotics"),
    (r"table (understanding|qa|parsing)|structured (data|prediction)|tabular",
     "Structured Data"),
    (r"document (understanding|layout|parsing)|ocr\b|visually rich document",
     "Document AI"),
    (r"knowledge graph|ontology|knowledge base|entity link|wikidata\b|knowledge representation",
     "Knowledge Graphs"),

    # ── Evaluation & Robustness ───────────────────────────────────────────────
    (r"adversarial (attack|example|robustness|training)|robust(ness)? to",
     "Adversarial"),
    (r"bias|fairness|gender bias|racial bias|toxic|hate speech|social bias",
     "Fairness & Ethics"),
    (r"interpretab|explainab|attention visuali|saliency|feature importance",
     "Interpretability"),
    (r"benchmark|evaluation framework|leaderboard|human evaluation|automatic evaluation",
     "Evaluation"),

    # ── Embeddings ────────────────────────────────────────────────────────────
    (r"word embedding|sentence embedding|text embedding|semantic similarity|dense vector",
     "Embeddings"),
]

# ── Supersedes: if the key tag is present, remove the value tags ──────────────
# Prevents redundant co-tagging (e.g. VLMs + Multimodal, RAG + IR, RLHF + RL)
_SUPERSEDES: dict[str, list[str]] = {
    "VLMs":       ["Multimodal"],
    "RAG":        ["IR"],
    "RLHF":       ["RL"],
    "LLMs":       ["NLG", "Transformers"],
    "Text-to-Image": ["Diffusion"],
    "Video AI":   ["Multimodal"],
    "Code Generation": ["LLMs"],
}

_COMPILED_TAGS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p, re.IGNORECASE), tag) for p, tag in _BUILTIN_RULES
]


# ── Paper-type rules ──────────────────────────────────────────────────────────

_TYPE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsurvey\b|\boverview\b|\bcomprehensive review\b",      re.IGNORECASE), "survey"),
    (re.compile(r"\bbenchmark\b|\bleaderboard\b|\bcomparative study\b",   re.IGNORECASE), "benchmark"),
    (re.compile(r"\bdataset\b|\bcorpus\b|\bannotation\b|\bcollection\b",  re.IGNORECASE), "dataset"),
    (re.compile(r"\bsystems?\b.*\bdesign\b|\bscalable\b|\binfrastructure\b|\bdeployment\b",
                re.IGNORECASE), "systems"),
    (re.compile(r"\btheorem\b|\bproof\b|\blemma\b|\bconvergence\b",       re.IGNORECASE), "theory"),
    (re.compile(r"\btutorial\b|\bprimer\b|\bintroduction to\b|\bgetting started\b",
                re.IGNORECASE), "tutorial"),
    (re.compile(r"\bposition paper\b|\bwe argue\b|\bwe call for\b",       re.IGNORECASE), "position"),
    (re.compile(r"\bnegative result\b|\bfailed\b|\bdoes not\b.*improve",  re.IGNORECASE), "negative_result"),
    (re.compile(r"\breplication\b|\breproduc\b",                          re.IGNORECASE), "replication"),
    (re.compile(r"\bwe propose\b|\bwe introduce\b|\bnovel method\b|\bnew (model|approach|architecture)\b",
                re.IGNORECASE), "methods"),
    (re.compile(r"\bwe (conduct|run|perform) experiment|\bempirical (study|analysis|evaluation)\b",
                re.IGNORECASE), "empirical"),
]


class PaperTagger:
    """
    Enrich paper.tags from title+abstract keywords.
    Detect paper.paper_type from structural language cues.
    """

    def tag(self, paper: Paper) -> Paper:
        haystack = f"{paper.title} {paper.abstract}"
        existing_order = list(dict.fromkeys(paper.tags))
        existing = set(existing_order)

        for pattern, tag_name in _COMPILED_TAGS:
            if tag_name not in existing and pattern.search(haystack):
                existing.add(tag_name)

        # Remove tags superseded by more specific ones
        for specific, redundant in _SUPERSEDES.items():
            if specific in existing:
                existing -= set(redundant)

        # Cap at 5 tags: built-ins in rule priority, then existing custom tags.
        builtin_names = {tag for _, tag in _BUILTIN_RULES}
        ordered = [tag for _, tag in _BUILTIN_RULES if tag in existing]
        custom = [
            tag
            for tag in existing_order
            if tag in existing and tag not in builtin_names
        ]
        paper.tags = (ordered + custom)[:5]

        if not paper.paper_type:
            paper.paper_type = self._detect_type(haystack)

        return paper

    @staticmethod
    def _detect_type(text: str) -> str:
        for pattern, ptype in _TYPE_RULES:
            if pattern.search(text):
                return ptype
        return "methods"  # sensible default
