# copilot-cli-skills

Personal collection of [GitHub Copilot CLI](https://docs.github.com/copilot/how-tos/use-copilot-agents/use-copilot-cli)
plugins/skills — packaged so they can be installed on **any machine**, not just the one they were
built on.

This repo doubles as a **plugin marketplace** (via `.github/plugin/marketplace.json`), so every
plugin under `plugins/` is installable directly by GitHub Copilot CLI without manually copying or
symlinking files.

## Installing a plugin from this repo (recommended — works on any machine)

**Option A — register this repo as a marketplace once, then install by name:**

```bash
copilot plugin marketplace add senthilkumar-eswaren/copilot-cli-skills
copilot plugin install cbse-unit-test-prep@copilot-cli-skills
copilot plugin install sof-olympiad-prep@copilot-cli-skills
```

**Option B — install directly from the GitHub subdirectory, no marketplace needed:**

```bash
copilot plugin install senthilkumar-eswaren/copilot-cli-skills:plugins/cbse-unit-test-prep
copilot plugin install senthilkumar-eswaren/copilot-cli-skills:plugins/sof-olympiad-prep
```

Verify with `copilot plugin list` (or `/plugin list` inside an interactive session).

> Installing a plugin only loads its `SKILL.md`/agents/hooks into Copilot CLI — it does **not**
> install whatever external command-line tools that skill's instructions may shell out to (e.g.
> `pandoc`, a browser, Python packages). Check each plugin's own docs for its runtime requirements.

### Windows step by step (sof-olympiad-prep)

Run these in **PowerShell** (Start → type "PowerShell"), opening a new window after each install
so the new commands are found.

1. Install PowerShell 7 and Copilot CLI (needs an active GitHub Copilot plan), then sign in:

   ```powershell
   winget install Microsoft.PowerShell
   winget install GitHub.Copilot
   copilot      # first run: type /login, follow the prompts, then /exit
   ```

2. Install **Python Install Manager** from the [Microsoft Store](https://apps.microsoft.com/detail/9NQ7512CXL7T)
   or [python.org](https://www.python.org/downloads/windows/). In a new window run `python --version`
   (the first run downloads Python; accept its prompts), then optionally add page footers and previews:

   ```powershell
   python -m pip install pymupdf
   ```

3. Install the skill:

   ```powershell
   copilot plugin marketplace add senthilkumar-eswaren/copilot-cli-skills
   copilot plugin install sof-olympiad-prep@copilot-cli-skills
   ```

4. Start `copilot` and ask, for example, *"Make an IMO Class 5 mock paper"*. The question paper,
   answer key and OMR sheet PDFs are saved in **Downloads** (made with Microsoft Edge, which comes
   with Windows, or Chrome if installed).

Update later with `copilot plugin update sof-olympiad-prep@copilot-cli-skills`. Windows support is
new in 1.1.1; please report problems in this repo's Issues.

## Repo structure

```text
copilot-cli-skills/
├── README.md
├── .github/plugin/marketplace.json   # marketplace registry — lists every plugin below
└── plugins/
    ├── cbse-unit-test-prep/
    │   ├── plugin.json               # plugin manifest (name, description, version, ...)
    │   └── skills/
    │       └── cbse-unit-test-prep/
    │           ├── SKILL.md          # triggers Copilot CLI to use this skill automatically
    │           └── references/       # detail docs the skill reads on-demand
    └── sof-olympiad-prep/
        ├── plugin.json
        └── skills/
            └── sof-olympiad-prep/
                ├── SKILL.md
                ├── data/             # class3.json, class5.json (exam patterns, syllabi), question styles
                ├── references/
                └── scripts/          # Python helpers (blueprint, validate, render PDFs, score)
```

A plugin can bundle more than skills (agents, hooks, MCP server configs — see the
[plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)),
but every plugin in this repo currently contains just one skill.

## Plugins in this repo

| Plugin | Description |
|---|---|
| [`cbse-unit-test-prep`](./plugins/cbse-unit-test-prep) | Generates a detailed CBSE unit-test/exam study guide (chapter notes + CBSE-pattern Q&A, exported as DOCX + PDF) from a school exam timetable/portions circular. Covers CBSE Class XI/XII, any stream. Requires `pandoc`, Python (`python-docx`, `pypdf`), and a Chromium-based browser on the machine running it — see the plugin's `references/03-assembly-and-conversion-pipeline.md` for an install matrix and graceful-fallback behavior when a tool is missing. |
| [`sof-olympiad-prep`](./plugins/sof-olympiad-prep) | Generates original SOF-style practice papers for Class 3 and Class 5 olympiads (IMO, IEO, ICSO): full mock tests and topic-wise practice sets with answer keys and OMR sheets as print-ready PDFs, plus marking, a separate score log for each child and weak-topic reports. Several children can share one setup: register each with its class (`sof_common.py students add <label> --class 3`) and pass `--student <label>`. Papers are written fresh from the published exam pattern and syllabus — no SOF papers are copied or bundled; not affiliated with SOF. Requires Python 3.9+ (standard library only) and Google Chrome, Microsoft Edge or Chromium for PDFs (or set `OLYMPIAD_BROWSER` to the browser binary; without a browser it writes HTML only); PyMuPDF is optional (page footers, previews). Data is kept in `~/olympiad-prep` (override with `OLYMPIAD_PREP_HOME`); PDFs are saved to `~/Downloads` when it exists (override with `OLYMPIAD_OUT_DIR`). On Windows, see [Windows step by step](#windows-step-by-step-sof-olympiad-prep). |

## Adding a new plugin to this repo

1. Create `plugins/<plugin-name>/plugin.json` (minimum: `{"name": "<plugin-name>"}` — see the
   [plugin manifest reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference#pluginjson)
   for optional fields like `description`, `version`, `author`).
2. Add its `SKILL.md` (+ optional `references/`) under `plugins/<plugin-name>/skills/<plugin-name>/`.
3. Add an entry for it to the `plugins` array in `.github/plugin/marketplace.json`, with
   `"source": "plugins/<plugin-name>"`.
4. Install and smoke-test locally: `copilot plugin install ./plugins/<plugin-name>`, then
   `copilot plugin list` to confirm it loaded, and exercise the skill to confirm it triggers and
   behaves as expected.
5. Commit and push. Anyone with this marketplace registered can now
   `copilot plugin install <plugin-name>@copilot-cli-skills`.

### Local development loop

While iterating on a plugin before it's pushed, install straight from your local clone:

```bash
copilot plugin install ~/copilot-cli-skills/plugins/<plugin-name>
```

Plugin components are cached on install, so re-run `copilot plugin install <path>` after each
local edit to pick up changes (`copilot plugin uninstall <name>` to remove it entirely).
