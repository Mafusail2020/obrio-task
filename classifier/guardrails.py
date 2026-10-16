"""Keyword safety net that runs before (and independently of) the LLM.

If the LLM misses a crisis or a legal threat — or fails entirely — these
patterns still catch the obvious cases. A match on a REDIRECT flag sets
`redirect_to_human`: the LLM still runs to enrich the ticket, but the router
forces a human at P1 whatever the LLM says. An explicit request for a human
also sets `redirect_to_human`, but leaves priority unchanged.

Patterns favour recall over precision: a false alarm costs an agent a minute,
a missed crisis costs much more.
"""

import re

from classifier.schema import GuardrailResult
from classifier.taxonomy import RiskFlag

PATTERNS: dict[RiskFlag, list[str]] = {
    RiskFlag.SELF_HARM_OR_CRISIS: [
        # en
        r"\bkill(ing)? my ?self\b", r"\bsuicid", r"\bend(ing)? my life\b", r"\bwant(ed)? to die\b",
        r"\bself[- ]?harm", r"\bno reason to live\b", r"\bdon'?t want to live\b", r"\bhurt(ing)? myself\b",
        # uk
        r"не хочу жити", r"покінчити з собою", r"суїцид", r"хочу померти", r"накласти на себе руки",
        # ru
        r"не хочу жить", r"покончить с собой", r"суицид", r"хочу умереть",
        # es / de / fr
        r"suicid", r"quiero morir", r"quitarme la vida", r"no quiero vivir",
        r"umbringen", r"nicht mehr leben", r"selbstmord",
        r"me tuer", r"envie de mourir",
    ],
    RiskFlag.LEGAL_OR_CHARGEBACK_THREAT: [
        # en
        r"\bcharge ?back\b", r"\bdispute (the|this|these) (charge|payment|transaction)", r"\blawyer\b",
        r"\battorney\b", r"\bsue\b", r"\blawsuit\b", r"\blegal action\b", r"\bftc\b",
        r"\bconsumer protection\b", r"\bsmall claims\b", r"\breport(ing)? (you|this) to (my|the) bank\b",
        # uk / ru
        r"чарджбек", r"юрист", r"адвокат", r"подам до суду", r"подам в суд", r"захист прав споживачів",
        r"защит[аы] прав потребителей",
        # es / de / fr
        r"abogado", r"demanda", r"denuncia", r"anwalt", r"rückbuchung", r"verbraucherschutz", r"avocat",
    ],
    RiskFlag.SCAM_ACCUSATION: [
        r"\bscam", r"\bfraud", r"\bstealing\b", r"\bthie(f|ves)\b", r"\brip[- ]?off\b",
        r"шахра", r"обман", r"мошенни", r"estafa", r"betrug", r"arnaque",
    ],
}

REDIRECT_FLAGS = (RiskFlag.SELF_HARM_OR_CRISIS, RiskFlag.LEGAL_OR_CHARGEBACK_THREAT)

# Customer explicitly asks for a person. Not a risk flag (priority is unchanged),
# but the ticket must not get an automated answer.
HUMAN_REQUEST_PATTERNS = [
    r"\b(talk|speak|chat) (to|with) (a |an )?(real |live |actual )?(human|person|agent|manager|someone real)\b",
    r"\breal (human|person)\b", r"\blive agent\b", r"\bhuman (agent|being|support)\b", r"\bnot a bot\b",
    r"з (живою )?людиною", r"жив(а|у) людин", r"с (живым )?человеком", r"жив(ой|ого) человек",
    r"hablar con una persona", r"persona real", r"mit einem menschen", r"echte[nm]? (mensch|mitarbeiter)",
]

_COMPILED = {flag: [re.compile(p, re.IGNORECASE) for p in pats] for flag, pats in PATTERNS.items()}
_HUMAN_REQUEST = [re.compile(p, re.IGNORECASE) for p in HUMAN_REQUEST_PATTERNS]


def _hits(patterns: list[re.Pattern], text: str) -> list[str]:
    return list(dict.fromkeys(m.group(0).lower() for p in patterns if (m := p.search(text))))


def check(text: str) -> GuardrailResult:
    flags: list[RiskFlag] = []
    matches: dict[str, list[str]] = {}
    for flag, patterns in _COMPILED.items():
        if hits := _hits(patterns, text):
            flags.append(flag)
            matches[flag.value] = hits

    human_hits = _hits(_HUMAN_REQUEST, text)
    if human_hits:
        matches["human_requested"] = human_hits

    reasons = [f.value for f in flags if f in REDIRECT_FLAGS] + (["human_requested"] if human_hits else [])
    return GuardrailResult(
        flags=flags,
        matches=matches,
        human_requested=bool(human_hits),
        redirect_to_human=bool(reasons),
        reason=f"keyword match: {', '.join(reasons)}" if reasons else None,
    )
