import re

EQUATION_PATTERN = re.compile(r"[=∑∫√±≤≥≠^]|\\frac|\\sum|\\int")
HEADING_PATTERN = re.compile(r"^[A-Z0-9][A-Za-z0-9 ,'\-]{2,80}$")


def looks_like_equation(line: str) -> bool:
    return bool(EQUATION_PATTERN.search(line)) and len(line.strip()) < 200


def looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.endswith((".", ",", ";")):
        return False
    return bool(HEADING_PATTERN.match(stripped)) and len(stripped.split()) <= 12
