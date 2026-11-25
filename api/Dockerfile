FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --disable-pip-version-check --require-hashes -r requirements.lock
COPY src /app/src
USER 65534:65534
EXPOSE 8000
CMD ["uvicorn", "licence_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]
