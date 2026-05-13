#!/bin/bash
export GITHUB_TOKEN=
export GITHUB_REPO=
export LLM_API_TYPE=
export LLM_API_BASE_URL=
export LLM_API_KEY=
export LLM_MODEL=
export PR2DECK_PROMPT_FILE=

python pr2deck.py < changelog.txt > index.html
