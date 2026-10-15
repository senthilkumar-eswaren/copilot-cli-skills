# Writing questions from a part spec

You are writing ONE part of an SOF-style Olympiad paper (IMO = Maths, IEO = English,
ICSO = Computer Science) for an Indian school student. Everything you need is in the spec file
you were given (`work/<slug>/part_<pid>.spec.json`). This guide explains how to turn its rows into
questions that pass `validate_paper.py` and feel like a real SOF paper. If any row has
`"figure": true` (or a passage has `"allow_figure": true`), also read `04-figures.md`.

On Windows (PowerShell), type `python -X utf8` wherever this guide or `04-figures.md` says
`python3`; it keeps files and printed text in UTF-8.

## 1. Workflow

1. `cat` the spec. Note `exam`, `class`, `level`, `mode`, `output`, `validate_cmd`, `rules`,
   `exam_rules`, `avoid_similar`, `passages` and `rows`. `rules` and `exam_rules` are binding
   instructions for you, the writer: follow them, but never print them or copy their wording into a
   question, passage, direction or explanation.
2. Write exactly one question per row, keeping the row's `id` and the row order.
3. Work out every answer yourself with python3 (arithmetic, counting, dates, clocks, patterns,
   word counts) before you fix the options. Never trust mental arithmetic.
4. Build the part file with a python3 script (do not hand-type JSON) and save it to the exact
   `output` path from the spec with `open(output, "w", encoding="utf-8")` and
   `json.dump(data, f, ensure_ascii=False, indent=1)`.
5. Run `validate_cmd` exactly as given. Fix every ERROR. Fix WARNINGs too unless doing so would
   break a row instruction. Re-run until there are no errors.
6. Reply with a 1-2 line summary (part id, number of questions, validator result).
   Do not paste the questions into the reply.

Never edit the spec, `blueprint.json`, other parts' files, or any script.

## 2. Part file shape

```json
{
 "questions": [ {...}, {...} ],
 "passages": [ {"id": "P1", "title": "...", "text": "First paragraph...\n\nSecond paragraph..."} ],
 "directions": [ {"from": 31, "to": 35, "text": "...", "passage_id": "P1"} ]
}
```

`passages` and `directions` are only needed when the spec lists passages or a group of questions
shares one instruction or figure. A minimal question:

```json
{"id": 7, "format": "standard", "question": "...",
 "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
 "answer": "C", "explanation": "..."}
```

`section`, `topic`, `syllabus_class`, `difficulty` and `answer` are copied from the row if you
leave them out. If you include them they must match the row. Always include `answer`.

## 3. Using each row field

| Row field | What to do |
|---|---|
| `id` | Use it as the question `id` (integer). |
| `section_name`, `topic` | The question must clearly test this topic in this section. |
| `syllabus_class` | Write at this class's level. When it is the class below (Level-1 mocks revise it), use that year's syllabus, numbers and vocabulary (Class 4 for a Class 5 paper, Class 2 for a Class 3 paper; about 40% of Level-1 questions). |
| `difficulty` | `easy` = one step or direct recall. `medium` = two steps or one twist. `hard` = several steps, careful reading, or a tempting trap option. |
| `achievers`, `marks` | Achievers rows (3 marks in Class 5, 2 marks in Class 3) are harder, HOTS-style, always on the current class syllabus. |
| `style` | The kind of SOF question to write (for example "odd one out" or "complete the pattern"). Follow it. It already includes the class's own overrides, so it wins over this guide's generic examples. |
| `format`, `format_instructions` | The layout to use (section 5). `format_instructions` are binding and win over the examples here. |
| `prefix` | A flavour instruction, not stem text. `Everyday-life word problem:` means a real-life Indian situation (shopping, travel, school, cooking, festivals, sports). `Achievers-level HOTS:` means multi-step, higher-order reasoning. Never copy the prefix into the question. |
| `tips` | Topic hints from the style bank (common traps, good contexts), already adjusted for the paper's class. Use them. |
| `brief` | A readable summary of the row, including the style. Use it as a reminder. |
| `answer` | The letter that MUST be correct. Arrange the options so that it is. |
| `figure` | `true`: include an SVG the student genuinely needs (see `04-figures.md`). `false`: no figure. |
| `passage_id` | Put the same `passage_id` on the question and base the question on that passage. |

## 4. Optional question keys

| Key | Use |
|---|---|
| `items` | List of plain strings shown under the stem. The renderer adds the labels. |
| `item_style` | `"roman"` (default) gives (i) (ii) (iii); `"statement"` gives Statement-I:, Statement-II:; `"letter"` gives (a) (b); `"bullet"` gives bullets; `"statement_num"` gives Statement 1 :, Statement 2 : (Class 3 `statements_c3`); `"plain"` gives no labels. No other values are allowed. |
| `question_after` | Text shown after the items/table/figure, e.g. "Which of the following is correct?". |
| `table` | `{"headers": [...], "rows": [[...], [...]], "caption": "..."}` for data such as timetables, bills, scores and pictographs. Never draw a table in SVG. |
| `match` | `{"left_title": "Column I", "right_title": "Column II", "left": [...], "right": [...]}`. |
| `figure` | An SVG string (see `04-figures.md`). |
| `figure_position` | `"below"` (default), `"above"` or `"right"` (small figure beside the text). |
| `option_headers` | Column headers when options are lists, e.g. `["(i)", "(ii)"]`. |
| `option_layout` | `auto` (default), `row`, `grid` or `column`. Usually leave it out. |

Option values may be strings, `{"svg": "...", "text": "..."}` (figure options, `text` optional),
or lists (only with `option_headers`).

Never write labels yourself inside `items`, `match.left` or `match.right`. The renderer adds
(i)/(ii), Statement-I/II, Statement 1/2, P/Q/R/S and 1/2/3/4. Options refer to those labels.

## 5. Formats, with one example each

Follow the row's `format_instructions` wherever they differ from these examples.

### standard
A normal question. It may still use `items`, `table` or `figure`.

```json
{"id": 1, "format": "standard",
 "question": "Riya buys 3 pens at Rs 12 each and a notebook for Rs 45. How much money will she get back from a Rs 100 note?",
 "options": {"A": "Rs 43", "B": "Rs 19", "C": "Rs 29", "D": "Rs 55"},
 "answer": "B",
 "explanation": "Pens cost 3 × 12 = Rs 36. Total = 36 + 45 = Rs 81. Change = 100 − 81 = Rs 19."}
```
The distractors are real slips: Rs 43 counts only one pen, Rs 29 adds 36 + 45 wrongly, and
Rs 55 forgets the pens.

### not
The stem contains `<b>NOT</b>` and exactly one option is the exception.

```json
{"id": 2, "format": "not",
 "question": "Which of the following is <b>NOT</b> a factor of 48?",
 "options": {"A": "6", "B": "8", "C": "12", "D": "18"},
 "answer": "D",
 "explanation": "48 = 6 × 8 = 4 × 12, so 6, 8 and 12 divide 48 exactly. 48 ÷ 18 = 2 remainder 12, so 18 is not a factor."}
```

### statements
Two plain sentences in `items` with `item_style` `"statement"`, and these four options word for
word. Decide the truth of each statement so that the row's answer letter is correct.

```json
{"id": 3, "format": "statements",
 "question": "Read the given statements carefully.",
 "items": ["The smallest 5-digit number is 10,000.", "The place value of 7 in 47,325 is 700."],
 "item_style": "statement",
 "question_after": "Which of the following is correct?",
 "options": {"A": "Both Statement-I and Statement-II are true.",
             "B": "Both Statement-I and Statement-II are false.",
             "C": "Statement-I is true but Statement-II is false.",
             "D": "Statement-I is false but Statement-II is true."},
 "answer": "C",
 "explanation": "Statement-I is true. Statement-II is false: 7 is in the thousands place of 47,325, so its place value is 7000."}
```

### statements_c3
Class 3 ICSO only (never on figure rows). Two plain sentences in `items` with `item_style`
`"statement_num"`, `question_after` "Which of the given statements hold(s) true?" (you may add the
topic, e.g. "... hold(s) true about MS-Word?") and these four options word for word. Decide the
truth of each statement so that the row's answer letter is correct.

```json
{"id": 8, "format": "statements_c3",
 "question": "Read the given statements.",
 "items": ["We can use the Undo option to cancel the last change made in a document.", "The Bold option makes the selected text slanted."],
 "item_style": "statement_num",
 "question_after": "Which of the given statements hold(s) true about MS-Word?",
 "options": {"A": "Only Statement 1", "B": "Only Statement 2",
             "C": "Both Statement 1 and Statement 2", "D": "Neither Statement 1 nor Statement 2"},
 "answer": "A",
 "explanation": "Undo (Ctrl + Z) cancels the last change, so Statement 1 is true. Bold makes text darker and thicker; Italic makes it slanted, so Statement 2 is false."}
```

### table_i_ii
Two labelled blanks in the stem, `option_headers` `["(i)", "(ii)"]`, and every option a list of
two strings.

```json
{"id": 4, "format": "table_i_ii",
 "question": "Fill in the blanks with the correct option.<br>Yesterday Meera [[blank:(i)]] to the market and [[blank:(ii)]] a kilogram of mangoes.",
 "option_headers": ["(i)", "(ii)"],
 "options": {"A": ["went", "bought"], "B": ["go", "bought"], "C": ["went", "brought"], "D": ["gone", "buyed"]},
 "answer": "A",
 "explanation": "'Yesterday' needs the simple past: go becomes went and buy becomes bought. 'Brought' is the past of 'bring', and 'buyed' is not a word."}
```

### roman_combo
Four plain items with `item_style` `"roman"`. Options are combinations of the numerals, and
exactly one combination is fully correct.

```json
{"id": 5, "format": "roman_combo",
 "question": "Which of the following are input devices?",
 "items": ["Scanner", "Microphone", "Monitor", "Keyboard"],
 "item_style": "roman",
 "options": {"A": "Only (i) and (iii)", "B": "Only (i), (ii) and (iv)", "C": "Only (ii), (iii) and (iv)", "D": "All of these"},
 "answer": "B",
 "explanation": "A scanner, a microphone and a keyboard send data into the computer, so they are input devices. A monitor shows the output."}
```

### match
Four items on each side, without labels. Options are mappings, and exactly one mapping is fully
correct. Make the wrong mappings share some correct pairs so the student must check every pair.

```json
{"id": 6, "format": "match",
 "question": "Match Column I with Column II and select the correct option.",
 "match": {"left_title": "Column I", "right_title": "Column II",
           "left": ["1 kilogram", "1 litre", "1 kilometre", "1 hour"],
           "right": ["60 minutes", "1000 grams", "1000 metres", "1000 millilitres"]},
 "options": {"A": "P → 2, Q → 4, R → 3, S → 1", "B": "P → 2, Q → 3, R → 4, S → 1",
             "C": "P → 4, Q → 2, R → 3, S → 1", "D": "P → 1, Q → 4, R → 3, S → 2"},
 "answer": "A",
 "explanation": "1 kg = 1000 g (P → 2), 1 L = 1000 mL (Q → 4), 1 km = 1000 m (R → 3) and 1 hour = 60 minutes (S → 1)."}
```

## 6. Passages

Each spec passage looks like
`{"id": "P1", "text_type": "Reports", "syllabus_class": 5, "words": "150-220", "question_ids": [31, 32, 33, 34, 35], "skills": [...], "allow_table": false, "allow_figure": false}`.

- Write an ORIGINAL passage of that `text_type` (story, report, notice, letter, diary entry,
  poem and so on) with a short `title`.
- Keep the word count inside the `words` range. Count it with python3: `len(text.split())`.
- Separate paragraphs with a blank line (`"\n\n"`) inside `text`. Do not use `<br>` for paragraphs.
- Write one question per id in `question_ids`. Question k tests `skills[k]` (for example main
  idea, detail, vocabulary in context, inference, sequence, title).
- Every passage question carries `"passage_id": "P1"`, and its answer must come from the passage,
  not from general knowledge. In vocabulary-in-context questions, show the word in bold.
- Add a `directions` entry for the group:
  `{"from": 31, "to": 35, "passage_id": "P1", "text": "Read the passage given below and answer the questions that follow."}`
- Use a `table` only when `allow_table` is true.
- When `allow_figure` is true (a Picture Reading passage of 15-60 words), draw the picture as the
  passage's `figure` (an SVG at most 520px wide; see `04-figures.md`) and keep `text` a short
  caption; the validator gives an ERROR if it is missing. When it is false, give the passage no
  figure.
- Class 3 Achievers reading questions put a 40-70 word paragraph in the question stem, not in
  `passages`.
- Use clear, age-appropriate language at the passage's `syllabus_class` level, with Indian names and settings.

## 7. Markup and tokens

- The only tags allowed are bare `<b>`, `<i>`, `<u>`, `<sup>`, `<sub>` and `<br>` (no
  attributes). Never put `<svg>`, `<p>`, `<span>` or `<table>` in text; use the proper fields.
- Write a comparison sign with spaces on both sides (`9 < 10`), or as `&lt;` / `&gt;`. A sign
  that stands alone (for example an option that is just the sign) must be `&lt;` / `&gt;`.
- Fractions: `[[frac:3/4]]`; mixed numbers: `[[frac:2 3/4]]`. Never write 3/4 as plain text in
  maths questions.
- Blanks: `[[blank]]` for a single blank, `[[blank:(i)]]` and `[[blank:(ii)]]` for labelled blanks.
- Powers and units: `10<sup>3</sup>`, `cm<sup>2</sup>`. Use the × and ÷ signs, never * or /.
- Money: `Rs 250`. In Class 5, large numbers use Indian grouping (`1,25,000`) with lakh and crore.
  Class 3 numbers stay within 4 digits (up to 9999), with no lakh or crore.
- In IEO, SOF prints key instruction words in capitals or bold: SIMILAR, OPPOSITE,
  INCORRECTLY spelt, <b>NOT</b>.

## 8. Options, distractors and explanations

- Exactly four options, A to D, all different. Exactly one is correct, and it sits at the row's
  `answer` letter.
- Build each distractor from a real mistake that a child of the paper's class makes: wrong
  operation, a forgotten step, units not converted, off-by-one counting, place-value slips, the
  reverse of the rule, look-alike words (bought/brought, quiet/quite), wrong tense or agreement,
  a confused computer term.
- Keep options similar in length, form and units. Avoid "None of these" or "All of these" unless
  the style needs it; if used, it must be clearly right or clearly wrong.
- Class 3 IMO papers often use "None of these" as option D, so you may use it there too.
- Avoid joke options and options that can be ruled out without any knowledge.
- `explanation` (at least 25 characters, 1-3 sentences) shows the working (maths), the rule
  (English) or the reason (computers). It must agree with the answer letter.

## 9. Exam-specific guidance

### IMO (Maths)
- Sections: Logical Reasoning, Mathematical Reasoning, Everyday Mathematics, Achievers.
- Logical Reasoning: series, analogy, odd one out, coding-decoding, direction sense, ranking,
  mirror and water images, counting figures, embedded figures, paper folding, dice and cubes,
  Venn diagrams, calendars and clocks. Many need a figure.
- Mathematical Reasoning follows the class syllabus. In Class 5: large numbers, the four
  operations, factors and multiples, HCF/LCM, fractions, decimals, measurement, perimeter and
  area, time, money, geometry and angles, symmetry, data handling, patterns.
- Everyday Mathematics: real Indian situations such as bills, train timings, recipes, fees,
  savings, sports scores and travel.
- A prepared child should solve a question in about a minute (Achievers about two). Prefer
  clever reasoning to long calculation.
- Class 3: Level 1 is Logical Reasoning 10, Mathematical Reasoning 10, Everyday Mathematics 10
  and Achievers 5 (2 marks each); Level 2 is Mathematics 30 and Achievers 5. Numbers stay within
  9999. No 24-hour clock, angles in degrees, area, decimals, averages, HCF/LCM or Roman numerals.
  In mirror-image questions the mirror line is on the right of the figure. Papers are
  picture-heavy, and "None of these" is a common option D.

### IEO (English)
- Sections: Word and Structure Knowledge, Reading, Spoken and Written Expression, Achievers.
- Follow `exam_rules`: modern standard usage; no continuous forms of stative verbs (know,
  like, believe, own, understand); choose will/can/would/should strictly from context so only
  one option fits; passages are original.
- Word and structure: synonyms, antonyms, homophones, one-word substitution, spelling, tenses,
  articles, prepositions, conjunctions, degrees of comparison, pronouns, subject-verb agreement,
  punctuation, idioms, jumbled words.
- Spoken and Written Expression: dialogue completion, "what would you say", polite requests,
  rearranging sentences, choosing the correctly punctuated sentence.
- Use British/Indian spelling (colour, centre, practise as a verb). If two options could be
  defended by a careful adult, rewrite the question.
- Class 3: Level 1 is Word and Structure Knowledge 15, Reading 10, Spoken and Written Expression 5
  and Achievers 5 (2 marks each); Level 2 is Word and Structure Knowledge 20, Reading 10 and
  Achievers 5. Use simple tenses only; no phrasal verbs, reported speech or passive voice. Reading
  uses stories, anecdotes, Picture Reading, time-tables, messages and invitations. Spoken and
  Written Expression covers apologies, greetings, introductions and requests. Achievers reading
  paragraphs are 40-70 words.

### ICSO (Computers)
- Logical Reasoning questions work as in IMO.
- Computers and IT (Class 5): parts of a computer, input/output/storage devices, memory units,
  types and uses of computers, the desktop, files and folders, keyboard shortcuts (write
  `Ctrl + C`), MS Paint tools, MS Word formatting, MS PowerPoint slides, Logo commands (FD, BK,
  RT, LT, PU, PD, REPEAT), Scratch blocks, internet, email and cyber safety, history of computers.
- Questions follow Windows 11 and MS-Office 2016 menus, shortcuts and features (see `exam_rules`).
  Writing "MS-Word" or "Windows" is enough, and naming Windows 11 or MS-Office 2016 is fine, but
  never mention other versions such as Windows 10 or 7, Office 2019 or 365, or Microsoft 365 (the
  validator warns).
- Class 3 (Level 1 only): Logical Reasoning 5, Computer Science 20, AI, Robotics and IT 5 and
  Achievers 5 (2 marks each). Computer Science covers fundamentals, parts and uses of a computer,
  memory and storage, input and output devices, the internet, MS-Paint and MS-Word; AI, Robotics
  and IT covers AI, robotics, IT gadgets and devices, apps and computerisation, and developments
  in IT. No Logo, Scratch or PowerPoint. Use `statements_c3` when a row asks for it.
- Trace every Logo path with python3 (see `04-figures.md`).

## 10. Originality and variety

- Never copy or closely paraphrase SOF, MTG or any published question, passage or figure. Use
  your own numbers, names, contexts and wording. Generic instructions ("Fill in the blank with
  the correct option.") are fine.
- `avoid_similar` lists earlier questions on these topics. Do not write anything close to them;
  the validator flags near-duplicates.
- Inside your part, do not reuse one stem with only the numbers changed.
- Vary names and settings across India: Aarav, Ananya, Kabir, Meera, Ishaan, Diya, Fatima,
  Harpreet, Joseph, Lakshmi, Arjun, Tenzing; Diwali, Eid, Pongal, Onam, Christmas, Baisakhi,
  Durga Puja; Chennai, Jaipur, Guwahati, Kochi, Pune.
- Keep content kind and school-appropriate: no violence, brands, politics or ranking of religions.

## 11. Directions for a group of questions

`directions` entries look like `{"from": 21, "to": 23, "text": "Study the given figure and answer the questions."}`.
Add `"figure": "<svg ...>"` for a shared figure or `"passage_id"` for a passage. `from` and `to`
must be ids in your part.

## 12. Final checklist

- [ ] One question per row, same ids, same order.
- [ ] Each answer was worked out with python3 and sits at the row's `answer` letter.
- [ ] Four different options A-D with exactly one correct; distractors are real mistakes.
- [ ] The format follows `format_instructions`; no hand-written labels in items or match columns.
- [ ] Rows with `figure: true` have a meaningful SVG that follows `04-figures.md`; other rows have none.
- [ ] Passages are original, inside the word range, titled and split into paragraphs with blank lines.
- [ ] Only allowed tags; tokens well formed; comparison signs spaced or escaped.
- [ ] Explanations show the working and agree with the answer.
- [ ] Indian context, class-appropriate language, nothing similar to `avoid_similar`.
- [ ] `rules` and `exam_rules` were followed, and none of their wording appears in the paper.
- [ ] A passage has a `figure` exactly when its `allow_figure` is true.
- [ ] `validate_cmd` reports no errors.
