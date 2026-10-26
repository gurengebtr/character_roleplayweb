# Security

This MVP is intended for a trusted local machine, bound to loopback. It has not been hardened for an internet-facing production deployment.

Report vulnerabilities privately through the repository's GitHub **Security → Report a vulnerability** feature when enabled. Otherwise contact the maintainer privately through the contact information on their GitHub profile. Do not post credentials, authorization URLs, encryption keys or personal chats in public issues.

Keep `.env` and `.local/` private. They contain generated secrets and encrypted model credentials. Use disposable test accounts for integration tests. If a credential is exposed, revoke it with its provider and replace the affected secret; removing it from a later commit does not remove it from Git history.
