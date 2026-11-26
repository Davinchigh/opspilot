FROM python:3.13-slim
WORKDIR /app
COPY opspilot ./opspilot
COPY knowledge ./knowledge
COPY public ./public
COPY evals ./evals
RUN useradd -m app && mkdir /data && chown app /data
USER app
ENV OPSPILOT_DB=/data/opspilot-v2.db
EXPOSE 8000
CMD ["python", "-m", "opspilot", "serve", "--host", "0.0.0.0", "--port", "8000"]
