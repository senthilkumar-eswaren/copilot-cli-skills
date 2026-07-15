# Document Assembly & DOCX/PDF Conversion Pipeline (tested, working)

This is the exact pipeline used successfully to assemble N independently-generated subject
Markdown files into one polished DOCX + PDF. Follow it in order; each step exists because of a
real failure mode hit the first time this was built (see inline notes).

## 0. Toolchain check (do this once, early, in parallel with launching content agents)

```bash
which pandoc textutil python3 2>&1
ls /Applications 2>&1 | grep -iE "chrome|word|libreoffice"
```

- If `pandoc` is missing: `brew install pandoc` (lightweight, no LaTeX needed — its built-in docx
  writer works standalone; for PDF we go via HTML + headless Chrome instead of a LaTeX engine).
- Chrome is used headless for HTML→PDF printing (reliable, respects CSS `page-break` rules).
  macOS `textutil` can convert docx↔rtf/html but not from Markdown directly, so it's not the primary
  path here — pandoc handles Markdown directly.
- `python3 -m pip install python-docx pypdf --quiet` — needed for page-break insertion and PDF
  verification respectively (install once, reuse).

## 1. Front matter file (write this yourself while agents run)

Create `00_front_matter.md` with: `# <TITLE>` (H1), a subtitle/school-name line, an **Exam
Timetable & Portions** table transcribed from the circular (Date/Subject/Portions/Marks/Duration),
a "How to Use This Guide" section, and CBSE general exam-writing tips.

**Do NOT start the file with pandoc title-block `%` lines** (`% Title` / `% Author` / `% Date` as
the first 3 lines) — combined with metadata passed via `--metadata` on the command line, or with a
later stray `---`, this reliably produces a cryptic `Error parsing YAML metadata` failure from
pandoc. Just use a plain `# Heading` and pass `--metadata title="..."` on the pandoc command line
instead.

**Avoid standalone horizontal-rule lines (`---` or `***` alone on a line)** anywhere in any source
file if possible. If used for visual separation, they must be stripped before running pandoc (see
step 4) because pandoc's Markdown reader will interpret a bare `---` appearing after a blank line
as the start of a new YAML metadata block and fail parsing the non-YAML content that follows. Table
separator rows like `|---|---|---:|` are a different syntax and are NOT affected — only bare
standalone `---` lines need stripping.

## 2. Per-subject extraction (after each agent finishes)

```bash
# Inspect the raw temp file first to find the real content start (usually line 4, but verify):
sed -n '1,6p' "$RAW_AGENT_OUTPUT_TMPFILE"
tail -n +4 "$RAW_AGENT_OUTPUT_TMPFILE" > "$DIR/NN_subject-slug.md"

# Find and strip any trailing conversational offer (varies in wording — search broadly):
grep -n "^If you want\|I can next\|I can also turn\|Would you like" "$DIR/NN_subject-slug.md"
# then trim the file to end just before that line, e.g.:
sed -i '' '<offer_line_start>,$d' "$DIR/NN_subject-slug.md"
```

Re-check every file afterward: `grep -ln "^If you want\|I can next\|I can also turn" "$DIR"/*.md`
should return nothing.

## 3. Heading normalization (critical — run before assembling)

Every agent invents its own heading-level scheme independently (some nest `# Chapter N` under
`## SUBJECT`, some use flat `##` for everything). A naive "renumber all levels by a fixed offset"
rule breaks because schemes are inconsistent per file. A naive "numbered title = chapter" regex
also breaks because some agents write individual Q&A questions as literal headings
(`## 1. What is business?`), which is textually identical in shape to a real numbered chapter title
(`## 1. Hornbill: The Portrait of a Lady`).

**Use this exact script** (save as `/tmp/normalize.py`, run once per subject file):

```python
import re, sys

H3_KEYWORDS = ['Chapter Overview', 'Detailed Notes', 'Key Formula', 'Key Definitions',
               'Golden Rules', 'Worked ', 'Fully Worked', 'Important Questions and Answers',
               'Previous Year', 'Quick Revision', 'Final Exam Tips', 'Last-Minute Exam Tips',
               'Most Important Must-Prepare', 'Sample 5-Mark', 'One-Line', 'Full Editing Exercise',
               'Key Literary Devices', 'Character Sketch', 'Difficult Words', 'Central Theme',
               'Detailed Summary', 'Author Introduction']
H4_KEYWORDS = ['Very Short Answer', 'Short Answer Question', 'Long Answer', 'Case Study',
               'Extract-Based', 'A. Very Short', 'B. Short Answer', 'C. Long Answer', 'D. Case Study']

CHAPTER_RE = re.compile(r'^(Chapter\s+\d+|Part\s+[AB]\b)', re.IGNORECASE)

# Per-file whitelist: ONLY populate this for a file where you've confirmed bare numbered titles
# (e.g. "1. Hornbill...", "4. Poster Making") really are chapter-level, not Q&A questions.
TOP_LEVEL_WHITELIST = {
    # 'NN_subject-slug.md': ['Known Chapter Title Fragment', 'Another One'],
}

def classify(title, current_level, whitelist):
    low = title.lower()
    if any(k.lower() in low for k in H4_KEYWORDS):
        return 4, 4
    if any(k.lower() in low for k in H3_KEYWORDS):
        return 3, 3
    if CHAPTER_RE.match(title.strip()):
        return 2, 2
    if any(k.lower() in low for k in whitelist):
        return 2, 2
    level = min(current_level + 1, 6)  # generic heading: nest one deeper than current context
    return level, current_level        # don't advance the tracker for generic headings

def normalize(text, whitelist):
    lines = text.split('\n')
    out = []
    first_heading_seen = False
    current_level = 2
    for line in lines:
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            _, title = m.groups()
            if not first_heading_seen:
                out.append(f"# {title}")   # first heading in file = subject title = H1
                first_heading_seen = True
                current_level = 1
                continue
            level, new_current = classify(title, current_level, whitelist)
            current_level = new_current
            out.append(f"{'#' * level} {title}")
        else:
            out.append(line)
    return '\n'.join(out)

path = sys.argv[1]
fname = path.split('/')[-1]
whitelist = TOP_LEVEL_WHITELIST.get(fname, [])
with open(path, encoding='utf-8') as f:
    content = f.read()
with open(path, 'w', encoding='utf-8') as f:
    f.write(normalize(content, whitelist))
print(f"Normalized {path} (whitelist entries: {len(whitelist)})")
```

Run: `python3 /tmp/normalize.py "$DIR/NN_subject-slug.md"` for every subject file.

**Verify before proceeding**: `grep -oE "^#{1,6}" file.md | sort | uniq -c` per file (sane
distribution — a handful of H2 "chapters", many H3/H4), and specifically
`grep -nE "^## [0-9]+\. [A-Z]" file.md` on every file that ISN'T in your whitelist — any hits mean a
Q&A question got misclassified as a chapter and you need to either fix the source formatting or add
a smarter exclusion, not just ignore it.

## 4. Concatenate (newline-safe) and strip stray horizontal rules

```bash
# Guarantee every file ends with a newline BEFORE concatenating — a missing trailing newline
# silently merges the last line of one file with the first heading of the next
# (e.g. "...joint stock company.# COMPUTER SCIENCE" on one line), which drops that subject's
# heading from the document entirely and is easy to miss.
for f in "$DIR"/*.md; do printf '\n' >> "$f"; done

cat "$DIR/00_front_matter.md" "$DIR/01_subject-a.md" "$DIR/02_subject-b.md" ... > "$DIR/MASTER.md"

# Strip standalone horizontal rules (bare --- or *** alone on a line) — leaves table separators
# (|---|---|) untouched since those don't match this anchored pattern:
sed -i '' -E '/^-{3,}[[:space:]]*$/d' "$DIR/MASTER.md"

# Sanity check: exactly one H1 per subject + front matter, each on its own line:
grep -n "^# " "$DIR/MASTER.md"
```

## 5. Convert to DOCX

```bash
cd "$DIR"
pandoc MASTER.md -o study_guide.docx --toc --toc-depth=2 --metadata title="<TITLE>"
```

Then insert page breaks before each subject (pandoc's docx writer has no Markdown syntax for this —
`\newpage` is LaTeX-only and is silently dropped/ignored by the docx writer):

```python
# /tmp/insert_pagebreaks.py
import docx
from docx.enum.text import WD_BREAK

path = "<DIR>/study_guide.docx"
d = docx.Document(path)
first_h1_seen = False
count = 0
for para in d.paragraphs:
    if para.style.name == 'Heading 1':
        if not first_h1_seen:
            first_h1_seen = True
            continue  # skip the very first H1 (document title) — no break needed before it
        new_run = para.insert_paragraph_before().add_run()
        new_run.add_break(WD_BREAK.PAGE)
        count += 1
d.save(path)
print(f"Inserted {count} page breaks")
```

**Verify**: `count` should equal (number of subjects − 1), i.e. one break before every subject
except the very first Heading 1 in the doc (the title). If it doesn't match, some subject's H1 is
missing — almost always the newline-concatenation bug from step 4; re-check file boundaries.

## 6. Convert to PDF (via styled HTML + headless Chrome — no LaTeX needed)

```bash
cat > "$DIR/style.css" << 'CSSEOF'
@page { size: A4; margin: 20mm 16mm; }
body { font-family: 'Georgia', 'Times New Roman', serif; font-size: 11.5pt; line-height: 1.5; color: #1a1a1a; }
h1 { font-family: 'Helvetica Neue', Arial, sans-serif; color: #0b3d91; font-size: 22pt; border-bottom: 3px solid #0b3d91; padding-bottom: 6px; margin-top: 0; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-family: 'Helvetica Neue', Arial, sans-serif; color: #b8291f; font-size: 16pt; margin-top: 26px; border-bottom: 1.5px solid #b8291f; padding-bottom: 3px; page-break-before: always; }
h3 { font-family: 'Helvetica Neue', Arial, sans-serif; color: #1a5d1a; font-size: 13pt; margin-top: 18px; }
h4 { font-family: 'Helvetica Neue', Arial, sans-serif; color: #444; font-size: 11.5pt; margin-top: 12px; }
table { border-collapse: collapse; width: 100%; margin: 10px 0 16px 0; font-size: 10.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #999; padding: 5px 8px; text-align: left; vertical-align: top; }
th { background-color: #e8eef7; font-weight: bold; }
code { background-color: #f2f2f2; padding: 1px 4px; border-radius: 3px; font-size: 10pt; }
pre { background-color: #f2f2f2; padding: 8px; border-radius: 4px; overflow-x: auto; }
#TOC, nav#TOC { page-break-after: always; background: #f7f7f7; padding: 16px 20px; border-radius: 6px; }
#TOC ul { line-height: 1.9; }
CSSEOF

cd "$DIR"   # must cd first — relative --css path won't resolve otherwise
pandoc MASTER.md -o study_guide.html --toc --toc-depth=2 \
  --metadata title="<TITLE>" --css=style.css --embed-resources --standalone

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --no-pdf-header-footer --print-to-pdf="$DIR/study_guide.pdf" \
  --print-to-pdf-no-header "file://$DIR/study_guide.html"
```

(Harmless `task_policy_set` stderr warnings from Chrome headless can be ignored as long as the PDF
file is written.)

## 7. Verify — don't just check the files exist

```bash
python3 -c "
import docx
d = docx.Document('<DIR>/study_guide.docx')
h1 = [p.text for p in d.paragraphs if p.style.name == 'Heading 1']
print('Heading 1 sections:', h1)   # must list front-matter title + every subject, none missing
"

python3 -c "
from pypdf import PdfReader
r = PdfReader('<DIR>/study_guide.pdf')
print('Total pages:', len(r.pages))
print(r.pages[0].extract_text()[:400])   # title/TOC page should look right
# spot-check a page you know contains a table (search for known text from a worked example)
for i, p in enumerate(r.pages):
    if '<KNOWN TEXT FROM A NUMERIC TABLE>' in p.extract_text():
        print(f'Found on page {i+1}:', p.extract_text()[:600]); break
"
```

If a subject is missing from the Heading 1 list or the PDF page count looks too low, don't guess —
re-check file boundaries from step 4 (trailing newlines) before re-running the conversion.

## 8. Finalize

```bash
cp "$DIR/study_guide.docx" ~/Downloads/"<School>_<Grade><Stream>_UT<N>_Study_Guide.docx"
cp "$DIR/study_guide.pdf" ~/Downloads/"<School>_<Grade><Stream>_UT<N>_Study_Guide.pdf"
rm -f "$DIR/check.txt" /tmp/normalize.py /tmp/insert_pagebreaks.py
```

Keep the per-subject `.md` files and `MASTER.md` in the session's `files/` directory (useful if the
user wants a follow-up tweak) — only the final DOCX/PDF need to land in `~/Downloads`.
