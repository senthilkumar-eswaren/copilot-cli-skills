---
name: cbse-unit-test-prep
description: >-
  Creates a detailed CBSE unit-test / exam study guide (chapter notes + CBSE-pattern Q&A, exported
  as DOCX and PDF) from a school's exam timetable/portions circular. Use whenever the user attaches
  or references a school unit-test / periodic-test / exam timetable document (PDF/image) listing
  subjects, chapters/units, dates and marks, and asks for study material, revision notes, a
  question bank, or exam preparation content covering those chapters. Applies to CBSE Class XI/XII
  (any stream — Commerce, Science, Humanities) but the workflow generalizes to any board/grade once
  the syllabus portions are known. Always read references/*.md before starting — they contain the
  exact textbook-mapping knowledge, the per-subject content-generation prompt template, and the
  tested document-assembly/PDF-conversion pipeline (including fixes for pandoc/heading/newline
  pitfalls hit the first time this was built).
---

# CBSE Unit Test Study Guide Generator

Builds a comprehensive, ready-to-print study guide (chapter notes + CBSE-pattern Q&A) for a school
unit test, from a timetable/portions circular the user attaches. Output: one DOCX + one PDF (with
table of contents and a page break per subject), saved to `~/Downloads`.

## Workflow overview

1. **Read the attached circular carefully** (it arrives as a native PDF/image attachment — don't
   re-fetch or re-OCR it, just read what's already in context). Extract: school name, grade/class,
   stream/group (if applicable), unit test number, and for each subject the exam date, marks,
   duration, and **exact chapter/unit portions**.
2. **Confirm scope with the user** if the circular covers multiple streams/groups, or lists more
   subjects than the user asked for — use `ask_user` (multiple choice) to confirm which subjects
   to include. Don't silently guess scope.
3. **Map each subject to its real-world CBSE textbook/publisher** using
   `references/01-syllabus-extraction-and-textbook-mapping.md`. Chapter titles and numbering are a
   strong fingerprint for which book the school follows (NCERT / TS Grewal / TR Jain & VK Ohri /
   Sumita Arora / etc.) — notes must match the actual book the student has, not a generic syllabus.
4. **Set up tracking** (SQL `todos`, one row per subject + assemble + convert) and **verify the
   toolchain** (pandoc, Chrome, Word/textutil, python3) — install anything missing. See
   `references/03-assembly-and-conversion-pipeline.md` for exact commands.
5. **Launch one background `general-purpose` task agent per subject, in parallel** (this is the
   single biggest time-saver — subjects are fully independent). Use the prompt template in
   `references/02-content-generation-agent-template.md`, filled in with that subject's exact
   chapters and textbook mapping. Each agent must return the full Markdown as its text response
   (instruct it NOT to create files) — you assemble everything centrally afterwards.
6. **While agents run, don't idle** — draft the front-matter file yourself: title page, an exam
   timetable table transcribed from the circular, a "how to use this guide" section, and CBSE
   exam-writing tips. Template in `references/03-assembly-and-conversion-pipeline.md`.
7. **As each agent finishes**, extract its output to a per-subject `.md` file, stripping (a) the
   leading agent-status header line the tool wrapper adds, and (b) any trailing conversational
   offer the agent tacks on ("If you want, I can also turn this into...").
8. **Normalize heading levels** across all subject files before assembling. Every agent invents its
   own heading scheme independently, and a naive "renumber levels" or "numbered title = chapter"
   regex over-fires (individual Q&A questions are often themselves written as `##`/`###` headings,
   which looks identical to a real numbered chapter title). Use the tested, stateful normalizer
   script in `references/03-assembly-and-conversion-pipeline.md` verbatim rather than re-deriving
   it — it already handles this ambiguity via a small file-specific whitelist.
9. **Assemble and convert** to DOCX + PDF following the exact pipeline in
   `references/03-assembly-and-conversion-pipeline.md` — this includes non-obvious fixes (missing
   trailing newlines corrupting concatenation, stray `---` lines breaking pandoc's YAML parser,
   `\newpage` not working outside LaTeX output) that cost real debugging time the first pass.
10. **Verify before declaring done** — don't just check the file exists:
    - `python-docx`: confirm every subject appears as a `Heading 1` paragraph (catches silent
      concatenation/parsing drops).
    - `pypdf`: confirm total page count is sane, and extract text from 2-3 content pages —
      especially any page containing a numeric table (journal entries, number-system conversions,
      demand/utility schedules) — to confirm tables actually rendered, not just that a PDF exists.
11. Save final files to `~/Downloads` with a descriptive name, e.g.
    `<School>_<Grade><Stream>_UT<N>_Study_Guide.{docx,pdf}`, and delete temp/scratch files (keep
    the per-subject `.md` sources and the master `.md` in the session's `files/` folder as an
    editable archive, not in Downloads).

## Per-subject content depth (apply to every subject, every time — don't thin this out)

For each chapter: chapter overview, detailed notes (with worked numerical examples where the
subject is numerical — Accountancy journals/ledgers, Economics schedules, Computer Science number
conversions), key formulas/golden rules, a definitions glossary, and CBSE-pattern Important
Questions & Answers — **Very Short (1 mark) / Short (3-4 marks) / Long (5-6 marks) /
case-study-application**, plus a short previous-year-board-style question section. This weighting
mirrors actual CBSE marking schemes.

## Key lessons baked into the reference pipeline (do not skip these steps)

- Agents love to end with a conversational "would you like me to also turn this into..." — always
  strip it before assembling.
- Files without a **trailing newline** silently merge with the next file's first line when
  concatenated with `cat` — e.g. `...joint stock company.# COMPUTER SCIENCE` on one line instead of
  two — which drops that subject's heading entirely. Always enforce trailing newlines first.
- A stray standalone `---` line anywhere in the assembled Markdown makes pandoc misparse it as a
  YAML metadata block and fail with a cryptic YAML error. Strip all standalone `---`/`***`
  horizontal-rule lines before running pandoc (table separator rows like `|---|---|` are safe and
  must NOT be touched).
- `\newpage` in Markdown only page-breaks LaTeX/PDF output — it does **nothing** for DOCX or for
  the HTML→Chrome-headless-PDF route used here. Use `python-docx` to insert a page break before
  each `Heading 1` in the docx, and CSS `page-break-before: always` on `h1`/`h2` for the PDF route.
- Don't trust a blind "numbered heading = chapter" regex when classifying/normalizing headings —
  some subjects format individual Q&A questions as literal `##`/`###` headings (e.g.
  `## 1. What is business?`), which is structurally identical to a real chapter title like
  `## 1. Hornbill: The Portrait of a Lady`. Only whitelist bare numbered titles as chapter-level
  for the specific subject/file where you've confirmed that's how chapters are actually written;
  everywhere else, rely on the `Chapter N:` / `Part A|B` pattern and the "nest one level deeper
  than current section" fallback instead.
