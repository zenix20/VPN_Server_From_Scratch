# WireGuard VPN Server + Custom Management Dashboard

A self-hosted VPN server built from scratch using WireGuard, paired with a custom Flask web dashboard for live monitoring and peer management. Built as a hands-on cybersecurity project to understand VPN architecture, authentication, and secure secret handling — not just deploy a pre-built solution.

**Full write-up with step-by-step explanations:** [Read the full tutorial on Medium](https://medium.com/@yourusername/REPLACE_WITH_YOUR_POST_LINK)

## What This Does

- Runs a real WireGuard VPN tunnel with NAT routing and IP forwarding
- Custom dashboard shows live peer status, handshake times, and bandwidth usage
- Add or remove VPN peers directly from the browser — no manual config editing
- JWT-based authentication protects the dashboard (httponly + SameSite cookies)
- Auto-generated client configs with DNS leak protection built in

## Tech Stack

- **VPN:** WireGuard
- **Backend:** Python (Flask)
- **Frontend:** HTML, CSS, JavaScript (vanilla, no frameworks)
- **Auth:** JWT (PyJWT)
- **OS tested on:** Kali Linux (Debian-based)

## How It Works

```
Browser → Flask backend → runs "wg show" → parses output → returns JSON → renders live dashboard
```

The dashboard polls the server every 10 seconds and updates peer status, transfer stats, and handshake times without a page refresh.

## Project Structure

```
vpn-dashboard/
├── app.py                    # Flask backend
├── templates/
│   ├── index.html            # Dashboard UI
│   └── login.html            # Login page
├── static/
│   └── style.css             # Styling
├── wg0.conf.example           # Server config template (no real keys)
├── wg-client.conf.example     # Client config template (no real keys)
└── README.md
```

## Setup

1. Install WireGuard:
```bash
   sudo apt update && sudo apt install wireguard -y
```

2. Generate server and client key pairs:
```bash
   wg genkey | sudo tee server_private.key | wg pubkey | sudo tee server_public.key
```

3. Copy `wg0.conf.example` to `/etc/wireguard/wg0.conf` and fill in your generated keys.

4. Enable IP forwarding:
```bash
   echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
   sudo sysctl -p
```

5. Start the VPN:
```bash
   sudo wg-quick up wg0
```

6. Install Python dependencies and run the dashboard:
```bash
   pip install flask pyjwt --break-system-packages
   export SECRET_KEY="your_random_secret_key"
   export DASHBOARD_PASSWORD="your_dashboard_password"
   sudo -E python3 app.py
```

7. Visit `http://127.0.0.1:5000` and log in.

## Security Notes

- Real WireGuard keys and config files are excluded from this repo — only templates are included
- Dashboard password and JWT secret are loaded from environment variables, never hardcoded
- Sudo access for the Flask app is scoped to only the `wg` command (least privilege), not unrestricted root access

## Why WireGuard

WireGuard was chosen over OpenVPN for its modern cryptography (ChaCha20 + Poly1305) and significantly smaller codebase (~4,000 lines vs. ~100,000+), which reduces the overall attack surface while improving performance.

## Docker

A pre-built image is available on Docker Hub:

```bash
docker pull zainabq055/vpn-dashboard:latest
docker run -d -p 5000:5000 --env-file .env --cap-add=NET_ADMIN zainabq055/vpn-dashboard:latest
```

Note: this image packages the dashboard application only. It does not include a running WireGuard server — see THREAT_MODEL.md (T10) for details on this architectural boundary.

## Author

Zainab Qureshi
