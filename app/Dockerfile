FROM python:3.14.3-slim

WORKDIR	/app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p database

EXPOSE 5000

CMD ["sh", "-c", "python init_db.py && gunicorn --bind 0.0.0.0:5000 app:app"]
