# copilot-cli-skills

Personal collection of reusable [GitHub Copilot CLI](https://docs.github.com/copilot/how-tos/use-copilot-agents/use-copilot-cli) skills.

Each top-level folder is one skill: a `SKILL.md` (with YAML frontmatter — `name` + `description`
that tells Copilot CLI when to auto-invoke it) plus an optional `references/` folder of detail docs
that are only read on demand, to keep the main skill file lean.

## Installing a skill locally

Copilot CLI loads personal skills from `~/.copilot/skills/<skill-name>/`. To install one from this
repo:

```bash
ln -s ~/copilot-cli-skills/<skill-name> ~/.copilot/skills/<skill-name>
```

Symlinking (rather than copying) keeps your local install and this repo in sync — edit either
location and the change shows up in both.

## Skills in this repo

| Skill | Description |
|---|---|
| [`cbse-unit-test-prep`](./cbse-unit-test-prep) | Generates a detailed CBSE unit-test/exam study guide (chapter notes + CBSE-pattern Q&A, exported as DOCX + PDF) from a school exam timetable/portions circular. Covers CBSE Class XI/XII, any stream. |

## Adding a new skill

1. Create `<skill-name>/SKILL.md` with YAML frontmatter (`name`, `description`) and the skill's
   instructions in Markdown below it.
2. Put any large reference material the skill should read on-demand under `<skill-name>/references/`.
3. Symlink it into `~/.copilot/skills/<skill-name>` to activate it locally.
4. Commit and push.
