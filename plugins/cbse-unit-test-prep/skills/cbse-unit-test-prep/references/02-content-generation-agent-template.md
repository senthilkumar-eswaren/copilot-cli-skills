# Per-Subject Content Generation — Agent Prompt Template

Launch **one background `general-purpose` task agent per subject, in parallel**, in the same
response batch (independent subjects = ideal parallelism; never generate subjects sequentially).
Do not use `sync` mode — you want to keep working (drafting front matter, checking the toolchain)
while all subjects generate simultaneously.

## Prompt template (fill in every `<...>` placeholder)

```
You are preparing detailed Unit Test study material for a CBSE Class <GRADE> (Grade <GRADE>)
<STREAM> student, subject: <SUBJECT NAME>, following <TEXTBOOK/PUBLISHER, from the mapping
reference>. The exam is <DURATION>, out of <MARKS> marks.

EXACT SYLLABUS PORTIONS FOR THIS TEST (do not go beyond these):
<PASTE THE EXACT CHAPTER/UNIT LIST FROM THE CIRCULAR, ONE PER LINE, WITH ENOUGH SUB-TOPIC DETAIL
THAT THE AGENT KNOWS WHAT'S IN SCOPE FOR EACH CHAPTER — e.g. for a numerical/technical subject,
enumerate the specific concepts/formulas/processes each chapter should cover so the agent doesn't
have to guess syllabus boundaries>

Your task: produce a comprehensive, well-organized STUDY GUIDE in clean Markdown format (use ##
and ### headings, bold for key terms, tables for comparisons/schedules/journals/truth-tables, code
blocks for pseudocode if relevant) with the following structure for EACH chapter/unit listed above:

1. **Chapter overview** (3-4 lines)
2. **Detailed notes** covering every sub-topic thoroughly — definitions, classifications, examples,
   and (for numerical/technical subjects) fully WORKED EXAMPLES showing every step, not just final
   answers. For humanities/literature subjects: summaries, character sketches, themes, literary
   devices, glossary of difficult words, as applicable.
3. **Key formulas / golden rules / classification tables** clearly highlighted, where the subject
   has them.
4. **Key definitions glossary** — 10+ precise, exam-ready one/two-line definitions per chapter.
5. **Important Questions and Answers**, organized by CBSE marking pattern:
   - Very Short Answer (1 mark) — at least 5-6 per chapter, with model answers
   - Short Answer (3-4 marks) — at least 5-6 per chapter, with model answers
   - Long Answer (5-6 marks) — at least 3-4 per chapter, with full model answers (numericals,
     diagrams-described-in-text, or multi-part explanations as appropriate)
   - 1-2 case-study / application-based questions per chapter (CBSE's current competency-based
     question format — a short scenario followed by 2-3 sub-questions)
6. A short **Previous Year CBSE Board-style Questions** section per chapter with worked answers.

Use your own knowledge of the actual prescribed textbook. You may use the web_fetch tool if useful
to verify facts or pull authentic previous-year-style questions, but don't spend excessive time —
your own knowledge of these standard CBSE texts is reliable and sufficient as a base.

IMPORTANT: Do not create any files. Do not use the create/edit tools. Just return the ENTIRE final
markdown content as your text response (this will be assembled into a larger document by the
parent process). Be thorough and detailed — this is exam preparation material a real student will
study from. Start your response directly with "## <SUBJECT NAME IN CAPS>" as the top heading, then
subsections below it.
```

## Subject-specific notes to append to the template

- **Numerical subjects (Accountancy, Economics, Computer Science, Maths)**: explicitly demand
  fully worked numerical examples with all steps shown, and that final numbers must balance/check
  out (e.g. debits = credits, assets = liabilities + capital, converted values verified by
  reverse-conversion). Ask for at least one large worked example per numerically-heavy chapter
  distinct from the ones used inside the Q&A answers.
- **Accountancy specifically**: ask for journal entries in a proper `Date | Particulars | L.F. |
  Debit | Credit` markdown table with narrations, and ledger postings in T-account or running-
  balance format.
- **Computer Science specifically**: ask for full step-by-step number-system conversions (show the
  division/remainder table or bit-grouping explicitly) and full truth tables for any logic-gate /
  Boolean-law question.
- **Economics specifically**: ask for schedules (utility, demand, PPC) as small numeric tables, and
  for elasticity/marginal-value calculations to show the formula, substitution, and final answer.
- **English / literature subjects**: ask for a "reference to context" / extract-based question (a
  quoted passage followed by 2-3 questions on it) since this is a very common CBSE English question
  type; also ask for creative-writing format checklists (poster/advertisement/notice/article) with
  a couple of fully worked sample answers within the CBSE word limit, plus a grammar revision
  section with one full CBSE-style editing/omission exercise and answer key if grammar is in scope.
- **History/Political Science/Psychology/Legal Studies and similar theory subjects**: emphasize
  distinguish-between and explain-with-examples question types, since these dominate CBSE papers
  for these subjects.

## After each agent finishes

1. Retrieve with `read_agent` (large outputs get saved to a temp file — read that file rather than
   pulling the whole thing inline).
2. Strip the leading status header the tool wrapper adds. The real content starts after a blank
   line and a `[Turn 0]` marker — i.e. `tail -n +4 <tmpfile>` typically gets you to the first line
   of actual Markdown (verify by checking the first few lines before trusting this offset).
3. Strip any trailing conversational offer the agent appends (e.g. "If you want, I can also turn
   this into..."). Search for it (`grep -n "^If you want"` or similar) and trim the file to before
   that line — don't assume a fixed line count, agents vary.
4. Save the cleaned result as `<NN>_<subject-slug>.md` in the session's `files/` working directory,
   NOT in the final Downloads deliverable location (that's for the assembled/converted output only).
