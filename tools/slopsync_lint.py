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
# Stem-based: each family below generates its matchable British forms from
# a stem list plus a CLOSED set of real inflectional suffixes -- never a
# bare wildcard -- so a word that merely shares a prefix with a stem
# (organism, capitalism, modernism, optimism, realism, initialism,
# specialism, apologist, catalyst, analysis, paralysis, catalysis,
# emphasis, sombrero, cancellation) can never match.
# "analyses"/"paralyses"/"catalyses" are the one genuine ambiguity (Greek-
# plural noun, identical in both dialects, vs. the British 3rd-person-
# singular verb spelling) -- matched only when followed by a determiner
# that marks it as a verb-with-object, same heuristic as before.
def _build_british_regex():
    forms = set()

    # -our -> -or (hour/four/your/pour/sour/tour/contour/velour/glamour/
    # devour/flour/paramour/troubadour are real English, never in this set)
    our_stems = (
        "favour", "behaviour", "colour", "honour", "labour", "neighbour",
        "flavour", "armour", "harbour", "humour", "rumour", "saviour",
        "vapour", "endeavour", "rigour", "vigour", "valour", "clamour",
        "odour", "parlour", "splendour", "tumour", "candour", "ardour",
        "fervour", "demeanour",
    )
    our_suffixes = ("", "s", "ed", "ing", "er", "ers", "ite", "ites",
                    "able", "ably", "ful", "fully", "less", "y")
    for stem in our_stems:
        for sfx in our_suffixes:
            forms.add(stem + sfx)
    forms.update(("savour", "savours", "savoured", "savouring",
                  "savoury", "savouries"))

    # -ise/-isation -> -ize/-ization, -yse -> -yze. Built from the verb
    # ROOT (stem minus trailing "e") plus a closed suffix template, so
    # "organism"/"capitalism"/"analysis"/"emphasis"/"catalyst" etc. --
    # which merely share a prefix -- are structurally excluded, not
    # exception-listed.
    ise_stems = (
        "organise", "realise", "recognise", "initialise", "serialise",
        "synchronise", "customise", "minimise", "maximise", "optimise",
        "normalise", "utilise", "categorise", "prioritise", "summarise",
        "authorise", "standardise", "stabilise", "finalise", "generalise",
        "specialise", "visualise", "randomise", "sanitise", "capitalise",
        "centralise", "equalise", "italicise", "memorialise", "modernise",
        "neutralise", "penalise", "personalise", "publicise", "quantise",
        "localise", "tokenise", "emphasise", "apologise", "harmonise",
    )
    for stem in ise_stems:
        root = stem[:-1]  # "organise" -> "organis"
        # NOTE: no bare "root" (empty suffix) form -- for stems like
        # "emphasise" the bare root ("emphasis") IS the real English noun
        # and must never match. The bare verb comes from `stem` itself
        # (below), which still ends in "e".
        for sfx in ("es", "ed", "ing", "er", "ers", "ation", "ations", "able"):
            forms.add(root + sfx)
        forms.add(stem)  # bare verb, e.g. "organise"

    yse_stems = ("analyse", "paralyse", "catalyse")
    for stem in yse_stems:
        root = stem[:-1]  # "analys"
        for sfx in ("", "ed", "ing", "er", "ers"):
            forms.add(root + sfx)
        forms.add(stem)
        # deliberately no "-es" form: "analyses"/"paralyses"/"catalyses"
        # are the ambiguous Greek-plural noun, handled below instead.

    # -re -> -er (mere/acre/genre/mediocre/massacre/ogre/timbre/cadre/
    # sombrero are real English and structurally excluded: bare/plural/
    # past suffixes only, never \w*)
    re_stems = (
        "centre", "metre", "litre", "fibre", "calibre", "theatre",
        "sombre", "spectre", "lustre", "manoeuvre", "sceptre",
        "centimetre", "millimetre", "kilometre",
    )
    for stem in re_stems:
        for sfx in ("", "s", "d"):
            forms.add(stem + sfx)

    # -ogue -> house style -og (this project says "catalog" hundreds of times)
    forms.update((
        "catalogue", "catalogues", "catalogued", "cataloguing", "cataloguer",
        "analogue", "analogues",
        "dialogue", "dialogues", "dialogued", "dialoguing",
        "epilogue", "epilogues",
        "prologue", "prologues",
    ))

    # doubled-L inflections -> single-L (cancellation is correct US, both
    # sides double the L -- excluded by simply never being in this list)
    forms.update((
        "travelled", "travelling", "traveller", "travellers",
        "labelled", "labelling",
        "modelled", "modelling",
        "cancelled", "cancelling",
        "levelled", "levelling",
        "signalled", "signalling",
        "channelled", "channelling",
        "marshalled", "marshalling",
        "totalled", "totalling",
        "equalled", "equalling",
        "fuelled", "fuelling",
        "dialled", "dialling",
        "rivalled", "rivalling",
        "funnelled", "funnelling",
        "tunnelled", "tunnelling",
        "panelled", "panelling",
        "quarrelled", "quarrelling",
        "counselled", "counselling", "counsellor", "counsellors",
        "spiralled", "spiralling",
    ))

    # misc singles (doughnut/glamour: accept both spellings, never listed)
    forms.update((
        "grey", "greys", "greyed", "greying", "greyscale",
        "judgement", "judgements",
        "acknowledgement", "acknowledgements",
        "aluminium",
        "artefact", "artefacts",
        "licence", "licences",
        "defence", "defences",
        "offence", "offences",
        "pretence", "pretences",
        "practise", "practises", "practised", "practising",
        "programme", "programmes",
        "tyre", "tyres",
        "kerb", "kerbs",
        "mould", "moulds", "moulded", "moulding", "mouldy",
        "smoulder", "smoulders", "smouldered", "smouldering",
        "whilst", "amongst", "amidst",
        "learnt", "spelt", "dreamt",
        "storey", "storeys",
        "sceptical", "scepticism",
        "enquire", "enquires", "enquired", "enquiring", "enquiry", "enquiries",
        "fulfil", "fulfils", "fulfilment",
        "skilful", "skilfully",
        "wilful", "wilfully",
        "enrol", "enrols", "enrolment", "enrolments",
        "distil", "distils", "distilment",
        "jewellery",
        "plough", "ploughs", "ploughed", "ploughing",
        "draught", "draughts",
        "behaviourally",
        "speciality", "specialities",
        "cosy", "cosier", "cosiest",
        "snigger", "sniggers", "sniggered", "sniggering",
        "aeroplane", "aeroplanes",
        "cheque", "cheques",
        "gaol", "gaols",
        "moustache", "moustaches",
        "pyjamas",
        "furore",
    ))

    literal_rx = r"\b(?:%s)\b" % "|".join(sorted(forms, key=len, reverse=True))
    # Ambiguous Greek-plural/British-verb collision: only flag when a
    # determiner+object follows, marking it as a verb use ("it analyses
    # the data"), never the bare plural noun ("risk analyses").
    ambiguous_rx = (
        r"\b(?:analyses|paralyses|catalyses)"
        r"(?=\s+(?:the|a|an|this|that|each|every|it|them)\b)"
    )
    return re.compile(literal_rx + "|" + ambiguous_rx, re.IGNORECASE)


BRITISH_RX = _build_british_regex()

# Pre-existing British spellings living in code comments/strings, surfaced
# for the first time by the 2026-07-28 dictionary upgrade (a docs-only
# pass -- rewording code comments was explicitly out of scope for it, see
# the pass's own commit). Tracked by exact line, not silently dropped
# (CANON C-3: a conflict gets flagged, never silently ignored) -- a NEW
# British spelling anywhere else, including new lines in these same files,
# still fails the gate. Remove an entry only by fixing the spelling there.
BRITISH_SPELLING_KNOWN_CODE_HITS = {
    ("clients/js/session.js", 399),
    ("clients/js/session.js", 919),
    ("clients/mfp/SlopSync.cs", 422),
    ("clients/mfp/SlopSync.cs", 433),
    ("clients/mfp/SlopSync.cs", 1843),
    ("lib/slopsync/include/slopsync/client/client_impl.hpp", 393),
    ("lib/slopsync/include/slopsync/client/client_impl.hpp", 548),
    ("lib/slopsync/include/slopsync/hub/hub.hpp", 9),
    ("lib/slopsync/include/slopsync/hub/hub_impl.hpp", 979),
    ("lib/slopsync/include/slopsync/hub/hub_impl.hpp", 2471),
    ("lib/slopsync/include/slopsync/hub/hub_impl.hpp", 2658),
    ("lib/slopsync/include/slopsync/wire/raw/catalog_ready.hpp", 8),
    ("tools/slopsync_probe.py", 2749),
    ("tools/slopsync_probe.py", 2819),
}
# The spec fresh-eyes panel's own finding-title text is a standing
# exception, not deferred work: spec/reviews/spec-panel-2026-07-27.md's own
# preamble promises "the panel text below is untouched" (a verbatim
# assessment record), so this one line is permanent, unlike the code hits
# above which are a to-do.
BRITISH_SPELLING_QUOTE_EXEMPT_HITS = {
    ("spec/reviews/spec-panel-2026-07-27.md", 85),
}

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
                if c["name"] == "british-spelling" and (
                        (rel, lineno) in BRITISH_SPELLING_KNOWN_CODE_HITS
                        or (rel, lineno) in BRITISH_SPELLING_QUOTE_EXEMPT_HITS):
                    continue
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
