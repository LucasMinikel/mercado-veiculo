# Stage 1: Preparar shared
FROM python:3.11-alpine as shared-stage
WORKDIR /shared
COPY shared/ .

FROM python:3.11-alpine
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN apk add --no-cache curl
COPY services/orquestrador/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=shared-stage /shared ./shared
COPY services/orquestrador/ .
RUN adduser -D app && chown -R app:app /app
USER app
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]