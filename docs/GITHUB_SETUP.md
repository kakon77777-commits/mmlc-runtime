# GitHub setup

Recommended repository:

```text
kakon77777-commits/mmlc-runtime
```

After creating an empty GitHub repository, extract the release package and run:

```bash
git init
git add .
git commit -m "Release MMLC Runtime v1.0.0"
git branch -M main
git remote add origin https://github.com/kakon77777-commits/mmlc-runtime.git
git push -u origin main
```

Create the release tag:

```bash
git tag -a v1.0.0 -m "MMLC Runtime v1.0.0"
git push origin v1.0.0
```

Suggested repository description:

> Auditable multidirectional matrix-ledger runtime for deterministic computation, constraints, temporal dynamics, counterfactuals, uncertainty, and finite decision analysis.

Suggested topics:

```text
matrix-computation
ledger
audit
counterfactual
causal-inference
symbolic-computation
uncertainty
decision-analysis
python
```

## First release assets

Attach:

- `MMLC_Runtime_v1.0_完整實作包.zip`
- the source distribution or wheel from `dist/`
- `MMLC_Runtime_v1.0_SHA256.txt`
- `RELEASE_NOTES_v1.0.0.md`

## Recommended repository settings

- default branch: `main`
- enable Issues and Discussions
- require the CI workflow before merging
- enable Dependabot security updates when desired
- create a branch protection rule after the initial push
