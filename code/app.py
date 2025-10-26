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
        html, body {
            margin: 0;
            padding: 0;
            overflow: hidden;
            background-color: black;
            color: #00ff00;
            font-family: 'Share Tech Mono', monospace;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
        }
        form {
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .input-wrapper {
            position: relative;
            width: 250px;
            margin: 10px;
        }
        input {
            width: 100%;
            background: #111;
            border: 1px solid #00ff00;
            color: #00ff00;
            padding: 8px 60px 8px 8px; /* add space for icons */
            font-family: 'Share Tech Mono', monospace;
            box-sizing: border-box;
            height: 36px;
            line-height: 20px;
        }
        .icon {
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
            font-size: 14px;
            cursor: pointer;
            user-select: none;
        }
        #caps-icon {
            right: 45px;
            color: #ff3333;
            visibility: hidden;
            pointer-events: none;
        }
        #toggle-icon {
            right: 10px;
            color: #00ff00;
        }
        #toggle-icon:hover {
            color: #00cc00;
        }
        button {
            width: 250px;
            margin-top: 10px;
            padding: 8px;
            font-family: 'Share Tech Mono', monospace;
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
        <div class="input-wrapper">
            <input type="text" name="username" placeholder="SSH Username" required>
        </div>
        <div class="input-wrapper">
            <input id="password" type="password" name="password" placeholder="SSH Password" required>
            <span id="caps-icon" class="icon">C</span>
            <span id="toggle-icon" class="icon">Show</span>
        </div>
        <button type="submit">Launch</button>
    </form>

    <script>
        const passwordField = document.getElementById('password');
        const capsIcon = document.getElementById('caps-icon');
        const toggleIcon = document.getElementById('toggle-icon');

        // Track Caps Lock state globally
        let capsLockActive = false;

        function updateCapsIndicator(e) {
            capsLockActive = e.getModifierState('CapsLock');
            capsIcon.style.visibility = capsLockActive ? 'visible' : 'hidden';
        }

        passwordField.addEventListener('keydown', updateCapsIndicator);
        passwordField.addEventListener('keyup', updateCapsIndicator);

        // Hide Caps Lock icon when leaving the field
        passwordField.addEventListener('focusout', () => {
            capsIcon.style.visibility = 'hidden';
        });

        // Toggle password visibility
        toggleIcon.addEventListener('click', () => {
            if (passwordField.type === 'password') {
                passwordField.type = 'text';
                toggleIcon.textContent = 'Hide';
            } else {
                passwordField.type = 'password';
                toggleIcon.textContent = 'Show';
            }

            // Restore Caps Lock indicator immediately
            capsIcon.style.visibility = capsLockActive ? 'visible' : 'hidden';
        });
    </script>
</body>
</html>
"""

ERROR_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Connection Error</title>
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <style>
        html, body {
            margin: 0;
            padding: 0;
            overflow: hidden;
            height: 100%;
        }
        body {
            background-color: black;
            color: #ff3333;
            font-family: 'Share Tech Mono', monospace;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
        }
        h1 { color: #ff3333; margin: 0 0 10px 0; }
        p { color: #ff7777; max-width: 600px; text-align: center; margin: 0 0 20px 0; }
        a {
            color: #00ff00;
            text-decoration: none;
            margin-top: 20px;
            border: 1px solid #00ff00;
            padding: 8px 16px;
        }
        a:hover {
            background-color: #00ff00;
            color: black;
        }
    </style>
</head>
<body>
    <h1>Connection Failed</h1>
    <p>{{ error_message }}</p>
    <a href="/">Try Again</a>
</body>
</html>
"""

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


def create_ssh_connection(ip, username, password, timeout=5):
    """Create and return an SSH connection using Paramiko."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username=username, password=password, timeout=timeout)
    return ssh

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        ip = get_local_ip()

        delay_seconds = 1
        server_ip = request.host.split(':')[0]

        # Try to establish SSH first to validate credentials
        try:
            ssh = create_ssh_connection(ip, username, password)
            ssh.close()
        except Exception as e:
            error_message = f"Could not connect to {ip}: {str(e)}"
            return render_template_string(ERROR_PAGE, error_message=error_message)

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

def start_server(username, ip, password):
    try:
        print("Starting NAS server...")
        ssh = create_ssh_connection(ip, username, password)

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
