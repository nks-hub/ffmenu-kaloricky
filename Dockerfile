FROM python:3.12-slim
# DejaVu Sans has the Czech letters for the photo card that KT requires with a new food
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && apt-get clean
RUN pip install --no-cache-dir pillow==13.0.0
WORKDIR /app
# no static/: the phone page writes into the diary of the server's account, so the shared server ships only the API
COPY ffkt ffkt
RUN mkdir data && chown nobody data
USER nobody
ENV PYTHONUNBUFFERED=1
EXPOSE 8077
CMD ["python", "-m", "ffkt", "serve", "--port", "8077"]
