"""Offline rule-based triage and drafting.

This is NOT a language model. It is the free baseline that lets the whole workflow run
with no account, and the fallback when a model call fails or returns invalid output.
"""
import re

from .retrieval import tokenize

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
    fields = extract(text)
    # "How much is a cake?" names a product, not a number wanted.
    if intent != "order" and fields["quantity"] == 1 and not re.search(r"\b(?:1|one)\b", text.lower()):
        fields["quantity"] = None
    return {"intent": intent, "urgency": urgency(text, intent), "confidence": confidence, **fields}


def sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", " ".join(text.split())) if part.strip()]


def best_facts(message: str, chunk, limit: int = 2) -> list[str]:
    """The sentences of one document section that share the most words with the message."""
    wanted = set(tokenize(message))
    parts = sentences(chunk.text)
    scored = sorted(range(len(parts)), key=lambda i: (-len(wanted & set(tokenize(parts[i]))), i))
    keep = [i for i in scored[:limit] if wanted & set(tokenize(parts[i]))] or [0]
    return [parts[i] for i in sorted(keep)]


def order_facts(result: dict, sources: list) -> tuple[list[str], list[str]]:
    """Only the price of what was asked for and the fee for where it is going."""
    facts, cited = [], []
    wanted = [(result.get("product"), r"\bcosts?\b|\bstarts at\b"), (result.get("area"), r"\bdeliver")]
    for term, must in wanted:
        if not term:
            continue
        name = re.compile(PRODUCTS.get(term, rf"\b{re.escape(term)}\b"), re.I)
        for chunk, _ in sources:
            found = [s for s in sentences(chunk.text) if name.search(s) and re.search(must, s, re.I)]
            if found:
                facts += found[:2]
                cited.append(chunk.id)
                break
    return facts, list(dict.fromkeys(cited))


def draft(message: str, result: dict, sources: list) -> dict:
    intent = result["intent"]
    cited: list[str] = []
    if intent == "complaint":
        body = ("I am sorry about this. Please send a photo of the order and the name it was booked under. "
                "A manager will review it and get back to you.")
    elif intent == "cancellation":
        policy = next((c for c, _ in sources if c.id.endswith("#cancellation")), None)
        body = "We have received your cancellation request and a team member will confirm it."
        if policy:
            body += "\n\n" + " ".join(sentences(policy.text))
            cited = [policy.id]
    elif intent == "order":
        facts, cited = order_facts(result, sources)
        what = result.get("product")
        noted = "your order"
        if what:
            noted = f"your order ({what}, quantity {result['quantity']})" if result.get("quantity") else f"your {what} order"
        body = f"Thank you, we have noted {noted}."
        if facts:
            body += "\n\n" + " ".join(facts)
        missing = [label for key, label in (("date", "the date you need it"),
                                            ("area", "whether you want delivery or pickup")) if not result.get(key)]
        if missing:
            body += f"\n\nPlease tell us {' and '.join(missing)}."
        body += "\n\nWe will confirm availability shortly."
    elif intent == "question" and sources:
        chunk = sources[0][0]
        body, cited = " ".join(best_facts(message, chunk)), [chunk.id]
    else:
        body = "Thank you for your message. A team member will reply shortly."
    return {"reply": f"Hello,\n\n{body}\n\nSweet Crumb Bakery", "citations": cited}
