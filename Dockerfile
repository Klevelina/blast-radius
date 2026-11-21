# The scorer builds this on linux/amd64 and runs it with no network. The
# digest is the image we labeled every commit in.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
COPY selector_v5.py /app/selector.py
COPY data/map5.json.gz /app/data/
CMD ["python", "/app/selector.py"]
