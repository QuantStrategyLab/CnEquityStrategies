# Security Policy

Thanks for helping keep `CnEquityStrategies` safe.

This repository is an A-share strategy-library package: it owns strategy implementations, manifests, and catalog metadata for downstream platform repositories. It does not store broker credentials, submit orders, or connect to brokers itself. Please do not open a public issue for a vulnerability; report it privately instead.

## Reporting a Vulnerability

- Contact the maintainer directly at GitHub: `@Pigbibi`.
- Private vulnerability reporting is not currently enabled for this repository, so please report by direct contact rather than through GitHub's advisory flow.
- Include the repository name, affected commit or branch, environment details, and exact reproduction steps.

## Secret and Credential Exposure

This repository should never contain broker credentials, account identifiers, or private order data. If you find any committed secrets, tokens, or other sensitive material:

1. Report it privately rather than filing a public issue.
2. Note the exact file and commit so it can be purged, and rotated if it corresponds to a live credential.
3. Share only the minimum evidence needed to reproduce the issue.

## Scope Notes

Security fixes should stay minimal and focused. Please avoid bundling unrelated refactors with a security report or patch.
