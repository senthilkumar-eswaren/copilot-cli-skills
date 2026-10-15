#!/usr/bin/env python3
"""Mark a finished SOF-style paper, keep a score log, and track weak topics.

Examples
  score.py mark IMO_Class5_Mock_Paper_01 --answers "DDCA-DAB..." --minutes 55
  score.py IMO_Class5_Mock_Paper_01 -a "1D 2D 3C 4A ..."     (mark is the default)
  score.py mark paper.json --answers-file answers.txt --dry-run
  score.py report [--exam IMO] [--student child3]
  score.py weak-topics --exam IMO        prints "Topic A; Topic B" for blueprint.py --topics

Answer formats
  * one letter per question, in order: A-D, and - _ . x ? for a skipped question
    (spaces, commas, ; and | are ignored, so "ABCD ABCD ..." is fine)
  * numbered pairs: "1A 2C 3- 4.B 5)D" - numbers not mentioned count as skipped
  * a file: .txt in either format above, or .json (list, string or {"1": "A", ...})
  * --answers - reads the answers from standard input
SOF papers have no negative marking: a wrong or skipped answer scores 0.

Children
  Each child has a separate score log. --student LABEL picks the child (before or
  after the subcommand): mark uses the paper's child by default; report and
  weak-topics use the default child unless --student is given.
"""
import argparse
import csv
import json
import os
import re
import shlex
import sys
import textwrap
from collections import OrderedDict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sof_common import (EXAMS, LETTERS, attempts_path, base_home, die,  # noqa: E402
                        get_level, load_paper, load_students, marks_for, norm_exam,
                        paper_footer_label, paper_title, prep_home, scores_csv_path,
                        set_student, strip_markup, student_desc, student_label,
                        student_slug, today, topic_lookup)

SUBCOMMANDS = ("mark", "report", "weak-topics")
CSV_FIELDS = ["date", "time", "slug", "exam", "mode", "level", "class", "paper_no",
              "title", "score", "max", "percent", "correct", "wrong", "skipped",
              "total", "minutes", "name"]
BLANK_CHARS = "-_.xX?"
BLANK_WORDS = ("", "skip", "skipped", "blank", "none", "null", "na", "n/a")
PAIR_RE = re.compile(r"(\d+)\s*[:.)=\-]?\s*([A-Da-d]|[-_.xX?])")
BANDS = ((90, "Outstanding"), (75, "Very good"), (60, "Good"),
         (40, "Needs more practice"))
BLUEPRINT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blueprint.py")


# ---------------------------------------------------------------- answers
def _letter(v, where):
    s = "" if v is None else str(v).strip()
    if s.lower() in BLANK_WORDS or (len(s) == 1 and s in BLANK_CHARS):
        return ""
    if len(s) == 1 and s.upper() in LETTERS:
        return s.upper()
    raise ValueError("invalid answer %r for %s (use A-D, or - for skipped)" % (s, where))


def _read_file(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if path.lower().endswith(".json"):
        try:
            return json.loads(raw)
        except ValueError as e:
            raise ValueError("answers file %s is not valid JSON: %s" % (path, e))
    return raw


def answer_source(args):
    """Return the raw answers: text, or a list/dict from a JSON file."""
    if args.answers_file:
        if args.answers_file == "-":
            return sys.stdin.read()
        p = os.path.expanduser(args.answers_file)
        if not os.path.isfile(p):
            raise ValueError("answers file not found: %s" % p)
        return _read_file(p)
    a = args.answers or ""
    if a.strip() == "-":
        return sys.stdin.read()
    p = os.path.expanduser(a.strip())
    if p and len(p) < 1024 and os.path.isfile(p):
        return _read_file(p)
    return a


def parse_answers(src, n):
    """Return n answers, each 'A'-'D' or '' for skipped."""
    if isinstance(src, dict) and "answers" in src:
        src = src["answers"]
    if isinstance(src, dict):
        ans = [""] * n
        for k, v in src.items():
            try:
                i = int(str(k).strip().lstrip("Qq"))
            except ValueError:
                raise ValueError("bad question number %r in the answers" % (k,))
            if not 1 <= i <= n:
                raise ValueError("Q%d is outside 1..%d" % (i, n))
            ans[i - 1] = _letter(v, "Q%d" % i)
        return ans
    if isinstance(src, list):
        if len(src) != n:
            raise ValueError("got %d answers, paper has %d (use - for skipped)" % (len(src), n))
        return [_letter(v, "Q%d" % (i + 1)) for i, v in enumerate(src)]
    text = str(src or "")
    if re.search(r"\d", text):
        ans, seen, left, pos = [""] * n, {}, [], 0
        for m in PAIR_RE.finditer(text):
            left.append(text[pos:m.start()])
            pos = m.end()
            i = int(m.group(1))
            if not 1 <= i <= n:
                raise ValueError("Q%d is outside 1..%d" % (i, n))
            a = _letter(m.group(2), "Q%d" % i)
            if i in seen and seen[i] != a:
                raise ValueError("Q%d answered twice (%s and %s)" % (i, seen[i] or "-", a or "-"))
            seen[i] = a
            ans[i - 1] = a
        left.append(text[pos:])
        junk = re.sub(r"[\s,;|Qq]+", "", "".join(left))
        if junk:
            raise ValueError("could not read %r in the answers (use pairs like 1A 2C 3-)" % junk[:30])
        if not seen:
            raise ValueError("no answers found")
        return ans
    s = re.sub(r"[\s,;|]+", "", text)
    if not s:
        raise ValueError("no answers given")
    if len(s) != n:
        raise ValueError("got %d answers, paper has %d (use - for skipped)" % (len(s), n))
    return [_letter(c, "Q%d" % (i + 1)) for i, c in enumerate(s)]


# ---------------------------------------------------------------- grading
def _qid(q):
    try:
        return int(q.get("id"))
    except (TypeError, ValueError):
        return 10 ** 6


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def _blank():
    return OrderedDict([("total", 0), ("correct", 0), ("wrong", 0), ("skipped", 0),
                        ("marks", 0), ("max", 0)])


def band(pct):
    for cut, label in BANDS:
        if pct >= cut:
            return label
    return "Revise the basics"


def check_paper(paper):
    qs = paper.get("questions") or []
    if not qs:
        raise ValueError("the paper has no questions - was it assembled?")
    if sorted(_qid(q) for q in qs) != list(range(1, len(qs) + 1)):
        raise ValueError("question ids are not 1..%d - re-run assemble_paper.py" % len(qs))
    for q in qs:
        if str(q.get("answer") or "").strip().upper() not in LETTERS:
            raise ValueError("Q%s has no answer key (A-D) - re-run assemble_paper.py" % q.get("id"))
    return len(qs)


def grade(paper, answers):
    """Return (result, review) - review lists (question, given, key, status) to go over."""
    qs = sorted(paper.get("questions") or [], key=_qid)
    names = {}
    for s in paper.get("sections") or []:
        try:
            names[int(s.get("no"))] = s.get("name") or s.get("short_name") or ""
        except (TypeError, ValueError):
            pass
    by_sec, by_top, per_q, review, tot = {}, OrderedDict(), [], [], _blank()
    for q, given in zip(qs, answers):
        key = str(q.get("answer")).strip().upper()
        m = int(marks_for(paper, q))
        status = "skipped" if not given else ("correct" if given == key else "wrong")
        got = m if status == "correct" else 0
        try:
            sno = int(q.get("section") or 0)
        except (TypeError, ValueError):
            sno = 0
        sname = q.get("section_name") or names.get(sno) or ("Section %d" % sno)
        topic = (q.get("topic") or "").strip() or "(no topic)"
        s = by_sec.get(sno)
        if s is None:
            s = by_sec[sno] = OrderedDict([("no", sno), ("name", sname)])
            s.update(_blank())
        t = by_top.get(topic)
        if t is None:
            t = by_top[topic] = OrderedDict([("topic", topic), ("section", sname)])
            t.update(_blank())
        for d in (s, t, tot):
            d["total"] += 1
            d[status] += 1
            d["marks"] += got
            d["max"] += m
        per_q.append([_qid(q), topic, sno, given, key, status, got])
        if status != "correct":
            review.append((q, given, key, status))
    for d in list(by_sec.values()) + list(by_top.values()):
        d["percent"] = _pct(d["correct"], d["total"])
    res = OrderedDict()
    for k, default in (("slug", ""), ("exam", ""), ("mode", "mock"), ("level", 1),
                       ("class", 5), ("paper_no", "")):
        v = paper.get(k)
        res[k] = default if v in (None, "") else v
    res["title"] = paper_title(paper)
    res["label"] = paper_footer_label(paper)
    res["score"], res["max"] = tot["marks"], tot["max"]
    res["percent"] = _pct(tot["marks"], tot["max"])
    for k in ("correct", "wrong", "skipped", "total"):
        res[k] = tot[k]
    res["band"] = band(res["percent"])
    res["time_limit"] = paper.get("time_minutes")
    res["by_section"] = [by_sec[k] for k in sorted(by_sec)]
    res["by_topic"] = sorted(by_top.values(), key=lambda d: (d["percent"], -d["total"], d["topic"]))
    res["per_question"] = per_q
    return res, review


# ---------------------------------------------------------------- printing
def _cut(s, w):
    s = str(s)
    return s if len(s) <= w else s[:w - 1] + "…"


def time_note(minutes, limit, total):
    if minutes is None:
        return ""
    if limit and minutes > limit:
        return (" Time: %d min - %d min over the %d-min limit. Aim for about %d seconds"
                " per question." % (minutes, minutes - limit, limit,
                                    round(limit * 60.0 / max(total, 1))))
    if limit:
        return " Time: %d of %d min." % (minutes, limit)
    return " Time: %d min." % minutes


def print_result(res, review, minutes=None, explanations=True):
    w = 70
    print("=" * w)
    print(" " + res["title"])
    if res["label"]:
        print(" " + res["label"])
    print("=" * w)
    print(" Score: %d / %d  (%.1f%%)  -  %s" % (res["score"], res["max"], res["percent"], res["band"]))
    print(" Correct %d | Wrong %d | Skipped %d | Questions %d" % (
        res["correct"], res["wrong"], res["skipped"], res["total"]))
    note = time_note(minutes, res.get("time_limit"), res["total"])
    if note:
        print(note)
    print("-" * w)
    print(" %-38s %4s %5s %5s %4s %7s" % ("Section", "Qs", "Right", "Wrong", "Skip", "Marks"))
    for s in res["by_section"]:
        print(" %-38s %4d %5d %5d %4d %7s" % (
            _cut("%d. %s" % (s["no"], s["name"]), 38), s["total"], s["correct"], s["wrong"],
            s["skipped"], "%d/%d" % (s["marks"], s["max"])))
    print("-" * w)
    missed = [t for t in res["by_topic"] if t["correct"] < t["total"]]
    if missed:
        print(" %-50s %4s %5s %5s" % ("Topics with mistakes (weakest first)", "Qs", "Right", "%"))
        for t in missed:
            print(" %-50s %4d %5d %4.0f%%" % (_cut(t["topic"], 50), t["total"], t["correct"],
                                              t["percent"]))
        rest = len(res["by_topic"]) - len(missed)
        if rest:
            print(" + %d other topic%s: all correct" % (rest, "" if rest == 1 else "s"))
    else:
        print(" All %d topics fully correct" % len(res["by_topic"]))
    print("-" * w)
    if not review:
        print(" All questions correct - excellent!")
    else:
        print(" Review - wrong and skipped questions")
        for q, given, key, status in review:
            what = ("your " + given) if status == "wrong" else "skipped"
            print(" Q%-3s [%s] %s, correct %s" % (q.get("id"), _cut(q.get("topic") or "-", 44),
                                                  what, key))
            if explanations:
                ex = re.sub(r"\s+", " ", strip_markup(q.get("explanation") or "")).strip()
                if len(ex) > 220:
                    ex = ex[:219].rstrip() + "…"
                if ex:
                    print(textwrap.fill(ex, width=w, initial_indent="      ",
                                        subsequent_indent="      "))
        if res["skipped"]:
            print(" Tip: SOF has no negative marking - in the exam, never leave a question blank.")
    print("=" * w)


# ---------------------------------------------------------------- logging
def load_attempts():
    p = str(attempts_path())
    out = []
    if not os.path.isfile(p):
        return out
    with open(p, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                print("warning: skipping unreadable line %d in %s" % (n, p), file=sys.stderr)
    return out


def _ends_without_newline(path):
    with open(path, "rb") as f:
        f.seek(-1, os.SEEK_END)
        return f.read(1) not in (b"\n", b"\r")


def log_attempt(res):
    """Append to scores.csv and attempts.jsonl; return (attempt_no, attempt_no_for_this_paper)."""
    csv_p, jl_p = str(scores_csv_path()), str(attempts_path())
    for d in {os.path.dirname(csv_p), os.path.dirname(jl_p)}:
        if d:
            os.makedirs(d, exist_ok=True)
    now = datetime.now()
    row = OrderedDict([("date", today()), ("time", now.strftime("%H:%M"))])
    for k in ("slug", "exam", "mode", "level", "class", "paper_no", "title", "score", "max"):
        row[k] = res[k]
    row["percent"] = "%.1f" % res["percent"]
    for k in ("correct", "wrong", "skipped", "total"):
        row[k] = res[k]
    row["minutes"] = "" if res.get("minutes") is None else res["minutes"]
    row["name"] = res.get("name") or ""
    header = None
    if os.path.isfile(csv_p) and os.path.getsize(csv_p) > 0:
        with open(csv_p, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), None)
        if header and _ends_without_newline(csv_p):
            with open(csv_p, "a", encoding="utf-8") as f:
                f.write("\n")
    with open(csv_p, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header or CSV_FIELDS, extrasaction="ignore",
                           lineterminator="\n")
        if not header:
            w.writeheader()
        w.writerow(row)
    rec = OrderedDict(row)
    rec["percent"] = res["percent"]
    rec["minutes"] = res.get("minutes")
    for k in ("label", "band", "time_limit", "answers", "by_section", "by_topic", "per_question"):
        rec[k] = res.get(k)
    with open(jl_p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    allp = load_attempts()
    return len(allp), sum(1 for a in allp if a.get("slug") == res["slug"])


# ---------------------------------------------------------------- progress
def _filter(attempts, exam=None, name=None):
    out = []
    for a in attempts:
        if exam and str(a.get("exam") or "").upper() != exam:
            continue
        if name and str(a.get("name") or "").strip().lower() != name.strip().lower():
            continue
        out.append(a)
    return out


def topic_stats(attempts, recent=10, min_qs=2):
    """Per-topic accuracy over the most recent attempts, weakest first."""
    agg = OrderedDict()
    for a in (attempts[-recent:] if recent and recent > 0 else attempts):
        for row in a.get("per_question") or []:
            try:
                topic, status = row[1], row[5]
            except (TypeError, IndexError):
                continue
            d = agg.setdefault(topic, OrderedDict([("topic", topic), ("total", 0), ("correct", 0)]))
            d["total"] += 1
            if status == "correct":
                d["correct"] += 1
    rows = [d for d in agg.values() if d["total"] >= max(min_qs, 1)]
    for d in rows:
        d["percent"] = _pct(d["correct"], d["total"])
    rows.sort(key=lambda d: (d["percent"], -d["total"], d["topic"]))
    return rows


def _known_topic(topic, exam, cls):
    try:
        return bool(topic_lookup(topic, exam, cls))
    except Exception:
        return False


def weak_list(rows, exam, cls, top, threshold):
    out = []
    for d in rows:
        if d["percent"] >= threshold or len(out) >= top:
            break
        if d["topic"] != "(no topic)" and _known_topic(d["topic"], exam, cls):
            out.append(d["topic"])
    return out


def _dq(s):
    return '"' + re.sub(r'([\\"$`])', r'\\\1', s) + '"'


def _student_opt():
    lab = student_label()
    return " --student " + shlex.quote(lab) if lab else ""


def _for_child():
    lab = student_label()
    return " for " + student_desc(lab) if lab else ""


def _nonempty(p):
    return p.is_file() and p.stat().st_size > 0


def _hint_other_children(file=None):
    """Point to the other children's logs when the selected child has none."""
    file = file or sys.stdout
    name, me, found = attempts_path().name, student_slug(), []
    root = base_home()
    if me and _nonempty(root / name):
        found.append("the default child (--student '')")
    sdir = root / "students"
    if sdir.is_dir():
        known = load_students()
        for d in sorted(sdir.iterdir()):
            if d.is_dir() and d.name != me and _nonempty(d / name):
                e = known.get(d.name)
                lab = (e.get("label") if isinstance(e, dict) else None) or d.name
                found.append("'%s' (--student %s)" % (lab, shlex.quote(lab)))
    if found:
        print("Attempts are logged for " + ", ".join(found) + ".", file=file)


def suggest_cmd(exam, cls, topics):
    bp, home = BLUEPRINT, os.path.expanduser("~")
    if bp.startswith(home + os.sep):
        bp = "~" + bp[len(home):]
    parts = ["python3", bp, "--exam", exam, "--mode", "practice"]
    try:
        if int(cls) != 5:
            parts += ["--class", str(cls)]
    except (TypeError, ValueError):
        pass
    lab = student_label()
    if lab:
        parts += ["--student", shlex.quote(lab)]
    # "; " because some topic names contain commas (e.g. "Length, Weight and Capacity")
    return " ".join(parts) + " --topics " + _dq("; ".join(topics))


def cmd_report(args):
    exam = norm_exam(args.exam) if args.exam else None
    atts = _filter(load_attempts(), exam, args.name)
    if not atts:
        print("No %sattempts logged yet%s in %s.\nMark a finished paper first:  score.py mark <paper>"
              ' --answers "DDCA-B..." --minutes 55%s' % (exam + " " if exam else "", _for_child(),
                                                         prep_home(), _student_opt()))
        _hint_other_children()
        return 0
    if student_label():
        print("Progress for %s" % student_desc(student_label()))
    exams = [e for e in EXAMS if any(a.get("exam") == e for a in atts)]
    exams += sorted(set(str(a.get("exam")) for a in atts) - set(exams))
    w = 70
    for e in exams:
        ea = [a for a in atts if str(a.get("exam")) == e]
        pcts = [float(a.get("percent") or 0) for a in ea]
        best = max(range(len(ea)), key=lambda i: pcts[i])
        mocks = sum(1 for a in ea if a.get("mode") == "mock")
        print("=" * w)
        print(" %s - %d attempt%s (%d mock, %d practice) | average %.1f%% | best %.1f%%" % (
            e, len(ea), "" if len(ea) == 1 else "s", mocks, len(ea) - mocks,
            sum(pcts) / len(pcts), pcts[best]))
        last = pcts[-5:]
        if len(last) >= 2:
            diff = last[-1] - last[0]
            trend = "improving" if diff > 3 else ("slipping" if diff < -3 else "steady")
            print(" Last %d: %s  (%s)" % (len(last), " > ".join("%.0f%%" % x for x in last), trend))
        print("-" * w)
        for a in ea[-5:]:
            mins = a.get("minutes")
            print(" %-10s %-40s %6s %6.1f%%%s" % (
                a.get("date") or "", _cut(a.get("title") or a.get("slug") or "", 40),
                "%s/%s" % (a.get("score"), a.get("max")), float(a.get("percent") or 0),
                ("  %s min" % mins) if mins not in (None, "") else ""))
        rows = topic_stats(ea, args.recent, args.min_qs)
        if not rows:
            continue
        print("-" * w)
        print(" Weakest topics (last %d attempt%s, %d+ questions each)" % (
            min(args.recent, len(ea)) if args.recent > 0 else len(ea),
            "" if len(ea) == 1 else "s", args.min_qs))
        for d in rows[:max(args.top, 1)]:
            flag = "   <- practise" if d["percent"] < args.threshold else ""
            print("  %4.0f%%  %3d/%-3d %s%s" % (d["percent"], d["correct"], d["total"],
                                                _cut(d["topic"], 44), flag))
        cls = ea[-1].get("class") or 5
        weak = weak_list(rows, e, cls, 4, args.threshold)
        if weak:
            print(" Suggested practice set:")
            print("   " + suggest_cmd(e, cls, weak))
        else:
            nxt = "a fresh full mock"
            try:
                get_level(e, 2, int(cls))
                nxt += ", or a Level 2 paper (--level 2) after qualifying"
            except (KeyError, TypeError, ValueError):
                pass
            print(" Every topic is at %g%% or better - next: %s." % (args.threshold, nxt))
    print("=" * w)
    return 0


def cmd_weak(args):
    exam = norm_exam(args.exam)
    ea = _filter(load_attempts(), exam, args.name)
    if not ea:
        print("No %s attempts logged yet%s - mark a paper first (score.py mark ...)."
              % (exam, _for_child()), file=sys.stderr)
        _hint_other_children(sys.stderr)
        return 1
    rows = topic_stats(ea, args.recent, args.min_qs)
    weak = weak_list(rows, exam, ea[-1].get("class") or 5, max(args.top, 1), args.threshold)
    if not weak:
        print("No %s topic below %g%% in the last %d attempts (use --threshold 100 to list the"
              " weakest anyway)." % (exam, args.threshold, min(args.recent, len(ea))
                                     if args.recent > 0 else len(ea)), file=sys.stderr)
        return 1
    print("; ".join(weak))
    return 0


# ---------------------------------------------------------------- marking
def cmd_mark(args):
    paper, _path = load_paper(args.paper, auto_student=(getattr(args, "student", None) is None))
    n = check_paper(paper)
    if args.minutes is not None and args.minutes <= 0:
        raise ValueError("--minutes must be a positive number")
    answers = parse_answers(answer_source(args), n)
    res, review = grade(paper, answers)
    res["minutes"] = args.minutes
    res["name"] = (args.name or student_label() or "").strip()
    res["answers"] = "".join(a or "-" for a in answers)
    logged = None if args.dry_run else log_attempt(res)
    if args.json:
        out = OrderedDict(res)
        if logged:
            out["attempt_no"] = logged[0]
        print(json.dumps(out, indent=2, ensure_ascii=False))
        if logged:
            print("Logged attempt #%d" % logged[0], file=sys.stderr)
        return 0
    print_result(res, review, args.minutes, not args.no_explanations)
    if logged:
        k, j = logged
        print("Logged attempt #%d%s%s in %s" % (k, (" (attempt #%d at this paper)" % j) if j > 1 else "",
                                               _for_child(), scores_csv_path()))
        so = _student_opt()
        print("Progress: score.py report%s  |  weak topics: score.py weak-topics --exam %s%s"
              % (so, res["exam"], so))
    else:
        print("(dry run - not logged)")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="score.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = argparse.ArgumentParser(add_help=False)
    sp.add_argument("--student", help="child's label ('' = the default child; default: the paper's"
                                      " child for mark, the default child for report and weak-topics)")
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("mark", parents=[sp], help="mark one attempt and log it (default command)")
    m.add_argument("paper", help="paper slug (e.g. IMO_Class5_Mock_Paper_01) or paper JSON path")
    g = m.add_mutually_exclusive_group(required=True)
    g.add_argument("-a", "--answers",
                   help='answers in order ("DDCA-B..."), pairs ("1D 2D 3C"), a file, or - (stdin)')
    g.add_argument("-f", "--answers-file", help="file with the answers (.txt or .json), or -")
    m.add_argument("-m", "--minutes", type=int, help="minutes taken (limit is usually 60)")
    m.add_argument("--name", default="", help="name stored with the attempt (default: the child's label)")
    m.add_argument("--dry-run", action="store_true", help="show the result but do not log it")
    m.add_argument("--json", action="store_true", help="print the result as JSON")
    m.add_argument("--no-explanations", action="store_true", help="list mistakes without explanations")
    m.set_defaults(func=cmd_mark)
    for name, hlp, func, top in (
            ("report", "progress per exam and the weakest topics", cmd_report, 5),
            ("weak-topics", 'print the weakest topics as "A; B" for blueprint.py --topics',
             cmd_weak, 4)):
        p = sub.add_parser(name, parents=[sp], help=hlp)
        p.add_argument("--exam", required=(name == "weak-topics"), help="IMO, IEO or ICSO")
        p.add_argument("--name", default="", help="only attempts logged with this name")
        p.add_argument("--top", type=int, default=top, help="how many topics (default %d)" % top)
        p.add_argument("--threshold", type=float, default=70.0,
                       help="a topic is weak below this accuracy %% (default 70)")
        p.add_argument("--min-qs", type=int, default=2,
                       help="ignore topics with fewer questions than this (default 2)")
        p.add_argument("--recent", type=int, default=10,
                       help="use the last N attempts per exam for topic stats (0 = all; default 10)")
        p.set_defaults(func=func)
    return ap


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    lead = []  # "--student X" given before the subcommand is moved after it
    while argv and (argv[0] == "--student" or argv[0].startswith("--student=")):
        if argv[0] != "--student":
            lead.append(argv.pop(0))
            continue
        if len(argv) < 2 or argv[1] in SUBCOMMANDS:
            die("--student needs a value (a child's label, or '' for the default child)")
        lead.append("--student=" + argv[1])
        del argv[:2]
    if not argv:
        build_parser().print_help()
        return 2
    if argv[0] not in SUBCOMMANDS and argv[0] not in ("-h", "--help"):
        argv.insert(0, "mark")
    if argv[0] in SUBCOMMANDS:
        argv[1:1] = lead
    fixed, i = [], 0
    while i < len(argv):
        t = argv[i]
        if t == "--student" and i + 1 < len(argv):
            fixed.append("--student=" + argv[i + 1])
            i += 2
            continue
        if t in ("-a", "--answers", "-f", "--answers-file") and i + 1 < len(argv):
            # glue the value on so answers starting with "-" (skipped Q1) are not read as options
            flag = "--answers=" if t in ("-a", "--answers") else "--answers-file="
            fixed.append(flag + argv[i + 1])
            i += 2
            continue
        fixed.append(t)
        i += 1
    args = build_parser().parse_args(fixed)
    set_student(getattr(args, "student", None))
    try:
        return args.func(args)
    except (ValueError, OSError) as e:
        die(str(e))


if __name__ == "__main__":
    sys.exit(main())
