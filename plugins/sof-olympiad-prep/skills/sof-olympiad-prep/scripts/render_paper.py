#!/usr/bin/env python3
"""Render an assembled SOF-style paper JSON into print-ready A4 PDFs.

Outputs (in --out-dir, default: $OLYMPIAD_OUT_DIR, else ~/Downloads):
  <slug>.pdf              question paper (student view - no answers)
  <slug>_Answer_Key.pdf   answers grid, topic summary, explanations
  <slug>_OMR.pdf          OMR answer sheet + parent score box (skip: --no-omr)

Usage:
  render_paper.py PAPER_JSON_OR_SLUG [--out-dir DIR] [--no-omr] [--no-record]
                  [--html-only] [--force] [--preview] [--student LABEL]

--student picks the child whose papers/history are used (default: the child the
paper was made for).

HTML sources are kept in the paper's work folder. PDFs are printed with headless
Chrome/Edge/Chromium; page footers are stamped with PyMuPDF when it is installed.
Without a browser, the HTML files are copied to the output folder instead.
"""
import argparse, html, math, os, re, shutil, sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from sof_common import (LETTERS, default_out_dir, die, find_browser, get_exam,  # noqa: E402
    get_level, html_to_pdf, load_paper, marks_for, max_marks, paper_footer_label,
    paper_title, question_figures, record_paper, render_markup, set_student, strip_markup,
    student_view, svg_check, svg_for_html, work_dir)

try:
    import pymupdf as fitz  # PyMuPDF (optional: footers, verification, previews)
except Exception:  # pragma: no cover
    try:
        import fitz  # PyMuPDF older than 1.24.3; newer releases print a deprecation notice on stdout
    except Exception:
        fitz = None

esc = html.escape
ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"]
ROMAN_UP = [r.upper() for r in ROMAN]
DISCLAIMER = "Original practice paper modelled on the SOF pattern; not an official SOF paper."

CSS = """
@page { size: A4; margin: 12mm 12mm 16mm 12mm; }
* { -webkit-print-color-adjust: exact; print-color-adjust: exact; box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
/* Symbols: "SOF Shapes" takes all geometric shapes and misc symbols from one symbol font, so full,
   half and outline shapes match in size; the symbol fonts after the text fonts cover the rest
   (Windows, macOS, Linux). Without them Chrome picks a fallback font per line, so the same symbol
   can print in two sizes on one page. */
@font-face { font-family: "SOF Shapes"; src: local("Segoe UI Symbol"), local("Apple Symbols"),
  local("DejaVu Sans"); unicode-range: U+25A0-25FF, U+2600-26FF, U+2B00-2BFF; }
body { font-family: "SOF Shapes", "Helvetica Neue", Helvetica, Arial, "Segoe UI Symbol",
  "Apple Symbols", "Zapf Dingbats", "DejaVu Sans", sans-serif; font-size: 10.5pt; line-height: 1.35;
  color: #1b1b1b; }
svg { font-family: "SOF Shapes", Arial, "Segoe UI Symbol", "Apple Symbols", "Zapf Dingbats",
  "DejaVu Sans", sans-serif; }
.hdr { display: flex; align-items: stretch; border-bottom: 3px solid #e8731a;
  padding-bottom: 6px; margin-bottom: 8px; }
.badge { width: 96px; min-height: 52px; background: #1f2a44; color: #fff; text-align: center;
  border-radius: 0 0 16px 16px; font-weight: 800; display: flex; flex-direction: column;
  justify-content: center; margin-right: 12px; flex: none; }
.badge .c { font-size: 8.5pt; letter-spacing: 3px; }
.badge .n { font-size: 21pt; line-height: 1.05; }
.htitle { flex: 1; display: flex; flex-direction: column; justify-content: center; min-width: 0; }
.htitle .t { font-size: 17pt; font-weight: 800; color: #1f2a44; letter-spacing: .4px; line-height: 1.15; }
.htitle .t.long { font-size: 13pt; }
.htitle .s { font-size: 9.5pt; color: #555; margin-top: 3px; }
.tiles { display: flex; gap: 4px; align-items: center; flex: none; margin-left: 8px; }
.tile { width: 26px; height: 30px; background: #e8731a; color: #fff; font-weight: 800; font-size: 13pt;
  display: flex; align-items: center; justify-content: center; border-radius: 4px; }
.tile:nth-child(even) { background: #1f2a44; }
.info { background: #fdf3d0; border: 1.5px solid #e0b03a; border-radius: 8px; padding: 7px 12px;
  margin: 6px 0 10px; font-size: 9.5pt; break-inside: avoid; }
.info h3 { margin: 0 0 4px; font-size: 10.5pt; color: #1f2a44; }
.info table { border-collapse: collapse; margin: 4px 0; }
.info td, .info th { border: 1px solid #d9b65a; padding: 1px 8px; text-align: center; }
.info th { background: #f7e3a1; }
.info .l { text-align: left; }
.info ul { margin: 2px 0 2px 16px; padding: 0; font-size: 8.5pt; }
.fill { display: flex; gap: 14px; margin-top: 8px; }
.fill span { flex: 1; border-bottom: 1px solid #8a7a4a; padding-bottom: 1px; }
.disc { font-size: 8pt; color: #7a5b00; margin-top: 5px; font-style: italic; }
.banner { background: #1f2a44; color: #fff; font-weight: 800; font-size: 10.5pt; letter-spacing: 1px;
  padding: 3px 10px; margin: 10px 0 7px; border-left: 7px solid #e8731a; break-after: avoid; }
.dir { margin: 4px 0 4px; break-after: avoid; }
.dir b { color: #1f2a44; }
.passage { border: 1px solid #c9cfdc; background: #f6f8fc; border-radius: 6px; padding: 6px 10px;
  margin: 2px 0 8px; text-align: justify; break-after: avoid; }
.passage .pt { text-align: center; font-weight: 700; margin-bottom: 3px; }
.passage .pfig { text-align: center; }
.passage .tbl { margin: 4px auto 2px; }
.dfig { break-after: avoid; }
.q { display: flex; gap: 6px; margin: 0 0 9px; break-inside: avoid; }
.qn { min-width: 26px; font-weight: 800; color: #c0392b; flex: none; }
.qb { flex: 1; min-width: 0; }
.stem { margin-bottom: 3px; }
.qfig { margin: 4px 0; }
.qfig svg { max-width: 100%; height: auto; }
.frow { display: flex; gap: 12px; align-items: flex-start; }
.frow .fl { flex: 1; min-width: 0; }
.frow .fr { max-width: 42%; flex: none; }
.items { margin: 2px 0 3px; }
.items .it { margin: 1px 0 1px 8px; }
.items ul { margin: 1px 0 1px 22px; padding: 0; }
.tbl { border-collapse: collapse; margin: 4px 0; font-size: 9.5pt; }
.tbl th, .tbl td { border: 1px solid #777; padding: 2px 9px; text-align: center; }
.tbl th { background: #e9edf5; }
.tbl.mt td { text-align: left; }
.cap { font-size: 9pt; font-style: italic; margin-top: 3px; }
.opts { display: grid; gap: 2px 12px; margin-top: 3px; }
.opts.row { grid-template-columns: repeat(4, 1fr); }
.opts.grid { grid-template-columns: repeat(2, 1fr); }
.opts.column { grid-template-columns: 1fr; }
.opt { display: flex; gap: 4px; align-items: flex-start; min-width: 0; }
.ol { font-weight: 700; flex: none; }
.opt svg { max-width: 100%; height: auto; vertical-align: top; }
.otbl { border-collapse: collapse; margin-top: 3px; font-size: 10pt; }
.otbl th, .otbl td { border: 1px solid #999; padding: 1px 10px; text-align: left; }
.otbl th { background: #eef1f6; }
.frac { display: inline-flex; flex-direction: column; vertical-align: middle; text-align: center;
  font-size: .9em; line-height: 1.1; margin: 0 2px; }
.frac .num { border-bottom: 1px solid currentColor; padding: 0 2px; }
.frac .den { padding: 0 2px; }
.mixed { white-space: nowrap; }
.mixed .whole { margin-right: 1px; }
.blank { display: inline-block; min-width: 46px; border-bottom: 1px solid #333; height: 1em; }
.blank.labeled { min-width: 58px; height: auto; text-align: center; font-size: .85em; color: #333; }
.end { text-align: center; margin-top: 12px; font-weight: 700; color: #1f2a44; letter-spacing: 2px; }
.akgrid { width: 100%; border-collapse: collapse; margin: 4px 0 10px; }
.akgrid td { border: 1px solid #c9cfdc; padding: 3px 2px; text-align: center; font-size: 10pt; width: 10%; }
.akgrid .an { color: #c0392b; font-weight: 700; }
.ex { margin: 0 0 7px; break-inside: avoid; }
.ex .eh { font-weight: 700; }
.ex .qn2 { color: #c0392b; }
.ex .tag { font-size: 8pt; color: #555; background: #eef1f6; border-radius: 3px; padding: 0 5px;
  margin-left: 6px; font-weight: 400; }
.ex .et { margin-left: 22px; }
.sum { width: 100%; border-collapse: collapse; font-size: 9.5pt; margin-bottom: 6px; }
.sum th, .sum td { border: 1px solid #999; padding: 2px 6px; }
.sum th { background: #e9edf5; }
.sum .c { text-align: center; }
.omr-det { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px 12px; margin: 8px 0; }
.omr-det div { border: 1.2px solid #1f2a44; border-radius: 4px; padding: 3px 6px; height: 36px;
  font-size: 8.5pt; color: #555; }
.omr-det .w2 { grid-column: span 2; }
.omr-ins { font-size: 8.5pt; border: 1px solid #e0b03a; background: #fdf3d0; border-radius: 6px;
  padding: 4px 10px; margin: 6px 0 10px; }
.omr-ins ol { margin: 2px 0 2px 18px; padding: 0; }
.omr-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0 8px; border: 2px solid #1f2a44;
  padding: 8px; border-radius: 6px; break-inside: avoid; }
.omr-col { display: flex; flex-direction: column; }
.omr-r { display: flex; align-items: center; gap: 4px; height: 22px; }
.omr-r .n { width: 22px; font-weight: 700; text-align: right; margin-right: 2px; font-size: 9pt; }
.omr-r.ach .n { color: #c0392b; }
.bub { width: 15px; height: 15px; border: 1.2px solid #1f2a44; border-radius: 50%; font-size: 7pt;
  display: flex; align-items: center; justify-content: center; color: #1f2a44; }
.score { margin-top: 12px; border: 2px solid #e8731a; border-radius: 6px; padding: 6px 10px; break-inside: avoid; }
.score h3 { margin: 0 0 4px; font-size: 10.5pt; color: #1f2a44; }
.score table { width: 100%; border-collapse: collapse; }
.score td { border: 1px solid #ccc; padding: 4px 6px; font-size: 9.5pt; height: 30px; vertical-align: top; }
"""

def rm(s):
    return render_markup("" if s is None else str(s))


def _plain(v):
    if isinstance(v, dict):
        return strip_markup(str(v.get("text") or ""))
    if isinstance(v, list):
        return " ".join(strip_markup(str(x)) for x in v)
    return strip_markup(str(v))


def opt_html(v):
    if isinstance(v, dict):
        parts = []
        if v.get("svg"):
            parts.append(svg_for_html(v["svg"]))
        if v.get("text"):
            parts.append(rm(v["text"]))
        return " ".join(parts)
    if isinstance(v, list):
        return ", ".join(rm(x) for x in v)
    return rm(v)


def options_html(q, right_fig=False):
    opts = q.get("options") or {}
    keys = [k for k in LETTERS if k in opts]
    hdrs = q.get("option_headers")
    if hdrs:
        rows = []
        for k in keys:
            v = opts[k]
            cells = v if isinstance(v, list) else [v]
            rows.append("<tr><td class='ol'>(%s)</td>%s</tr>" % (k, "".join("<td>%s</td>" % opt_html(c) for c in cells)))
        return "<table class='otbl'><tr><th></th>%s</tr>%s</table>" % (
            "".join("<th>%s</th>" % rm(h) for h in hdrs), "".join(rows))
    lay = q.get("option_layout") or "auto"
    if lay not in ("row", "grid", "column"):
        has_svg = any(isinstance(opts[k], dict) and opts[k].get("svg") for k in keys)
        longest = max([len(_plain(opts[k])) for k in keys] or [0])
        lay = "row" if (has_svg or longest <= 16) else ("grid" if longest <= 38 else "column")
    if right_fig and lay == "row":
        lay = "grid"
    return "<div class='opts %s'>%s</div>" % (lay, "".join(
        "<div class='opt'><span class='ol'>(%s)</span><div style='min-width:0'>%s</div></div>" % (k, opt_html(opts[k]))
        for k in keys))


def items_html(q):
    items = q.get("items") or []
    if not items:
        return ""
    style = q.get("item_style") or "roman"
    if style == "bullet":
        return "<div class='items'><ul>%s</ul></div>" % "".join("<li>%s</li>" % rm(x) for x in items)
    out = []
    for i, x in enumerate(items):
        if style == "statement":
            lab = "<b>Statement-%s:</b> " % (ROMAN_UP[i] if i < len(ROMAN_UP) else i + 1)
        elif style == "statement_num":
            lab = "<b>Statement %d :</b> " % (i + 1)
        elif style == "roman":
            lab = "(%s) " % (ROMAN[i] if i < len(ROMAN) else i + 1)
        elif style == "letter":
            lab = "(%s) " % chr(97 + i)
        else:
            lab = ""
        out.append("<div class='it'>%s%s</div>" % (lab, rm(x)))
    return "<div class='items'>%s</div>" % "".join(out)


def table_html(t, cls="tbl"):
    if not t:
        return ""
    hdrs = t.get("headers") or []
    head = ("<tr>%s</tr>" % "".join("<th>%s</th>" % rm(h) for h in hdrs)) if hdrs else ""
    body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % rm(c) for c in (r if isinstance(r, list) else [r]))
                   for r in (t.get("rows") or []))
    cap = ("<div class='cap'>%s</div>" % rm(t["caption"])) if t.get("caption") else ""
    return "<table class='%s'>%s%s</table>%s" % (cls, head, body, cap)


def match_html(m):
    if not m:
        return ""
    left, right = m.get("left") or [], m.get("right") or []
    rows = []
    for i in range(max(len(left), len(right))):
        lc = ("<b>%s.</b> %s" % ("PQRSTUVW"[i], rm(left[i]))) if i < len(left) else ""
        rc = ("<b>%d.</b> %s" % (i + 1, rm(right[i]))) if i < len(right) else ""
        rows.append("<tr><td>%s</td><td>%s</td></tr>" % (lc, rc))
    return "<table class='tbl mt'><tr><th>%s</th><th>%s</th></tr>%s</table>" % (
        rm(m.get("left_title") or "Column I"), rm(m.get("right_title") or "Column II"), "".join(rows))


def fig_html(svg, cls="qfig"):
    return ("<div class='%s'>%s</div>" % (cls, svg_for_html(svg))) if svg else ""


def question_html(q):
    pos = q.get("figure_position") or "below"
    if pos not in ("above", "right"):
        pos = "below"
    fig = fig_html(q.get("figure"))
    parts = []
    if fig and pos == "above":
        parts.append(fig)
    if q.get("question"):
        parts.append("<div class='stem'>%s</div>" % rm(q["question"]))
    parts.append(items_html(q))
    parts.append(table_html(q.get("table")))
    parts.append(match_html(q.get("match")))
    if fig and pos == "below":
        parts.append(fig)
    if q.get("question_after"):
        parts.append("<div class='stem'>%s</div>" % rm(q["question_after"]))
    if fig and pos == "right":
        body = "<div class='frow'><div class='fl'>%s%s</div><div class='fr'>%s</div></div>" % (
            "".join(parts), options_html(q, right_fig=True), fig)
    else:
        body = "".join(parts) + options_html(q)
    return "<div class='q'><div class='qn'>%s.</div><div class='qb'>%s</div></div>" % (esc(str(q.get("id"))), body)


def direction_html(d):
    a, b = d.get("from"), d.get("to")
    rng = str(a) if (b is None or a == b) else "%s-%s" % (a, b)
    return "<div class='dir'><b>Directions (%s):</b> %s</div>%s" % (
        rng, rm(d.get("text")), fig_html(d.get("figure"), "dfig qfig"))


def passage_html(p):
    paras = [x.strip() for x in re.split(r"\n\s*\n", str(p.get("text") or "")) if x.strip()]
    title = ("<div class='pt'>%s</div>" % rm(p["title"])) if p.get("title") else ""
    return "<div class='passage'>%s%s%s%s</div>" % (
        title, fig_html(p.get("figure"), "pfig qfig"),
        "".join("<p style='margin:0 0 4px'>%s</p>" % rm(x) for x in paras), table_html(p.get("table")))


def banner_html(sec):
    return "<div class='banner'>SECTION %s : %s</div>" % (
        esc(str(sec.get("no", ""))), esc(str(sec.get("name") or "").upper()))


GENERAL_RULES = [
    "Each question has four options (A), (B), (C) and (D), of which only ONE is correct.",
    "Mark answers on the OMR sheet by completely darkening one bubble with a blue/black ball-point pen.",
    "There is no negative marking, so attempt every question.",
    "Use the margins of this booklet for rough work. Calculators and other gadgets are not allowed.",
]


def sections_of(paper):
    secs = paper.get("sections") or []
    if not secs:
        n = len(paper.get("questions", []))
        secs = [{"no": 1, "name": "Questions", "questions": n, "marks_each": 1, "start": 1, "end": n}]
    return secs


def section_for(secs, q):
    no = q.get("section")
    if no is not None:
        for s in secs:
            if str(no) in (str(s.get("no")), str(s.get("name")), str(s.get("short_name"))):
                return s
    qid = int(q.get("id", 0))
    for s in secs:
        if int(s.get("start", 0)) <= qid <= int(s.get("end", 0)):
            return s
    return None


def topic_label(t):
    t = str(t or "").strip()
    if t and " " not in t and "_" in t:
        t = t.replace("_", " ")
        t = t[:1].upper() + t[1:]
    return t


def header_html(paper, kind=""):
    exam = str(paper.get("exam", ""))
    try:
        full = get_exam(exam, paper.get("class", 5)).get("full_name") or exam
    except Exception:
        full = exam
    bits = [kind, paper_title(paper), "Level %s" % paper.get("level", 1), paper.get("academic_year")]
    sub = " &middot; ".join(esc(str(b)) for b in bits if b)
    tiles = "".join("<div class='tile'>%s</div>" % esc(ch) for ch in exam.upper() if ch.isalnum())
    return ("<div class='hdr'><div class='badge'><span class='c'>CLASS</span><span class='n'>%s</span></div>"
            "<div class='htitle'><div class='t%s'>%s</div><div class='s'>%s</div></div>"
            "<div class='tiles'>%s</div></div>") % (
        esc(str(paper.get("class", 5))), " long" if len(full) > 32 else "", esc(full.upper()), sub, tiles)


def info_box_html(paper):
    secs = sections_of(paper)
    total = paper.get("total_marks") or max_marks(paper)
    nq = len(paper.get("questions", []))
    rows = []
    for s in secs:
        cnt, me = int(s.get("questions") or 0), int(s.get("marks_each") or 1)
        rows.append("<tr><td class='l'>Section %s: %s</td><td>%s&ndash;%s</td><td>%d</td><td>%d</td><td>%d</td></tr>" % (
            esc(str(s.get("no"))), esc(str(s.get("name"))), s.get("start"), s.get("end"), cnt, me, cnt * me))
    rows.append("<tr><th class='l'>Total</th><th></th><th>%d</th><th></th><th>%d</th></tr>" % (nq, int(total)))
    table = ("<table><tr><th class='l'>Section</th><th>Q. Nos.</th><th>Questions</th><th>Marks each</th>"
             "<th>Marks</th></tr>%s</table>") % "".join(rows)
    # paper["exam_rules"] (in older papers) holds writer-only notes, never student instructions.
    rules = GENERAL_RULES
    topics = ""
    if paper.get("mode") == "practice" and paper.get("topics"):
        names = [topic_label(t.get("name") or t.get("id")) if isinstance(t, dict) else topic_label(t)
                 for t in paper["topics"]]
        topics = "<div><b>Topics covered:</b> %s</div>" % esc(", ".join(n for n in names if n))
    fill = ("<div class='fill'><span>Name:</span><span>Date:</span><span>Start time:</span>"
            "<span>End time:</span><span>Score: &nbsp;&nbsp;&nbsp;&nbsp; / %d</span></div>") % int(total)
    return ("<div class='info'><h3>Time: %s minutes &nbsp;|&nbsp; Questions: %d &nbsp;|&nbsp; Maximum Marks: %d</h3>"
            "%s%s<ul>%s</ul>%s<div class='disc'>%s</div></div>") % (
        esc(str(paper.get("time_minutes") or 60)), nq, int(total), table, topics,
        "".join("<li>%s</li>" % rm(r) for r in rules), fill, esc(DISCLAIMER))


def html_doc(title, body):
    return ("<!DOCTYPE html>\n<html lang='en'><head><meta charset='utf-8'><title>%s</title>"
            "<style>%s</style></head><body>%s</body></html>\n") % (esc(title), CSS, body)


def paper_doc(paper):
    sv = student_view(paper)
    secs = sections_of(sv)
    dirs = {}
    for d in sv.get("directions") or []:
        dirs.setdefault(int(d.get("from") or 0), []).append(d)
    passages = dict((p.get("id"), p) for p in (sv.get("passages") or []))
    shown, cur = set(), None
    out = [header_html(sv), info_box_html(sv)]
    for q in sv.get("questions", []):
        qid = int(q.get("id", 0))
        sec = section_for(secs, q)
        if sec is not None and sec is not cur:
            out.append(banner_html(sec))
            cur = sec
        for d in dirs.get(qid, []):
            out.append(direction_html(d))
            pid = d.get("passage_id")
            if pid in passages and pid not in shown:
                out.append(passage_html(passages[pid]))
                shown.add(pid)
        pid = q.get("passage_id")
        if pid in passages and pid not in shown:
            out.append(passage_html(passages[pid]))
            shown.add(pid)
        out.append(question_html(q))
    out.append("<div class='end'>*** END OF PAPER ***</div>")
    return html_doc(paper_title(sv), "".join(out))


def answer_key_doc(paper):
    qs = paper.get("questions", [])
    cells = ["<td>%s. <span class='an'>%s</span></td>" % (esc(str(q.get("id"))), esc(str(q.get("answer", "?"))))
             for q in qs]
    rows = []
    for i in range(0, len(cells), 10):
        part = cells[i:i + 10]
        rows.append("<tr>%s</tr>" % "".join(part + ["<td></td>"] * (10 - len(part))))
    grid = "<table class='akgrid'>%s</table>" % "".join(rows)
    stats, order = {}, []
    for q in qs:
        t = topic_label(q.get("topic")) or "General"
        if t not in stats:
            stats[t] = {"n": 0, "m": 0, "ids": []}
            order.append(t)
        stats[t]["n"] += 1
        stats[t]["m"] += marks_for(paper, q)
        stats[t]["ids"].append(str(q.get("id")))
    summ = ("<table class='sum'><tr><th>Topic</th><th class='c'>Questions</th><th class='c'>Marks</th>"
            "<th>Question numbers</th></tr>%s</table>") % "".join(
        "<tr><td>%s</td><td class='c'>%d</td><td class='c'>%d</td><td>%s</td></tr>" % (
            esc(t), stats[t]["n"], stats[t]["m"], esc(", ".join(stats[t]["ids"]))) for t in order)
    ex = []
    for q in qs:
        ans = str(q.get("answer", "?"))
        atxt = _plain((q.get("options") or {}).get(ans, "")).strip()
        atxt = (" &ndash; %s" % esc(atxt)) if atxt and len(atxt) <= 70 else ""
        tag = " &middot; ".join(esc(str(x)) for x in [topic_label(q.get("topic")), q.get("difficulty"),
                                                       "Achievers" if q.get("achievers") else ""] if x)
        ex.append("<div class='ex'><div class='eh'><span class='qn2'>Q%s.</span> Answer: (%s)%s"
                  "<span class='tag'>%s</span></div><div class='et'>%s</div></div>" % (
                      esc(str(q.get("id"))), esc(ans), atxt, tag, rm(q.get("explanation") or "")))
    body = (header_html(paper, "Answer Key") + "<div class='banner'>ANSWERS AT A GLANCE</div>" + grid +
            "<div class='banner'>TOPIC COVERAGE</div>" + summ +
            "<div class='banner'>STEP-BY-STEP EXPLANATIONS</div>" + "".join(ex) +
            "<div class='disc' style='text-align:center'>%s</div>" % esc(DISCLAIMER))
    return html_doc(paper_title(paper) + " - Answer Key", body)


def omr_doc(paper):
    qs = paper.get("questions", [])
    per = max(1, int(math.ceil(len(qs) / 5.0)))
    cols = []
    for c in range(5):
        rows = []
        for q in qs[c * per:(c + 1) * per]:
            bubs = "".join("<span class='bub'>%s</span>" % L for L in LETTERS)
            rows.append("<div class='omr-r%s'><span class='n'>%s</span>%s</div>" % (
                " ach" if q.get("achievers") else "", esc(str(q.get("id"))), bubs))
        cols.append("<div class='omr-col'>%s</div>" % "".join(rows))
    secs = sections_of(paper)
    ach = [s for s in secs if s.get("achievers")]
    ach_li = ("<li>Question numbers in <b style='color:#c0392b'>red</b> are from the Achievers Section "
              "(%s marks each).</li>" % esc(str(ach[0].get("marks_each")))) if ach else ""
    det = ("<div class='omr-det'><div class='w2'>Student's name</div><div>Class / Section</div>"
           "<div class='w2'>School</div><div>Date</div><div class='w2'>Paper: <b>%s</b></div>"
           "<div>Roll no.</div></div>") % esc(paper_footer_label(paper))
    ins = ("<div class='omr-ins'><b>How to fill this OMR sheet</b><ol>"
           "<li>Use a blue/black ball-point pen and darken ONE bubble completely, like this: &#9679;</li>"
           "<li>Ticks, crosses, half-filled bubbles or two bubbles for one question are treated as wrong.</li>"
           "<li>There is no negative marking &ndash; attempt every question.</li>%s</ol></div>") % ach_li
    total = paper.get("total_marks") or max_marks(paper)
    srows = "".join("<tr><td>Section %s: %s (%s &times; %s)</td><td>Correct:</td><td>Marks:</td></tr>" % (
        esc(str(s.get("no"))), esc(str(s.get("name"))), esc(str(s.get("questions"))), esc(str(s.get("marks_each"))))
        for s in secs)
    srows += "<tr><td><b>Total</b> (out of %d)</td><td>Correct:</td><td>Marks:</td></tr>" % int(total)
    srows += "<tr><td colspan='3'>Time taken: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Parent's signature / remarks:</td></tr>"
    score = ("<div class='score'><h3>Score card (check with the Answer Key, or run score.py)</h3>"
             "<table>%s</table></div>") % srows
    body = (header_html(paper, "OMR Answer Sheet") + det + ins +
            "<div class='omr-grid'>%s</div>" % "".join(cols) + score)
    return html_doc(paper_title(paper) + " - OMR Sheet", body)


def check_svgs(paper):
    probs = []
    for q in paper.get("questions", []):
        for where, svg in question_figures(q):
            errs, _w = svg_check(svg)
            probs += ["Q%s (%s): %s" % (q.get("id"), where, e) for e in errs]
    for d in paper.get("directions") or []:
        if d.get("figure"):
            errs, _w = svg_check(d["figure"])
            probs += ["Directions %s-%s: %s" % (d.get("from"), d.get("to"), e) for e in errs]
    return probs


def stamp_footer(pdf, label):
    """Add 'label | Page i of n' at the foot of every page (needs PyMuPDF)."""
    if fitz is None:
        return False
    label = str(label).replace("\u2013", "-").replace("\u2014", "-")
    tmp = str(pdf) + ".tmp"
    try:
        doc = fitz.open(str(pdf))
        n = len(doc)
        for i in range(n):
            page = doc[i]
            page.insert_text((36, page.rect.height - 16), "%s  |  Page %d of %d" % (label, i + 1, n),
                             fontsize=7.5, color=(0.42, 0.42, 0.42))
        doc.save(tmp, garbage=3, deflate=True)
        doc.close()
        os.replace(tmp, str(pdf))
        return True
    except Exception as e:  # keep the unstamped PDF
        if os.path.exists(tmp):
            os.remove(tmp)
        print("note: could not add footer to %s (%s)" % (pdf, e), file=sys.stderr)
        return False


def verify_pdf(pdf):
    """Page count; None if missing/broken, -1 if it exists but pages cannot be counted."""
    p = Path(pdf)
    if not p.exists() or p.stat().st_size < 1024:
        return None
    if fitz is not None:
        try:
            d = fitz.open(str(p))
            n = len(d)
            d.close()
            return n
        except Exception:
            return None
    data = p.read_bytes()
    if not data.startswith(b"%PDF"):
        return None
    n = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))
    return n or -1


def preview_pngs(pdf, out_dir, pages=(0, 1)):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem, out = Path(pdf).stem, []
    if fitz is not None:
        try:
            doc = fitz.open(str(pdf))
            for i in pages:
                if i >= len(doc):
                    break
                page, mat = doc[i], fitz.Matrix(1.3, 1.3)
                pix = page.get_pixmap(matrix=mat) if hasattr(page, "get_pixmap") else page.getPixmap(matrix=mat)
                png = out_dir / ("%s_p%d.png" % (stem, i + 1))
                (pix.save if hasattr(pix, "save") else pix.writePNG)(str(png))
                out.append(str(png))
            doc.close()
            return out
        except Exception:
            out = []
    import subprocess
    png = out_dir / ("%s_p1.png" % stem)
    try:  # macOS fallback: first page only
        subprocess.run(["sips", "-s", "format", "png", str(pdf), "--out", str(png)],
                       check=True, capture_output=True, timeout=60)
        out.append(str(png))
    except Exception:
        pass
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Render a paper JSON into a question paper, answer key and OMR sheet (PDF).")
    ap.add_argument("paper", help="paper slug (e.g. IMO_Class5_Mock_Paper_01) or path to its JSON")
    ap.add_argument("--out-dir", help="where to write the PDFs (default: %s)" % default_out_dir())
    ap.add_argument("--no-omr", action="store_true", help="skip the OMR answer sheet")
    ap.add_argument("--no-record", action="store_true", help="do not add the paper to history.json")
    ap.add_argument("--html-only", action="store_true", help="write HTML files instead of PDFs")
    ap.add_argument("--force", action="store_true", help="overwrite existing files; ignore figure problems")
    ap.add_argument("--preview", action="store_true", help="also save PNG previews of the first pages")
    ap.add_argument("--student", help="child's label (default: the paper's student)")
    a = ap.parse_args(argv)

    set_student(a.student)
    try:
        paper, ppath = load_paper(a.paper, auto_student=(a.student is None))
    except ValueError as e:
        die(str(e))
    probs = check_svgs(paper)
    for p in probs:
        print("FIGURE: " + p, file=sys.stderr)
    if probs and not a.force:
        die("%d figure problem(s); fix the SVGs (or re-run with --force)" % len(probs))

    slug = paper["slug"]
    out_dir = Path(a.out_dir).expanduser() if a.out_dir else default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    wd = work_dir(slug)
    docs = [("paper", slug, paper_doc(paper), ""),
            ("answer_key", slug + "_Answer_Key", answer_key_doc(paper), " | Answer Key")]
    if not a.no_omr:
        docs.append(("omr", slug + "_OMR", omr_doc(paper), " | OMR Sheet"))

    browser = None if a.html_only else find_browser()
    if browser is None and not a.html_only:
        print("WARNING: Chrome/Edge/Chromium not found - writing HTML instead of PDF "
              "(set OLYMPIAD_BROWSER to the browser binary).", file=sys.stderr)
    ext = ".pdf" if browser else ".html"
    targets = [out_dir / (d[1] + ext) for d in docs]
    clash = [str(t) for t in targets if t.exists()]
    if clash and not a.force:
        die("already exists (use --force to overwrite): " + ", ".join(clash))

    label, files, ok_all, previews = paper_footer_label(paper), {}, True, []
    for (key, name, doc, suffix), target in zip(docs, targets):
        hp = wd / (name + ".html")
        hp.write_text(doc, encoding="utf-8")
        if not browser:
            shutil.copyfile(str(hp), str(target))
            files[key] = str(target)
            print("HTML  %s" % target)
            continue
        ok, msg = html_to_pdf(str(hp), str(target), browser)
        pages = verify_pdf(target) if ok else None
        if not ok or pages is None:
            ok_all = False
            print("ERROR rendering %s: %s (HTML kept at %s)" % (name, msg or "empty PDF", hp), file=sys.stderr)
            continue
        stamp_footer(target, label + suffix)
        files[key] = str(target)
        print("PDF   %s  (%s pages)" % (target, pages if pages > 0 else "?"))
        if a.preview:
            previews += preview_pngs(target, wd / "preview")
    for p in previews:
        print("PNG   %s" % p)
    if files and not a.no_record:
        record_paper(paper, ppath, files)
    if not ok_all:
        return 1
    print("Done: %d file(s) in %s" % (len(files), out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
