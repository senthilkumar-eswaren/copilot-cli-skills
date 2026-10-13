---
name: sof-olympiad-prep
description: >-
  Prepare an Indian Class 5 student for Science Olympiad Foundation (SOF, sofworld.org) exams -
  IMO (International Mathematics Olympiad), IEO (International English Olympiad) and ICSO
  (International Computer Science Olympiad / cyber olympiad). Generates ORIGINAL SOF-style sample
  question papers and full mock tests modelled on previous years' papers, topic-wise practice sets
  and worksheets, answer keys with explanations and OMR answer sheets as print-ready PDFs; marks the
  child's answers, keeps a score log and reports progress and weak topics. Use for requests like
  "make an IMO mock paper", "IEO sample paper", "ICSO question paper", "olympiad practice on
  fractions / tenses", "SOF previous-year style questions", "answer key", "OMR sheet",
  "mark her answers", "check my daughter's olympiad score", "weak topics", "progress report".
---

# SOF Olympiad Prep (IMO · IEO · ICSO)

Builds print-ready practice papers that follow SOF's official pattern, syllabus and difficulty
(Class 5 by default), written fresh every time, and marks the child's attempts to track progress.

## Layout

`SKILL_DIR` is the folder containing this `SKILL.md` (the path shown when the skill was loaded).
If unknown, find it:

```bash
SKILL_DIR=$(dirname "$(find -L "${COPILOT_HOME:-$HOME/.copilot}/skills" "${COPILOT_HOME:-$HOME/.copilot}/installed-plugins" -path '*/sof-olympiad-prep/SKILL.md' 2>/dev/null | head -1)")
S=$SKILL_DIR/scripts
```

| Path | Purpose |
|---|---|
| `data/class5.json` | Exam patterns (sections, questions, marks, time, levels) and syllabi for Class 5 and Class 4 |
| `data/question_styles.json` | SOF question styles and writing hints for ~97 topics |
| `scripts/blueprint.py` | Picks topics, difficulty, figures and answer letters; writes `blueprint.json` and one spec per part |
| `scripts/validate_paper.py` | Checks a part or a whole paper (format, answers, SVG safety, balance, duplicates) |
| `scripts/assemble_paper.py` | Merges the parts into `papers/<slug>.json` |
| `scripts/render_paper.py` | Question paper, answer key and OMR PDFs via headless Chrome |
| `scripts/score.py` | Marks answers, keeps the score log, reports and weak topics |
| `scripts/sof_common.py` | Shared helpers and small utilities (`paths`, `list`, `next-no`, `student-view`, `selfcheck`) |
| `references/03-question-writing.md` | Brief for question-writer agents (must be read by every writer) |
| `references/04-figures.md` | SVG figure rules for writer agents |

Environment:
- `OLYMPIAD_PREP_HOME` (default `~/olympiad-prep`) holds `history.json`, `work/`, `papers/`,
  `scores.csv` and `attempts.jsonl`.
- `OLYMPIAD_OUT_DIR` (default `~/Downloads`) is where the PDFs go.
- Python 3.9 standard library only, plus Google Chrome (or Edge/Chromium) for PDFs; PyMuPDF, if
  installed, adds page footers and previews. Do not install packages.

## Golden rules

1. **Every question is original.** Never copy, closely paraphrase or lightly edit questions from SOF
   sample papers, MTG workbooks, textbooks or websites. Previous years' papers inform only the
   pattern, topic mix, question styles and difficulty.
2. **Follow the blueprint exactly**: question ids, section, topic, syllabus class, difficulty,
   answer letter, figure and format flags. It balances the answer key and difficulty; don't override it.
3. **Indian Class 5 context**: rupees, metric units, Indian names, places and festivals; simple,
   clear wording; Indian/British English spelling.
4. Exactly one correct option per question. Answers and explanations appear only in the answer key.
5. Verify every calculation with `python3` before it goes into a paper.
6. Be encouraging when reporting results to a parent or child.

## Workflow A - generate a paper

**1. Clarify** with `ask_user`, one question at a time, skipping anything already stated:
exam (IMO / IEO / ICSO) -> full mock paper or topic-wise practice set -> level (1 by default;
2 only if she qualified) -> for practice: topics and number of questions (default 20).
For topic choices run `python3 $S/blueprint.py --exam IMO --list-topics` and offer the real names.
Class defaults to 5.

**2. Blueprint** (always `tail`, never `head` - a broken pipe can stop the specs being written):

```bash
python3 $S/blueprint.py --exam IMO 2>&1 | tail -40                          # full mock, Level 1
python3 $S/blueprint.py --exam IEO --level 2 2>&1 | tail -40                # Level 2 mock
python3 $S/blueprint.py --exam IMO --mode practice \
    --topics "Fractions and Decimals; Money" --count 20 2>&1 | tail -40     # practice set
```

Separate topics with `;`. Other flags: `--paper-no N`, `--set-name "..."`, `--seed N`, `--clean`
(rebuild a half-finished work folder). Note the **slug** and every `part_<pid>.spec.json` path it
prints (all under `work/<slug>/`). Level 1 mocks have 4 parts (IMO `s1 s2 s3 s4`, IEO
`s1a s1b s2 s3-4`, ICSO `s1 s2a s2b s3-4`); for other papers use the parts printed. Practice sets
of up to 25 questions have one part `all`, larger ones `p1`, `p2`, ...

**3. Write the parts** - launch one `general-purpose` sub-agent per spec, all in parallel
(background mode), then wait for every completion notification. Prompt (fill in `<...>`):

```
Write part <pid> of an ORIGINAL SOF <EXAM> Class <N> practice paper.
1. Read the spec <absolute spec path> completely, then every file listed in its "references".
2. Write exactly the questions in "rows": same ids, section, topic, syllabus class,
   difficulty, answer letter and figure/format flags. Obey "rules" and "exam_rules";
   nothing may resemble "avoid_similar".
3. Every question must be original. Never copy or paraphrase SOF, MTG, textbook or web
   questions. Use Indian context and simple Class <N> language.
4. Check every answer and calculation with python3 before writing it.
5. Save the JSON to the spec's "output" path.
6. Run the spec's "validate_cmd"; fix every error and re-run until it reports 0 errors.
Reply with only the final validator line.
```

**4. Assemble**: `python3 $S/assemble_paper.py --blueprint <slug>`. On errors (cross-part
near-duplicates, balance), fix that part with `write_agent` to its writer or a direct edit, re-run
its `validate_cmd`, then assemble again. `--force` overwrites an existing paper.

**5. Render**: `python3 $S/render_paper.py <slug> --preview`. View the preview PNGs it prints
(figures, tables, page breaks). Fix the part, re-assemble with `--force`, then
`render_paper.py <slug> --force --preview`.

**6. Report** the three PDFs (question paper, answer key, OMR sheet), the time allowed and
total marks. Suggest: print paper + OMR, keep the key away from the child, time the attempt, then
send her answers back for marking.

## Workflow B - mark an attempt

1. Find the paper slug (`python3 $S/sof_common.py list`) and get her answers in question order:
   a string like `"DDCA-BADC..."` (`-` = left blank), pairs `"1D 2D 3C"`, a `.txt`/`.json` file
   (`-f FILE`) or `-a -` to read stdin. Ask how many minutes she took.
2. If the parent sends a photo of the OMR sheet, transcribe it, read the answers back in groups
   of 10 and get confirmation before marking.
3. Mark it. Add `--name "<child>"` when more than one child uses the skill; `--dry-run` previews
   without saving to the score log.

```bash
python3 $S/score.py mark IMO_Class5_Mock_Paper_01 -a "DDCA-BADC..." -m 55
python3 $S/score.py report --exam IMO          # score history and trend
python3 $S/score.py weak-topics --exam IMO     # weakest topics as "A; B" (below 70%)
```

4. Report the total and section scores, then each wrong or blank question with the correct
   option and its explanation. Praise what went well first, then offer a practice set on the
   2-4 weakest topics: pass the `weak-topics` output straight to
   `blueprint.py --mode practice --topics "..."` (Workflow A).

## Patterns (Class 5)

Every paper: 50 questions, 60 marks, 60 minutes, no negative marking. Achievers questions carry
3 marks each, all others 1. Level 1 takes about 40% of questions from the previous class's syllabus.

| Exam | Level | Sections (questions) |
|---|---|---|
| IMO | 1 | Logical Reasoning 15, Mathematical Reasoning 20, Everyday Mathematics 10, Achievers 5 |
| IMO | 2 | Mathematics 45, Achievers 5 |
| IEO | 1 | Word and Structure Knowledge 30, Reading 10, Spoken and Written Expression 5, Achievers 5 |
| IEO | 2 | Word and Structure Knowledge 35, Reading 10, Achievers 5 |
| ICSO | 1 | Logical Reasoning 10, Computer Science 30, AI, Robotics and Information Technology 5, Achievers 5 |

ICSO has no Level 2. Full syllabi: `data/class5.json`; topic names: `blueprint.py --list-topics`.

## Utilities

```bash
python3 $S/sof_common.py paths                  # where files live
python3 $S/sof_common.py list                   # papers made so far
python3 $S/sof_common.py next-no --exam IMO     # next mock paper number
python3 $S/sof_common.py student-view <slug>    # questions only, no answers
python3 $S/sof_common.py selfcheck              # check data and scripts
```

When quizzing her in chat, read questions only from `student-view` output so answers never leak.
Set `OLYMPIAD_PREP_HOME` to use a separate folder (e.g. for a second child or for testing).

## Troubleshooting

- Validator errors name the question id and the problem: fix the JSON and re-run `validate_cmd`.
  Warnings are acceptable; `--strict` makes them fail.
- "already exists": add `--force` to assemble/render, or rebuild with `blueprint.py --clean`.
- `BrokenPipeError` from `blueprint.py`: output was piped to `head`; use `tail`.
- Chrome hangs: `ps -ax | grep '[s]of-chrome'`, then `kill <PID>`; `--html-only` writes HTML
  that can be printed from a browser.
- PDFs go to `OLYMPIAD_OUT_DIR` (default `~/Downloads`) or `--out-dir`.
