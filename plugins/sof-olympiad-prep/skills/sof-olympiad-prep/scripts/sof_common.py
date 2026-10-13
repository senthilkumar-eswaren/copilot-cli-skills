#!/usr/bin/env python3
"""Shared helpers for the sof-olympiad-prep skill.

Library used by blueprint.py, validate_paper.py, assemble_paper.py,
render_paper.py and score.py.  Also a small CLI:

  python3 sof_common.py paths
  python3 sof_common.py next-no --exam IMO --mode mock [--level 1]
  python3 sof_common.py next-no --exam IEO --mode practice --topics "Tenses"
  python3 sof_common.py list [--exam IMO]
  python3 sof_common.py student-view <paper.json | slug> [--out FILE]
  python3 sof_common.py selfcheck

Data root: $OLYMPIAD_PREP_HOME (default ~/olympiad-prep) holds papers/,
work/, history.json, scores.csv and attempts.jsonl.  Printable PDFs go to
$OLYMPIAD_OUT_DIR (default ~/Downloads).
"""
import argparse
import copy
import csv
import datetime as _dt
import difflib
import hashlib
import html
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
REFERENCES_DIR = SKILL_DIR / "references"
SCRIPTS_DIR = SKILL_DIR / "scripts"

EXAMS = ("IMO", "IEO", "ICSO")
LETTERS = ("A", "B", "C", "D")
ALLOWED_TAGS = ("b", "i", "u", "sup", "sub", "br")
ANY_TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)\b[^<>]*>")
BARE_TAG_RE = re.compile(r"^(?:</?(?:b|i|u|sup|sub)>|<br\s*/?>)$", re.I)
TOKEN_RE = re.compile(r"\[\[(frac|blank)(?::([^\]]*))?\]\]")
FRAC_RE = re.compile(r"^\s*(?:(\d+)\s+)?([^/\s][^/]*?)\s*/\s*([^/]+?)\s*$")


# ----------------------------------------------------------------- basics
def rhalf(x: float) -> int:
    """Round half up (Python's round() is banker's rounding)."""
    return int(math.floor(x + 0.5))


def today() -> str:
    return _dt.date.today().isoformat()


def read_json(path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, obj) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))
    return path


def die(msg: str, code: int = 2):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


# ------------------------------------------------------------------ paths
def prep_home() -> Path:
    home = Path(os.environ.get("OLYMPIAD_PREP_HOME") or (Path.home() / "olympiad-prep")).expanduser()
    for sub in ("papers", "work"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    return home


def papers_dir() -> Path:
    return prep_home() / "papers"


def work_dir(slug: str, create: bool = True) -> Path:
    p = prep_home() / "work" / slug
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def history_path() -> Path:
    return prep_home() / "history.json"


def scores_csv_path() -> Path:
    return prep_home() / "scores.csv"


def attempts_path() -> Path:
    return prep_home() / "attempts.jsonl"


def default_out_dir() -> Path:
    env = os.environ.get("OLYMPIAD_OUT_DIR")
    if env:
        p = Path(env).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    dl = Path.home() / "Downloads"
    if dl.is_dir():
        return dl
    p = prep_home() / "output"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------- data
_CACHE: Dict[str, Any] = {}


def load_class(cls: int = 5) -> dict:
    """Exam patterns + syllabus for a class (cached; do not mutate)."""
    key = "class%d" % int(cls)
    if key not in _CACHE:
        p = DATA_DIR / ("class%d.json" % int(cls))
        if not p.exists():
            raise ValueError("No data for class %s (expected %s). This skill currently supports Class 5." % (cls, p))
        _CACHE[key] = read_json(p)
    return _CACHE[key]


def load_styles() -> Dict[str, dict]:
    """Per-topic question styles: {topic: {figure, figure_styles, text_styles, tips?}}."""
    if "styles" not in _CACHE:
        _CACHE["styles"] = read_json(DATA_DIR / "question_styles.json")["topics"]
    return _CACHE["styles"]


def norm_exam(exam: str) -> str:
    e = (exam or "").strip().upper()
    if e not in EXAMS:
        raise ValueError("Unknown exam %r (use one of %s)" % (exam, ", ".join(EXAMS)))
    return e


def get_exam(exam: str, cls: int = 5) -> dict:
    return load_class(cls)["exams"][norm_exam(exam)]


def get_level(exam: str, level=1, cls: int = 5) -> dict:
    ex = get_exam(exam, cls)
    lv = ex["levels"].get(str(int(level)))
    if not lv:
        raise ValueError("%s has no Level %s (available: %s)" % (norm_exam(exam), level, ", ".join(sorted(ex["levels"]))))
    return lv


def section_ranges(level: dict) -> List[Tuple[int, int, dict]]:
    out, start = [], 1
    for s in level["sections"]:
        end = start + int(s["questions"]) - 1
        out.append((start, end, s))
        start = end + 1
    return out


def expected_section(level: dict, qid: int) -> Optional[dict]:
    for a, b, s in section_ranges(level):
        if a <= qid <= b:
            return s
    return None


def section_by_no(level: dict, no) -> Optional[dict]:
    for s in level["sections"]:
        if s["no"] == no:
            return s
    return None


def uniq(seq) -> list:
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def section_topics(sec: dict) -> List[str]:
    return uniq(list(sec["topics"]["current"]) + list(sec["topics"]["previous"]))


def all_topics(exam: Optional[str] = None, cls: int = 5, level=None) -> List[str]:
    data = load_class(cls)
    exams = [norm_exam(exam)] if exam else list(EXAMS)
    seen: List[str] = []
    for e in exams:
        for lk, lv in data["exams"][e]["levels"].items():
            if level is not None and str(level) != lk:
                continue
            for s in lv["sections"]:
                for t in section_topics(s):
                    if t not in seen:
                        seen.append(t)
    return seen


def current_class_topics(exam: str, cls: int = 5) -> List[str]:
    out: List[str] = []
    for lv in get_exam(exam, cls)["levels"].values():
        for s in lv["sections"]:
            for t in s["topics"]["current"]:
                if t not in out:
                    out.append(t)
    return out


def _norm_topic(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def topic_lookup(name: str, exam: Optional[str] = None, cls: int = 5) -> str:
    """Canonical topic name: exact (case-insensitive) match first, then a
    unique partial match; otherwise ValueError listing the candidates."""
    cands = all_topics(exam, cls)
    q = _norm_topic(name)
    if not q:
        raise ValueError("Empty topic name")
    exact = [t for t in cands if _norm_topic(t) == q]
    if exact:
        return exact[0]
    part = [t for t in cands if q in _norm_topic(t)]
    if len(part) == 1:
        return part[0]
    scope = norm_exam(exam) if exam else "all exams"
    if part:
        raise ValueError("Topic %r is ambiguous for %s; did you mean one of: %s" % (name, scope, "; ".join(part)))
    sugg = difflib.get_close_matches(name, cands, n=5, cutoff=0.4)
    hint = ("Closest: " + "; ".join(sugg)) if sugg else ("Valid topics: " + "; ".join(cands))
    raise ValueError("Unknown topic %r for %s. %s" % (name, scope, hint))


def topic_home_section(exam: str, topic: str, cls: int = 5) -> Tuple[int, int]:
    """(level, section no) where a topic first appears (current list preferred)."""
    ex = get_exam(exam, cls)
    for which in ("current", "previous"):
        for lk in sorted(ex["levels"]):
            for s in ex["levels"][lk]["sections"]:
                if topic in s["topics"][which]:
                    return int(lk), int(s["no"])
    raise ValueError("Topic %r not in %s syllabus" % (topic, exam))


def topic_syllabus_class(exam: str, topic: str, cls: int = 5) -> int:
    """cls if the topic is in any current-class list of the exam, else cls-1."""
    return int(cls) if topic in current_class_topics(exam, cls) else int(cls) - 1


# ----------------------------------------------------------------- markup
def find_bad_tags(text) -> List[str]:
    """Tags other than bare <b> <i> <u> <sup> <sub> <br> (attributes are not allowed)."""
    if not isinstance(text, str):
        return []
    bad = []
    for m in ANY_TAG_RE.finditer(text):
        if not BARE_TAG_RE.match(m.group(0)):
            bad.append(m.group(0)[:40])
    return bad


def unbalanced_tags(text) -> List[str]:
    if not isinstance(text, str):
        return []
    out = []
    for t in ("b", "i", "u", "sup", "sub"):
        o = len(re.findall(r"<%s>" % t, text, flags=re.I))
        c = len(re.findall(r"</%s>" % t, text, flags=re.I))
        if o != c:
            out.append("<%s> opened %d, closed %d" % (t, o, c))
    return out


def _render_token(kind: str, arg: Optional[str]) -> str:
    arg = arg or ""
    if kind == "frac":
        m = FRAC_RE.match(arg)
        if not m:
            return html.escape(arg, quote=False)
        whole, num, den = m.groups()
        frac = ('<span class="frac"><span class="num">%s</span><span class="den">%s</span></span>'
                % (html.escape(num, quote=False), html.escape(den, quote=False)))
        if whole:
            return '<span class="mixed"><span class="whole">%s</span>%s</span>' % (html.escape(whole), frac)
        return frac
    # blank: [[blank]], [[blank:6]] (width in em) or [[blank:(i)]] (label)
    a = arg.strip()
    if not a:
        return '<span class="blank"></span>'
    if re.fullmatch(r"\d+(\.\d+)?", a):
        return '<span class="blank" style="min-width:%sem"></span>' % a
    return '<span class="blank labeled">%s</span>' % html.escape(a, quote=False)


def render_markup(text) -> str:
    """Safe HTML for question text: escapes everything except the allowed bare
    tags, turns newlines into <br> and expands [[frac:..]] / [[blank..]] tokens."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    store: List[str] = []

    def _protect(m):
        store.append(_render_token(m.group(1), m.group(2)))
        return "\x00%d\x00" % (len(store) - 1)

    t = TOKEN_RE.sub(_protect, text)
    t = html.escape(t, quote=False)
    t = re.sub(r"&lt;(/?)(b|i|u|sup|sub)&gt;", lambda m: "<%s%s>" % (m.group(1), m.group(2).lower()), t, flags=re.I)
    t = re.sub(r"&lt;br\s*/?&gt;", "<br>", t, flags=re.I)
    t = t.replace("\r\n", "\n").replace("\n", "<br>")
    t = re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], t)
    return t


def strip_markup(text) -> str:
    if text is None:
        return ""
    t = str(text)

    def _tok(m):
        kind, arg = m.group(1), (m.group(2) or "").strip()
        if kind == "frac":
            return " %s " % arg
        if arg and not re.fullmatch(r"\d+(\.\d+)?", arg):
            return " ____%s " % arg
        return " ____ "

    t = TOKEN_RE.sub(_tok, t)
    t = re.sub(r"<br\s*/?>", " ", t, flags=re.I)
    t = re.sub(r"</?(b|i|u|sup|sub)>", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def option_plain(opt) -> str:
    if isinstance(opt, dict):
        t = strip_markup(opt.get("text", ""))
        if opt.get("svg"):
            t = (t + " [figure]").strip()
        return t
    if isinstance(opt, (list, tuple)):
        return " | ".join(strip_markup(x) for x in opt)
    return strip_markup(opt)


def _norm_cmp(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9\u20b9%]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def question_text_for_compare(q: dict) -> str:
    parts = [strip_markup(q.get("question", ""))]
    for it in q.get("items") or []:
        parts.append(strip_markup(it))
    if q.get("question_after"):
        parts.append(strip_markup(q["question_after"]))
    tb = q.get("table")
    if isinstance(tb, dict):
        parts.extend(strip_markup(h) for h in tb.get("headers", []) or [])
        for row in tb.get("rows", []) or []:
            parts.extend(strip_markup(c) for c in row)
    mt = q.get("match")
    if isinstance(mt, dict):
        parts.extend(strip_markup(x) for x in list(mt.get("left", []) or []) + list(mt.get("right", []) or []))
    opts = q.get("options") or {}
    if isinstance(opts, dict):
        for L in LETTERS:
            if L in opts:
                parts.append(option_plain(opts[L]))
    return _norm_cmp(" ".join(parts))


def question_figures(q: dict) -> List[Tuple[str, str]]:
    """[(where, svg)] for the stem figure and any option figures."""
    out = []
    if q.get("figure"):
        out.append(("figure", q["figure"]))
    opts = q.get("options") or {}
    if isinstance(opts, dict):
        for L in LETTERS:
            o = opts.get(L)
            if isinstance(o, dict) and o.get("svg"):
                out.append(("option " + L, o["svg"]))
    return out


def question_signature(q: dict) -> str:
    h = hashlib.sha1()
    h.update(question_text_for_compare(q).encode("utf-8"))
    for _, svg in question_figures(q):
        h.update(b"|fig|")
        h.update(re.sub(r"\s+", " ", svg).strip().encode("utf-8"))
    return h.hexdigest()


# -------------------------------------------------------------------- svg
def _svg_len(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    m = re.fullmatch(r"\s*([0-9.]+)\s*(px)?\s*", str(v))
    return float(m.group(1)) if m else None


def svg_check(svg: str) -> Tuple[List[str], Optional[float]]:
    """(errors, width_px).  Rejects anything that is not a plain, self-contained SVG."""
    errs: List[str] = []
    if not isinstance(svg, str) or not svg.strip():
        return ["empty SVG"], None
    s = re.sub(r"^\s*<\?xml[^>]*\?>", "", svg.strip())
    if re.search(r"<!(DOCTYPE|ENTITY)", s, flags=re.I):
        errs.append("DOCTYPE/ENTITY not allowed")
    if re.search(r"<\s*(script|foreignObject|iframe|object|embed)\b", s, flags=re.I):
        errs.append("script/foreignObject/embedded content not allowed")
    if re.search(r"\son[a-z]+\s*=", s, flags=re.I):
        errs.append("event-handler (on*) attributes not allowed")
    for m in re.finditer(r"(?:xlink:)?href\s*=\s*['\"]([^'\"]*)['\"]", s, flags=re.I):
        if not m.group(1).startswith("#"):
            errs.append("external href not allowed: %s" % m.group(1)[:40])
    if re.search(r"url\(\s*['\"]?(?!#)", s, flags=re.I):
        errs.append("url(...) must reference an internal #id")
    if re.search(r"@import|javascript:", s, flags=re.I):
        errs.append("@import / javascript: not allowed")
    width = None
    try:
        root = ET.fromstring(s)
    except ET.ParseError as e:
        errs.append("SVG does not parse: %s" % e)
        return errs, None
    if not root.tag.endswith("svg"):
        errs.append("root element is <%s>, expected <svg>" % root.tag)
    w, h = _svg_len(root.get("width")), _svg_len(root.get("height"))
    vb = root.get("viewBox")
    if not vb and (w is None or h is None):
        errs.append("SVG needs a viewBox or numeric width and height")
    if w is not None:
        width = w
    elif vb:
        try:
            width = float(re.split(r"[\s,]+", vb.strip())[2])
        except Exception:
            errs.append("bad viewBox %r" % vb)
    if not root.get("width") or not root.get("height"):
        errs.append("SVG must set width and height in px")
    return errs, width


def svg_for_html(svg: str) -> str:
    return re.sub(r"^\s*<\?xml[^>]*\?>", "", svg.strip())


# ---------------------------------------------------------------- history
def load_history() -> dict:
    p = history_path()
    if p.exists():
        try:
            h = read_json(p)
            if isinstance(h, dict) and isinstance(h.get("papers"), dict):
                return h
        except Exception:
            bak = p.with_name("history.corrupt-%s.json" % _dt.datetime.now().strftime("%Y%m%d%H%M%S"))
            shutil.copy2(str(p), str(bak))
            print("WARNING: history.json unreadable; backed up to %s" % bak, file=sys.stderr)
    return {"version": 1, "papers": {}}


def save_history(h: dict) -> None:
    write_json(history_path(), h)


def record_paper(paper: dict, paper_json_path, files: Dict[str, str]) -> None:
    h = load_history()
    h["papers"][paper["slug"]] = {
        "slug": paper["slug"],
        "exam": paper["exam"],
        "class": paper.get("class", 5),
        "level": paper.get("level", 1),
        "mode": paper.get("mode", "mock"),
        "paper_no": paper.get("paper_no", 1),
        "title": paper_title(paper),
        "created": paper.get("created") or today(),
        "rendered": _dt.datetime.now().isoformat(timespec="seconds"),
        "paper_json": str(paper_json_path),
        "files": files,
        "questions": [
            {"id": q.get("id"), "topic": q.get("topic"), "sig": question_signature(q),
             "text": question_text_for_compare(q)[:600], "has_figure": bool(question_figures(q))}
            for q in paper.get("questions", [])
        ],
    }
    save_history(h)


def history_questions(exclude_slug: Optional[str] = None) -> List[dict]:
    out = []
    for slug, e in load_history()["papers"].items():
        if slug == exclude_slug:
            continue
        for q in e.get("questions", []):
            d = dict(q)
            d["slug"] = slug
            out.append(d)
    return out


# ----------------------------------------------------------------- naming
def slugify(s: str, maxlen: int = 40) -> str:
    s = (s or "").replace("&", " and ")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    s = re.sub(r"_+", "_", s)
    return s[:maxlen].rstrip("_") or "Set"


def practice_name(topics: List[str], set_name: Optional[str] = None) -> str:
    if set_name:
        return set_name
    if topics and len(topics) == 1:
        return topics[0]
    return "Mixed Topics"


def _slug_prefix(exam: str, cls: int, level, mode: str, name: Optional[str]) -> str:
    exam = norm_exam(exam)
    if mode == "mock":
        lv = "" if int(level) == 1 else "_L%d" % int(level)
        return "%s_Class%d%s_Mock_Paper_" % (exam, int(cls), lv)
    return "%s_Class%d_Practice_%s_" % (exam, int(cls), slugify(name or "Mixed Topics"))


def paper_slug(exam: str, cls: int, level, mode: str, paper_no: int, name: Optional[str] = None) -> str:
    return _slug_prefix(exam, cls, level, mode, name) + "%02d" % int(paper_no)


def existing_slugs() -> List[str]:
    s = set(load_history()["papers"].keys())
    s.update(p.stem for p in papers_dir().glob("*.json"))
    return sorted(s)


def next_paper_no(exam: str, mode: str = "mock", level=1, cls: int = 5, name: Optional[str] = None) -> int:
    pat = re.compile("^" + re.escape(_slug_prefix(exam, cls, level, mode, name)) + r"(\d+)$")
    used = [int(m.group(1)) for m in (pat.match(s) for s in existing_slugs()) if m]
    return (max(used) + 1) if used else 1


def paper_display_name(paper: dict) -> str:
    if paper.get("mode") == "practice":
        return paper.get("set_name") or practice_name(paper.get("topics") or [])
    return ""


def paper_title(paper: dict) -> str:
    if paper.get("title"):
        return paper["title"]
    no = int(paper.get("paper_no", 1))
    if paper.get("mode") == "practice":
        return "TOPIC-WISE PRACTICE SET %02d \u2013 %s" % (no, paper_display_name(paper))
    if int(paper.get("level", 1)) == 2:
        return "LEVEL 2 MOCK TEST PAPER %02d" % no
    return "MOCK TEST PAPER %02d" % no


def paper_footer_label(paper: dict) -> str:
    no = int(paper.get("paper_no", 1))
    cls = paper.get("class", 5)
    if paper.get("mode") == "practice":
        first = "Practice Set %02d \u2013 %s" % (no, paper_display_name(paper))
    elif int(paper.get("level", 1)) == 2:
        first = "Level 2 Mock Paper %02d" % no
    else:
        first = "Mock Paper %02d" % no
    return "%s | Class-%s | %s" % (first, cls, paper.get("exam", ""))


# ------------------------------------------------------------ paper utils
def load_paper(arg: str) -> Tuple[dict, Path]:
    p = Path(arg).expanduser()
    if not p.exists():
        cand = papers_dir() / (arg if arg.endswith(".json") else arg + ".json")
        if cand.exists():
            p = cand
        else:
            raise ValueError("Paper not found: %s (looked in %s)" % (arg, papers_dir()))
    paper = read_json(p)
    if not isinstance(paper, dict) or "questions" not in paper:
        raise ValueError("%s is not a paper JSON (no 'questions')" % p)
    return paper, p.resolve()


def marks_for(paper: dict, q: dict) -> int:
    if paper.get("mode") == "practice":
        return 3 if q.get("achievers") else 1
    lv = get_level(paper["exam"], paper.get("level", 1), paper.get("class", 5))
    s = section_by_no(lv, q.get("section")) or expected_section(lv, int(q.get("id", 0)))
    return int(s["marks_each"]) if s else 1


def max_marks(paper: dict) -> int:
    return sum(marks_for(paper, q) for q in paper.get("questions", []))


def student_view(paper: dict) -> dict:
    sv = copy.deepcopy(paper)
    for k in list(sv.keys()):
        if k.startswith("_"):
            del sv[k]
    for q in sv.get("questions", []):
        for k in list(q.keys()):
            if k in ("answer", "explanation") or k.startswith("_"):
                del q[k]
    sv["_note"] = "Student view: answers and explanations removed."
    return sv


# ---------------------------------------------------------------- browser
_BROWSER_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
_BROWSER_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                  "microsoft-edge", "microsoft-edge-stable", "msedge"]
_WSL_PATHS = [
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
]


def find_browser() -> Optional[str]:
    env = os.environ.get("OLYMPIAD_BROWSER")
    if env and Path(env).exists():
        return env
    for p in _BROWSER_PATHS:
        if Path(p).exists():
            return p
    for n in _BROWSER_NAMES:
        w = shutil.which(n)
        if w:
            return w
    for p in _WSL_PATHS:
        if Path(p).exists():
            return p
    return None


def _wsl_win(path: Path) -> str:
    try:
        return subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return str(path)


def html_to_pdf(html_path, pdf_path, browser: Optional[str] = None, timeout: int = 120) -> Tuple[bool, str]:
    """Print an HTML file to PDF with headless Chrome/Chromium/Edge.  (ok, message)"""
    browser = browser or find_browser()
    if not browser:
        return False, "No Chrome, Chromium or Edge found (set OLYMPIAD_BROWSER to the browser binary)."
    html_path = Path(html_path).resolve()
    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()
    wsl = browser.startswith("/mnt/") and browser.lower().endswith(".exe")
    prof = tempfile.mkdtemp(prefix="sof-chrome-")
    fd, errname = tempfile.mkstemp(prefix="sof-chrome-", suffix=".log")
    os.close(fd)
    if wsl:
        url = "file:///" + _wsl_win(html_path).replace("\\", "/")
        out_arg, prof_arg = _wsl_win(pdf_path), _wsl_win(Path(prof))
    else:
        url, out_arg, prof_arg = html_path.as_uri(), str(pdf_path), prof
    cmd = [browser, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf-no-header",
           "--print-to-pdf=" + out_arg, "--user-data-dir=" + prof_arg, "--no-first-run",
           "--no-default-browser-check", "--disable-extensions", "--disable-background-networking",
           "--disable-component-update", "--disable-sync", "--disable-default-apps", "--mute-audio",
           "--metrics-recording-only", "--disable-breakpad", "--password-store=basic", "--use-mock-keychain",
           url]
    rc, timed_out, start_err = None, False, ""
    try:
        with open(errname, "ab") as errf:
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errf,
                                        start_new_session=(os.name == "posix"))
            except OSError as e:
                start_err = "Could not start browser: %s" % e
                proc = None
            if proc is not None:
                # Chrome sometimes keeps running after the PDF is written, so stop as soon as it is complete.
                deadline = time.time() + timeout
                last_size, stable = -1, 0
                while True:
                    rc = proc.poll()
                    if rc is not None:
                        break
                    size = pdf_path.stat().st_size if pdf_path.exists() else 0
                    if size > 800:
                        stable = stable + 1 if size == last_size else 0
                        last_size = size
                        try:
                            written = "bytes written to file" in Path(errname).read_text(errors="replace")
                        except OSError:
                            written = False
                        if written or stable >= 4:
                            time.sleep(0.3)
                            _kill_tree(proc)
                            break
                    if time.time() > deadline:
                        timed_out = True
                        _kill_tree(proc)
                        break
                    time.sleep(0.25)
        try:
            err_text = Path(errname).read_text(errors="replace")
        except OSError:
            err_text = ""
    finally:
        shutil.rmtree(prof, ignore_errors=True)
        try:
            os.unlink(errname)
        except OSError:
            pass
    if start_err:
        return False, start_err
    noise = ("task_policy_set", "bytes written to file", "DevTools listening", "Fontconfig")
    msg = "\n".join(l for l in err_text.splitlines() if l.strip() and not any(n in l for n in noise))
    ok = pdf_path.exists() and pdf_path.stat().st_size > 800
    if not ok:
        if timed_out:
            msg = ("Browser timed out after %ss\n" % timeout) + msg
        elif not msg:
            msg = "Browser exited with code %s and produced no PDF" % rc
    return ok, msg.strip()


def _kill_tree(proc) -> None:
    """Stop a browser and the helper processes in its session (SIGTERM, then SIGKILL)."""
    for hard in (False, True):
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL if hard else signal.SIGTERM)
            elif hard:
                proc.kill()
            else:
                proc.terminate()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


# -------------------------------------------------------------- selfcheck
def selfcheck(verbose: bool = True) -> int:
    errors: List[str] = []
    warns: List[str] = []
    data = load_class(5)
    styles = load_styles()
    for ek in EXAMS:
        ex = data["exams"].get(ek)
        if not ex:
            errors.append("missing exam %s" % ek)
            continue
        for lk, lv in ex["levels"].items():
            tag = "%s L%s" % (ek, lk)
            secs = lv["sections"]
            if [s["no"] for s in secs] != list(range(1, len(secs) + 1)):
                errors.append("%s: sections not numbered 1..n" % tag)
            nq = sum(s["questions"] for s in secs)
            nm = sum(s["questions"] * s["marks_each"] for s in secs)
            if nq != lv["total_questions"]:
                errors.append("%s: section questions %d != total %d" % (tag, nq, lv["total_questions"]))
            if nm != lv["total_marks"]:
                errors.append("%s: section marks %d != total %d" % (tag, nm, lv["total_marks"]))
            for s in secs:
                cur, prev = s["topics"]["current"], s["topics"]["previous"]
                if not cur:
                    errors.append("%s S%s: no current topics" % (tag, s["no"]))
                for nm_, lst in (("current", cur), ("previous", prev)):
                    if len(set(lst)) != len(lst):
                        errors.append("%s S%s: duplicate %s topics" % (tag, s["no"], nm_))
                if (s.get("achievers") or lv.get("previous_class_share", 0) == 0) and prev:
                    errors.append("%s S%s: Achievers/Level 2 section must have no previous-class topics" % (tag, s["no"]))
                if lv.get("previous_class_share", 0) > 0 and not s.get("achievers") and not prev:
                    errors.append("%s S%s: Level 1 section needs previous-class topics" % (tag, s["no"]))
                for t in section_topics(s):
                    st = styles.get(t)
                    if not st:
                        errors.append("no style entry for topic %r (%s S%s)" % (t, tag, s["no"]))
    topics_all = set(all_topics())
    for t, st in styles.items():
        if t not in topics_all:
            warns.append("style entry %r is not used by any syllabus" % t)
        f = st.get("figure")
        fs, ts = st.get("figure_styles") or [], st.get("text_styles") or []
        if f not in ("always", "often", "sometimes", "never"):
            errors.append("style %r: bad figure value %r" % (t, f))
        elif f == "always" and (not fs or ts):
            errors.append("style %r: 'always' needs figure_styles and no text_styles" % t)
        elif f == "never" and (not ts or fs):
            errors.append("style %r: 'never' needs text_styles and no figure_styles" % t)
        elif f in ("often", "sometimes") and (not fs or not ts):
            errors.append("style %r: '%s' needs both style lists" % (t, f))
    for t in ("Time", "Fractions", "Memory", "Tenses", "Idioms", "MS-Word", "Internet"):
        for ex in EXAMS:
            if t in all_topics(ex):
                if topic_lookup(t, ex) != t:
                    errors.append("topic_lookup(%r, %s) did not return the exact topic" % (t, ex))
    for nm_ in ("markup",):
        r = render_markup("2 < 3 and <b>NOT</b> [[frac:1 2/3]] [[blank]] x<br>y")
        if "<b>NOT</b>" not in r or "&lt; 3" not in r or 'class="frac"' not in r or "<br>" not in r:
            errors.append("render_markup self-test failed: %s" % r)
        if find_bad_tags('<span style="x">a</span> <b>ok</b>') != ['<span style="x">', "</span>"]:
            errors.append("find_bad_tags self-test failed")
    br = find_browser()
    if not br:
        warns.append("no Chrome/Chromium/Edge found: render_paper.py will produce HTML only")
    try:
        import fitz  # noqa: F401
        fitz_ok = True
    except Exception:
        fitz_ok = False
        warns.append("PyMuPDF (fitz) not installed: PDF footers/verification/previews are skipped")
    if verbose:
        print("Skill dir : %s" % SKILL_DIR)
        print("Topics    : %d in syllabus, %d style entries" % (len(topics_all), len(styles)))
        print("Browser   : %s" % (br or "NOT FOUND"))
        print("PyMuPDF   : %s" % ("ok" if fitz_ok else "missing"))
        for w in warns:
            print("WARNING: " + w)
        for e in errors:
            print("ERROR: " + e)
        print("selfcheck: %s" % ("OK" if not errors else "%d error(s)" % len(errors)))
    return 1 if errors else 0


# -------------------------------------------------------------------- cli
def _cmd_list(exam: Optional[str]) -> None:
    h = load_history()["papers"]
    scores: Dict[str, List[float]] = {}
    if scores_csv_path().exists():
        with open(str(scores_csv_path()), newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    scores.setdefault(row["slug"], []).append(float(row["percent"]))
                except Exception:
                    pass
    rows = [e for e in h.values() if not exam or e.get("exam") == norm_exam(exam)]
    if not rows:
        print("No papers yet in %s" % history_path())
        return
    rows.sort(key=lambda e: (e.get("exam", ""), e.get("mode", ""), e.get("slug", "")))
    print("%-48s %-10s %4s %9s %s" % ("slug", "created", "Qs", "attempts", "best %"))
    for e in rows:
        sc = scores.get(e["slug"], [])
        print("%-48s %-10s %4d %9d %s" % (e["slug"], e.get("created", ""), len(e.get("questions", [])),
                                           len(sc), ("%.0f" % max(sc)) if sc else "-"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SOF Olympiad prep helpers")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("paths", help="show data/output locations")
    p = sub.add_parser("next-no", help="next free paper number")
    p.add_argument("--exam", required=True)
    p.add_argument("--mode", choices=("mock", "practice"), default="mock")
    p.add_argument("--level", type=int, default=1)
    p.add_argument("--class", dest="cls", type=int, default=5)
    p.add_argument("--topics", default="", help="practice: comma-separated topics")
    p.add_argument("--set-name", default=None, help="practice: custom set name")
    p = sub.add_parser("list", help="list generated papers")
    p.add_argument("--exam", default=None)
    p = sub.add_parser("student-view", help="write the paper without answers/explanations")
    p.add_argument("paper")
    p.add_argument("--out", default=None)
    sub.add_parser("selfcheck", help="check data files and tools")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "paths":
            print("skill      : %s" % SKILL_DIR)
            print("home       : %s" % prep_home())
            print("papers     : %s" % papers_dir())
            print("work       : %s" % (prep_home() / "work"))
            print("history    : %s" % history_path())
            print("scores     : %s" % scores_csv_path())
            print("attempts   : %s" % attempts_path())
            print("pdf output : %s" % default_out_dir())
            print("browser    : %s" % (find_browser() or "NOT FOUND"))
        elif a.cmd == "next-no":
            name = None
            if a.mode == "practice":
                topics = [topic_lookup(t, a.exam, a.cls) for t in a.topics.split(",") if t.strip()]
                name = practice_name(topics, a.set_name)
            n = next_paper_no(a.exam, a.mode, a.level, a.cls, name)
            print(n)
            print("slug: %s" % paper_slug(a.exam, a.cls, a.level, a.mode, n, name), file=sys.stderr)
        elif a.cmd == "list":
            _cmd_list(a.exam)
        elif a.cmd == "student-view":
            paper, path = load_paper(a.paper)
            out = Path(a.out) if a.out else work_dir(paper.get("slug") or path.stem) / "student_view.json"
            write_json(out, student_view(paper))
            print(out)
        elif a.cmd == "selfcheck":
            return selfcheck()
        else:
            ap.print_help()
    except ValueError as e:
        die(str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
