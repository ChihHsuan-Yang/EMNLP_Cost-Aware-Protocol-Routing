# Contributing

Thanks for your interest. This repository is a research artifact accompanying a
published paper, so the bar for changes is a little different from a normal
software project.

## What we especially welcome

- **Reproduction reports.** If a documented command does not work in your
  environment, that is a bug and we want to hear about it. Please include your
  OS, Python version, and the full output.
- **Discrepancies against the paper.** If a regenerated number disagrees with a
  table in `results/aggregate/`, open an issue with the command and the diff.
- **Documentation fixes**, especially anywhere the text assumes knowledge a
  first-time reader would not have.
- **Portability fixes** that do not change any scientific value.

## What we will not merge

- Changes that alter a published result. The numbers in `results/aggregate/` are
  the camera-ready record. If you believe one is wrong, open an issue; we will
  not silently change it.
- Upstream benchmark problem text or gold answers. See `NOTICE` for why.
- New dependencies without a clear need. The install is deliberately small.
- Anything containing credentials, internal paths, or private infrastructure
  detail.

## Before you open a pull request

```bash
make setup
make test
make smoke
```

All three must pass. If your change touches analysis code, also run
`make reproduce-tables` and confirm it still matches the camera-ready tables.

## Reporting a problem with the data

Data issues (a wrong identifier, a schema mismatch, a checksum that does not
verify) should be filed here as issues rather than on the Hugging Face
repositories, so that discussion stays in one place.

## Code of conduct

Participation is governed by `CODE_OF_CONDUCT.md`.
