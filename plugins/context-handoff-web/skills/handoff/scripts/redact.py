"""Secret redaction applied to every HANDOFF.md before it is written.

Conservative pattern list: false positives only cost a "[REDACTED]" marker,
false negatives could leak a credential into a file that may get committed.
"""

import re

PATTERNS = [
    ("private-key", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe-key", re.compile(r"\b[rs]k_(?:live|test)_[0-9A-Za-z]{16,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("url-credentials", re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)")),
    ("bearer-token", re.compile(r"(?i)(?<=bearer )[A-Za-z0-9_\-.=]{16,}")),
]

# key = value assignments whose key name suggests a secret. The key is kept,
# the value is replaced.
ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|"
    r"private[_-]?key|client[_-]?secret|credentials?)[A-Z0-9_.-]*)(\s*[:=]\s*)(['\"]?)([^\s'\"`]{6,})(\3)"
)

_PLACEHOLDER = re.compile(r"^(\$\{?[A-Z_]+\}?|<[^>]+>|\*+|x{4,}|\.\.\.|REDACTED.*|changeme|example|your[_-].*)$", re.I)


def redact(text: str):
    """Return (redacted_text, {kind: count})."""
    found = {}

    for kind, rx in PATTERNS:
        def _sub(m, kind=kind):
            found[kind] = found.get(kind, 0) + 1
            return f"[REDACTED:{kind}]"
        text = rx.sub(_sub, text)

    def _assign(m):
        value = m.group(4)
        if _PLACEHOLDER.match(value) or value.startswith("[REDACTED"):
            return m.group(0)
        found["secret-assignment"] = found.get("secret-assignment", 0) + 1
        return f"{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED]{m.group(5)}"

    text = ASSIGNMENT.sub(_assign, text)
    return text, found
