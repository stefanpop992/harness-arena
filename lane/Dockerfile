FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY client.py worker.py run.py final.py ./
COPY seed/ ./seed/
RUN useradd -m lane && mkdir /work && chown lane /work
USER lane
CMD ["python", "-u", "run.py"]