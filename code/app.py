from flask import Flask, request, render_template_string
import threading
import paramiko
import socket

app = Flask(__name__)

HTML_FORM = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>NAS Launcher</title>
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <style>
        body {
            background-color: black;
            color: #00ff00;
            font-family: 'Share Tech Mono', monospace;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding-top: 100px;
        }
        form {
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        input, button {
            display: block;
            width: 250px;
            margin: 10px;
            padding: 8px;
            font-family: 'Share Tech Mono', monospace;
        }
        input {
            background: #111;
            border: 1px solid #00ff00;
            color: #00ff00;
        }
        button {
            background-color: #00ff00;
            color: black;
            cursor: pointer;
            border: none;
        }
        button:hover {
            background-color: #00cc00;
        }
    </style>
</head>
<body>
    <h1>Launch NAS UI</h1>
    <form method="POST">
        <input type="text" name="username" placeholder="SSH Username" required><br>
        <input type="password" name="password" placeholder="SSH Password" required><br>
        <button type="submit">Launch</button>
    </form>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        ip = get_local_ip()

        delay_seconds = 1
        server_ip = request.host.split(':')[0]

        threading.Thread(target=start_server, args=(username, ip, password), daemon=True).start()

        return f"""
           <html>
             <head>
               <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
               <script>
                 setTimeout(function() {{
                   window.location.href = "http://{server_ip}:8888";
                 }}, {delay_seconds * 1000});
               </script>
             </head>
             <body style="background-color:black;">
               <h2 style="color:#00ff00; font-family: 'Share Tech Mono', monospace;">
                 Launching NAS... Redirecting you in {delay_seconds} second{'s' if delay_seconds != 1 else ''}.
               </h2>
             </body>
           </html>
           """

    return render_template_string(HTML_FORM)

def get_local_ip():
    # Creates a temporary socket to get the local IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to be reachable, just used to get the local IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def start_server(username, ip, password):
    try:
        print("Starting NAS server...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password)

        # Run the server in a nohup-like way to keep it running after SSH disconnects
        cmd = "nohup python3 /nas/storage/code/server.py > /dev/null 2>&1 &"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        stdout.channel.recv_exit_status()  # Wait for command to be accepted
        print("NAS server started remotely.")
        ssh.close()
    except Exception as e:
        print("Failed to start NAS server:", e)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
