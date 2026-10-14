FROM python:3.12-slim
WORKDIR /app
COPY meter.py .
USER nobody
EXPOSE 8080
CMD ["python", "-u", "meter.py"]
