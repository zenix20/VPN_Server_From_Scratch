FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wireguard-tools \
    iptables \
    sudo \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash appuser

RUN echo "appuser ALL=(ALL) NOPASSWD: /usr/bin/wg, /usr/bin/wg-quick, /sbin/ip" > /etc/sudoers.d/appuser \
    && chmod 0440 /etc/sudoers.d/appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

CMD ["python3", "app.py"]
