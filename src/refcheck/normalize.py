from __future__ import annotations

import re
import unicodedata


_LATEX_ACCENT = re.compile(r"\\[`'\"^~=.uvHckbdtr]\s*\{?([A-Za-z])\}?")
_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+\*?(?:\s*\{([^{}]*)\})?")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TITLE_STOP_WORDS = {
    "about",
    "after",
    "around",
    "from",
    "into",
    "of",
    "on",
    "the",
    "to",
    "using",
    "with",
}


def latex_to_text(value: str) -> str:
    """Remove common LaTeX markup while retaining its text."""

    text = value.replace(r"\&", "&").replace("~", " ")
    text = _LATEX_ACCENT.sub(r"\1", text)
    for command, replacement in {
        r"\ae": "ae",
        r"\AE": "AE",
        r"\o": "o",
        r"\O": "O",
        r"\ss": "ss",
        r"\l": "l",
        r"\L": "L",
    }.items():
        text = text.replace(command, replacement)
    while True:
        updated = _LATEX_COMMAND.sub(lambda match: match.group(1) or " ", text)
        if updated == text:
            break
        text = updated
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = latex_to_text(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return _NON_ALNUM.sub("", text.lower())


def normalize_author(value: str | None) -> tuple[str, str]:
    if not value:
        return "", ""
    text = latex_to_text(value)
    text = re.sub(r"\([^)]*\)", "", text).strip()
    if "," in text:
        surname, given = text.split(",", 1)
    else:
        parts = text.split()
        surname = parts[-1] if parts else ""
        given = " ".join(parts[:-1])
    surname_key = normalize_text(surname)
    given_ascii = unicodedata.normalize("NFKD", given)
    given_ascii = "".join(
        char for char in given_ascii if not unicodedata.combining(char)
    )
    tokens = re.findall(r"[A-Za-z]+", given_ascii)
    initials = "".join(token[0].lower() for token in tokens if token)
    return surname_key, initials


def authors_equivalent(left: str | None, right: str | None) -> bool:
    left_surname, left_initials = normalize_author(left)
    right_surname, right_initials = normalize_author(right)
    if not left_surname or left_surname != right_surname:
        return False
    if not left_initials or not right_initials:
        return True
    return left_initials == right_initials


def normalize_journal(value: str | None) -> str:
    if not value:
        return ""
    raw = value.strip().lower().lstrip("\\")
    compact = normalize_text(raw)
    aliases = {
        "apj": "apj",
        "apjl": "apj",
        "apjlett": "apj",
        "apjletter": "apj",
        "apjletters": "apj",
        "astrophysicaljournal": "apj",
        "theastrophysicaljournal": "apj",
        "astrophysicaljournalletters": "apj",
        "theastrophysicaljournalletters": "apj",
        "mnras": "mnras",
        "monthlynoticesoftheroyalastronomicalsociety": "mnras",
        "aanda": "aanda",
        "aa": "aanda",
        "astronomyandastrophysics": "aanda",
        "aj": "aj",
        "astronomicaljournal": "aj",
        "theastronomicaljournal": "aj",
    }
    return aliases.get(compact, compact)


def journal_bibstem(value: str | None) -> str | None:
    if not value:
        return None
    compact = normalize_text(value.strip().lower().lstrip("\\"))
    if compact in {
        "apjl",
        "apjlett",
        "apjletter",
        "apjletters",
        "astrophysicaljournalletters",
        "theastrophysicaljournalletters",
    }:
        return "ApJL"
    normalized = normalize_journal(value)
    return {
        "apj": "ApJ",
        "mnras": "MNRAS",
        "aanda": "A&A",
        "aj": "AJ",
    }.get(normalized)


def normalize_page(value: str | None) -> str:
    if not value:
        return ""
    text = latex_to_text(value).strip()
    text = re.split(r"-{1,2}|\N{EN DASH}", text, maxsplit=1)[0]
    text = re.sub(r"^[Ll](?=\d)", "", text)
    return normalize_text(text).lstrip("0") or "0"


def normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip().lower()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", text)
    return text.rstrip(".,; ")


def normalize_arxiv(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip()
    text = re.sub(r"^(?:https?://arxiv\.org/(?:abs|pdf)/|arxiv\s*:\s*)", "", text, flags=re.I)
    text = re.sub(r"v\d+$", "", text, flags=re.I)
    return text.rstrip("/.,; ").lower()


def title_keywords(value: str | None, limit: int = 8) -> list[str]:
    if not value:
        return []
    text = latex_to_text(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    selected: list[str] = []
    for word in words:
        if len(word) < 4 or word in _TITLE_STOP_WORDS or word in selected:
            continue
        selected.append(word)
        if len(selected) == limit:
            break
    return selected


def title_similarity(left: str | None, right: str | None) -> float:
    left_words = set(title_keywords(left, limit=50))
    right_words = set(title_keywords(right, limit=50))
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / len(left_words | right_words)
