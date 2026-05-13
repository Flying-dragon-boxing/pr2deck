#!/usr/bin/pwsh
$env:GITHUB_TOKEN = ""
$env:GITHUB_REPO = ""
$env:LLM_API_TYPE = ""
$env:LLM_API_BASE_URL = ""
$env:LLM_API_KEY = ""
$env:LLM_MODEL = ""
$env:PR2DECK_PROMPT_FILE = ""

Get-Content .\changelog.txt | python .\pr2deck.py > .\index.html
