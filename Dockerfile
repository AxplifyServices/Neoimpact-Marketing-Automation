FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Streamlit
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Dépendances système utiles (sqlite, build deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Déps Python (on privilégie requirements.txt si tu l'as)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Code + DB (clients.db est à la racine, on le garde pareil)
COPY . /app

EXPOSE 8501

# ⚠️ À ajuster à ton fichier Streamlit "entrée" si besoin
# (on met une valeur par défaut, tu pourras la changer ensuite)
ENV STREAMLIT_APP=app/streamlit/Consolide_int.py

CMD ["bash", "-lc", "streamlit run ${STREAMLIT_APP} --server.port ${STREAMLIT_SERVER_PORT} --server.address ${STREAMLIT_SERVER_ADDRESS}"]
