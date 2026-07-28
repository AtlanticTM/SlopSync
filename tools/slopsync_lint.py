#!/usr/bin/env python3
"""SlopSync repo lint -- judgment-free mechanical checks.

Every hit is a defect BY DEFINITION: these checks encode only hard rules
(violation classes that have actually bitten this protocol/library). If a
check fires falsely, the fix is an exemption-list edit in this file --
never ignoring the output.

Adapted from SlopDrive-32's tools/canon_lint.py for this repo: the frozen-
artifact pins and the British-spelling scan travel unchanged (in spirit);
checks that depended on SlopDrive-32-only paths (src/, include/, webui/,
the device-channel-map generator) are dropped -- this repo has none of
those trees.

Usage:
    python tools/slopsync_lint.py            # all checks
    python tools/slopsync_lint.py --no-gen   # skip registry codegen --check

Exit codes: 0 clean, 1 findings, 2 could not run.
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- frozen
# Byte-identical or it's a protocol break. Changing these requires an
# explicit ruling and an updated hash here in the SAME commit.
FROZEN_SHA256 = {
    "lib/slopsync/include/slopsync/conformance/mini_catalog.hpp":
        "2a90bf8a5658b4ecb2c96a28d9aa9e39a908926c91e0aebba5844366c3252eb2",
    "spec/vectors/fixtures/mini-catalog.yaml":
        "b2b6a3063e66b56916683c6878ce237085fbcd8ea145c02369f5b96a45c6901c",
}

VENDORED_PREFIXES = (
    "docs-site/docs/assets/javascripts/",  # vendored mermaid bundle
)
BINARY_SUFFIXES = (".bin", ".png", ".jpg", ".webp", ".ico", ".pdf",
                   ".woff", ".woff2", ".idx", ".gz", ".lock")

# ------------------------------------------------------------------ American English
# Stems + suffixes kept explicit so no legitimate US word matches (e.g.
# "analysis", "cancellation", "premise" must NOT hit).
_BRITISH = (
    r"behaviours?|colours?|colouring|flavours?|favourites?|honours?|honoured|honouring|"
    r"neighbours?|neighbouring|centres?|centred|centring|metres?|fibres?|litres?|"
    r"greys?|greyed|greying|artefacts?|whilst|amongst|catalogues?|catalogued|cataloguing|"
    r"dialogues?|licences?|licenced|defences?|offences?|pretences?|"
    r"practise|practises|practised|practising|"
    r"cancelled|cancelling|signalled|signalling|modelled|modelling|"
    r"labelled|labelling|travelled|travelling|levelled|levelling|"
    r"channelled|channelling|totalled|totalling|"
    r"analyse|analyses(?=\s+(?:the|a|an|this|that|each|every|it|them))|analysed|analysing|analysers?|paralysed?|"
    r"(?:initial|serial|deserial|normal|synchron|author|util|final|organ|optim|"
    r"minim|maxim|custom|priorit|summar|recogn|emphas|special|stabil|equal|"
    r"central|visual|material|standard|modular|generalis)is(?:e|es|ed|ing|ation|ations|ers?|able)"
)
BRITISH_RX = re.compile(r"\b(?:%s)\b" % _BRITISH, re.IGNORECASE)

GREP_CHECKS = [
    dict(
        name="slopsync-purity",
        msg="platform header inside hardware-free lib/slopsync (std headers only, DOCTRINE.md's library invariants)",
        rx=re.compile(r'#\s*include\s*[<"](?:Arduino\.h|freertos/|esp_|driver/|soc/|nvs)'),
        include=("lib/slopsync/include/",),
        exempt=(),
    ),
    dict(
        name="this-assign",
        msg="*this = T{...} reset pattern (a known field bug: a large struct's assignment form puts a "
            "full temporary on the caller's stack; use in-place destroy + placement-new instead)",
        rx=re.compile(r"\*\s*this\s*=\s*"),
        include=("lib/slopsync/",),
        exempt=(),
    ),
    dict(
        name="links2004-ghost",
        msg="reference to the deleted links2004/WebSocketsServer stack outside its own "
            "historical-context prose (this repo has no src/include/webui trees left to leak into)",
        rx=re.compile(r"links2004|arduinoWebSockets|\bWebSocketsServer\b|\bWebSocketsClient\b"),
        # The original check scoped to src/, include/, webui/src/, platformio.ini --
        # none of the first three exist in this repo. platformio.ini is the one
        # surviving path where a live reference would actually be a problem;
        # tools/slopsoak.py's own mentions are deliberate historical rationale
        # (why the tool exists), not a leak, so they are exempted by name below
        # rather than by widening scope to catch nothing real.
        include=("platformio.ini",),
        exempt=(),
    ),
    dict(
        name="british-spelling",
        msg="British spelling (American English only)",
        rx=BRITISH_RX,
        include=("",),  # every tracked text file
        exempt=("LICENSE", "LICENSE-SPEC", "NOTICE",
                "tools/slopsync_lint.py"),  # this file quotes the banned words
    ),
]


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    for f in out.splitlines():
        if f.startswith(VENDORED_PREFIXES) or f.endswith(BINARY_SUFFIXES):
            continue
        yield f


def run_grep_checks():
    findings = []
    for rel in tracked_files():
        applicable = [c for c in GREP_CHECKS
                      if any(rel.startswith(p) for p in c["include"])
                      and not any(rel.startswith(e) for e in c["exempt"])]
        if not applicable:
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for c in applicable:
                m = c["rx"].search(line)
                if m:
                    findings.append((c["name"], rel, lineno, m.group(0), c["msg"]))
    return findings


def run_frozen_check():
    findings = []
    for rel, want in FROZEN_SHA256.items():
        p = ROOT / rel
        if not p.exists():
            findings.append(("frozen-missing", rel, 0, "", "frozen artifact is GONE"))
            continue
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != want:
            findings.append(("frozen-changed", rel, 0, got[:16],
                             "frozen artifact modified -- protocol break unless amended"))
    return findings


def run_registry_check():
    gen = ROOT / "tools" / "gen_registry_header.py"
    try:
        r = subprocess.run([sys.executable, str(gen), "--check"], cwd=ROOT,
                           capture_output=True, text=True, timeout=120)
    except Exception as e:  # missing yaml module etc. -- report, don't hide
        return [("registry-check", "tools/gen_registry_header.py", 0, str(e)[:60],
                 "could not run registry --check (run it manually with a python that has PyYAML)")]
    if r.returncode != 0:
        return [("registry-drift", "spec/registry/registry.yaml", 0, "",
                 "generated registry header out of sync -- regenerate, never hand-edit")]
    return []


def main(argv):
    findings = run_grep_checks() + run_frozen_check()
    if "--no-gen" not in argv:
        findings += run_registry_check()

    if not findings:
        print("slopsync_lint: clean (0 findings)")
        return 0

    findings.sort(key=lambda f: (f[0], f[1], f[2]))
    by_check = {}
    for name, rel, lineno, match, msg in findings:
        by_check.setdefault(name, []).append((rel, lineno, match, msg))
    for name, items in by_check.items():
        print("[%s] %d hit(s) -- %s" % (name, len(items), items[0][3]))
        for rel, lineno, match, _ in items[:40]:
            print("   %s:%d  %r" % (rel, lineno, match))
        if len(items) > 40:
            print("   ... and %d more" % (len(items) - 40))
    print("slopsync_lint: %d finding(s)" % len(findings))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
