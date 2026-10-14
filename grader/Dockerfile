FROM python:3.12-slim
WORKDIR /app
COPY grader.py runner.py ./
USER nobody
EXPOSE 8090
CMD ["python", "-u", "grader.py"]
