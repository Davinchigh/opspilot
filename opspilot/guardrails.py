"""Deterministic safety checks. They run the same way whichever provider wrote the draft.

Pattern checks catch common cases only. The real protection is that nothing is sent
without a person approving it.
"""
import re

INJECTION = [
    r"\b(?:ignore|disregard|forget|override)\b.{0,40}\b(?:instruction|rule|prompt|polic)",
    r"\bsystem prompt\b",
    r"\byou are now\b",
    r"\bact as\b.{0,30}\b(?:admin|manager|developer|system)\b",
    r"\b(?:reveal|print|show|repeat)\b.{0,30}\b(?:prompt|instructions|api key|password)\b",
    r"\b(?:approve|mark)\b.{0,40}\b(?:refund|paid|free)\b",
]
SENSITIVE = (r"\b(?:allerg\w*|anaphyla\w*|intoleran\w*|nut[- ]free|gluten[- ]free|sick|food poisoning|"
             r"hospital|lawyer|sue|police)\b")


def mask_pii(text: str) -> str:
    """Hide emails and phone numbers before text leaves the machine."""
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email]", text)
    return re.sub(r"(?<!\w)\+?\d(?:[ -]?\d){8,14}(?!\w)", "[phone]", text)


def amounts(text: str) -> set[str]:
    """Money and percentage figures mentioned in a piece of text."""
    found = re.findall(
        r"(?:GHS|GH₵|₵)\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(?:cedis|GHS|percent|%)", text, re.I)
    return {(a or b).replace(",", "") for a, b in found}


def check(message: str, result: dict, reply: str, citations: list, sources: list) -> list[str]:
    flags = []
    lower = message.lower()
    if any(re.search(p, lower, re.S) for p in INJECTION):
        flags.append("prompt_injection")
    if re.search(SENSITIVE, lower):
        flags.append("sensitive_topic")
    if result["intent"] == "complaint":
        flags.append("complaint")
    if result["confidence"] < 0.6:
        flags.append("low_confidence")
    known = {c.id for c, _ in sources}
    if any(c not in known for c in citations):
        flags.append("invented_citation")
    allowed = set().union(*(amounts(c.text) for c, _ in sources)) if sources else set()
    if amounts(reply) - allowed:
        flags.append("unsupported_amount")
    if result["intent"] == "question" and not citations:
        flags.append("no_source")
    return flags
