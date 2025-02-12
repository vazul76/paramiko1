from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import paramiko
import time
import json
from paramiko.ssh_exception import SSHException
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
    return render_template('dashboard.html')


#                       Function to get CPU and memory usage
def get_usage():
    ssh = create_ssh()
    if not ssh:
        return None

    try:
        # Perintah untuk mendapatkan penggunaan CPU, memori, dan disk
        cmd = "top -bn1 | grep 'Cpu(s)' && free -m | grep 'Mem' && df -h /"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        output = stdout.read().decode().strip()
        ssh.close()

        # Parsing output
        cpu_line, mem_line, disk_line = output.split('\n', 2)
        
        # Parsing CPU usage
        cpu_usage = cpu_line.split(',')
        cpu_idle = cpu_usage[3].split()[0]
        cpu_used = 100.0 - float(cpu_idle)

        # Parsing memory usage
        mem_usage = mem_line.split()
        total_mem = float(mem_usage[1])
        used_mem = float(mem_usage[2])
        mem_used = (used_mem / total_mem) * 100.0

        # Parsing disk usage
        disk_usage = disk_line.split()
        disk_used = disk_usage[4]  # Assuming the 5th column is the used percentage

        # Format the values to two decimal places
        mem_used = round(mem_used, 2)

        return {
            'cpu': cpu_used,
            'memory': mem_used,
            'disk': disk_used
        }

    except Exception as e:
        print(f"Error: {e}")
        return None

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

    if username == "root":
        return jsonify({"error": "Cannot delete root user"}), 403

    ssh = create_ssh()
    if not ssh:
        return jsonify({"error": "SSH connection failed"}), 500

    try:
        # Perintah dengan penanganan sudo yang lebih baik
        command = f"sudo -S userdel -r {username}"
        
        # Eksekusi dengan pseudo-TTY
        stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
        
        # Kirim password sudo jika diperlukan
        stdin.write(session['password'] + '\n')
        stdin.flush()
        
        # Tunggu hingga perintah selesai
        exit_status = stdout.channel.recv_exit_status()
        
        if exit_status == 0:
            return jsonify({"success": True, "message": f"User {username} deleted"})
        else:
            error = stderr.read().decode().strip()
            return jsonify({"error": f"Failed (code {exit_status}): {error}"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        ssh.close()


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)