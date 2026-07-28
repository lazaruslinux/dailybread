# Digest-pinned so a build is reproducible and a poisoned tag can't slip in;
# Dependabot bumps the digest. The tag rides along as a comment for humans.
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements first so Docker can cache the install layer. The compiled
# requirements.txt pins every package with hashes; --require-hashes makes pip
# refuse anything that doesn't match it.
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations

# The app parses untrusted input (image uploads, two phone-sync dialects), so
# it runs unprivileged. The media dir is chowned here because the named volume
# mounted over it copies this ownership on first use.
RUN useradd --create-home app && mkdir -p /app/media && chown app /app/media
USER app

EXPOSE 8000

# Apply any pending schema migrations, then start the API. Upgrade is a no-op
# when the database is already current, so restarts stay fast.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
