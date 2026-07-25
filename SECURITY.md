# Security policy

## Supported versions

Security fixes are accepted for the latest Runtime 1.x release.

## Reporting

Do not publish exploit details in a public issue before maintainers have had a reasonable opportunity to investigate. Use a private GitHub security advisory when the repository is available.

Include:

- affected version;
- minimal reproducer;
- expected and observed behavior;
- impact;
- whether the issue involves schema validation, resource exhaustion, path handling, untrusted plugins, or output integrity.

## Current security boundary

MMLC documents are data, but the runtime can consume large graphs and expensive fixed-point, repair, uncertainty, and decision analyses. Resource limits should be applied when processing untrusted documents. Runtime 1.0 does not provide a hardened multi-tenant sandbox.
