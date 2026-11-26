"""Small BM25 retriever over markdown files, one chunk per "##" section."""
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

STOP = set(
    "a an and are at be but by can do does for from have how i in is it me my of on or our "
    "please so the to we what when where which will with you your hi hello thanks much".split()
)


def tokenize(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOP:
            continue
        # Light stemming so "deliveries" matches "delivery" and "cakes" matches "cake".
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        if w.startswith("deliver"):
            w = "deliver"
        elif w.startswith("cancel"):
            w = "cancel"
        out.append(w)
    return out


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str


class Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        # The file name and heading in the id are searchable too.
        self.docs = [Counter(tokenize(c.id + " " + c.text)) for c in chunks]
        self.avg_len = sum(sum(d.values()) for d in self.docs) / max(len(self.docs), 1)
        self.df = Counter(term for d in self.docs for term in d)

    @classmethod
    def from_dir(cls, directory: str) -> "Index":
        chunks = []
        for path in sorted(Path(directory).glob("*.md")):
            for section in re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.M)[1:]:
                title, _, body = section.partition("\n")
                slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
                chunks.append(Chunk(f"{path.stem}#{slug}", body.strip()))
        if not chunks:
            raise ValueError(f"No '## ' sections found in {directory}")
        return cls(chunks)

    def search(self, query: str, k: int = 3) -> list[tuple[Chunk, float]]:
        terms, n, results = set(tokenize(query)), len(self.docs), []
        for chunk, doc in zip(self.chunks, self.docs):
            length, score = sum(doc.values()), 0.0
            for t in terms:
                if t not in doc:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                score += idf * doc[t] * 2.2 / (doc[t] + 1.2 * (0.25 + 0.75 * length / self.avg_len))
            if score > 0:
                results.append((chunk, round(score, 3)))
        return sorted(results, key=lambda r: -r[1])[:k]
