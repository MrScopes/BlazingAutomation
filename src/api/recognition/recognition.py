import re
from dataclasses import dataclass
from rapidfuzz import fuzz

FUZZY_THRESHOLD = 75
NEGATIVE_THRESHOLD = 88
TRANSITION_BONUS = 5

def normalize(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))

def similarity(phrase, raw):
    target = normalize(phrase).split()
    words = normalize(raw).split()

    if not target or not words:
        return 0.0

    if len(target) == 1 and len(target[0]) <= 3:
        return 100.0 if target[0] in words else 0.0

    text = " ".join(target)
    best = 0.0

    for size in range(max(1, len(target) - 1), min(len(words), len(target) + 1) + 1):
        for pos in range(len(words) - size + 1):
            candidate = " ".join(words[pos:pos + size])
            score = fuzz.ratio(text, candidate)

            if score > best:
                best = score

            if best == 100:
                return best

    return best

@dataclass(frozen=True)
class Screen:
    name: str
    phrases: tuple = ()
    required: tuple = ()
    negative: tuple = ()
    min_hits: int = 1
    patterns: tuple = ()

@dataclass(frozen=True)
class Match:
    name: str
    score: float

class Recognizer:
    def __init__(self, screens, transitions=None, fuzzy_threshold=FUZZY_THRESHOLD, transition_bonus=TRANSITION_BONUS):
        self.screens = tuple(screens)
        self.transitions = transitions or {}
        self.fuzzy_threshold = fuzzy_threshold
        self.transition_bonus = transition_bonus

    def _score(self, screen, raw):
        required = [similarity(phrase, raw) for phrase in screen.required]

        if any(score < self.fuzzy_threshold for score in required):
            return 0.0

        if screen.patterns and not any(re.search(pattern, raw, re.I) for pattern in screen.patterns):
            return 0.0

        if any(similarity(phrase, raw) >= NEGATIVE_THRESHOLD for phrase in screen.negative):
            return 0.0

        scores = [similarity(phrase, raw) for phrase in screen.phrases]
        matched = [score for score in scores if score >= self.fuzzy_threshold]

        if len(matched) < screen.min_hits:
            return 0.0

        if not matched and not required:
            return 0.0

        primary = max(required) if required else max(matched)
        supporting = len(matched)

        score = primary * 0.85 + min(supporting, 3) * 5

        if required:
            score += 5

        return min(100.0, score)

    def matches(self, raw, previous=None):
        ranked = []

        for screen in self.screens:
            score = self._score(screen, raw)

            if score < self.fuzzy_threshold:
                continue

            if previous and screen.name in self.transitions.get(previous, ()):
                score = min(100.0, score + self.transition_bonus)

            ranked.append(Match(screen.name, round(score, 2)))

        return sorted(ranked, key=lambda match: match.score, reverse=True)

    def match(self, raw, previous=None):
        matches = self.matches(raw, previous)
        return matches[0] if matches else Match("unknown", 0.0)

    def identify(self, raw, previous=None):
        return self.match(raw, previous).name

def extract_quantity(raw, item="ninja pearl", threshold=75):
    text = normalize(raw)
    target = normalize(item)

    if not target:
        return None

    for match in re.finditer(r"\bx\s*(\d+)\b", text):
        prefix = text[max(0, match.start() - 65):match.start()]
        words = prefix.split()

        for count in range(1, min(5, len(words)) + 1):
            candidate = " ".join(words[-count:])

            if fuzz.ratio(candidate, target) >= threshold:
                return int(match.group(1))

    return None
