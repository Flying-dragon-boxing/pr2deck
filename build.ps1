#!/usr/bin/pwsh
Get-Content .\changelog.txt | python .\changelog2beamer.py > .\index.html
