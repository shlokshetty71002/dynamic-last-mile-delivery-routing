# Windows PowerShell: run, test, commit, and push

This guide assumes Windows PowerShell and the personal repository only:
`https://github.com/shlokshetty71002/dynamic-last-mile-delivery-routing`.

## 1. Install prerequisites

Install Git for Windows and 64-bit Python 3.11 or 3.12. During Python installation, select
**Add Python to PATH**. Open a new PowerShell window and verify:

```powershell
git --version
python --version
```

If `python` is missing, reinstall from python.org with the PATH option or run the executable by
its full path. This project does not require the `py` launcher.

## 2. Clone the correct repository

```powershell
Set-Location "$env:USERPROFILE\Documents"
git clone https://github.com/shlokshetty71002/dynamic-last-mile-delivery-routing.git
Set-Location .\dynamic-last-mile-delivery-routing
git remote -v
git status
```

Both remote lines must end in `shlokshetty71002/dynamic-last-mile-delivery-routing.git`. If they
do not, stop before pushing.

## 3. Create the environment once

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

You do not have to activate the environment when using the explicit executable paths shown here.
If `.venv\Scripts\python.exe` is missing, the `python -m venv .venv` command did not finish; fix
that first rather than running later commands.

## 4. Verify the project

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\dlm.exe --help
```

Expected local gate: 60 tests pass, Ruff reports all checks passed and all files formatted, and
pip reports no broken requirements.

## 5. Build the Dublin graph and run the app

```powershell
.\.venv\Scripts\dlm.exe network build
.\.venv\Scripts\dlm.exe network stats
.\.venv\Scripts\streamlit.exe run app\main.py
```

The first graph build downloads OSM data and can take several minutes. Later builds should report
`"cache_hit": true`. Open the Streamlit local URL, normally `http://localhost:8501`. Stop it with
`Ctrl+C` in PowerShell.

## 6. Run a comparison without the UI

```powershell
.\.venv\Scripts\dlm.exe compare `
  --instance data\instances\small-n8.json `
  --scenario scenarios\oconnell_march.yaml `
  --information-model reactive `
  --output-dir results\small-oconnell

Invoke-Item .\results\small-oconnell\comparison.html
```

The folder contains JSON metrics, an interactive HTML map, and PNG/SVG figures.

## 7. Make a safe commit

Never commit `.venv`, downloaded graph caches, generated `results`, or `.env`; `.gitignore`
already excludes them.

```powershell
git branch --show-current
git status --short
git diff --check
git diff

# Stage only the files you intend to commit.
git add README.md docs src tests app data\presets data\instances scenarios `
  .github pyproject.toml requirements.txt Makefile CHANGELOG.md .gitignore `
  .env.example .pre-commit-config.yaml scripts

git status --short
git diff --cached --check
git diff --cached
git commit -m "feat: build disruption-aware Dublin routing model"
```

Review `git diff --cached` before every commit. A line-ending warning about LF/CRLF is normally
informational; `git diff --check` is the whitespace-error gate.

## 8. Push a feature branch

```powershell
git switch -c stage-01-full-routing-model
git push -u origin stage-01-full-routing-model
```

If the branch already exists locally, use `git switch stage-01-full-routing-model`. If it exists
only remotely, use `git fetch origin` then
`git switch --track origin/stage-01-full-routing-model`. Open a draft pull request on GitHub,
wait for CI to pass on Python 3.11/3.12, inspect the changed-files tab, then request review. Do not
merge or create a release tag until the project owners approve the evidence.

## 9. Continue after somebody else changes the branch

```powershell
git status --short
git pull --ff-only
.\.venv\Scripts\python.exe -m pytest
```

Commit or stash local work before pulling. `--ff-only` refuses an implicit merge and protects a
clear academic history.

## Troubleshooting

- **`fatal: not a git repository`** — use `Set-Location` into the cloned folder containing `.git`.
- **`py is not recognized`** — use `python`, which this guide and repository support directly.
- **venv executable missing** — rerun `python -m venv .venv` and inspect its error first.
- **Graph download fails** — check internet access and retry. A matching cache avoids the network.
- **Push authentication** — sign in through Git Credential Manager when prompted; never paste a
  password or token into a committed file.
- **Wrong remote** — stop and correct it with
  `git remote set-url origin https://github.com/shlokshetty71002/dynamic-last-mile-delivery-routing.git`.
