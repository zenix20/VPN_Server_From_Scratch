# Threat-Model: Self-hosted WireGuard VPN Server with Web Management Dashboard  
## 1. Project Overview

This project implements a self-hosted VPN server using WireGuard, paired with a 
custom Flask-based web dashboard for peer management. The system allows an 
administrator to monitor connected peers, add new peers, and revoke access, 
all through a browser interface protected by JWT authentication. The project 
also includes a Dockerized version of the dashboard, published to Docker Hub.

---

## 2. Assets to Protect

| Asset | Description | Sensitivity |
|---|---|---|
| WireGuard private key | Server's cryptographic identity | Critical |
| Peer private keys | Generated per peer, enables tunnel access | Critical |
| Dashboard password | Controls admin access to VPN management | High |
| JWT secret key | Signs authentication tokens | High |
| wg0.conf | Contains all peer public keys and IPs | Medium |
| Peer traffic | Data flowing through the VPN tunnel | Medium |
| .env file | Holds real SECRET_KEY, DASHBOARD_PASSWORD, SERVER_ENDPOINT | High |

---

## 3. Threat Actors

**External attacker** — No credentials, network access only  
**Compromised peer** — Has a valid peer config, trying to escalate  
**Local attacker** — Has low-privilege access to the server OS  
**Anyone browsing the public GitHub repo or pulling the public Docker image** — No access to the live server at all, but full visibility into source code and image layers

---

## 4. Attack Surface

```
Internet
   │
   ├── UDP :51820  ← WireGuard tunnel endpoint
   │
   └── TCP :5000   ← Flask dashboard (should be restricted in production)
         │
         ├── /login       ← password brute force target
         ├── /api/status  ← JWT protected
         ├── /api/peers/add    ← JWT protected
         └── /api/peers/remove ← JWT protected

Public GitHub repo  ← source code, README, .template configs
Public Docker Hub image ← packaged dashboard application
```

---

## 5. Threats and Mitigations

### T1 — Unauthorized Dashboard Access
**Threat:** Attacker discovers port 5000 and tries to access the dashboard  
**Impact:** Full VPN management access — add backdoor peers, remove legitimate users  
**Likelihood:** Medium (port scanning is trivial)  
**Mitigation:**
- JWT authentication required on all routes and API endpoints
- Unauthenticated requests redirected to login, no data exposed
- In production: restrict port 5000 to localhost only, use a reverse proxy (nginx)

---

### T2 — Password Brute Force
**Threat:** Attacker repeatedly tries passwords against /login  
**Impact:** Dashboard compromise if weak password used  
**Likelihood:** High (no rate limiting currently implemented)  
**Mitigation implemented:**
- Single password with no username enumeration possible
**Known gap — not yet implemented:**
- Rate limiting on /login (e.g. Flask-Limiter: 5 attempts per minute)
- Account lockout after N failed attempts
- Recommended for production deployment

---

### T3 — JWT Token Theft
**Threat:** Attacker steals a valid JWT token and replays it  
**Impact:** Authenticated dashboard access without password  
**Likelihood:** Low  
**Mitigations implemented:**
- httponly cookie — JavaScript cannot read the token (XSS protection)
- SameSite=Strict — token not sent on cross-site requests (CSRF protection)
- Token expiry set to 2 hours — limits the window of a stolen token

---

### T4 — Private Key Exposure
**Threat:** Attacker reads /etc/wireguard/server_private.key  
**Impact:** Can impersonate the VPN server, decrypt all past and future traffic  
**Likelihood:** Low (requires root or file system access)  
**Mitigations implemented:**
- chmod 600 on private key files — only root can read them
- Private key never transmitted over network or displayed in dashboard
- wg show hides private key even from root in output

---

### T5 — Rogue Peer Injection
**Threat:** Attacker adds themselves as a peer by modifying wg0.conf directly  
**Impact:** Unauthorized VPN access  
**Likelihood:** Low (requires OS-level access)  
**Mitigation:**
- WireGuard's cryptographic peer authentication — only peers with valid 
  key pairs can complete a handshake
- Dashboard is the only intended interface for peer management

---

### T6 — Traffic Interception Between Peer and Server
**Threat:** Network attacker intercepts VPN tunnel traffic  
**Impact:** Exposure of peer data  
**Likelihood:** Low  
**Mitigation:**
- WireGuard uses ChaCha20 for encryption and Poly1305 for authentication
- All tunnel traffic is encrypted end-to-end between peer and server
- Attacker sees only encrypted ciphertext

---

### T7 — DNS Leakage
**Threat:** DNS queries bypass the VPN tunnel and go directly to ISP  
**Impact:** ISP can see what domains the peer is resolving despite VPN  
**Likelihood:** Medium (common misconfiguration)  
**Mitigation implemented:**
- DNS = 8.8.8.8 set in client config forces DNS through the tunnel
- resolvconf integration ensures system DNS changes when tunnel comes up

---

### T8 — Sudo Privilege Escalation via Dashboard
**Threat:** Attacker exploits Flask app to run arbitrary sudo commands  
**Impact:** Full root access to the server  
**Likelihood:** Low-Medium  
**Mitigation:**
- sudoers rule grants NOPASSWD only for /usr/bin/wg, /usr/bin/wg-quick, 
  and /sbin/ip — not unrestricted sudo
- Principle of least privilege applied — Flask process cannot run 
  arbitrary commands as root
- Same scoped pattern carried into the Docker image via a dedicated 
  non-root `appuser`, rather than running the container as root

---

### T9 — Secret Exposure via Public Repository or Image
**Threat:** Real WireGuard private keys, the dashboard password, or the JWT 
signing key end up committed to the public GitHub repository or baked into 
the published Docker image  
**Impact:** Full compromise of the VPN server's identity and/or the 
dashboard's authentication if discovered — public repos and public Docker 
images are routinely scraped by automated bots searching for exposed secrets  
**Likelihood:** Medium  
**Mitigations implemented:**
- Real key files (*.key), real wg0.conf and wg-client.conf, and the real 
  .env file were never uploaded — only .example templates were published
- app.py reads SECRET_KEY, DASHBOARD_PASSWORD, and SERVER_ENDPOINT via 
  os.getenv() with safe, obviously-fake fallback values, so the published 
  source code contains no real secrets even though the application is 
  fully functional out of the box
- A .dockerignore excludes *.key, wg0.conf, wg-client.conf, and .env from 
  the Docker build context, preventing them from being copied into any 
  image layer
- Manual verification (`grep -r "PrivateKey" .`) was run against the 
  project directory before uploading, as a final check given that no 
  .gitignore-based automation was in place

---

### T10 — Docker Network Isolation Misunderstood as a Bug
**Threat:** An operator runs the published Docker image expecting it to 
function as a complete, self-contained VPN server, and either misconfigures 
the container in an attempt to "fix" the empty dashboard, or assumes the 
image is broken  
**Impact:** Low security impact directly, but a real risk of operators 
reaching for `--network host` (which removes container network isolation) 
without understanding the tradeoff, just to make the dashboard show data  
**Likelihood:** Low  
**Mitigations implemented:**
- Documented explicitly in the project README that the Docker image 
  packages the dashboard application only — it does not include or manage 
  a WireGuard server inside the container
- Confirmed through direct testing that `wg show` inside the container 
  correctly reports no interfaces, since wg0 exists on the host's network 
  namespace, not the container's, by Docker's default isolation design
- Any deployment choosing to bridge this gap (e.g. via `--network host`) 
  is a deliberate, documented tradeoff against Docker's default isolation, 
  not a silent default

---

## 6. Security Decisions Log

| Decision | Reason |
|---|---|
| WireGuard over OpenVPN | Modern cryptography, smaller attack surface (~4000 lines vs ~100,000) |
| JWT in httponly cookie | Prevents XSS token theft vs localStorage |
| SameSite=Strict | CSRF protection without needing CSRF tokens |
| chmod 600 on keys | Least privilege file access |
| NOPASSWD scoped to wg only | Least privilege sudo access |
| DNS forced through tunnel | Prevents DNS leak attacks |
| Token expiry 2 hours | Limits stolen token validity window |
| .env + .env.example pattern | Chosen over plain export commands so anyone deploying this themselves has a recognizable, standard template to fill in — not just a convenience for local testing |
| Non-root appuser in Docker image | Carries the same least-privilege sudoers principle from the host VM into the container, rather than defaulting to root-in-container for simplicity |
| Documented Docker network limitation | Chose to explicitly document that the image does not include a running WireGuard server, rather than reaching for --network host by default and silently giving up container network isolation |

---

## 7. Known Gaps (Future Work)

- [ ] Rate limiting on /login endpoint
- [ ] HTTPS (TLS) for dashboard in production — currently HTTP
- [ ] Peer activity logging with timestamps
- [ ] Kill switch implementation for clients
- [ ] Dashboard port restricted to localhost + nginx reverse proxy in production
- [ ] Password hashing (currently plaintext comparison in memory)
- [ ] No automated secret-scanning (e.g. trufflehog, git-secrets) before publishing — relies on manual review
- [ ] Docker image does not include a running WireGuard server; live peer data requires the container to have visibility into a host's wg0 interface

---

## 8. Out of Scope

- Physical security of the host machine
- Security of peer devices themselves
- Compromise of the cloud provider (if deployed to VPS)
