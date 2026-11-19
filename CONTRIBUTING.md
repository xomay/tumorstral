# Contributing to tumorstral

Contributions improving correctness, reproducibility and clarity are welcome.
Use [issues](https://github.com/xomay/tumortwin/issues) to report bugs or discuss
changes that affect the scientific protocol.

## Set up a checkout

```sh
git clone https://github.com/xomay/tumortwin.git tumorstral
cd tumorstral
uv sync --locked
uv run --offline pytest
uv build
```

Use Python 3.11 or newer and uv for dependency management. The checkout defaults
to Python 3.14. Commit dependency changes together with `uv.lock`.
Install `uv sync --locked --extra timestral` when testing real model inference.
Core tests do not require weights or human data.

## Submit a change

Create a branch, make a focused change, run the relevant tests and open a pull
request. Describe the problem, resulting behaviour, checks and any effect on
existing experimental results. Add tests for scientific or numerical behaviour;
documentation corrections do not need tests that repeat the text.

For a bug report, include the command, software versions, configuration and a
minimal synthetic example. Do not upload credentials, raw patient data or model
weights. Public source identifiers should be included only when needed to
reproduce a source-specific issue.

## Scientific conventions

- Preserve original dates, units, missing values and source provenance.
- Treat Laleh's diameter-derived volume as an estimate for one target lesion.
- Keep individuals disjoint between development and test. Never condition a
  forecast on future target values or clean a prefix using future observations.
- Export duplicate dates, censored readings and numerical failures explicitly.
- Compare models on common targets and report the number of individuals.
- Keep Timestral weights frozen and document its internal handling of missing
  values. Preserve raw outputs, including negative forecasts.
- Use deterministic seeds and record data, code, configuration and model hashes.
- Keep historical experiment snapshots intact. Use a new run directory for
  changed data, protocols or implementations.
- Link acronyms to the [glossary](src/tumorstral/glossary.md), expand plot labels,
  and include a local glossary in exported reports.

The source layout and additional conventions are in [AGENTS.md](AGENTS.md).
Original contributions are distributed under the [project MIT licence](LICENSE).
Data and model sources retain their [separate terms](THIRD_PARTY_NOTICES.md).
