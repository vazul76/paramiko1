from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_file
import paramiko
import time
import json
import os
import threading
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Ganti dengan secret key yang aman

BASE_DIR = "/home"

# Helper function untuk membuat koneksi SSH
def create_ssh():
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            session['host'],
            port=session['port'],
            username=session['username'],
            password=session['password']
        )
        return ssh
    except Exception as e:
        return None

# Halaman Login
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['host'] = request.form['host']
        session['port'] = int(request.form['port'])
        session['username'] = request.form['username']
        session['password'] = request.form['password']
        
        # Test koneksi SSH
        ssh = create_ssh()
        if ssh:
            ssh.close()
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Koneksi Gagal")
    
    return render_template('login.html')

# Dashboard utama
@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('dashboard.html')

# Terminal SSH
@app.route('/terminal', methods=['GET', 'POST'])
def terminal():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    history = session.get('terminal_history', [])
    
    if request.method == 'POST':
        cmd = request.form['command']
        ssh = create_ssh()
        if ssh:
            stdin, stdout, stderr = ssh.exec_command(cmd)
            output = stdout.read().decode() + stderr.read().decode()
            history.append({'command': cmd, 'output': output})
            session['terminal_history'] = history[-10:]  # Simpan 10 history terakhir
            ssh.close()
    
    return render_template('terminal.html', history=history)


# API untuk data monitoring
@app.route('/dashboard_data')
def monitoring_data():
    usage = get_usage()
    if usage:
        return jsonify(usage)
    return jsonify({'cpu': 0, 'memory': 0})

# Monitoring Server
@app.route('/dahboard')
def monitoring():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('monitoring.html')


#                       Function to get CPU and memory usage
def get_usage():
    ssh = create_ssh()
    if not ssh:
        return None

    # Get CPU usage
    stdin, stdout, stderr = ssh.exec_command("mpstat 1 1 | awk '/Average:/ {print 100 - $12}'")
    cpu_usage = float(stdout.read().decode().strip())

    # Get memory usage
    stdin, stdout, stderr = ssh.exec_command("free -m | awk 'NR==2{printf \"%.2f\", $3*100/$2 }'")
    mem_usage = float(stdout.read().decode().strip())

    return {
        'cpu': cpu_usage,
        'memory': mem_usage
    }

# user management
@app.route('/users')
def users():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    ssh = create_ssh()
    if not ssh:
        return "SSH connection failed", 500

    try:
        # Fetch users with home directories in /home or /root
        cmd = "getent passwd | awk -F: '$6 ~ /^\\/home\\/|^\\/root$/ {print $1, $3, $6}'"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        users_data = stdout.read().decode().strip().split("\n")

        user_list = []

        for user in users_data:
            parts = user.split(" ")
            if len(parts) >= 3:
                username = parts[0]
                uid = parts[1]
                home_dir = parts[2]

                user_list.append({
                    "username": username,
                    "uid": uid,
                    "home_directory": home_dir
                })

        ssh.close()
        return render_template('users.html', users=user_list)

    except Exception as e:
        ssh.close()
        return str(e), 500

    
@app.route('/api/users')
def api_users():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

    ssh = create_ssh()
    if not ssh:
        return jsonify({"error": "SSH connection failed"}), 500

    try:
        # Fetch users with home directories in /home or /root
        cmd = "getent passwd | awk -F: '$6 ~ /^\\/home\\/|^\\/root$/ {print $1, $3, $6}'"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        users_data = stdout.read().decode().strip().split("\n")

        user_list = []

        for user in users_data:
            parts = user.split(" ")
            if len(parts) >= 3:
                username = parts[0]
                uid = parts[1]
                home_dir = parts[2]

                user_list.append({
                    "username": username,
                    "uid": uid,
                    "home_directory": home_dir
                })

        ssh.close()
        return jsonify(user_list)

    except Exception as e:
        ssh.close()
        return jsonify({"error": str(e)}), 500


@app.route('/add_user', methods=['POST'])
def add_user():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    username = data.get("username")
    password = data.get("password")
    group = data.get("group")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    ssh = create_ssh()
    if not ssh:
        return jsonify({"error": "SSH connection failed"}), 500

    try:
        cmd = f"sudo useradd -m {username} && echo '{username}:{password}' | sudo chpasswd"
        if group:
            cmd = f"sudo useradd -m -G {group} {username} && echo '{username}:{password}' | sudo chpasswd"
        
        ssh.exec_command(cmd)
        return jsonify({"success": True, "message": f"User {username} added successfully"})
    finally:
        ssh.close()

@app.route('/delete_user/<username>', methods=['DELETE'])
def delete_user(username):
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

    ssh = create_ssh()
    if not ssh:
        return jsonify({"error": "SSH connection failed"}), 500

    try:
        ssh.exec_command(f"sudo userdel -r {username}")
        return jsonify({"success": True, "message": f"User {username} deleted successfully"})
    finally:
        ssh.close()


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# file explorer
@app.route("/files")
def index():
    return render_template("file_explorer.html")

@app.route("/list_files", methods=["GET"])
def list_files():
    path = request.args.get("path", BASE_DIR)
    if not os.path.exists(path):
        return jsonify({"error": "Path does not exist"}), 400

    items = []
    for entry in os.scandir(path):
        items.append({
            "name": entry.name,
            "is_dir": entry.is_dir(),
            "size": os.path.getsize(entry.path) if not entry.is_dir() else None,
        })

    return jsonify(items)

@app.route("/download", methods=["GET"])
def download_file():
    file_path = request.args.get("file")
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    app.run(debug=True)