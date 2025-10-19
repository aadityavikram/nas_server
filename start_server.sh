# Not being used

#!/data/data/com.termux/files/usr/bin/bash

# Prompt user for input
read -p "Enter Ubuntu username: " UBUNTU_USER
read -p "Enter Ubuntu IP address: " UBUNTU_IP
read -p "Enter Android IP address: " ANDROID_IP

# Configuration
REMOTE_FILE_DIR="/nas/storage/files"
LOCAL_PORT=8888
REMOTE_PORT=8888

# Start remote HTTP server over SSH
echo
echo "Starting HTTP server on Ubuntu..."
ssh "${UBUNTU_USER}@${UBUNTU_IP}" "nohup python3 ${REMOTE_FILE_DIR}/server.py > /dev/null 2>&1 &"

# Wait briefly to allow server to start
sleep 2

# Start SSH tunnel
echo
echo "Creating SSH tunnel (localhost:${LOCAL_PORT} -> ${UBUNTU_IP}:${REMOTE_PORT})..."
ssh -L ${LOCAL_PORT}:localhost:${REMOTE_PORT} "${UBUNTU_USER}@${UBUNTU_IP}" &
TUNNEL_PID=$!

# Start socat to forward Android IP on port 8888 to localhost:8888
echo
echo "Starting socat to forward ${ANDROID_IP}:8888 to localhost:8888..."
socat TCP-LISTEN:${LOCAL_PORT},bind=${ANDROID_IP},fork TCP:127.0.0.1:${LOCAL_PORT} &
SOCAT_PID=$!

# Display URL
STORAGE_URL="http://${ANDROID_IP}:${LOCAL_PORT}"
echo
echo "=================================================="
echo "You can now access the storage at:"
echo "    ${STORAGE_URL}"
echo
echo "Open it in any browser on your Android device."
echo "To stop the tunnel, kill the SSH process (PID: $TUNNEL_PID) and socat processes."
echo "=================================================="

# Wait until user wants to quit
read -p "Press ENTER to stop the tunnel and exit..."

# Kill the SSH tunnel and socat process
kill $TUNNEL_PID
kill $SOCAT_PID
