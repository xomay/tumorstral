# Third-party data and models

The MIT licence at the repository root applies to original TumorTwin code and
documentation. It does not replace the licences of dependencies, datasets,
model weights or source-derived material. Raw datasets and model weights are
downloaded separately and are not distributed in this repository.

## INSPECTumours

Source: [AstraZeneca/INSPECTumours](https://github.com/AstraZeneca/INSPECTumours),
revision `eb41f4f80595b7185cf925a3195d35e1e3b34394`.
The example data and dictionary are obtained from that repository.
The upstream [Apache License 2.0](https://github.com/AstraZeneca/INSPECTumours/blob/eb41f4f80595b7185cf925a3195d35e1e3b34394/LICENSE.md)
is retained alongside the downloaded files as `LICENSE.upstream.md`.
The preclinical reference figures and numerical summaries are derived analyses;
the raw file is unchanged.

## Human target-lesion measurements

Ghaffari Laleh N, Loeffler CML, Grajek J, Staňková K, Pearson AT, Muti HS, et al.
(2022). *Classical mathematical models for prediction of response to
chemotherapy and immunotherapy.* PLOS Computational Biology 18(2): e1009822.
[Article](https://doi.org/10.1371/journal.pcbi.1009822) ·
[Original S1 Data supplement](https://doi.org/10.1371/journal.pcbi.1009822.s006).

The publication and supporting material are released under the Creative
Commons Attribution licence stated on the article. Human figures and summaries
in `reports/human_review/` and `docs/human_results.md` are derived from this
public supplement. TumorTwin computes estimated volumes as `0.5 × diameter_mm³`,
preserves the published relative days, and does not apply whole-dataset
normalization. The curated figures show anonymized source identifiers.
These derived analyses are not original study outcomes or segmented volumes.
Retain this attribution when reusing them; the project MIT licence does not
waive the source's attribution conditions.

## Timestral code

Source: [Mistral AI Timestral](https://github.com/mistralai/timestral), revision
`a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff`.
The optional upstream implementation is licensed under
[Apache License 2.0](https://github.com/mistralai/timestral/blob/a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff/LICENSE)
and is installed as a dependency, not copied into TumorTwin's source tree.

## Timestral model weights

Source: [mistralai/Timestral-5M](https://huggingface.co/mistralai/Timestral-5M),
revision `bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f`.
The weights use a separate
[Modified MIT licence](https://huggingface.co/mistralai/Timestral-5M/blob/bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f/LICENSE)
with additional conditions, including a commercial revenue restriction.
This is not standard MIT and is not replaced by TumorTwin's code licence.
The download keeps the model's own `LICENSE` and checksums locally.

## Other dependencies

Python dependencies keep their respective licences. `pyproject.toml` declares
them and `uv.lock` records their resolved versions and sources. Build metadata
includes this notice and the project licence.
