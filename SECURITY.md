# Security

## Reporting a vulnerability

Please report security issues privately, not in a public issue. Use GitHub's
private vulnerability reporting: open the repository's **Security** tab and
choose **Report a vulnerability**. That keeps the details between us until
there is a fix.

## What counts

Anything that crosses the family wall is in scope: one family reading or
changing another family's data, an authentication or authorization bypass, a
child account reaching an adults-only surface, or any path that exposes stored
data to someone who should not see it. Session, cookie, and token handling
count too.

## Deployment note

dailybread is designed to run on a private network behind a reverse proxy that
terminates TLS, not exposed directly to the public internet. The public demo is
the one deliberate exception, and it holds only fake data. A report is still
welcome for anything that would be a real risk in that intended setup.
