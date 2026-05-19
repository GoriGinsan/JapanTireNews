# JapanTireNews operations

## Hourly news task

The Windows task `JapanTireNewsHourly` runs `scripts/run_once.ps1`.

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install_windows_task.ps1
```

`run_once.ps1` writes a run log under `logs/`. If the Python job fails, it creates a GitHub issue with labels `bug`, `automation`, and `fatal`. Duplicate failures are de-duplicated by a hash in `logs/last_failure_issue_hash.txt`.

GitHub issue creation requires one of the following:

- GitHub CLI (`gh`) authenticated with `gh auth login`
- `GITHUB_TOKEN` in `.env` or the task environment, with Issues read/write permission

## Daily Codex review task

The Windows task `JapanTireNewsCodexReview` asks Codex CLI to inspect open issues and propose reliability or news-quality improvements at 09:00.

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install_codex_review_task.ps1
```

To allow Codex CLI to apply fatal fixes without asking the user, register the task with `-Autofix`.

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install_codex_review_task.ps1 -Autofix
```

The Codex job pulls the latest `main`, reads up to 20 open GitHub issues, and writes its prompt to `logs/codex_daily_prompt.md`. In autofix mode, Codex is instructed to keep changes small, avoid committing secrets or runtime data, run a dry-run check, commit the fix, and leave the repository on a `codex/autofix-*` branch. After Codex exits successfully, the wrapper pushes that branch and creates a GitHub pull request with `gh pr create`.
