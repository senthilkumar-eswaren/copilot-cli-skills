#!/usr/bin/env python3
"""Validate an SOF Olympiad sample paper, or one writer part, before assembly.

  validate_paper.py PAPER.json [--blueprint BP]             full paper
  validate_paper.py part_s1.json --blueprint BP --part s1   one writer part
  --no-history   skip the duplicate check against earlier papers
  --strict       treat warnings as errors

Prints ERROR:/WARN: lines and a summary line.
Exit 0 = OK (warnings allowed), 1 = validation errors, 2 = usage error.
"""
import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sof_common import (LETTERS, TOKEN_RE, read_json, die, get_level,  # noqa: E402
                        norm_exam, expected_section, find_bad_tags,
                        unbalanced_tags, question_text_for_compare,
                        question_figures, question_signature, svg_check,
                        option_plain, history_questions, strip_markup)

DIFFICULTIES = ("easy", "medium", "hard")
MODES = ("mock", "practice")
ITEM_STYLES = ("statement", "roman", "bullet", "plain", "letter", "statement_num")
KNOWN_KEYS = set("""id section section_name topic syllabus_class difficulty
achievers marks question items item_style question_after table match figure
figure_position passage_id options option_headers option_layout answer
explanation format""".split())
TOKEN_ANY_RE = re.compile(r"\[\[.*?\]\]")
ICSO_OLD_RE = re.compile(r"windows\s*(10|7)\b|office\s*(2019|365)|microsoft\s*365", re.I)
NEAR_DUP_RATIO = 0.92
NEAR_DUP_MIN_CHARS = 40


class Report(object):
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, where, msg):
        self.errors.append("%s: %s" % (where, msg) if where else msg)

    def warn(self, where, msg):
        self.warnings.append("%s: %s" % (where, msg) if where else msg)


class Ctx(object):
    """What the checks need to know about the paper being validated."""


def norm_ws(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def nonempty_text(v):
    return isinstance(v, str) and bool(norm_ws(strip_markup(v)))


def id_list(ids):
    """[1,2,3,7] -> '1-3, 7'"""
    ids = sorted(ids)
    out, start = [], None
    for i, v in enumerate(ids):
        if start is None:
            start = v
        if i + 1 == len(ids) or ids[i + 1] != v + 1:
            out.append(str(start) if start == v else "%s-%s" % (start, v))
            start = None
    return ", ".join(out)


def words_range(v):
    """Return (lo, hi) for an int or a "lo-hi" string, else None."""
    if is_int(v):
        return (int(v), int(v))
    if isinstance(v, str):
        m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", v)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            return (min(lo, hi), max(lo, hi))
    return None


def load_doc(path):
    """Return (doc, problem); doc always has questions/passages/directions lists."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
    except (IOError, OSError) as e:
        die("cannot read %s: %s" % (path, e))
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_-]*[ \t]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    try:
        data = json.loads(text)
    except ValueError as e:
        return None, "invalid JSON (%s)" % e
    if isinstance(data, list):
        data = {"questions": data}
    if not isinstance(data, dict):
        return None, "top level must be a list of questions or an object with 'questions'"
    for key in ("questions", "passages", "directions"):
        if data.get(key) is None:
            data[key] = []
        if not isinstance(data[key], list):
            return None, "'%s' must be a list" % key
    return data, None


def build_ctx(args, doc, rep):
    """Collect paper metadata from the blueprint (part mode) or the paper itself."""
    ctx = Ctx()
    ctx.part, ctx.bp, ctx.rows, ctx.bp_passages = args.part, None, {}, {}
    if args.part and not args.blueprint:
        die("--part needs --blueprint")
    meta = doc
    if args.blueprint:
        try:
            ctx.bp = read_json(args.blueprint)
        except Exception as e:  # noqa: BLE001
            die("cannot read blueprint %s: %s" % (args.blueprint, e))
        meta = ctx.bp
        ctx.rows = dict((r["id"], r) for r in ctx.bp.get("rows") or [])
        ctx.bp_passages = dict((p["id"], p) for p in ctx.bp.get("passages") or [])
    try:
        ctx.exam = norm_exam(meta.get("exam"))
    except Exception:  # noqa: BLE001
        rep.err("paper", "invalid exam %r (IMO, IEO or ICSO)" % (meta.get("exam"),))
        return None
    ctx.cls, ctx.mode, ctx.slug = meta.get("class"), meta.get("mode"), meta.get("slug")
    if ctx.mode not in MODES:
        rep.err("paper", "invalid mode %r (mock or practice)" % (ctx.mode,))
        return None
    if not is_int(ctx.cls):
        rep.err("paper", "class must be an integer (got %r)" % (ctx.cls,))
        return None
    try:
        ctx.level_no = int(meta.get("level"))
        ctx.level = get_level(ctx.exam, ctx.level_no, ctx.cls)
    except (TypeError, ValueError, KeyError) as e:
        rep.err("paper", "invalid level %r for %s Class %s (%s)" % (meta.get("level"), ctx.exam, ctx.cls, e))
        return None
    ctx.sec_by_no = dict((s["no"], s) for s in ctx.level["sections"])
    if ctx.part:
        parts = ctx.bp.get("parts") or []
        match = [p for p in parts if p.get("name") == ctx.part]
        if not match:
            die("part %r is not in the blueprint (parts: %s)" % (ctx.part, ", ".join(p.get("name", "?") for p in parts)))
        ctx.expected_ids = sorted(match[0]["ids"])
    elif ctx.rows:
        ctx.expected_ids = sorted(ctx.rows)
    elif ctx.mode == "mock":
        ctx.expected_ids = list(range(1, sum(s["questions"] for s in ctx.level["sections"]) + 1))
    else:
        ctx.expected_ids = list(range(1, len(doc["questions"]) + 1))
    ctx.doc_passage_ids = set()
    return ctx

from sof_common import FRAC_RE  # noqa: E402


def is_cell(v):
    return isinstance(v, str) or (isinstance(v, (int, float)) and not isinstance(v, bool))


def table_texts(t, prefix="table"):
    """(label, text) pairs for the string cells of a {headers?, rows, caption?} table."""
    out = []
    if not isinstance(t, dict):
        return out
    if isinstance(t.get("caption"), str):
        out.append(("%s caption" % prefix, t["caption"]))
    hdr = t.get("headers")
    if isinstance(hdr, list):
        for i, h in enumerate(hdr):
            if isinstance(h, str):
                out.append(("%s header %d" % (prefix, i + 1), h))
    rows = t.get("rows")
    if isinstance(rows, list):
        for r, row in enumerate(rows):
            if isinstance(row, list):
                for c, cell in enumerate(row):
                    if isinstance(cell, str):
                        out.append(("%s r%dc%d" % (prefix, r + 1, c + 1), cell))
    return out


def text_fields(q):
    """Every (label, text) pair of a question that is rendered as markup."""
    out = []

    def add(label, v):
        if isinstance(v, str):
            out.append((label, v))

    add("question", q.get("question"))
    items = q.get("items")
    if isinstance(items, list):
        for i, it in enumerate(items):
            add("item %d" % (i + 1), it)
    add("question_after", q.get("question_after"))
    out.extend(table_texts(q.get("table")))
    m = q.get("match")
    if isinstance(m, dict):
        add("match left_title", m.get("left_title"))
        add("match right_title", m.get("right_title"))
        for side in ("left", "right"):
            vals = m.get(side)
            if isinstance(vals, list):
                for i, v in enumerate(vals):
                    add("match %s %d" % (side, i + 1), v)
    oh = q.get("option_headers")
    if isinstance(oh, list):
        for i, h in enumerate(oh):
            add("option_headers %d" % (i + 1), h)
    opts = q.get("options")
    if isinstance(opts, dict):
        for k in sorted(opts, key=str):
            v = opts[k]
            if isinstance(v, dict):
                add("option %s" % k, v.get("text"))
            elif isinstance(v, list):
                for i, p in enumerate(v):
                    add("option %s part %d" % (k, i + 1), p)
            else:
                add("option %s" % k, v)
    add("explanation", q.get("explanation"))
    return out


def check_markup(rep, where, label, text):
    """Allowed tags only, balanced tags, and only known [[...]] tokens."""
    if not isinstance(text, str):
        return
    if "<svg" in text.lower():
        rep.err(where, "%s: inline <svg> is not allowed in text; use the figure field" % label)
    else:
        bad = find_bad_tags(text)
        if bad:
            rep.err(where, "%s: tag(s) not allowed: %s (allowed: b, i, u, sup, sub, br; "
                           "write a lone < as &lt;)" % (label, ", ".join(bad)))
        for msg in unbalanced_tags(text):
            rep.err(where, "%s: unbalanced tag %s" % (label, msg))
    toks = TOKEN_ANY_RE.findall(text)
    for tok in toks:
        m = TOKEN_RE.fullmatch(tok)
        if not m:
            rep.err(where, "%s: unknown token %s (use [[frac:3/4]] or [[blank]])" % (label, tok[:40]))
        elif m.group(1) == "frac" and not (m.group(2) and FRAC_RE.match(m.group(2))):
            rep.err(where, "%s: bad fraction %s (use [[frac:3/4]] or [[frac:2 1/2]])" % (label, tok[:40]))
    if text.count("[[") != len(toks) or text.count("]]") != len(toks):
        rep.err(where, "%s: unclosed [[ ]] token" % label)


def check_table(rep, where, label, t):
    if not isinstance(t, dict):
        rep.err(where, "%s must be an object {headers, rows}" % label)
        return
    extra = sorted(set(map(str, t)) - {"headers", "rows", "caption"})
    if extra:
        rep.warn(where, "%s: unknown key(s) ignored: %s" % (label, ", ".join(extra)))
    hdr = t.get("headers")
    if hdr is not None and not (isinstance(hdr, list) and all(is_cell(h) for h in hdr)):
        rep.err(where, "%s: headers must be a list of text or numbers" % label)
        hdr = None
    width = len(hdr) if hdr else None
    rows = t.get("rows")
    if not isinstance(rows, list) or not rows:
        rep.err(where, "%s: rows must be a non-empty list of rows" % label)
        return
    for r, row in enumerate(rows):
        if not isinstance(row, list) or not row:
            rep.err(where, "%s: row %d must be a non-empty list of cells" % (label, r + 1))
            continue
        if width is None:
            width = len(row)
        elif len(row) != width:
            rep.err(where, "%s: row %d has %d cells, expected %d" % (label, r + 1, len(row), width))
        if not all(is_cell(c) for c in row):
            rep.err(where, "%s: row %d has a cell that is not text or a number" % (label, r + 1))


def plain_opt(v):
    """Plain text of one option (string, {text, svg} or list of parts)."""
    if isinstance(v, str):
        return strip_markup(v)
    if isinstance(v, dict):
        t = v.get("text")
        return strip_markup(t) if isinstance(t, str) else ""
    if isinstance(v, list):
        return " | ".join(strip_markup(p) for p in v if isinstance(p, str))
    return ""


def opt_key(v):
    key = norm_ws(plain_opt(v))
    if isinstance(v, dict) and isinstance(v.get("svg"), str):
        key += " |svg| " + norm_ws(v["svg"])
    return key


def check_options(rep, where, q):
    opts = q.get("options")
    if not isinstance(opts, dict):
        rep.err(where, "options must be an object with keys %s" % ", ".join(LETTERS))
        return
    keys = sorted(map(str, opts))
    if set(keys) != set(LETTERS):
        rep.err(where, "options must have exactly the keys %s (got %s)"
                % (", ".join(LETTERS), ", ".join(keys) or "none"))
    raw_headers = q.get("option_headers")
    headers = raw_headers
    if headers is not None and not (isinstance(headers, list) and headers
                                    and all(nonempty_text(h) for h in headers)):
        rep.err(where, "option_headers must be a non-empty list of strings")
        headers = None
    present = [k for k in LETTERS if k in opts]
    n_list = sum(1 for k in present if isinstance(opts[k], list))
    if n_list and raw_headers is None:
        rep.err(where, "list-style options need option_headers")
    elif headers is not None and n_list != len(present):
        rep.err(where, "with option_headers every option must be a list with one entry per header")
    seen = {}
    for k in present:
        v = opts[k]
        label = "option %s" % k
        if isinstance(v, str):
            if not v.strip():
                rep.err(where, "%s is empty" % label)
                continue
        elif isinstance(v, dict):
            extra = sorted(set(map(str, v)) - {"text", "svg"})
            if extra:
                rep.err(where, "%s has unknown key(s) %s (allowed: text, svg)" % (label, ", ".join(extra)))
            for sub in ("text", "svg"):
                if v.get(sub) is not None and not isinstance(v.get(sub), str):
                    rep.err(where, "%s %s must be a string" % (label, sub))
            if not nonempty_text(v.get("text")) and not nonempty_text(v.get("svg")):
                rep.err(where, "%s needs text or svg" % label)
                continue
        elif isinstance(v, list):
            if headers is not None and len(v) != len(headers):
                rep.err(where, "%s has %d parts but option_headers has %d" % (label, len(v), len(headers)))
            if not v or not all(nonempty_text(p) for p in v):
                rep.err(where, "%s parts must be non-empty strings" % label)
                continue
        else:
            rep.err(where, "%s must be a string, {text, svg} or a list of strings" % label)
            continue
        key = opt_key(v)
        if key in seen:
            rep.err(where, "options %s and %s are the same" % (seen[key], k))
        else:
            seen[key] = k


def statement_ok(k, t):
    has_t, has_f = "true" in t, "false" in t
    if k == "A":
        return "both" in t and has_t and not has_f
    if k == "B":
        return "both" in t and has_f and not has_t
    it, iff = t.find("true"), t.find("false")
    if k == "C":
        return 0 <= it < iff
    return 0 <= iff < it


def statement_c3_ok(k, t):
    if k == "A":
        return "only" in t and "1" in t and "2" not in t
    if k == "B":
        return "only" in t and "2" in t and "1" not in t
    if k == "C":
        return "both" in t
    return "neither" in t


def check_format(rep, where, q, fmt):
    stem = q.get("question") if isinstance(q.get("question"), str) else ""
    items = q.get("items") if isinstance(q.get("items"), list) else []
    opts = q.get("options") if isinstance(q.get("options"), dict) else {}
    tag = "format '%s'" % fmt
    if fmt == "not":
        if "<b>NOT</b>" not in stem:
            rep.err(where, "%s: the question must contain <b>NOT</b>" % tag)
    elif fmt == "statements":
        if len(items) != 2:
            rep.err(where, "%s: items must hold exactly Statement-I and Statement-II" % tag)
        if q.get("item_style") != "statement":
            rep.warn(where, "%s: item_style should be \"statement\"" % tag)
        bad = [k for k in LETTERS if not statement_ok(k, plain_opt(opts.get(k)).lower())]
        if bad:
            rep.err(where, "%s: option(s) %s must use the fixed wording (A both true, B both false, "
                           "C I true and II false, D I false and II true)" % (tag, ", ".join(bad)))
    elif fmt == "statements_c3":
        if len(items) != 2:
            rep.err(where, "%s: items must hold exactly Statement 1 and Statement 2" % tag)
        if q.get("item_style") != "statement_num":
            rep.warn(where, "%s: item_style should be \"statement_num\"" % tag)
        bad = [k for k in LETTERS if not statement_c3_ok(k, plain_opt(opts.get(k)).lower())]
        if bad:
            rep.err(where, "%s: option(s) %s must use the fixed wording (A Only Statement 1, B Only Statement 2, "
                           "C Both Statement 1 and Statement 2, D Neither Statement 1 nor Statement 2)"
                    % (tag, ", ".join(bad)))
    elif fmt == "table_i_ii":
        blob = " ".join(t for lbl, t in text_fields(q)
                        if not lbl.startswith("option") and lbl != "explanation")
        for tok in ("[[blank:(i)]]", "[[blank:(ii)]]"):
            if tok not in blob:
                rep.err(where, "%s: %s is missing from the question" % (tag, tok))
        if q.get("option_headers") != ["(i)", "(ii)"]:
            rep.err(where, '%s: option_headers must be ["(i)", "(ii)"]' % tag)
    elif fmt == "roman_combo":
        if len(items) < 3:
            rep.err(where, "%s: needs items (i) to (iv)" % tag)
        if q.get("item_style") != "roman":
            rep.warn(where, "%s: item_style should be \"roman\"" % tag)
    elif fmt == "match":
        m = q.get("match")
        if not isinstance(m, dict):
            rep.err(where, "%s: a match object {left_title, right_title, left, right} is required" % tag)
        else:
            left, right = m.get("left"), m.get("right")
            if (not (isinstance(left, list) and isinstance(right, list))
                    or len(left) != len(right) or len(left) < 3):
                rep.err(where, "%s: match.left and match.right need the same number (3 or more) "
                               "of entries" % tag)
            elif len(left) != 4:
                rep.warn(where, "%s: SOF match questions usually have 4 pairs (P-S and 1-4)" % tag)


FIG_POSITIONS = ("below", "above", "right")
OPTION_LAYOUTS = ("auto", "row", "grid", "column")


def check_figures(rep, where, q, row):
    fig = q.get("figure")
    if fig is not None and not isinstance(fig, str):
        rep.err(where, "figure must be an SVG string")
    try:
        figs = question_figures(q)
    except Exception:
        figs = []
    found = False
    for label, svg in figs:
        if not isinstance(svg, str) or not svg.strip():
            continue
        found = True
        errs, width = svg_check(svg)
        for e in errs:
            rep.err(where, "%s SVG: %s" % (label, e))
        if width is None:
            continue
        if label == "figure":
            if width < 60 or width > 340:
                rep.warn(where, "figure is %gpx wide; keep it between 60 and 340px" % width)
        elif width > 140:
            rep.warn(where, "%s figure is %gpx wide; keep option figures at 140px or less" % (label, width))
    if row is not None and row.get("figure") and not found:
        rep.warn(where, "the blueprint asks for a figure but none was given")
    pos = q.get("figure_position")
    if pos is not None and pos not in FIG_POSITIONS:
        rep.err(where, "figure_position must be one of %s" % ", ".join(FIG_POSITIONS))


def check_question(rep, ctx, q, idx):
    """Check one question; returns its effective fields (own value, else blueprint row)."""
    if not isinstance(q, dict):
        rep.err("question #%d" % (idx + 1), "must be an object")
        return None
    qid = q.get("id")
    if not is_int(qid):
        rep.err("question #%d" % (idx + 1), "id must be a whole number (got %r)" % (qid,))
        return None
    where = "Q%d" % qid
    row = ctx.rows.get(qid) if ctx.rows else None
    unknown = sorted(set(map(str, q)) - KNOWN_KEYS)
    if unknown:
        rep.warn(where, "unknown key(s) ignored: %s" % ", ".join(unknown))

    eff = {"id": qid}
    for key in ("section", "topic", "syllabus_class", "difficulty", "answer"):
        v = q.get(key)
        rv = row.get(key) if row is not None else None
        if v is None:
            v = rv
        elif rv is not None and v != rv and key != "section":
            rep.warn(where, "%s %r differs from the blueprint (%r)" % (key, v, rv))
        eff[key] = v
    for key in ("section", "topic", "syllabus_class", "difficulty"):
        if eff[key] is None:
            rep.err(where, "%s is missing" % key)

    sec = None
    if eff["section"] is not None:
        if is_int(eff["section"]) and eff["section"] in ctx.sec_by_no:
            sec = ctx.sec_by_no[eff["section"]]
        else:
            rep.err(where, "section %r is not a section of this paper (use %s)"
                    % (eff["section"], ", ".join(str(n) for n in sorted(ctx.sec_by_no))))
    exp = row.get("section") if row is not None else None
    if exp is None and ctx.mode == "mock":
        try:
            s = expected_section(ctx.level, qid)
            exp = s.get("no") if isinstance(s, dict) else None
        except Exception:
            exp = None
    if sec is not None and exp is not None and eff["section"] != exp:
        rep.err(where, "is in section %s but question %d belongs to section %s" % (eff["section"], qid, exp))
    if eff["topic"] is not None and not nonempty_text(eff["topic"]):
        rep.err(where, "topic must be a non-empty string")
    if eff["difficulty"] is not None and eff["difficulty"] not in DIFFICULTIES:
        rep.err(where, "difficulty must be one of %s" % ", ".join(DIFFICULTIES))

    ach = q.get("achievers")
    if ach is not None and not isinstance(ach, bool):
        rep.err(where, "achievers must be true or false")
        ach = None
    if ach is None and row is not None and isinstance(row.get("achievers"), bool):
        ach = row["achievers"]
    if ach is None and sec is not None:
        ach = bool(sec.get("achievers"))
    eff["achievers"] = bool(ach)
    if ctx.mode == "mock" and sec is not None and eff["achievers"] != bool(sec.get("achievers")):
        rep.err(where, "achievers flag does not match section %s (%s)" % (sec.get("no"), sec.get("name")))

    sc = eff["syllabus_class"]
    if sc is not None:
        if not is_int(sc) or sc not in (ctx.cls, ctx.cls - 1):
            rep.err(where, "syllabus_class must be %d or %d" % (ctx.cls, ctx.cls - 1))
        elif sc != ctx.cls and (eff["achievers"] or ctx.level_no == 2):
            rep.err(where, "Achievers and Level 2 questions must use the class %d syllabus" % ctx.cls)

    if not nonempty_text(q.get("question")):
        rep.err(where, "question text is missing")
    if q.get("question_after") is not None and not isinstance(q.get("question_after"), str):
        rep.err(where, "question_after must be a string")
    for label, text in text_fields(q):
        check_markup(rep, where, label, text)
    items = q.get("items")
    if items is not None and not (isinstance(items, list) and items
                                  and all(nonempty_text(i) for i in items)):
        rep.err(where, "items must be a non-empty list of non-empty strings")
    st = q.get("item_style")
    if st is not None and st not in ITEM_STYLES:
        rep.err(where, "item_style must be one of %s" % ", ".join(ITEM_STYLES))
    if q.get("table") is not None:
        check_table(rep, where, "table", q["table"])
    m = q.get("match")
    if m is not None:
        if not isinstance(m, dict):
            rep.err(where, "match must be an object {left_title, right_title, left, right}")
        else:
            for k in ("left_title", "right_title"):
                if not nonempty_text(m.get(k)):
                    rep.err(where, "match.%s is missing" % k)
            for k in ("left", "right"):
                v = m.get(k)
                if not (isinstance(v, list) and v and all(nonempty_text(x) for x in v)):
                    rep.err(where, "match.%s must be a non-empty list of strings" % k)
            extra = sorted(set(map(str, m)) - {"left_title", "right_title", "left", "right"})
            if extra:
                rep.warn(where, "match: unknown key(s) ignored: %s" % ", ".join(extra))

    check_options(rep, where, q)
    ans = eff["answer"]
    if not (isinstance(ans, str) and ans in set(LETTERS)):
        rep.err(where, "answer must be one of %s (got %r)" % (", ".join(LETTERS), ans))
    lay = q.get("option_layout")
    if lay is not None and lay not in OPTION_LAYOUTS:
        rep.err(where, "option_layout must be one of %s" % ", ".join(OPTION_LAYOUTS))
    mk = q.get("marks")
    if mk is not None:
        if not is_int(mk) or mk <= 0:
            rep.err(where, "marks must be a positive whole number")
        elif ctx.mode == "mock" and sec is not None and is_int(sec.get("marks_each")) and mk != sec["marks_each"]:
            rep.warn(where, "marks %d differs from the section's %d" % (mk, sec["marks_each"]))
    check_figures(rep, where, q, row)

    ex = q.get("explanation")
    if not nonempty_text(ex):
        rep.err(where, "explanation is missing")
    elif len(strip_markup(ex).strip()) < 25:
        rep.warn(where, "explanation is very short; explain why the answer is right")
    if ctx.exam == "ICSO":
        try:
            blob = question_text_for_compare(q)
        except Exception:
            blob = ""
        blob += " " + (ex if isinstance(ex, str) else "")
        mm = ICSO_OLD_RE.search(blob)
        if mm:
            rep.warn(where, "mentions '%s'; use the software versions in the ICSO syllabus" % mm.group(0))

    pid_q = q.get("passage_id") or None
    pid_row = (row.get("passage_id") or None) if row is not None else None
    if pid_q is None and pid_row is not None:
        rep.warn(where, "passage_id is missing (the blueprint uses %s)" % pid_row)
    elif row is not None and pid_q is not None and pid_q != pid_row:
        rep.err(where, "passage_id %s differs from the blueprint (%s)" % (pid_q, pid_row or "none"))
    pid = pid_q if pid_q is not None else pid_row
    if pid is not None and pid not in ctx.doc_passage_ids:
        rep.err(where, "passage_id %s does not match any passage in this file" % pid)
    eff["passage_id"] = pid

    fmt_q = q.get("format")
    fmt_row = row.get("format") if row is not None else None
    if fmt_q is not None and fmt_row is not None and fmt_q != fmt_row:
        rep.warn(where, "format %r differs from the blueprint (%r)" % (fmt_q, fmt_row))
    fmt = fmt_q or fmt_row or "standard"
    check_format(rep, where, q, fmt)
    eff["format"] = fmt
    return eff


from sof_common import papers_dir  # noqa: E402


def check_passages(rep, ctx, doc):
    seen = set()
    for i, p in enumerate(doc.get("passages") or []):
        where = "passage #%d" % (i + 1)
        if not isinstance(p, dict):
            rep.err(where, "must be an object {id, title, text}")
            continue
        pid = p.get("id")
        if isinstance(pid, bool) or not isinstance(pid, (str, int)) or not str(pid).strip():
            rep.err(where, "id is missing")
            continue
        where = "passage %s" % pid
        if pid in seen:
            rep.err(where, "duplicate passage id")
            continue
        seen.add(pid)
        text = p.get("text")
        if not nonempty_text(text):
            rep.err(where, "text is missing")
        else:
            check_markup(rep, where, "text", text)
        title = p.get("title")
        if title is not None:
            if isinstance(title, str):
                check_markup(rep, where, "title", title)
            else:
                rep.err(where, "title must be a string")
        if p.get("table") is not None:
            check_table(rep, where, "table", p["table"])
            for label, t in table_texts(p["table"]):
                check_markup(rep, where, label, t)
        bp = ctx.bp_passages.get(pid)
        fig = p.get("figure")
        if fig is not None:
            if not nonempty_text(fig):
                rep.err(where, "figure must be an SVG string")
            else:
                errs, width = svg_check(fig)
                for e in errs:
                    rep.err(where, "figure SVG: %s" % e)
                if width is not None and (width < 60 or width > 520):
                    rep.warn(where, "figure is %gpx wide; keep it between 60 and 520px" % width)
            if bp is not None and not bp.get("allow_figure"):
                rep.warn(where, "has a figure but the blueprint did not ask for one")
        elif bp is not None and bp.get("allow_figure"):
            rep.err(where, "needs a picture (figure) - this is a Picture Reading passage")
        wr = words_range(bp.get("words")) if bp is not None else None
        if wr is not None and nonempty_text(text):
            n = len(strip_markup(text).split())
            if n < 0.6 * wr[0] or n > 1.6 * wr[1]:
                rep.warn(where, "has %d words; the blueprint asks for %s" % (n, bp["words"]))
    ctx.doc_passage_ids = seen
    exp = set(ctx.expected_ids)
    for pid, bp in sorted(ctx.bp_passages.items(), key=lambda kv: str(kv[0])):
        need = set(bp.get("question_ids") or []) & exp
        if pid not in seen and need:
            rep.err("passage %s" % pid, "is missing (needed by Q%s)" % id_list(need))


def check_directions(rep, ctx, doc, ids):
    """Check direction blocks; returns the passage ids they use."""
    used, ranges = set(), []
    allowed = set(ctx.expected_ids) | set(ids)
    for i, d in enumerate(doc.get("directions") or []):
        where = "directions #%d" % (i + 1)
        if not isinstance(d, dict):
            rep.err(where, "must be an object {from, to, text}")
            continue
        a, b = d.get("from"), d.get("to")
        if not (is_int(a) and is_int(b)) or a > b:
            rep.err(where, "from/to must be question numbers with from <= to")
        else:
            where = "directions Q%d-%d" % (a, b)
            outside = set(range(a, b + 1)) - allowed
            if outside:
                rep.err(where, "covers question(s) not in this file: %s" % id_list(outside))
            for x, y in ranges:
                if a <= y and x <= b:
                    rep.warn(where, "overlaps directions Q%d-%d" % (x, y))
            ranges.append((a, b))
        if not nonempty_text(d.get("text")):
            rep.err(where, "text is missing")
        else:
            check_markup(rep, where, "text", d["text"])
        pid = d.get("passage_id") or None
        if pid is not None:
            if pid in ctx.doc_passage_ids:
                used.add(pid)
            else:
                rep.err(where, "passage_id %s does not match any passage in this file" % pid)
        fig = d.get("figure")
        if fig is not None:
            if not nonempty_text(fig):
                rep.err(where, "figure must be an SVG string")
            else:
                errs, width = svg_check(fig)
                for e in errs:
                    rep.err(where, "figure SVG: %s" % e)
                if width is not None and (width < 60 or width > 340):
                    rep.warn(where, "figure is %gpx wide; keep it between 60 and 340px" % width)
    return used


def check_ids(rep, ctx, ids):
    seen, dups = set(), set()
    for i in ids:
        (dups if i in seen else seen).add(i)
    if dups:
        rep.err("paper", "duplicate question id(s): %s" % id_list(dups))
    exp = set(ctx.expected_ids)
    if seen - exp:
        rep.err("paper", "unexpected question id(s): %s" % id_list(seen - exp))
    if exp - seen:
        rep.err("paper", "missing question(s): %s" % id_list(exp - seen))


def pct(n, d):
    return 100.0 * n / d if d else 0.0


def check_paper(rep, ctx, effs):
    """Balance checks across the whole paper (or part)."""
    effs = sorted(effs, key=lambda e: e["id"])
    n = len(effs)
    whole = ctx.part is None
    non_ach = [e for e in effs if not e["achievers"]]
    if whole and ctx.mode == "mock" and ctx.level_no == 1 and len(non_ach) >= 10:
        prev = sum(1 for e in non_ach if e["syllabus_class"] == ctx.cls - 1)
        p = pct(prev, len(non_ach))
        if p < 30 or p > 50:
            rep.warn("paper", "%.0f%% of non-Achievers questions use the class %d syllabus; "
                     "SOF Level 1 uses about 40%%" % (p, ctx.cls - 1))
    if whole and n >= 20:
        for L in LETTERS:
            c = sum(1 for e in effs if e["answer"] == L)
            if not 15 <= pct(c, n) <= 35:
                rep.warn("paper", "answer %s is right for %d of %d questions (%.0f%%); aim for 15-35%%"
                         % (L, c, n, pct(c, n)))
    if whole:
        run = []
        for e in effs + [None]:
            if (e is not None and run and e["answer"] == run[-1]["answer"]
                    and e["id"] == run[-1]["id"] + 1):
                run.append(e)
                continue
            if len(run) >= 4:
                rep.warn("paper", "Q%d-%d all have answer %s; vary the answer letters"
                         % (run[0]["id"], run[-1]["id"], run[0]["answer"]))
            run = [e] if e is not None else []
    if ctx.mode == "mock":
        by_sec = {}
        for e in effs:
            if e.get("passage_id") is None:
                by_sec.setdefault(e["section"], []).append(e)
        for s, es in sorted(by_sec.items(), key=lambda kv: str(kv[0])):
            topics = set(norm_ws(e["topic"]) for e in es if isinstance(e["topic"], str))
            if len(es) >= 10 and len(topics) < 0.5 * len(es):
                rep.warn("section %s" % s, "only %d different topics in %d questions; spread the topics"
                         % (len(topics), len(es)))
        if whole and n >= 20:
            for d, lo, hi in (("easy", 15, 45), ("hard", 10, 35)):
                p = pct(sum(1 for e in effs if e["difficulty"] == d), n)
                if not lo <= p <= hi:
                    rep.warn("paper", "%.0f%% of questions are %s; aim for %d-%d%%" % (p, d, lo, hi))
    if ctx.mode == "practice":
        first_ach = None
        for e in effs:
            if e["achievers"]:
                first_ach = first_ach or e["id"]
            elif first_ach is not None:
                rep.err("Q%d" % e["id"], "comes after Achievers Q%d; put Achievers questions last" % first_ach)
                break


def check_history(rep, ctx, questions):
    """No repeats inside the paper or of questions from earlier papers."""
    mine, sigs = [], {}
    for q in questions:
        if not isinstance(q, dict) or not is_int(q.get("id")):
            continue
        where = "Q%d" % q["id"]
        try:
            sig, text, has_fig = question_signature(q), question_text_for_compare(q), bool(question_figures(q))
        except Exception:
            continue
        if sig in sigs:
            rep.err(where, "is identical to Q%d" % sigs[sig])
        else:
            sigs[sig] = q["id"]
        mine.append((where, sig, text[:600], has_fig))
    if getattr(ctx, "no_history", False):
        return
    try:
        hist = history_questions(ctx.slug)
    except Exception as e:
        rep.warn("history", "could not read earlier papers (%s); repeat check skipped" % e)
        return
    by_sig, texts = {}, []
    for h in hist:
        s = h.get("sig") or h.get("signature")
        if s:
            by_sig.setdefault(s, h)
        t = h.get("text")
        if isinstance(t, str) and len(t) >= NEAR_DUP_MIN_CHARS and not h.get("has_figure"):
            texts.append((t, h))
    sm = difflib.SequenceMatcher(None, autojunk=False)
    for where, sig, text, has_fig in mine:
        h = by_sig.get(sig)
        if h is not None:
            rep.err(where, "repeats Q%s of %s; write a new question" % (h.get("id"), h.get("slug")))
            continue
        if has_fig or len(text) < NEAR_DUP_MIN_CHARS:
            continue
        sm.set_seq2(text)
        for ht, h in texts:
            sm.set_seq1(ht)
            if (sm.real_quick_ratio() >= NEAR_DUP_RATIO and sm.quick_ratio() >= NEAR_DUP_RATIO
                    and sm.ratio() >= NEAR_DUP_RATIO):
                rep.warn(where, "is almost the same as Q%s of %s; change it more" % (h.get("id"), h.get("slug")))
                break


def finish(rep, args, n):
    if args.strict and rep.warnings:
        rep.errors.extend("(strict) " + w for w in rep.warnings)
        rep.warnings = []
    for e in rep.errors:
        print("ERROR: " + e)
    for w in rep.warnings:
        print("WARN: " + w)
    print("%s: %s - %d questions, %d errors, %d warnings"
          % ("FAILED" if rep.errors else "OK", args.file, n, len(rep.errors), len(rep.warnings)))
    return 1 if rep.errors else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a generated SOF practice paper, or one writer part, for mistakes.")
    ap.add_argument("file", help="paper or part JSON file, or the slug of a saved paper")
    ap.add_argument("--blueprint", help="blueprint.json the questions were written from")
    ap.add_argument("--part", help="part name (e.g. s1) when checking one writer part")
    ap.add_argument("--no-history", action="store_true", help="skip the repeat check against earlier papers")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args(argv)
    if not os.path.isfile(args.file):
        name = args.file if args.file.endswith(".json") else args.file + ".json"
        alt = os.path.join(str(papers_dir()), name)
        if not os.path.isfile(alt):
            die("file not found: %s" % args.file)
        args.file = alt
    rep = Report()
    doc, problem = load_doc(args.file)
    if doc is None:
        rep.err("file", problem or "could not read the file")
        return finish(rep, args, 0)
    if problem:
        rep.warn("file", problem)
    ctx = build_ctx(args, doc, rep)
    questions = doc.get("questions") or []
    if ctx is None:
        return finish(rep, args, len(questions))
    ctx.no_history = args.no_history
    check_passages(rep, ctx, doc)
    effs, ids = [], []
    for i, q in enumerate(questions):
        if isinstance(q, dict) and is_int(q.get("id")):
            ids.append(q["id"])
        e = check_question(rep, ctx, q, i)
        if e is not None:
            effs.append(e)
    check_ids(rep, ctx, ids)
    used = check_directions(rep, ctx, doc, ids)
    used |= set(e["passage_id"] for e in effs if e.get("passage_id") is not None)
    for pid in sorted(ctx.doc_passage_ids - used, key=str):
        rep.warn("passage %s" % pid, "is not used by any question")
    check_paper(rep, ctx, effs)
    check_history(rep, ctx, questions)
    return finish(rep, args, len(questions))


if __name__ == "__main__":
    sys.exit(main())
