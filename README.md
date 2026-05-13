# pr2deck

Generate a paginated HTML slide deck from a GitHub pull request changelog.

`pr2deck` reads a grouped list of PRs from stdin, fetches PR metadata from GitHub, optionally summarizes PR descriptions with an OpenAI-compatible chat API, downloads author avatars, and writes a self-contained HTML deck to stdout.

## Features

- Turns PR lists into a 16:9 HTML presentation deck.
- Groups slides by section headings such as `Feature`, `Fix`, or `Refactor`.
- Fetches PR titles, bodies, authors, and avatars from GitHub.
- Supports OpenAI-compatible LLM APIs for compact card summaries.
- Reads the summary prompt from `prompt.txt` or a custom prompt file.
- Caches GitHub and LLM responses locally.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Input Format

Create a text file such as `changelog.txt`:

```text
Feature
Feature: add class PotXC_FDM and Pot_Cosikr by @linpeize in #6962
[Feature] Add gemv_op_mt for DSP by @Cstandardlib in #7009

Fix
Fix: correct the unit conversion between Plumed and ASE in example by @kirk0830 in #6993
```

Section lines become slide group labels. Lines containing `#1234` are treated as PR entries.

## Usage

```bash
python pr2deck.py < changelog.txt > index.html
```

Or use the helper scripts:

```bash
./build.sh
```

```powershell
.\build.ps1
```

## Environment Variables

| Variable | Description |
| --- | --- |
| `GITHUB_REPO` | GitHub repository in `owner/name` form. Defaults to `deepmodeling/abacus-develop`. |
| `GITHUB_TOKEN` | Optional GitHub token for higher API rate limits. |
| `LLM_API_BASE_URL` | Base URL for an OpenAI-compatible chat API, for example `https://api.deepseek.com`. |
| `LLM_API_KEY` | API key for the LLM service. |
| `LLM_MODEL` | Model name, for example `deepseek-chat`. Defaults to `deepseek-chat`. |
| `PR2DECK_PROMPT_FILE` | Prompt file path. Defaults to `prompt.txt`. |
| `PR_CACHE_FILE` | GitHub PR cache path. Defaults to `.pr_cache.json`. |
| `PR_CACHE_TTL` | GitHub PR cache TTL in seconds. Defaults to `86400`. |
| `MODEL_CACHE_FILE` | LLM response cache path. Defaults to `.model_cache.json`. |
| `MODEL_CACHE_TTL` | LLM response cache TTL in seconds. Defaults to `604800`. |

If `LLM_API_KEY` is empty, `pr2deck` skips LLM summarization and falls back to PR body text.

## Prompt

The default prompt lives in `prompt.txt`. Edit it directly, or point to another file:

```bash
export PR2DECK_PROMPT_FILE=my_prompt.txt
python pr2deck.py < changelog.txt > index.html
```

## CLI Options

```bash
python pr2deck.py --help
```

Common options:

- `--refresh-cache`: refresh PR data from GitHub.
- `--refresh-model-cache`: refresh LLM summaries.
- `--clear-cache`: delete local PR and model caches.
- `--title "My Changelog"`: set the HTML document title.

## Notes

Generated HTML files are ignored by default. Keep production credentials out of Git; use local scripts or environment variables for secrets.

## License

This project is licensed under the BSD 3-Clause License. See [LICENSE](LICENSE).
