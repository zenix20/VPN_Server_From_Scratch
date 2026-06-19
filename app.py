from flask import Flask, jsonify, render_template, request, redirect, url_for
import subprocess
import jwt
import datetime
from functools import wraps

app = Flask(__name__)

# ─── CONFIG ───────────────────────────────────────────────
SECRET_KEY = 'change_this_to_something_random_or_dont_idontcare'
DASHBOARD_PASSWORD = 'CHANGE_THIS'
TOKEN_EXPIRY_HOURS = 2
# ──────────────────────────────────────────────────────────


# ─── JWT HELPERS ──────────────────────────────────────────
def generate_token():
    payload = {
        'user': 'admin',
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TOKEN_EXPIRY_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')


def verify_token(token):
    try:
        jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return True
    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('token')
        if not token or not verify_token(token):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated
# ──────────────────────────────────────────────────────────


# ─── WireGuard PARSER ─────────────────────────────────────
def parse_wg_show():
    try:
        result = subprocess.run(
            ['sudo', 'wg', 'show'],
            capture_output=True,
            text=True
        )
        output = result.stdout
        data = {'interfaces': []}

        current_interface = None
        current_peer = None

        for line in output.splitlines():
            line = line.strip()

            if line.startswith('interface:'):
                if current_interface:
                    data['interfaces'].append(current_interface)
                current_interface = {
                    'name': line.split(':', 1)[1].strip(),
                    'public_key': '',
                    'listening_port': '',
                    'peers': []
                }
                current_peer = None

            elif line.startswith('public key:') and current_peer is None:
                current_interface['public_key'] = line.split(':', 1)[1].strip()

            elif line.startswith('listening port:'):
                current_interface['listening_port'] = line.split(':', 1)[1].strip()

            elif line.startswith('peer:'):
                if current_peer:
                    current_interface['peers'].append(current_peer)
                current_peer = {
                    'public_key': line.split(':', 1)[1].strip(),
                    'endpoint': 'N/A',
                    'allowed_ips': '',
                    'latest_handshake': 'Never',
                    'transfer_rx': '0',
                    'transfer_tx': '0',
                    'status': 'disconnected'
                }

            elif line.startswith('endpoint:') and current_peer:
                current_peer['endpoint'] = line.split(':', 1)[1].strip()

            elif line.startswith('allowed ips:') and current_peer:
                current_peer['allowed_ips'] = line.split(':', 1)[1].strip()

            elif line.startswith('latest handshake:') and current_peer:
                handshake = line.split(':', 1)[1].strip()
                current_peer['latest_handshake'] = handshake
                current_peer['status'] = 'connected'

            elif line.startswith('transfer:') and current_peer:
                parts = line.split(':', 1)[1].strip()
                rx, tx = parts.split(',')
                current_peer['transfer_rx'] = rx.strip().replace('received', '').strip()
                current_peer['transfer_tx'] = tx.strip().replace('sent', '').strip()

        if current_peer:
            current_interface['peers'].append(current_peer)
        if current_interface:
            data['interfaces'].append(current_interface)

        return data

    except Exception as e:
        return {'error': str(e)}
# ──────────────────────────────────────────────────────────

# ─── PEER MANAGEMENT ──────────────────────────────────────
def get_next_peer_ip():
    data = parse_wg_show()
    used_ips = set()
    for iface in data['interfaces']:
        for peer in iface['peers']:
            ip = peer['allowed_ips'].replace('/32', '').strip()
            used_ips.add(ip)
    for i in range(2, 255):
        candidate = f'10.0.0.{i}'
        if candidate not in used_ips:
            return candidate
    return None


def add_peer_to_config(public_key, peer_ip):
    config_path = '/etc/wireguard/wg0.conf'
    peer_block = f'\n[Peer]\nPublicKey = {public_key}\nAllowedIPs = {peer_ip}/32\n'
    with open(config_path, 'a') as f:
        f.write(peer_block)


def remove_peer_from_config(public_key):
    config_path = '/etc/wireguard/wg0.conf'
    with open(config_path, 'r') as f:
        content = f.read()

    blocks = content.split('\n[Peer]')
    filtered = [b for b in blocks if public_key not in b]
    new_content = '\n[Peer]'.join(filtered)

    with open(config_path, 'w') as f:
        f.write(new_content)
# ──────────────────────────────────────────────────────────


# ─── ROUTES ───────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password')
        if password == DASHBOARD_PASSWORD:
            token = generate_token()
            response = redirect(url_for('index'))
            response.set_cookie(
                'token',
                token,
                httponly=True,
                samesite='Strict',
                max_age=TOKEN_EXPIRY_HOURS * 3600
            )
            return response
        else:
            error = 'Invalid password'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    response = redirect(url_for('login'))
    response.delete_cookie('token')
    return response


@app.route('/')
@token_required
def index():
    return render_template('index.html')


@app.route('/api/status')
@token_required
def status():
    data = parse_wg_show()
    return jsonify(data)

@app.route('/api/peers/add', methods=['POST'])
@token_required
def add_peer():
    try:
        # Generate key pair
        private_key = subprocess.run(
            ['wg', 'genkey'],
            capture_output=True, text=True
        ).stdout.strip()

        public_key = subprocess.run(
            ['wg', 'pubkey'],
            input=private_key,
            capture_output=True, text=True
        ).stdout.strip()

        # Get next available IP
        peer_ip = get_next_peer_ip()
        if not peer_ip:
            return jsonify({'error': 'No available IPs'}), 500

        # Add to wg0.conf
        add_peer_to_config(public_key, peer_ip)

        # Add to running WireGuard without restart
        subprocess.run([
            'sudo', 'wg', 'set', 'wg0',
            'peer', public_key,
            'allowed-ips', f'{peer_ip}/32'
        ])

        # Get server public key
        with open('/etc/wireguard/server_public.key', 'r') as f:
            server_public_key = f.read().strip()

        # Build client config
        client_config = f"""[Interface]
Address = {peer_ip}/24
PrivateKey = {private_key}
DNS = 8.8.8.8

[Peer]
PublicKey = {server_public_key}
Endpoint = YOUR_SERVER_IP:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25"""

        return jsonify({
            'success': True,
            'peer_ip': peer_ip,
            'public_key': public_key,
            'client_config': client_config
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/peers/remove', methods=['POST'])
@token_required
def remove_peer():
    try:
        public_key = request.json.get('public_key')
        if not public_key:
            return jsonify({'error': 'No public key provided'}), 400

        # Remove from running WireGuard
        subprocess.run(['sudo', 'wg', 'set', 'wg0', 'peer', public_key, 'remove'])

        # Remove from config file
        remove_peer_from_config(public_key)

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

