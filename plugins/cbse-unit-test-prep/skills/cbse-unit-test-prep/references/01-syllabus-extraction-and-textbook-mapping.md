# Syllabus Extraction & Textbook Mapping (CBSE Class XI/XII)

## Reading the circular

School unit-test/periodic-test circulars are typically a table per stream/group with columns like
`S.No | Date and Day | Subject | Portions`, sometimes with multiple streams (e.g. Commerce and
Humanities) in the same document, each subject listing chapter numbers/names and occasionally page
ranges (e.g. "Till Page No 176"). Also capture, if present: total marks per paper, exam duration,
and any subjects given special treatment (e.g. shorter duration/lower marks for Design/Painting/AI
practical-style papers) — put this in the front matter, not in the per-subject notes.

If the same circular lists more subjects/streams than the user asked for, confirm scope with
`ask_user` rather than generating everything or silently dropping subjects.

## Why textbook mapping matters

Two schools teaching "CBSE Accountancy Class 11" may follow different reference books with
different chapter numbering and even different topic groupings for the same syllabus. Notes must
match the chapter numbering/title the user's circular shows, not a generic NCERT-only view of the
subject. Chapter titles + numbering are a strong fingerprint — use them to identify the likely book,
and mention the inferred book in the generated notes so the student can sanity-check it against
their actual textbook.

## Known fingerprints (from CBSE Class XI Commerce, confirmed against a real circular)

| Subject | Likely textbook/publisher | Fingerprint chapter titles seen |
|---|---|---|
| English Core | NCERT **Hornbill** (prose+poetry) + **Snapshots** (supplementary) — Class 11. Class 12 equivalents are **Flamingo** + **Vistas**. | "The Portrait of a Lady", "The Photograph" (poem) → Hornbill Ch1/P1. "The Summer of the Beautiful White Horse" → Snapshots Ch1. Creative writing: Poster/Advertisement/Notice/Article writing is the standard CBSE Class 11 writing-skills component. |
| Business Studies | NCERT **Business Studies Part I** (Class 11) / **Part II** (Class 12); Poonam Gandhi guide is a common supplementary reference with the same NCERT chapter order. | Class 11: Ch1 "Nature and Purpose of Business"/"Business, Trade and Commerce", Ch2 "Forms of Business Organisation", Ch3 "Private, Public and Global Enterprises", Ch4 "Business Services", Ch5 "Emerging Modes of Business", Ch6 "Social Responsibility of Business", Ch7 "Formation of a Company". Class 12: Principles of Management, Business Environment, Planning, Organising, Staffing, Directing, Controlling, Financial/Marketing Management, Consumer Protection. |
| Accountancy | **TS Grewal "Double Entry Book Keeping"** (very commonly used alongside/instead of NCERT; numbering below is TS Grewal's, not NCERT's) | Class 11 TS Grewal order: Ch1 Introduction to Accounting, Ch2 Basic Accounting Terms, Ch3 Theory Base of Accounting, Ch4 Process/Bases of Accounting, Ch5 Accounting Equations, Ch6 Accounting Procedures—Rules of Debit and Credit, Ch7 Origin of Transactions—Source Documents, Ch8 Journal, Ch9 Ledger, Ch10 Special Purpose Books I (Cash Book), Ch11 Special Purpose Books II (Other Books), then Bank Reconciliation, Trial Balance, Depreciation, Provisions/Reserves, Bills of Exchange, Rectification of Errors, Financial Statements. Class 12 TS Grewal Vol 1 (Not-for-Profit Orgs, Partnership) + Vol 2 (Company Accounts, Financial Statement Analysis, Cash Flow). NCERT alternative uses different numbering ("Theory Base of Accounting" as Ch2, etc.) — if chapter numbers don't match TS Grewal, check NCERT Financial Accounting Part 1/2 instead. |
| Economics | NCERT **Statistics for Economics** + either **Indian Economic Development** or **Introductory Microeconomics** (school-dependent) — OR the **TR Jain & VK Ohri / Sandeep Garg** reference books, which re-sequence some topics. | "Ch1 Introduction, Ch2 Consumer's Equilibrium, Ch3 Demand" for Microeconomics matches TR Jain/Sandeep Garg's numbering more closely than NCERT's own ("Ch2 Theory of Consumer Behaviour" etc.) — if you see "Consumer's Equilibrium" as its own chapter title, assume TR Jain/Sandeep Garg lineage. "Ch1 Economics: An Introduction, Ch2 Meaning Scope and Importance of Statistics, Ch3 Collection of Data" matches both NCERT and TR Jain fairly closely — safe to use NCERT Statistics for Economics structure. Class 12: Macroeconomics (National Income, Money & Banking, Government Budget, Balance of Payments, Determination of Income/Employment) + Indian Economic Development. |
| Computer Science | **Sumita Arora / Preeti Arora "Computer Science with Python"** — the dominant CBSE-aligned book since the Python-based curriculum (~2019 onward). | Class 11: Ch1 Computer System Overview, Ch2 Encoding Schemes & Number System / Data Representation, Ch3 Boolean Logic, Ch4 Introduction to Problem Solving, then Python basics, flow of control, functions, strings, lists/tuples/dictionaries, file handling, intro to SQL. Class 12 adds: SQL/MySQL joins, Data Structures (stack), Computer Networks, Society Law and Ethics, Flask/networking basics (recent syllabi). |
| Applied/Core Mathematics | NCERT **Mathematics** (core) or NCERT **Applied Mathematics** (commerce-specific alt.) | Core Maths Class 11: Sets, Relations and Functions, Trigonometric Functions, Complex Numbers, Linear Inequalities, Permutations & Combinations, Binomial Theorem, Sequences & Series, Straight Lines, Conic Sections, Statistics, Probability. Applied Maths swaps some calculus/geometry chapters for Logical Reasoning, Numerical Applications, and commerce-oriented topics. |
| Psychology | NCERT **Psychology** (Class 11: "Introduction to Psychology") | Ch1 What is Psychology, Ch2 Methods of Enquiry in Psychology, Ch3 The Bases of Human Behaviour, Ch4 Human Development, Ch5 Sensory/Attentional/Perceptual Processes, Ch6 Learning, Ch7 Human Memory, Ch8 Thinking, Ch9 Motivation and Emotion. |
| Legal Studies | CBSE-published **Legal Studies** textbook (introduced ~2019 as an elective) | Unit 1: Concept of State, Forms and Organs of Government, Separation of Powers. Unit 2: Salient Features of the Indian Constitution, Administrative Law. |
| Political Science | NCERT **Indian Constitution at Work** (Class 11) | Ch1 Constitution: Why and How?, Ch2 Rights in the Indian Constitution, Ch3 Election and Representation, Ch4 Executive, Ch5 Legislature, Ch6 Judiciary, Ch7 Federalism, Ch8 Local Governments, Ch9 Constitution as a Living Document, Ch10 Political Philosophy chapters (Freedom, Equality, Social Justice, etc. — second NCERT book "Political Theory"). |
| History | NCERT **Themes in World History** (Class 11) | Theme 1 "From the Beginning of Time", Theme 2 "Writing and City Life", Theme 3 "An Empire Across Three Continents" (Roman Empire), Theme 4 "The Central Islamic Lands", etc. |
| Entrepreneurship | CBSE-published **Entrepreneurship** elective textbook | Ch1 Entrepreneurship: Nature and Functions/Significance, Ch2 The Entrepreneur, Ch3 Entrepreneurship Planning Process, Ch4 Enterprise Marketing, Ch5 Enterprise Growth Strategies, Ch6 Business Arithmetic, Ch7 Resource Mobilisation. |
| Mass Media Studies | CBSE-published **Mass Media Studies** Core Book + Employability Book | Unit 1 Introduction to Mass Media (Mass Communication, Aspects/Barriers of Communication), Unit 2 Evolution of Media (Understanding Cinema), plus a separate Employability Skills book (Communication Skills, Self-Management, ICT Skills, Entrepreneurial Skills, Green Skills — common across all CBSE vocational subjects). |
| Food, Nutrition & Dietetics | CBSE-published textbook | Ch1 Nutritional Status and Primary Health Care, Ch2 Food: Basic Concept, Ch3 Nutrients, Ch4 Recommended Dietary Allowances, Ch5 Concepts of Meal Planning. |
| Physical Education | CBSE-published **Physical Education** textbook | Unit 1 Changing Trends and Career in Physical Education, Unit 2 Olympic Value Education, Unit 3 Yoga, Unit 4 Physical Fitness/Wellness, Unit 5 Sports Injuries, and further units on Training/Doping/Psychology/Sociology in Sports. |
| Painting | CBSE Fine Arts syllabus | Ch1 Prehistoric Rock Paintings, Ch2 Art of the Indus Valley, then Post-Maurya/Gupta/Mughal/Rajasthani/Company School periods. |
| Artificial Intelligence (skill subject) | CBSE **AI Level 1/2** curriculum | Unit 1 Introduction: AI for Everyone, Unit 2 AI Project Cycle / Unlocking Your Future in AI, Unit 3 Python Programming, Unit 4 Data Science / Computer Vision / NLP (varies by level). |
| IT (skill subject) | CBSE **Information Technology** curriculum | Unit 1 Computer Organisation, Unit 2 Networking Fundamentals, Unit 3 Employability Skills, Unit 4 Digital Documentation / RDBMS (DDL/DML statements), Unit 5 Web Applications. |

## When the fingerprint is ambiguous

If chapter numbering doesn't cleanly match a known book (e.g., numbering skips or a chapter title
you don't recognize), don't force-fit it — briefly note the ambiguity to the user and default to
the most common CBSE-prescribed book for that subject, using the exact chapter titles/order given
in the circular (student's actual portions always take precedence over the "standard" book order).
