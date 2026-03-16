# Security Policy

## Supported Versions

We release security updates for the latest stable release. Older versions may not receive patches.

## Reporting a Vulnerability

If you believe you have found a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue for security-sensitive bugs.
2. Email the maintainers (e.g. via the repository’s contact or owner list) with a description of the issue, steps to reproduce, and impact if possible.
3. Allow a reasonable time for a fix before any public disclosure.

We will acknowledge receipt and work with you to understand and address the issue. We appreciate your help in keeping the project and its users safe.

## Best Practices for Users

- Do not commit API keys, secrets, or credentials to the repository. Use environment variables or secure config (e.g. `~/.config/devsper/config.toml` with restricted permissions: `chmod 600`).
- When running tools that execute shell commands or external code, ensure inputs are validated and that you trust the task descriptions and tool outputs in your environment.
