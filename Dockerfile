FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 CONFIG_DIR=/config PORT=8765 HOME=/config
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r requirements.txt
COPY . .
VOLUME /config
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/ping'%os.environ.get('PORT','8765'),timeout=3)"
CMD ["python", "app.py"]
