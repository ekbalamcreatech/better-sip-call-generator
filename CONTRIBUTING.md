# Contributing

Thanks for helping. This project is maintained on a best-effort basis, so small,
focused pull requests get reviewed fastest.

## Ground rules

- Open an issue first for anything larger than a bug fix.
- Keep files small and readable (the codebase aims for short modules).
- No new runtime dependencies without a good reason.
- Never commit credentials, PCAPs, STIR keys, `storage/` data or `run/` output.
  `.gitignore` covers these; check `git status` before committing.
- Security-sensitive changes (scenario guard, auth, request validation, process
  launching) need a test that fails before the change and passes after.

## Sign-off (DCO)

By contributing you certify the [Developer Certificate of Origin](https://developercertificate.org/).
Add a sign-off to each commit with `git commit -s`.

## Licensing

Contributions are licensed under Apache-2.0, the same as the project.
SIPp (GPLv3) is never copied into this repository.

## Running locally

See the README. In short: install SIPp and tcpdump, `pip install -r requirements.txt`,
then `uvicorn main:app --host 127.0.0.1 --port 8000`.
