#!/usr/bin/env python3
"""Merge the writer sub-agents' part files into one validated paper JSON.

    python3 assemble_paper.py --blueprint <blueprint.json | its folder | slug>
                              [--out PATH] [--force] [--strict]
                              [--no-history] [--no-record] [--student LABEL]

1. Loads blueprint.json and every part file listed in blueprint["parts"].
2. Keeps the question ids each part owns; reports missing ids or broken files.
3. Merges passages and directions, adding a direction for any passage
   that has none.
4. Copies section, topic, class, difficulty and marks from the blueprint rows.
5. Validates the merged paper with validate_paper.py against the blueprint.
6. Saves <papers>/<slug>.json and records it in the question history.

--student picks the child whose papers/ and history are used (default: the
blueprint's student).

Exit codes: 0 = saved, 1 = problems found (nothing saved), 2 = bad arguments.
"""
import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from sof_common import (base_home, die, papers_dir, read_json,  # noqa: E402
                        record_paper, set_student, student_label, student_slug,
                        today, work_dir, write_json)
import validate_paper  # noqa: E402

META_KEYS = ("slug", "exam", "class", "level", "mode", "paper_no", "set_name",
             "name", "title", "topics", "seed", "time_minutes",
             "total_questions", "total_marks", "sections", "created")
# Keys that belong to the writers' spec rows, never to a finished question.
SPEC_ONLY_KEYS = ("brief", "style", "tips", "prefix", "format_instructions")
FAR = 10 ** 6


def as_int(v, default=None):
    if isinstance(v, bool):
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def blank(v):
    return v is None or (isinstance(v, str) and not v.strip())


def canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def compact_ids(ids):
    """[1, 2, 3, 5, 7, 8] -> '1-3, 5, 7-8'."""
    ids = sorted(set(ids))
    out, i = [], 0
    while i < len(ids):
        j = i
        while j + 1 < len(ids) and ids[j + 1] == ids[j] + 1:
            j += 1
        out.append(str(ids[i]) if i == j else "%d-%d" % (ids[i], ids[j]))
        i = j + 1
    return ", ".join(out)


def academic_year(d=None):
    d = d or _dt.date.today()
    y = d.year if d.month >= 4 else d.year - 1
    return "%d-%02d" % (y, (y + 1) % 100)


def part_ids(part):
    return [i for i in (as_int(x) for x in part.get("ids") or []) if i is not None]


def resolve_blueprint(arg):
    p = Path(arg).expanduser()
    if p.is_dir():
        p = p / "blueprint.json"
    if p.is_file():
        return p.resolve()
    if "/" not in arg:
        cand = work_dir(arg, create=False) / "blueprint.json"
        if cand.is_file():
            return cand
        if not student_label():
            hits = sorted(base_home().glob("students/*/work/%s/blueprint.json" % arg))
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                die("%s exists for several children (%s) - add --student LABEL"
                    % (arg, ", ".join(h.parents[2].name for h in hits)))
    die("blueprint not found: %s (give blueprint.json, its folder or the "
        "paper slug)" % arg)


def load_part(part):
    """Return (doc, problem) for one part file."""
    raw = part.get("json")
    if blank(raw) or not Path(raw).is_file():
        return None, "file not found: %s" % raw
    try:
        return validate_paper.load_doc(str(raw))
    except SystemExit:
        return None, "cannot read %s" % raw


def collect_parts(bp):
    """Return (parts, problems, notes); parts = [(part, doc, {qid: q})]."""
    parts, problems, notes = [], [], []
    for part in bp.get("parts") or []:
        name = part.get("name", "?")
        want = set(part_ids(part))
        doc, problem = load_part(part)
        if doc is None:
            problems.append("part %s: %s" % (name, problem))
            continue
        got = {}
        for q in doc.get("questions") or []:
            qid = as_int(q.get("id")) if isinstance(q, dict) else None
            if qid is None:
                problems.append("part %s: a question has no integer id" % name)
            elif qid not in want:
                notes.append("part %s: ignored Q%d (not one of this part's "
                             "questions)" % (name, qid))
            elif qid in got:
                problems.append("part %s: Q%d appears more than once"
                                % (name, qid))
            else:
                got[qid] = q
        missing = sorted(want - set(got))
        if missing:
            problems.append("part %s: missing questions %s"
                            % (name, compact_ids(missing)))
        parts.append((part, doc, got))
    return parts, problems, notes

FORMAT_NAMES = ("standard", "not", "statements", "table_i_ii", "roman_combo", "match", "statements_c3")


def norm_answer(a):
    if isinstance(a, str):
        s = a.strip().replace("(", "").replace(")", "").replace(".", "").strip().upper()
        if len(s) == 1 and s in "ABCD":
            return s
    return a


def pid_key(pid):
    if pid is None or isinstance(pid, bool):
        return None
    k = str(pid).strip()
    return k or None


def question_pid(q, rows, qid):
    pid = q.get("passage_id")
    if blank(pid):
        pid = (rows.get(qid) or {}).get("passage_id")
    return pid_key(pid)


def passage_owners(parts, rows):
    owner, first = {}, {}
    for part, _doc, got in parts:
        for qid, q in got.items():
            key = question_pid(q, rows, qid)
            if key is None:
                continue
            owner.setdefault(key, part.get("name"))
            first[key] = min(first.get(key, FAR), qid)
    return owner, first


def merge_passages(parts, rows, bp_ids, notes):
    owner, first = passage_owners(parts, rows)
    versions, order = {}, []
    for part, doc, _got in parts:
        for p in doc.get("passages") or []:
            if not isinstance(p, dict):
                notes.append("part %s: ignored a passage that is not an object" % part.get("name"))
                continue
            key = pid_key(p.get("id"))
            if key is None:
                notes.append("part %s: ignored a passage without an id" % part.get("name"))
                continue
            p = dict(p, id=bp_ids.get(key, p.get("id")))
            if key not in versions:
                versions[key] = []
                order.append(key)
            versions[key].append((part.get("name"), p))
    merged = []
    for key in order:
        vs = versions[key]
        chosen = None
        for name, p in vs:
            if name == owner.get(key):
                chosen = p
                break
        if chosen is None:
            chosen = vs[0][1]
        if len(set(canon(p) for _n, p in vs)) > 1:
            notes.append("passage %s: parts %s sent different versions; kept the one from part %s"
                         % (key, ", ".join(n for n, _p in vs), owner.get(key) or vs[0][0]))
        merged.append(chosen)
    merged.sort(key=lambda p: first.get(pid_key(p.get("id")), FAR))
    return merged


def merge_directions(parts, bp_ids, notes):
    out, seen = [], set()
    for part, doc, _got in parts:
        ids = part_ids(part)
        lo, hi = (min(ids), max(ids)) if ids else (None, None)
        for d in doc.get("directions") or []:
            if not isinstance(d, dict):
                notes.append("part %s: ignored a direction that is not an object" % part.get("name"))
                continue
            d = dict(d)
            for k in ("from", "to"):
                v = as_int(d.get(k))
                if v is not None:
                    d[k] = v
            if "passage_id" in d:
                key = pid_key(d.get("passage_id"))
                if key is None:
                    d.pop("passage_id")
                else:
                    d["passage_id"] = bp_ids.get(key, d["passage_id"])
            f, t = as_int(d.get("from")), as_int(d.get("to"))
            if lo is not None and f is not None and t is not None and (t < lo or f > hi):
                notes.append("part %s: dropped a direction for Q%s-%s (outside this part)"
                             % (part.get("name"), f, t))
                continue
            c = canon(d)
            if c in seen:
                continue
            seen.add(c)
            out.append(d)
    return out


def add_passage_directions(questions, directions, notes):
    uses = {}
    for q in questions:
        key = pid_key(q.get("passage_id"))
        if key is None:
            continue
        if key not in uses:
            uses[key] = (q["passage_id"], [])
        uses[key][1].append(q["id"])
    covered = set()
    for d in directions:
        key = pid_key(d.get("passage_id"))
        if key is not None:
            covered.add(key)
    for key, (pid, ids) in uses.items():
        if key in covered:
            continue
        lo, hi = min(ids), max(ids)
        match = None
        for d in directions:
            if pid_key(d.get("passage_id")) is None and as_int(d.get("from")) == lo \
                    and as_int(d.get("to")) == hi:
                match = d
                break
        if match is not None:
            match["passage_id"] = pid
            notes.append("linked the direction for Q%d-%d to passage %s" % (lo, hi, key))
        else:
            text = ("Read the passage and answer Q%d to Q%d." % (lo, hi) if hi > lo
                    else "Read the passage and answer Q%d." % lo)
            directions.append({"from": lo, "to": hi, "text": text, "passage_id": pid})
            notes.append("added a direction for passage %s (Q%s)" % (key, compact_ids(ids)))
    directions.sort(key=lambda d: (as_int(d.get("from"), FAR), as_int(d.get("to"), FAR)))
    return directions


def build_questions(parts, rows, secs, bp_ids, notes):
    questions = []
    for _part, _doc, got in parts:
        for qid, q in got.items():
            r = rows.get(qid)
            if r is None:
                notes.append("Q%d has no blueprint row; kept the writer's metadata" % qid)
                r = {}
            sno = as_int(r.get("section"), as_int(q.get("section")))
            s = secs.get(sno) or {}
            out = {"id": qid}
            out["section"] = sno if sno is not None else q.get("section")
            out["section_name"] = s.get("name") or r.get("section_name") or q.get("section_name")
            for k in ("topic", "syllabus_class", "difficulty"):
                v = r.get(k)
                out[k] = q.get(k) if blank(v) else v
            out["achievers"] = bool(s["achievers"]) if "achievers" in s else bool(q.get("achievers"))
            out["marks"] = s.get("marks_each") or r.get("marks") or q.get("marks")
            fmt = q.get("format")
            if blank(fmt) and r.get("format") in FORMAT_NAMES:
                fmt = r.get("format")
            if not blank(fmt):
                out["format"] = fmt
            for k, v in q.items():
                if k in out or k in SPEC_ONLY_KEYS or k == "format":
                    continue
                if k == "figure" and (v is False or blank(v)):
                    continue
                out[k] = v
            if "answer" in out:
                out["answer"] = norm_answer(out["answer"])
            pid = q.get("passage_id")
            if blank(pid):
                pid = r.get("passage_id")
            key = pid_key(pid)
            if key is None:
                out.pop("passage_id", None)
            else:
                out["passage_id"] = bp_ids.get(key, pid)
            questions.append(out)
    questions.sort(key=lambda q: q["id"])
    return questions


def print_part_map(bp):
    print("Parts (question ids -> spec):")
    for part in bp.get("parts") or []:
        print("  %-4s Q%s  %s" % (part.get("name"), compact_ids(part_ids(part)),
                                  part.get("spec", "")))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Merge the writer parts of a paper into one checked "
                    "paper JSON.")
    ap.add_argument("--blueprint", required=True,
                    help="blueprint.json, its folder, or the paper slug")
    ap.add_argument("--out", help="output path (default: <papers>/<slug>.json)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing paper")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors")
    ap.add_argument("--no-history", action="store_true",
                    help="skip the repeat check against earlier papers")
    ap.add_argument("--no-record", action="store_true",
                    help="do not add the paper to history")
    ap.add_argument("--student",
                    help="child's label (default: the blueprint's student)")
    args = ap.parse_args(argv)
    set_student(args.student)

    bp_path = resolve_blueprint(args.blueprint)
    bp = read_json(bp_path)
    if not isinstance(bp, dict) or not bp.get("rows") or not bp.get("parts"):
        die("%s has no rows or parts - re-run blueprint.py" % bp_path)
    bp_student = str(bp.get("student") or "").strip()
    if bp_student:
        if args.student is None and not student_label():
            set_student(bp_student)
            print("NOTE: using student '%s' from the blueprint" % bp_student)
        elif student_slug() != student_slug(bp_student):
            print("WARNING: blueprint was made for '%s' but the student is %s"
                  % (bp_student, ("'%s'" % student_label()) if student_label()
                     else "the default child"))
    slug = bp.get("slug") or bp_path.parent.name
    out = (Path(args.out).expanduser() if args.out
           else papers_dir() / ("%s.json" % slug))
    if out.exists() and not args.force:
        print("ERROR: %s already exists. Use --force to overwrite it." % out)
        return 1

    rows, secs, bp_ids = {}, {}, {}
    for r in bp["rows"]:
        i = as_int(r.get("id"))
        if i is not None:
            rows[i] = r
    for s in bp.get("sections") or []:
        n = as_int(s.get("no"))
        if n is not None:
            secs[n] = s
    for p in bp.get("passages") or []:
        if isinstance(p, dict) and not blank(p.get("id")):
            bp_ids[str(p["id"]).strip()] = p["id"]

    parts, problems, notes = collect_parts(bp)
    for n in notes:
        print("NOTE: %s" % n)
    if problems:
        for p in problems:
            print("ERROR: %s" % p)
        print_part_map(bp)
        print("Fix the part files above (re-run the writer for that part), "
              "then run this again.")
        return 1

    notes = []
    questions = build_questions(parts, rows, secs, bp_ids, notes)
    passages = merge_passages(parts, rows, bp_ids, notes)
    directions = merge_directions(parts, bp_ids, notes)
    directions = add_passage_directions(questions, directions, notes)
    for n in notes:
        print("NOTE: %s" % n)

    paper = {}
    for k in META_KEYS:
        if k in bp:
            paper[k] = bp[k]
    paper["slug"] = slug
    if student_label():
        paper["student"] = student_label()
    paper.setdefault("created", today())
    paper["academic_year"] = academic_year()
    paper["assembled"] = _dt.datetime.now().isoformat(timespec="seconds")
    paper["passages"] = passages
    paper["directions"] = directions
    paper["questions"] = questions

    draft = bp_path.parent / "paper.draft.json"
    write_json(draft, paper)
    vargs = [str(draft), "--blueprint", str(bp_path)]
    if args.strict:
        vargs.append("--strict")
    if args.no_history:
        vargs.append("--no-history")
    try:
        rc = validate_paper.main(vargs)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    if rc:
        print_part_map(bp)
        print("Not saved. Fix the parts named in the errors above, then run "
              "this again. Draft kept: %s" % draft)
        return 1

    write_json(out, paper)
    try:
        draft.unlink()
    except OSError:
        pass
    if not args.no_record:
        record_paper(paper, str(out), {})
    print("Saved %s" % out)
    print("%s - %d questions, %s marks, %s minutes"
          % (paper.get("title", slug), len(questions),
             paper.get("total_marks", "?"), paper.get("time_minutes", "?")))
    nxt = str(out) if args.out else slug
    if student_label():
        nxt += " --student '%s'" % student_label()
    print("Next: python3 %s %s" % (SCRIPTS / "render_paper.py", nxt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
