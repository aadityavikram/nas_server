import os
import shutil
import traceback
from profileUtil import get_profile_dir
from urllib.parse import unquote, parse_qs

def delete(handler, parsed_url, profile_root):
    query = parse_qs(parsed_url.query)
    filename = query.get("file", [None])[0]

    if not filename:
        handler.send_response(400)
        handler.end_headers()
        handler.wfile.write(b"Missing file parameter")
        return

    rel_path = os.path.normpath(unquote(filename)).lstrip("/")
    file_path = os.path.abspath(os.path.join(get_profile_dir(handler, profile_root), rel_path))
    
    print(f"Request to delete: {rel_path}")
    print(f"Resolved path: {file_path}")

    if not file_path.startswith(os.path.abspath(get_profile_dir(handler, profile_root))):
        handler.send_response(400)
        handler.end_headers()
        handler.wfile.write(b"Invalid file path")
        return

    if not os.path.exists(file_path):
        handler.send_response(404)
        handler.end_headers()
        handler.wfile.write(b"File or folder not found")
        return

    # Prevent deletion of root directory
    if os.path.abspath(file_path) == os.path.abspath(get_profile_dir(handler, profile_root)):
        handler.send_response(400)
        handler.end_headers()
        handler.wfile.write(b"Cannot delete root directory")
        return

    try:
        if os.path.isfile(file_path):
            os.remove(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)  # recursive delete
        else:
            handler.send_response(400)
            handler.end_headers()
            handler.wfile.write(b"Invalid file type")
            return

        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(b"Deleted")
    except Exception as e:
        print("Error while deleting: ", e)
        traceback.print_exc()
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(b"Failed to delete")