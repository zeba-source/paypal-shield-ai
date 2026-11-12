# Repository Security Audit

Date: 2026-11-12
Repository: PayPal Shield AI
Scope: Working tree and reachable Git history in the `Fintech/` repository.

## Executive Summary

The repository contains application source, tests, frontend code, SQL, documentation, a small PaySim-style sample, and published evaluation metrics. Local credentials are present in ignored files only. No tracked credential file, private key, hardcoded secret value, or historical credential value was identified by the read-only audit.

This audit does not certify the repository as completely secure. The local `.env` contains non-empty database and PayPal credential values and an LLM key field, so those values must remain local and should be rotated if they have ever been shared, logged, or committed outside the inspected Git history. The tracked sample dataset should also be reviewed for licensing and publication approval before a public release.

No destructive Git operation, history rewrite, credential rotation, deletion, commit, push, or external upload was performed.

## Inventory Summary

### A. Essential source code

- Root Python services, configuration, policy, orchestration, Kafka consumers/producers, database access, and evaluation scripts.
- `agents/`, `api/`, `scripts/`, `tests/`, and `sql/`.
- `frontend/app/`, `frontend/components/`, `frontend/hooks/`, and `frontend/lib/`.
- Python and frontend dependency manifests and lockfiles.

### B. Public documentation

- `README.md`, `LICENSE`, `docs/`, `frontend/README.md`, and repository guidance files.

### C. Safe configuration templates

- `.env.example` is tracked and now contains variable names with safe placeholders only.
- `frontend/.gitignore` and the root `.gitignore` are configuration, not credentials.
- `results/metrics.json` is a published evaluation report and remains trackable.

### D. Private credentials

- `.env`: local database values, PayPal client credentials, and an LLM key field. Ignored and untracked.
- `frontend/.env.local`: local API URL and public PayPal client ID. Ignored and untracked.
- No credential files, private keys, PEM/P12/PFX files, or service-account JSON files were found in the meaningful project tree.

### E. Private datasets

- `small_dataset.csv` is tracked and contains 1,000 PaySim-style transaction rows with transaction/account identifiers, balances, fraud labels, and flags. No obvious personal names or contact fields were observed in the header. It is preserved as an intentionally published sample, but provenance, licensing, and privacy approval remain required.
- No separate `data/`, `datasets/`, or model artifact directory was found outside ignored/local trees.

### F. Generated files and caches

Observed locally and ignored: `venv/`, `.venv/`, `.next/`, `frontend/node_modules/`, Python bytecode/cache directories, `.pytest_cache/`, `.agent/`, `.fintech-processes.json`, and `frontend/next-env.d.ts`.

### G. Potentially sensitive files investigated

- `config.py`: loads database settings from environment variables into `DB_CONFIG`.
- `api/paypal_client.py`: loads PayPal client ID and secret, obtains OAuth tokens, and sends bearer tokens to PayPal.
- `api/investigator.py`: consumes the LLM API key from the environment.
- `frontend/.env.local` and frontend shop code: use only the public PayPal client ID in the browser.
- `README.md`, tests, SQL, workflows/deployment paths, certificates, and key filenames were checked for credential indicators. No hardcoded secret value was identified.

### H. Git-tracked files

The repository has 68 tracked files at audit time. Tracked sensitive candidates were limited to `.env.example` and the sample `small_dataset.csv`; neither contains a real credential. `results/metrics.json` is tracked and intentionally preserved.

## Sensitive Findings

| File | Line | Category | Severity | Remediation |
| --- | ---: | --- | --- | --- |
| `.env` | 3 | Database password/value | High if shared | Keep ignored; rotate the database password if the file or value was exposed. |
| `.env` | 10-11 | PayPal client ID and client secret | High for the secret; informational for the ID | Keep the secret server-side; revoke/rotate the PayPal secret if exposed. The client ID is not itself a secret. |
| `.env` | 16 | LLM API key field | High if populated/shared | Keep the key out of Git and rotate it if exposed. |
| `frontend/.env.local` | 1-2 | Local API URL and public PayPal client ID | Low/informational | Keep local env files ignored; public client IDs must never be accompanied by a secret in frontend code. |

Only filenames, line locations, categories, and remediation are recorded here. Secret values are intentionally omitted.

## Existing Git Problems

- The previous root `.gitignore` did not cover private-data directories, model artifacts, database files, certificates/private keys, Terraform state/variables, or common temporary/log files.
- Local `.env`, frontend local environment values, and generated dependency/build trees were present but ignored.
- No sensitive file requiring `git rm --cached` was found.
- No historical real credential value was identified in the inspected reachable Git history. A complete GitHub-side secret scan should still be run before publication if the repository has other remotes, forks, or rewritten history not present locally.

## Ignore Rules Added or Expanded

The root `.gitignore` now covers:

- `.env.*` with exceptions for `.env.example` and `.env.template`.
- `secrets/`, `private/`, `credentials/`, `*.secret`, and `*.token`.
- Python virtual environments, caches, coverage, build outputs, and package artifacts.
- Node.js/Next.js dependencies, build output, package stores, and TypeScript build metadata.
- Logs, temporary files, operating-system files, and IDE metadata.
- `data/`, `datasets/`, `private_data/`, private CSVs by default, and common ML/model artifacts.
- Local SQLite/database files and database storage directories.
- Certificates, private keys, SSH keys, Terraform state/variables, and cloud/Kubernetes local credentials.
- Explicit exceptions for `small_dataset.csv`, `results/metrics.json`, and `results/ablation.csv`.

`package-lock.json`, `frontend/package-lock.json`, source code, tests, docs, and README files remain eligible for tracking.

## Environment Template

`.env.example` was sanitized with safe defaults/placeholders and retains the existing application variable names. `PAYPAL_BASE_URL` was added because the local configuration uses it. No local `.env` value was copied into the template.

## Tracking Remediation

No files were removed from Git tracking. Therefore, no `git rm --cached` command was executed.

If a sensitive file is later found tracked, use the following after reviewing the path:

```powershell
git rm --cached -- path/to/local-secret-file
```

This preserves the local file but removes it from the index. If a real secret was committed in any reachable or shared history, rotate/revoke it immediately and use an approved history-rewrite procedure only after coordination with all repository users. Do not rely on `.gitignore` alone for historical exposure.

## Credentials Requiring Rotation Review

- The local MySQL password value in `.env`, if it is real and has been shared or exposed.
- The PayPal client secret value in `.env`, if it is real and has been shared or exposed.
- The LLM API key value in `.env`, if populated and exposed.
- Any corresponding sandbox account credentials associated with the local PayPal integration, if reused elsewhere.

The audit did not rotate or revoke any credential.

## Verification Results

The following checks were run after the configuration edit:

- `git diff --check`: passed; only existing line-ending warnings were reported for unrelated modified files.
- `.env`: ignored.
- `.env.example`: not ignored.
- `frontend/.env.local`: ignored.
- `node_modules/`, `frontend/node_modules/`, `venv/`, and `.venv/`: ignored.
- `private_data/paysim.csv`: ignored.
- `model.onnx` and `local.sqlite3`: ignored by representative artifact rules.
- `small_dataset.csv`: trackable by explicit publication exception.
- `results/metrics.json`: trackable.
- `results/ablation.csv`: explicit publication exception; verify with `git check-ignore -q` because verbose output reports the matching negation rule.
- `README.md`, `tests/test_api.py`, and `docs/README.md`: trackable.
- Git status was inspected before and after the edit; existing user modifications were preserved.
- No local `gitleaks` or `trufflehog` executable was available, so no local third-party secret scanner was run.

Recommended final verification commands:

```powershell
git status --short
git ls-files
git check-ignore -v .env frontend/.env.local private_data/paysim.csv model.onnx local.sqlite3
git check-ignore -q .env.example; if ($LASTEXITCODE -eq 1) { 'OK: .env.example is not ignored' }
git check-ignore -q results/metrics.json; if ($LASTEXITCODE -eq 1) { 'OK: metrics are not ignored' }
git check-ignore -q results/ablation.csv; if ($LASTEXITCODE -eq 1) { 'OK: ablation output is not ignored' }
```

## Final GitHub Publishing Recommendations

1. Review the existing worktree changes before staging; this audit did not stage or commit anything.
2. Confirm that `small_dataset.csv` is legally publishable and contains no sensitive account data. Remove it from tracking only with explicit approval if it is not approved.
3. Run an approved secret scanner locally and inspect all findings without printing values.
4. Check repository settings, branch protection, required reviews, Dependabot, secret scanning, push protection, and environment-specific GitHub Actions secrets.
5. Keep PayPal, database, LLM, Kafka, OTP, and any future WebAuthn secrets in a managed secret store or local environment, never in frontend source or committed configuration.
6. Rotate any local credential listed above if it has been exposed outside the ignored local files.
7. Before the first public push, review the complete staged diff and verify that no ignored file was force-added.
