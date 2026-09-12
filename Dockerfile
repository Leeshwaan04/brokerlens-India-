# This Dockerfile is for exactly one thing: the live-quote stream service
# deployed to Cloud Run (see server/devserver.py's CLOUD RUN NOTE). It is NOT
# how the site itself is built or hosted - that's Vercel, driven entirely by
# scripts/vercel-build.sh, and does not go anywhere near this file.
#
# Lives at the repo root only because `gcloud run deploy --source .` requires
# a root-level Dockerfile with no way to point at a different path on this
# gcloud version - the build context still needs pipeline/, server/, and
# config/ as siblings, which is the actual reason for the location.
FROM python:3.12-slim

WORKDIR /app

# Zero pip dependencies anywhere in this repo, by design (see pipeline/
# module docstrings) - stdlib only, so no requirements.txt/pip install step.
COPY pipeline/ pipeline/
COPY server/ server/
COPY config/ config/

WORKDIR /app/server
CMD ["python3", "devserver.py"]
