import os
import time
import signal
import threading

def shutdown_and_kill(pid):
    # Wait a moment so response is sent before killing
    time.sleep(1)

    # Kill this server's process or process on port 8888
    # Assuming current process:
    print(f'Process ID: {pid}')
    os.kill(pid, signal.SIGTERM)

def logout(handler, pid):
    threading.Thread(target=shutdown_and_kill, args=(pid,)).start()
    handler.send_response(303)
    handler.send_header("Set-Cookie", "profile=; Max-Age=0; Path=/")  # Clear cookie
    handler.send_header("Set-Cookie", "authenticated=; Max-Age=0; Path=/")  # Clear auth cookie
    handler.end_headers()
    return