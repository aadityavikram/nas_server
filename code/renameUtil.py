import os
import json
from urllib.parse import unquote
from profileUtil import get_profile_dir

def rename(handler, profile_root):
    content_length = int(handler.headers.get('Content-Length', 0))
    body = handler.rfile.read(content_length)

    try:
        data = json.loads(body)
        old_path = data.get("old_path")
        new_path = data.get("new_path")

        if not old_path or not new_path:
            handler.send_response(400)
            handler.end_headers()
            handler.wfile.write(b"Missing old_path or new_path")
            return

        # Sanitize paths
        old_rel = os.path.normpath(unquote(old_path)).lstrip("/")
        new_rel = os.path.normpath(unquote(new_path)).lstrip("/")

        old_abs = os.path.abspath(os.path.join(get_profile_dir(handler, profile_root), old_rel))
        new_abs = os.path.abspath(os.path.join(get_profile_dir(handler, profile_root), new_rel))

        # Security check: ensure both are inside DIRECTORY
        if not old_abs.startswith(os.path.abspath(get_profile_dir(handler, profile_root))) or not new_abs.startswith(os.path.abspath(get_profile_dir(handler, profile_root))):
            handler.send_response(400)
            handler.end_headers()
            handler.wfile.write(b"Invalid path")
            return

        # Check existence and perform rename
        if not os.path.exists(old_abs):
            handler.send_response(404)
            handler.end_headers()
            handler.wfile.write(b"Source file or folder does not exist")
            return

        if os.path.exists(new_abs):
            handler.send_response(409)
            handler.end_headers()
            handler.wfile.write(b"Target name already exists")
            return

        os.rename(old_abs, new_abs)
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(b"Renamed successfully")

    except Exception as e:
        print("Error renaming:", e)
        traceback.print_exc()
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(b"Rename failed")