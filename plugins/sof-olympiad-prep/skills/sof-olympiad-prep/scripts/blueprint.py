#!/usr/bin/env python3
import sys, os, re, random, math, difflib, argparse, json, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sof_common import *

EVERYDAY = "Everyday-life word problem: "
HOTS = "Achievers-level HOTS: "


def warn(msg):
    print("WARNING: " + msg, file=sys.stderr)


def parse_args():
    ap = argparse.ArgumentParser(description="Create a SOF-style paper blueprint")
    ap.add_argument("--exam", type=str.upper, choices=EXAMS, required=True)
    ap.add_argument("--mode", choices=("mock", "practice"), default="mock")
    ap.add_argument("--level", type=int, choices=(1, 2), default=1)
    ap.add_argument("--class", dest="cls", type=int, default=5)
    ap.add_argument("--paper-no", type=int)
    ap.add_argument("--seed")
    ap.add_argument("--topics", action="append", default=[])
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--set-name")
    ap.add_argument("--achievers", type=int)
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--list-topics", action="store_true")
    a = ap.parse_args()
    if a.mode == "practice" and not a.list_topics:
        if not a.topics:
            die("--mode practice needs at least one --topics value")
        if not 1 <= a.count <= 50:
            die("--count must be between 1 and 50")
    return a


def resolve_topics(vals, exam, cls):
    names = []
    for v in vals:
        v = (v or "").strip()
        if not v:
            continue
        if ";" in v or "|" in v:
            pieces = [p for p in re.split(r"[;|]", v)]
        else:
            try:
                topic_lookup(v, exam, cls)
                pieces = [v]
            except ValueError:
                pieces = v.split(",")
        for p in pieces:
            p = p.strip()
            if not p:
                continue
            try:
                names.append(topic_lookup(p, exam, cls))
            except ValueError as e:
                die(str(e))
    return uniq(names)


_STYLES = None


def style_of(t):
    global _STYLES
    if _STYLES is None:
        s = load_styles()
        _STYLES = s.get("topics", s) if isinstance(s, dict) else {}
    e = _STYLES.get(t) or {}
    tips = e.get("tips", "")
    if isinstance(tips, list):
        tips = " ".join(str(x) for x in tips)
    return {
        "figure": e.get("figure", "never"),
        "figure_styles": list(e.get("figure_styles") or []),
        "text_styles": list(e.get("text_styles") or []) or ["standard MCQ"],
        "tips": tips or "",
    }


def is_lr_like(t):
    s = (t or "").lower()
    return s.startswith("pattern") or s.startswith("puzzle") or ("clock" in s and "calendar" in s)


def pick_topics(rng, topics, k, avoid=(), must=()):
    out = list(must)[:k]
    rest = k - len(out)
    if rest <= 0 or not topics:
        return out
    per = rest // len(topics)
    for t in topics:
        out.extend([t] * per)
    rem = rest - per * len(topics)
    if rem:
        avoid = set(avoid)
        pref = [t for t in topics if t not in avoid]
        other = [t for t in topics if t in avoid]
        rng.shuffle(pref)
        rng.shuffle(other)
        out.extend((pref + other)[:rem])
    return out


def class_split(sec, level):
    n = int(sec["questions"])
    prev = (sec.get("topics") or {}).get("previous") or []
    if sec.get("achievers") or int(level) == 2 or not prev:
        return n, 0
    n5 = rhalf(0.6 * n)
    return n5, n - n5


def _lead(s):
    w = re.sub(r"[-,]", " ", str(s).lower()).split()
    return w[0] if w else ""


def anchor_index(t, cur):
    if t in cur:
        return cur.index(t)
    lead = _lead(t)
    if len(lead) >= 4:
        for i, c in enumerate(cur):
            if _lead(c) == lead:
                return i
    best, bi = 0.0, len(cur)
    for i, c in enumerate(cur):
        r = difflib.SequenceMatcher(None, t.lower(), c.lower()).ratio()
        if r > best:
            best, bi = r, i
    return bi if best >= 0.6 else len(cur)


def difficulty_list(rng, n, ach):
    if ach:
        return ["hard"] * n
    e, h = rhalf(0.3 * n), rhalf(0.2 * n)
    out = ["easy"] * e + ["hard"] * h + ["medium"] * max(0, n - e - h)
    rng.shuffle(out)
    return out[:n]


def assign_fig_style(rows, seed):
    cnt, cyc = {}, {}
    for r in rows:
        t = r["topic"]
        st = style_of(t)
        r["tips"] = st.get("tips", "")
        if r.get("passage_id"):
            r["figure"] = False
            continue
        c = cnt.get(t, 0)
        cnt[t] = c + 1
        off = random.Random(seed + "|fig|" + t).randint(0, 2)
        f = str(st.get("figure", "never")).lower()
        if t == "Reading Comprehension" or f == "never":
            fig = False
        elif f == "always":
            fig = True
        elif f == "often":
            fig = (c + off) % 3 != 0
        elif f == "sometimes":
            fig = (c + off) % 3 == 0
        else:
            fig = False
        r["figure"] = fig
        kind = "fig" if fig else "text"
        a, b = st.get("figure_styles") or [], st.get("text_styles") or []
        lst = list(a if fig else b) or list(b if fig else a) or ["standard MCQ"]
        key = (t, kind)
        if key not in cyc:
            random.Random(seed + "|style|" + t + "|" + kind).shuffle(lst)
            cyc[key] = [lst, 0]
        L, i = cyc[key]
        r["style"] = L[i % len(L)]
        cyc[key][1] = i + 1


def assign_prefixes(rows, exam, level):
    k = 0
    for r in rows:
        if r.get("achievers"):
            r["prefix"] = HOTS
        elif r.get("section_name") == "Everyday Mathematics":
            r["prefix"] = EVERYDAY
        elif exam == "IMO" and int(level) == 2 and int(r.get("section", 0)) == 1 and not is_lr_like(r["topic"]):
            if k % 3 == 2:
                r["prefix"] = EVERYDAY
            k += 1


def assign_answers(n, seed):
    rng = random.Random(seed + "|ans")
    q = int(math.ceil(n / 4.0))
    for _ in range(200):
        left = dict((L, q) for L in LETTERS)
        out = []
        for _i in range(n):
            cand = [L for L in LETTERS if left[L] > 0 and not (len(out) >= 2 and out[-1] == L and out[-2] == L)]
            if not cand:
                break
            L = rng.choices(cand, weights=[left[x] for x in cand])[0]
            out.append(L)
            left[L] -= 1
        if len(out) == n:
            return out
    die("could not assign a balanced answer pattern")


FORMAT_INSTR = {
    "statements": ("Two-statement question. Put the two statements in 'items' (item_style \"statement\"; "
                   "labels Statement-I and Statement-II) and set question_after to \"Which of the following is correct?\". "
                   "Use exactly these options: A \"Both Statement-I and Statement-II are true.\", "
                   "B \"Both Statement-I and Statement-II are false.\", C \"Statement-I is true but Statement-II is false.\", "
                   "D \"Statement-I is false but Statement-II is true.\" Write the statements so the assigned answer letter is correct."),
    "table_i_ii": ("Two-blank table question. The stem contains [[blank:(i)]] and [[blank:(ii)]]. "
                   "Set option_headers to [\"(i)\", \"(ii)\"] and make every option a list of two strings (value for (i), value for (ii))."),
    "not": "Negative question: ask which option is <b>NOT</b> true / does <b>NOT</b> fit (write NOT exactly as <b>NOT</b>). Exactly one option is the exception.",
    "roman_combo": ("Combination question. Put four items (i)-(iv) in 'items' (item_style \"roman\"); options are combinations "
                    "such as \"Only (i) and (iii)\", \"Only (ii), (iii) and (iv)\", \"All of these\". Exactly one option is fully correct."),
    "match": ("Match-the-columns question. Fill 'match' with left_title \"Column I\", right_title \"Column II\", "
              "left = 4 items (P, Q, R, S) and right = 4 items (1, 2, 3, 4). Options are mappings like "
              "\"P → 2, Q → 4, R → 1, S → 3\"; exactly one mapping is fully correct."),
}


def eligible(r, fmt, exam):
    if r.get("passage_id") or r["topic"] == "Reading Comprehension":
        return False
    if r.get("figure"):
        return fmt == "not"
    if "Logical Reasoning" in r.get("section_name", "") or is_lr_like(r["topic"]):
        return fmt in ("not", "table_i_ii")
    if exam == "IMO":
        return fmt in ("statements", "table_i_ii", "not", "roman_combo")
    return True


def _set_fmt(r, f):
    r["format"] = f
    r["format_instructions"] = FORMAT_INSTR[f]


def mock_formats(rows, exam, seed):
    toks = ["statements"] * 2 + ["table_i_ii"] * 2 + ["not"] * 3 + ["roman_combo"]
    if exam in ("IEO", "ICSO"):
        toks.append("match")
    rng = random.Random(seed + "|fmt")
    rng.shuffle(toks)
    secs = uniq([r["section"] for r in rows])
    ach = [s for s in secs if any(r["achievers"] for r in rows if r["section"] == s)]
    rest = [s for s in secs if s not in ach]
    order = ach + rest[1:] + rest[:1]
    cap = dict((s, max(1, rhalf(0.4 * sum(1 for r in rows if r["section"] == s)))) for s in secs)
    used = dict((s, 0) for s in secs)
    p = 0
    for f in toks:
        done = False
        for k in range(len(order)):
            s = order[(p + k) % len(order)]
            if used[s] >= cap[s]:
                continue
            c = [r for r in rows if r["section"] == s and r["format"] == "standard" and eligible(r, f, exam)]
            if c:
                _set_fmt(rng.choice(c), f)
                used[s] += 1
                p = (p + k + 1) % len(order)
                done = True
                break
        if not done:
            warn("no eligible question for format '%s'; skipped" % f)


def practice_formats(rows, exam, seed):
    n = len(rows)
    toks = []
    if n >= 10:
        toks += ["not", "table_i_ii"]
    if n >= 15:
        toks.append("statements")
    if n >= 20:
        toks.append("roman_combo")
        if exam in ("IEO", "ICSO"):
            toks.append("match")
    rng = random.Random(seed + "|fmt")
    for f in toks:
        c = [r for r in rows if r["format"] == "standard" and eligible(r, f, exam)]
        if c:
            _set_fmt(rng.choice(c), f)
        else:
            warn("no eligible question for format '%s'; skipped" % f)


def make_row(i, sec, topic, scls):
    return {"id": i, "section": int(sec["no"]), "section_name": sec["name"], "topic": topic,
            "syllabus_class": int(scls), "difficulty": "", "achievers": bool(sec.get("achievers")),
            "marks": sec.get("marks_each", 1), "figure": False, "style": "", "format": "standard",
            "format_instructions": "", "prefix": "", "tips": "", "passage_id": None, "answer": ""}


def _is_reading(sec):
    return bool(sec) and str(sec.get("name", "")).strip().lower() == "reading"


def _passage(pid, ttype, scls, cls, ids, styles):
    low = ttype.lower()
    return {"id": pid, "text_type": ttype, "syllabus_class": int(scls),
            "words": "150-220" if int(scls) == int(cls) else "120-180",
            "question_ids": list(ids), "skills": uniq(styles),
            "allow_table": any(k in low for k in ("time-table", "timetable", "menu"))}


def reading_rows(sec, start, level, cls, rng):
    n = int(sec["questions"])
    t = sec.get("topics") or {}
    cur, prev = list(t.get("current") or []), list(t.get("previous") or [])
    npass = max(1, n // 5)
    sizes = [5] * npass
    sizes[-1] += n - 5 * npass
    pool = cur[:] or prev[:]
    rng.shuffle(pool)
    types = [(pool[k % len(pool)], cls) for k in range(npass)]
    if int(level) == 1 and prev and npass >= 2:
        pr = [p for p in prev if any(x in p.lower() for x in ("stor", "anecdote", "invitation"))] or prev
        types[1] = (rng.choice(pr), cls - 1)
    rows, passages, i = [], [], start
    for k, (tt, scls) in enumerate(types):
        pid = "P%d" % (k + 1)
        ts = style_of(tt)["text_styles"]
        ids, sty = [], []
        for j in range(sizes[k]):
            r = make_row(i, sec, tt, scls)
            r["passage_id"] = pid
            r["style"] = ts[j % len(ts)]
            rows.append(r)
            ids.append(i)
            sty.append(r["style"])
            i += 1
        passages.append(_passage(pid, tt, scls, cls, ids, sty))
    return rows, passages


def build_mock(exam, level, cls, seed):
    lv = get_level(exam, level, cls)
    rows, passages = [], []
    for s, e, sec in section_ranges(lv):
        no = int(sec["no"])
        rng = random.Random(seed + "|S%d" % no)
        ach = bool(sec.get("achievers"))
        if _is_reading(sec):
            secrows, pp = reading_rows(sec, s, level, cls, rng)
            passages += pp
        else:
            t = sec.get("topics") or {}
            cur, prev = list(t.get("current") or []), list(t.get("previous") or [])
            n5, n4 = class_split(sec, level)
            must = ["Reading Comprehension"] if (exam == "IEO" and ach and "Reading Comprehension" in cur) else []
            p5 = pick_topics(rng, [x for x in cur if x not in must], n5, must=must)
            p4 = pick_topics(rng, prev, n4, avoid=set(p5)) if n4 else []
            items = [(x, cls) for x in p5] + [(x, cls - 1) for x in p4]
            items.sort(key=lambda it: (anchor_index(it[0], cur), 0 if it[1] == cls else 1))
            secrows = [make_row(s + k, sec, tp, sc) for k, (tp, sc) in enumerate(items)]
        if len(secrows) != e - s + 1:
            die("section %d: built %d rows, expected %d" % (no, len(secrows), e - s + 1))
        for r, d in zip(secrows, difficulty_list(rng, len(secrows), ach)):
            r["difficulty"] = d
        rows += secrows
    return lv, rows, passages


def sections_from_rows(rows, short):
    secs = []
    for r in rows:
        last = secs[-1] if secs else None
        if last and last["no"] == r["section"] and last["achievers"] == r["achievers"]:
            last["questions"] += 1
            last["end"] = r["id"]
        else:
            secs.append({"no": r["section"], "name": r["section_name"],
                         "short_name": short.get(r["section_name"], r["section_name"]),
                         "questions": 1, "marks_each": r["marks"], "achievers": r["achievers"],
                         "start": r["id"], "end": r["id"]})
    return secs


def _home(exam, t, cls):
    hl, hs = topic_home_section(exam, t, cls)
    hl = int(hl or 1)
    try:
        lv = get_level(exam, hl, cls)
    except Exception:
        hl, lv = 1, get_level(exam, 1, cls)
    sec = section_by_no(lv, hs) if hs else None
    sec = sec or {"no": hs or 1, "name": "Practice", "marks_each": 1}
    return hl, int(sec.get("no") or 1), sec


def build_practice(exam, cls, topics, n, ach_arg, seed):
    rng = random.Random("%s|P" % seed)
    n = int(n)
    if n < 1:
        die("--count must be at least 1")
    info = []
    for t in topics:
        hl, hs, sec = _home(exam, t, cls)
        info.append((hl, hs, t, sec, int(topic_syllabus_class(exam, t, cls))))
    info.sort(key=lambda x: (x[0], x[1]))
    elig = [x for x in info if x[4] == int(cls) and not _is_reading(x[3])]
    A = ach_arg if ach_arg is not None else (0 if n < 6 else max(2, rhalf(0.15 * n)))
    if A and not elig:
        warn("no current-class, non-reading topic for Achievers questions; using 0")
        A = 0
    A = max(0, min(int(A), n))
    m = n - A
    if m < len(info):
        warn("only %d normal questions for %d topics; some topics get none" % (m, len(info)))
    base, extra = divmod(m, len(info))
    groups, rows, secmap = [], [], {}
    for k, (hl, hs, t, sec, scls) in enumerate(info):
        cnt = base + (1 if k < extra else 0)
        if not cnt:
            continue
        sno = secmap.setdefault((hl, hs), len(secmap) + 1)
        grp = []
        for _ in range(cnt):
            r = make_row(0, sec, t, scls)
            r.update({"marks": 1, "achievers": False, "section": sno})
            grp.append(r)
        groups.append((t, sec, grp))
        rows += grp
    easy = min(rhalf(0.3 * n), m)
    hard = max(0, min(max(rhalf(0.25 * n), A) - A, m - easy))
    labels = ["easy"] * easy + ["hard"] * hard + ["medium"] * (m - easy - hard)
    rng.shuffle(labels)
    for r, d in zip(rows, labels):
        r["difficulty"] = d
    order = {"easy": 0, "medium": 1, "hard": 2}
    rows = []
    for _t, _s, grp in groups:
        grp.sort(key=lambda r: order[r["difficulty"]])
        rows += grp
    if A:
        lv1 = get_level(exam, 1, cls)
        asec = next((sc for _a, _b, sc in section_ranges(lv1) if sc.get("achievers")), None)
        asec = asec or {"no": 0, "name": "Achievers Section", "marks_each": 3, "achievers": True}
        ano = len(secmap) + 1
        for j in range(A):
            _hl, _hs, t, _sec, scls = elig[j % len(elig)]
            r = make_row(0, asec, t, scls)
            r.update({"achievers": True, "marks": asec.get("marks_each", 3), "difficulty": "hard", "section": ano})
            rows.append(r)
    for i, r in enumerate(rows):
        r["id"] = i + 1
    passages, pn = [], 0
    for t, sec, grp in groups:
        if not _is_reading(sec):
            continue
        chunks = [grp[i:i + 5] for i in range(0, len(grp), 5)]
        if len(chunks) > 1 and len(chunks[-1]) < 3:
            chunks[-2] += chunks.pop()
        ts = style_of(t)["text_styles"]
        for ch in chunks:
            pn += 1
            pid = "P%d" % pn
            for j, r in enumerate(ch):
                r["passage_id"] = pid
                r["style"] = ts[j % len(ts)]
            passages.append(_passage(pid, t, ch[0]["syllabus_class"], cls,
                                     [r["id"] for r in ch], [r["style"] for r in ch]))
    return rows, passages


def practice_parts(rows):
    n = len(rows)
    if n <= 25:
        return [("all", [r["id"] for r in rows])]
    k = int(math.ceil(n / 20.0))
    size = int(math.ceil(n / float(k)))
    parts, cur = [], []
    for idx, r in enumerate(rows):
        nxt = rows[idx + 1] if idx + 1 < n else None
        cur.append(r["id"])
        inside = nxt is not None and r["passage_id"] and nxt["passage_id"] == r["passage_id"]
        if len(cur) >= size and not inside:
            parts.append(cur)
            cur = []
    if cur:
        parts.append(cur)
    return [("p%d" % (j + 1), ids) for j, ids in enumerate(parts)]


def mock_parts(rows):
    secs = []
    for r in rows:
        if not secs or secs[-1][0] != r["section"]:
            secs.append((r["section"], []))
        secs[-1][1].append(r)
    parts = []
    for no, grp in secs:
        n = len(grp)
        k = int(math.ceil(n / 20.0))
        base, extra = divmod(n, k)
        pos = 0
        for j in range(k):
            sz = base + (1 if j < extra else 0)
            ids = [r["id"] for r in grp[pos:pos + sz]]
            pos += sz
            parts.append(["s%d" % no + ("abcdefgh"[j] if k > 1 else ""), ids, no, no, k > 1])
    out = []
    for p in parts:
        if out and not out[-1][4] and not p[4] and len(out[-1][1]) + len(p[1]) <= 10:
            q = out[-1]
            q[1] = q[1] + p[1]
            q[3] = p[3]
            q[0] = "s%d-%d" % (q[2], q[3])
            continue
        out.append(p)
    return [(p[0], p[1]) for p in out]


def ref_path(prefix):
    hits = sorted(glob.glob(os.path.join(str(REFERENCES_DIR), prefix + "*")))
    if hits:
        return hits[0]
    warn("reference %s* is missing from %s" % (prefix, REFERENCES_DIR))
    return os.path.join(str(REFERENCES_DIR), prefix + "*")


RULES = [
    "Write ORIGINAL questions only. Never copy or closely paraphrase SOF, MTG or any published question.",
    "Exactly one option is correct; the other three are plausible distractors built from common Class 5 mistakes.",
    "Check every calculation with python3 before writing it; the explanation must show the working.",
    "Use Indian context (Rs symbol, lakh/crore, Indian names, places, festivals) and Class 5 vocabulary.",
    "Follow each row exactly: topic, syllabus_class, difficulty, format, format_instructions, style, prefix and tips.",
    "If figure is true, include an SVG figure (see reference 04) that the question genuinely needs.",
    "Write NOT as <b>NOT</b>.",
    "Put the correct answer at the row's assigned letter (answer).",
    "Allowed tags only: b, i, u, sup, sub, br.",
    "Tokens: [[frac:3/4]], [[frac:2 3/4]], [[blank]], [[blank:(i)]]. Put spaces around < and > used in text.",
    "Output JSON only, as described in reference 03, saved to the spec's output path; then run validate_cmd and fix every error.",
]
EXAM_RULES = {
    "IMO": [],
    "IEO": ["Use modern standard English usage.",
            "Never use continuous forms of stative verbs (know, like, want, believe, own, ...).",
            "Choose will/can/would strictly by context so that only one option fits.",
            "Reading passages must be original."],
    "ICSO": ["Refer only to Windows 11 and MS-Office 2016 (menus, shortcuts, features)."],
}


def _count(rows, key):
    out = {}
    for r in rows:
        v = r.get(key)
        out[v] = out.get(v, 0) + 1
    return out


def _fmt_of(r):
    f = r.get("format")
    return f if f and f != "standard" else ""


def brief(r):
    b = ["Q%d" % r["id"], str(r["section_name"]),
         "%s (Class %s syllabus)" % (r["topic"], r["syllabus_class"]), r["difficulty"]]
    if r.get("achievers"):
        b.append("ACHIEVERS, %s marks" % r["marks"])
    if r.get("passage_id"):
        b.append("Passage %s" % r["passage_id"])
    if r.get("figure"):
        b.append("FIGURE (SVG)")
    if r.get("style"):
        b.append("Style: %s" % r["style"])
    if _fmt_of(r):
        b.append("Format: %s" % _fmt_of(r))
    b.append("Answer: %s" % r["answer"])
    return " | ".join(b)


def _arg(a, *names, **kw):
    for n in names:
        v = getattr(a, n, None)
        if v is not None:
            return v
    return kw.get("default")


def avoid_similar(slug, topics):
    try:
        hist = history_questions(exclude_slug=slug) or []
    except Exception as e:
        warn("could not read history: %s" % e)
        return {}
    out = {}
    for h in hist:
        if not isinstance(h, dict) or h.get("topic") not in topics:
            continue
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(h.get("text") or ""))).strip()[:160]
        lst = out.setdefault(h["topic"], [])
        if txt and len(lst) < 6 and txt not in lst:
            lst.append(txt)
    return out


def write_specs(meta, rows, passages, parts, wd, bp_path):
    home = prep_home()
    validator = os.path.join(str(SCRIPTS_DIR), "validate_paper.py")
    refs = [ref_path("03"), ref_path("04")]
    avoid = avoid_similar(meta["slug"], set(r["topic"] for r in rows))
    out = []
    for pname, ids in parts:
        idset = set(ids)
        prows = [r for r in rows if r["id"] in idset]
        pids = set(r["passage_id"] for r in prows if r.get("passage_id"))
        ppass = [p for p in passages if p["id"] in pids]
        pjson = str(wd / ("part_%s.json" % pname))
        pspec = str(wd / ("part_%s.spec.json" % pname))
        ptopics = sorted(set(r["topic"] for r in prows))
        spec = dict(meta)
        spec.update({"part": pname, "ids": list(ids), "output": pjson, "references": refs,
                     "rules": RULES, "exam_rules": EXAM_RULES.get(meta["exam"], []),
                     "avoid_similar": dict((t, avoid[t]) for t in ptopics if t in avoid),
                     "validate_cmd": "OLYMPIAD_PREP_HOME='%s' python3 '%s' '%s' --blueprint '%s' --part %s"
                                     % (home, validator, pjson, bp_path, pname),
                     "passages": ppass, "rows": prows})
        write_json(pspec, spec)
        out.append({"name": pname, "ids": list(ids), "json": pjson, "spec": pspec})
    return out


def print_table(rows):
    fmt = "%-4s %-4s %-28s %-3s %-6s %-3s %s"
    print(fmt % ("Q", "Sec", "Topic", "Cls", "Diff", "Fig", "Tag"))
    for r in rows:
        tag = [r.get("passage_id") or "", "ACH" if r.get("achievers") else "",
               _fmt_of(r) or str(r.get("style") or "")[:30]]
        print(fmt % (r["id"], r["section"], str(r["topic"])[:28], r["syllabus_class"],
                     r["difficulty"], "Y" if r.get("figure") else "-", " ".join(t for t in tag if t)))


def _longest_run(seq):
    best, cur, prev = 0, 0, object()
    for x in seq:
        cur = cur + 1 if x == prev else 1
        prev = x
        best = max(best, cur)
    return best


def _counts(rows, key):
    c = _count(rows, key)
    return ", ".join("%s=%d" % (k, c[k]) for k in sorted(c, key=str))


def print_summary(meta, rows, passages, parts, bp_path):
    n = len(rows)
    cls = int(meta["class"])
    prev = sum(1 for r in rows if int(r["syllabus_class"]) == cls - 1)
    print("")
    print("%s  [%s]  seed=%s" % (meta["title"], meta["slug"], meta["seed"]))
    print("Questions: %d   Marks: %s   Time: %s min" % (n, meta["total_marks"], meta["time_minutes"]))
    print("Class %d syllabus: %d (%.0f%%)" % (cls - 1, prev, 100.0 * prev / max(n, 1)))
    print("Difficulty: " + _counts(rows, "difficulty"))
    print("Figures: " + _counts(rows, "figure"))
    print("Formats: " + _counts(rows, "format"))
    print("Answers: %s (longest run %d)" % (_counts(rows, "answer"), _longest_run([r["answer"] for r in rows])))
    for p in passages:
        q = p.get("question_ids") or []
        if q:
            print("Passage %s: Q%d-Q%d, %s, Class %s, %s words"
                  % (p["id"], min(q), max(q), p.get("text_type"), p.get("syllabus_class"), p.get("words")))
    print("Parts: " + ", ".join("%s(%d)" % (pt["name"], len(pt["ids"])) for pt in parts))
    print("Blueprint: %s" % bp_path)
    for pt in parts:
        print("  %s -> %s" % (pt["spec"], pt["json"]))
    print("Next: one writer agent per spec; each must pass its validate_cmd.")


def list_topics(exam, cls):
    for ex in ([norm_exam(exam)] if exam else list(EXAMS)):
        print("== %s Class %d ==" % (ex, cls))
        for t in all_topics(ex, cls):
            name = t if isinstance(t, str) else (t.get("name") or t.get("topic"))
            try:
                hl, secno, sec = _home(ex, name, cls)
                where = "L%d S%d %s" % (hl, secno, sec.get("short_name") or sec.get("name"))
            except Exception:
                where = "?"
            print("  %-45s %s" % (name, where))


def _short_names(exam, cls, mode, lv, rows):
    short = {}
    if mode == "mock":
        for _s, _e, sec in section_ranges(lv):
            short[sec["name"]] = sec.get("short_name") or sec["name"]
        return short
    for t in sorted(set(r["topic"] for r in rows)):
        try:
            _hl, _no, sec = _home(exam, t, cls)
        except Exception:
            continue
        short[sec["name"]] = sec.get("short_name") or sec["name"]
    return short


def main():
    a = parse_args()
    exam = norm_exam(a.exam) if getattr(a, "exam", None) else None
    cls = int(_arg(a, "cls", "class_", "klass", default=5))
    if getattr(a, "list_topics", False):
        list_topics(exam, cls)
        return 0
    seed = _arg(a, "seed")
    seed = str(seed) if seed not in (None, "") else str(random.SystemRandom().randint(100000, 999999))
    mode = _arg(a, "mode", default="mock")
    level = int(_arg(a, "level", default=1))
    topics, name, lv = [], None, None
    try:
        if mode == "mock":
            lv, rows, passages = build_mock(exam, level, cls, seed)
            time_minutes = int(lv.get("time_minutes") or 60)
        else:
            topics = resolve_topics(_arg(a, "topics", default=[]), exam, cls)
            if not topics:
                die("no valid topics; run with --list-topics to see the choices")
            rows, passages = build_practice(exam, cls, topics, int(_arg(a, "count", default=20)),
                                            _arg(a, "achievers", "ach"), seed)
            name = practice_name(topics, _arg(a, "set_name", "name"))
            time_minutes = rhalf(1.2 * len(rows))
    except (KeyError, ValueError, LookupError) as e:
        die(str(e) if isinstance(e, ValueError) else "%s: %s" % (type(e).__name__, e))
    assign_fig_style(rows, seed)
    assign_prefixes(rows, exam, level)
    if mode == "mock":
        mock_formats(rows, exam, seed)
    else:
        practice_formats(rows, exam, seed)
    for r, ans in zip(rows, assign_answers(len(rows), seed)):
        r["answer"] = ans
    for r in rows:
        r["brief"] = brief(r)
    paper_no = int(_arg(a, "paper_no", default=0) or next_paper_no(exam, mode, level, cls, name))
    slug = paper_slug(exam, cls, level, mode, paper_no, name)
    wd = work_dir(slug)
    bp = wd / "blueprint.json"
    clean = bool(_arg(a, "clean", default=False))
    if bp.exists() and not clean:
        die("%s exists; rerun with --clean to rebuild it (this deletes its part files)" % bp)
    if clean:
        for f in list(wd.iterdir()):
            if f.is_file():
                f.unlink()
    meta = {"slug": slug, "exam": exam, "class": cls, "level": level, "mode": mode,
            "paper_no": paper_no, "set_name": name, "name": name, "topics": topics,
            "created": today(), "seed": seed, "time_minutes": time_minutes,
            "total_questions": len(rows), "total_marks": sum(int(r.get("marks") or 1) for r in rows)}
    meta["title"] = paper_title(meta)
    plist = mock_parts(rows) if mode == "mock" else practice_parts(rows)
    parts = write_specs(meta, rows, passages, plist, wd, str(bp))
    bpd = dict(meta)
    bpd.update({"sections": sections_from_rows(rows, _short_names(exam, cls, mode, lv, rows)),
                "passages": passages, "rows": rows, "parts": parts,
                "rules": RULES, "exam_rules": EXAM_RULES.get(exam, [])})
    write_json(str(bp), bpd)
    print_table(rows)
    print_summary(meta, rows, passages, parts, str(bp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
