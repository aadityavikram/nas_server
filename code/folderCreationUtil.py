import os
from profileUtil import get_profile_dir
from urllib.parse import unquote, parse_qs

def create_folder(handler, parsed_url, profile_root):
    query = parse_qs(parsed_url.query)
    folder_name = query.get("name", [None])[0]

    if not folder_name:
        handler.send_response(400)
        handler.end_headers()
        handler.wfile.write(b"Missing folder name")
        return

    # Sanitize and create folder
    rel_path = os.path.normpath(unquote(folder_name)).lstrip("/")
    file_path = os.path.abspath(os.path.join(get_profile_dir(handler, profile_root), rel_path))
    print("Path of new folder: ", file_path)

    try:
        os.makedirs(file_path, mode=0o755, exist_ok=False)
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(b"Folder created")
    except FileExistsError:
        handler.send_response(409)
        handler.end_headers()
        handler.wfile.write(b"Folder already exists")
    except Exception as e:
        print("Error creating folder:", e)
        traceback.print_exc()
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(b"Failed to create folder")