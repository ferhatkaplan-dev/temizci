# Security policy

## Reporting a vulnerability

Please do not publish exploitable details in a public issue. Use GitHub's
**Report a vulnerability** feature (private vulnerability reporting) once it is
enabled for this repository. If private reporting is unavailable, contact a
maintainer privately before public disclosure.

Include the affected version, impact, and a minimal reproduction. Do not include
passwords, access tokens, or personal diagnostic data.

## Scope

Temizci is a local maintenance utility. Scanning is intended to be read-only;
file cleanup requires explicit user action. Privileged package/system commands
are shown in a terminal for review rather than executed by the application.
Please report any path traversal, command injection, unexpected mutation, or
private-data disclosure immediately.
