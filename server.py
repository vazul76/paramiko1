from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import paramiko
import time

import threading
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Ganti dengan secret key yang aman

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
@app.route('/monitoring_data')
def monitoring_data():
    usage = get_usage()
    if usage:
        return jsonify(usage)
    return jsonify({'cpu': 0, 'memory': 0})

# Monitoring Server
@app.route('/monitoring')
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

# # API untuk data monitoring
# @app.route('/monitoring_data')
# def monitoring_data():
#     def get_usage(cmd):
#         ssh = create_ssh()
#         if ssh:
#             stdin, stdout, stderr = ssh.exec_command(cmd)
#             output = stdout.read().decode().strip()
#             ssh.close()
#             return float(output) if output else 0
#         return 0
    
#     cpu = get_usage("top -bn1 | grep 'Cpu(s)' | awk '{print 100-$8}'")
#     mem = get_usage("free -m | awk 'NR==2{printf \"%.2f\", $3*100/$2 }'")
#     disk = get_usage("df / | awk 'NR==2{print $5}' | tr -d '%' ")
    
#     return jsonify({
#         'cpu': cpu,
#         'memory': mem,
#         'disk': disk
#     })

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)