FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TTSLIBRE_ROOT=/opt/ttslibre \
    AUDIO_OUTPUT_DIR=/data/audio

WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.5.1+cpu torchaudio==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth=1 https://github.com/franciscocarloserra/ttslibre.git /opt/ttslibre \
    && hf download FranciscoCarlosErra/ttslibre-poc-es-ar --local-dir /tmp/model \
    && hf download charactr/vocos-mel-24khz \
    && mkdir -p /opt/ttslibre/experiments/20-scaling/014-spanish-8h-openslr61/runs/es8h \
                /opt/ttslibre/experiments/20-scaling/014-spanish-8h-openslr61/runs/ae \
                /opt/ttslibre/experiments/voices \
                /opt/ttslibre/datasets/openslr61/prep \
    && cp /tmp/model/ttl.pt /opt/ttslibre/experiments/20-scaling/014-spanish-8h-openslr61/runs/es8h/ttl.pt \
    && cp /tmp/model/ae.pt /opt/ttslibre/experiments/20-scaling/014-spanish-8h-openslr61/runs/ae/ae.pt \
    && cp /tmp/model/config.json /opt/ttslibre/experiments/20-scaling/014-spanish-8h-openslr61/config.json \
    && sed -i 's#../../datasets/#../../../datasets/#g' /opt/ttslibre/experiments/20-scaling/014-spanish-8h-openslr61/config.json \
    && cp /tmp/model/latent_stats.pt /tmp/model/vocab.json /opt/ttslibre/datasets/openslr61/prep/ \
    && cp /tmp/model/ref_default.wav /opt/ttslibre/datasets/openslr61/arf_00295_00000740990.wav \
    && cp /tmp/model/voices/*.pt /opt/ttslibre/experiments/voices/

COPY app.py .
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
