"""Offline rule-based triage and drafting.

This is NOT a language model. It is the free baseline that lets the whole workflow run
with no account, and the fallback when a model call fails or returns invalid output.
"""
import re

PRODUCTS = {
    "cake": r"\bcakes?\b",
    "cupcake": r"\bcup ?cakes?\b",
    "doughnut": r"\bdo(?:ugh)?nuts?\b",
    "sausage roll": r"\bsausage rolls?\b",
    "banana bread": r"\bbanana (?:bread|breads|loaf|loaves)\b",
    "cinnamon roll": r"\bcinnamon rolls?\b",
}
AREAS = ["East Legon", "Madina", "Osu", "Tema"]
DAYS = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tonight|tomorrow"
MONTHS = r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "ten": 10, "twelve": 12}
COUNT = r"(?:a|an|\d+|one|two|three|four|five|six|ten|twelve|some)"

INTENT_PATTERNS = {
    "cancellation": [r"\bcancel", r"\bcall(?:ing)? off\b", r"\bno longer (?:need|want)"],
    "complaint": [r"\b(?:wrong|late|stale|damaged|smashed|broken|melted|disappointed|terrible|awful|bad|"
                  r"unhappy|refund|complain\w*|never (?:arrived|came)|not (?:arrived|delivered|happy|what)|"
                  r"missing|sick|hair|mou?ld\w*)\b"],
    "order": [rf"\b(?:i|we)(?: would|'d)? (?:like|love|want|need) (?:to (?:order|buy|book|get) )?{COUNT}\b",
              r"\b(?:can|could|may) (?:i|we) (?:order|get|book|have)\b",
              rf"\b(?:order|book|reserve) (?:me )?{COUNT}\b",
              r"\bplace an order\b"],
    "question": [r"\?", r"\b(?:how much|price|cost|do you|are you|what|when|where|which|is there|can you)\b"],
}


def classify(text: str) -> tuple[str, float]:
    lower = text.lower()
    scores = {intent: sum(bool(re.search(p, lower)) for p in patterns)
              for intent, patterns in INTENT_PATTERNS.items()}
    # Priority order: a complaint or cancellation matters more than the question mark in it.
    for intent in ("cancellation", "complaint", "order"):
        if scores[intent]:
            return intent, round(min(0.95, 0.7 + 0.1 * scores[intent]), 2)
    if scores["question"]:
        return "question", round(min(0.9, 0.6 + 0.1 * scores["question"]), 2)
    return "other", 0.3


def urgency(text: str, intent: str) -> str:
    if intent == "complaint":
        return "high"
    if re.search(r"\b(?:urgent\w*|asap|immediately|today|tonight|right now|sick|emergency)\b", text.lower()):
        return "high"
    return "normal" if intent in ("order", "cancellation") else "low"


def extract(text: str) -> dict:
    lower = text.lower()
    # Longest name first, so "cupcake" is not read as "cake".
    product = next((name for name, pattern in sorted(PRODUCTS.items(), key=lambda p: -len(p[0]))
                    if re.search(pattern, lower)), None)
    quantity = None
    # A size such as "8 inch" is not a quantity.
    cleaned = re.sub(r"\b\d+[ -]?(?:inch|in|tier)\w*", " ", lower)
    match = re.search(
        r"\b(\d{1,3}|" + "|".join(NUMBER_WORDS) + r")\s+(?:[a-z]+\s+){0,2}?"
        r"(?:cup ?cakes?|cakes?|do(?:ugh)?nuts?|sausage rolls?|banana (?:breads?|loaf|loaves)|"
        r"cinnamon rolls?|box(?:es)?)\b", cleaned)
    if match:
        raw = match.group(1)
        quantity = int(raw) if raw.isdigit() else NUMBER_WORDS[raw]
    date = re.search(
        rf"\b({DAYS}|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\w*|(?:{MONTHS})\w*\s+\d{{1,2}})\b", lower)
    area = next((a for a in AREAS if re.search(rf"\b{a.lower()}\b", lower)), None)
    return {"product": product, "quantity": quantity,
            "date": date.group(1) if date else None, "area": area}


def triage(text: str) -> dict:
    intent, confidence = classify(text)
    return {"intent": intent, "urgency": urgency(text, intent), "confidence": confidence, **extract(text)}


def draft(result: dict, sources: list) -> dict:
    intent = result["intent"]
    cited, facts = [], ""
    if sources:
        chunk = sources[0][0]
        cited, facts = [chunk.id], " ".join(chunk.text.split())
    if intent == "complaint":
        body = ("I am sorry about this. Please send a photo of the order and your order name. "
                "A manager will review it and get back to you.")
        cited = []
    elif intent == "cancellation":
        body = f"We have received your cancellation request. A team member will confirm it. {facts}"
    elif intent == "order":
        wanted = " ".join(str(v) for v in (result.get("quantity"), result.get("product")) if v) or "your order"
        missing = [label for key, label in (("date", "date needed"), ("area", "delivery area or pickup"))
                   if not result.get(key)]
        ask = f" Please confirm the {' and '.join(missing)}." if missing else ""
        body = f"Thank you. We noted your request ({wanted}).{ask} {facts}"
    elif intent == "question" and facts:
        body = facts
    else:
        body = "Thank you for your message. A team member will reply shortly."
        cited = []
    return {"reply": f"Hello, {body.strip()}\nSweet Crumb Bakery", "citations": cited}
