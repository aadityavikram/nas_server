from flask import Flask, request, render_template_string
import threading
import time
import webbrowser
import paramiko
import socket
import select

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
        <input type="text" name="ip" placeholder="Server IP" required><br>
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
        ip = request.form["ip"]
        password = request.form["password"]

        delay_seconds = 1

        threading.Thread(target=start_server, args=(username, ip, password), daemon=True).start()
        threading.Thread(target=port_forward, args=(username, ip, password), daemon=True).start()

        return f"""
           <html>
             <head>
               <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
               <script>
                 setTimeout(function() {{
                   window.location.href = "http://localhost:8888";
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


def start_server(username, ip, password):
    try:
        print("Starting NAS server...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password)

        # Run the server in a nohup-like way to keep it running after SSH disconnects
        cmd = "nohup python3 /nas/storage/files/server.py > /dev/null 2>&1 &"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        stdout.channel.recv_exit_status()  # Wait for command to be accepted
        print("NAS server started remotely.")
        ssh.close()
    except Exception as e:
        print("Failed to start NAS server:", e)


def port_forward(username, ip, password):
    try:
        print("Setting up port forwarding...")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password)

        # Local port 8888 forwarded to remote localhost:8888
        transport = client.get_transport()
        local_port = 8888
        remote_host = 'localhost'
        remote_port = 8888

        # Create a socket on local machine and forward data between this and remote server
        class ForwardServer (threading.Thread):
            def __init__(self):
                threading.Thread.__init__(self)
                self.daemon = True

            def run(self):
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(('0.0.0.0', local_port))
                    sock.listen(5)
                    print(f"Port forwarding: localhost:{local_port} -> {remote_host}:{remote_port} on {ip}")

                    while True:
                        client_sock, addr = sock.accept()
                        print(f"Incoming connection from {addr}")
                        # Start forwarding in a new thread
                        threading.Thread(target=handler, args=(client_sock,), daemon=True).start()
                except Exception as e:
                    print("Forward server error:", e)

        def handler(client_sock):
            try:
                chan = transport.open_channel('direct-tcpip', (remote_host, remote_port), client_sock.getsockname())
            except Exception as e:
                print("Failed to open channel:", e)
                client_sock.close()
                return

            if chan is None:
                print("Failed to open channel.")
                client_sock.close()
                return

            while True:
                r, w, x = select.select([client_sock, chan], [], [])
                if client_sock in r:
                    data = client_sock.recv(1024)
                    if len(data) == 0:
                        break
                    chan.send(data)
                if chan in r:
                    data = chan.recv(1024)
                    if len(data) == 0:
                        break
                    client_sock.send(data)

            chan.close()
            client_sock.close()

        forward_server = ForwardServer()
        forward_server.start()
        # Keep the forwarding thread running
        forward_server.join()
        client.close()

    except Exception as e:
        print("Failed to setup port forwarding:", e)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
