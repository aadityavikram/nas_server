import os
import cgi
from errorUtil import send_error_page
from profileUtil import get_profile_dir
from urllib.parse import unquote, parse_qs

def upload(handler, parsed_url, profile_root, code_directory):
    handler.profile_dir = get_profile_dir(handler, profile_root)
    if not handler.profile_dir:
        send_error_page(handler, 403, "Profile not selected", code_directory)
        return
    query = parse_qs(parsed_url.query)
    ctype, pdict = cgi.parse_header(handler.headers.get('Content-Type'))
    if ctype == 'multipart/form-data':
        pdict['boundary'] = bytes(pdict['boundary'], "utf-8")
        pdict['CONTENT-LENGTH'] = int(handler.headers.get('Content-Length'))
        try:
            form = cgi.FieldStorage(fp=handler.rfile,
                                    headers=handler.headers,
                                    environ={'REQUEST_METHOD': 'POST'},
                                    keep_blank_values=True)
        except Exception as e:
            send_error_page(handler, 400, f"Error parsing form data: {e}", code_directory)
            return

        if "file" not in form:
            send_error_page(handler, 400, "No file field in form", code_directory)
            return

        file_item = form["file"]

        if not file_item.filename:
            send_error_page(handler, 400, "No filename provided", code_directory)
            return

        # Sanitize filename to avoid directory traversal attacks
        filename = os.path.basename(file_item.filename)

        # Save file to DIRECTORY
        upload_path = query.get("path", ["/"])[0]  # Default to root if not provided
        safe_rel_path = os.path.normpath(unquote(upload_path)).lstrip("/")

        # Prevent escaping out of DIRECTORY
        abs_upload_dir = os.path.abspath(os.path.join(get_profile_dir(handler, profile_root), safe_rel_path))

        # Make sure it's still inside the DIRECTORY
        if not abs_upload_dir.startswith(os.path.abspath(get_profile_dir(handler, profile_root))):
            send_error_page(handler, 400, "Invalid upload path", code_directory)
            return

        try:
            os.makedirs(abs_upload_dir, exist_ok=True)
        except Exception as e:
            send_error_page(handler, 500, f"Failed to create directories: {e}", code_directory)
            return

        filepath = os.path.join(abs_upload_dir, filename)

        try:
            with open(filepath, 'wb') as f:
                data = file_item.file.read()
                f.write(data)
        except Exception as e:
            send_error_page(handler, 500, f"Failed to save file: {e}", code_directory)
            return

        # Redirect back to the main page (file listing)
        handler.send_response(303)  # See Other
        handler.send_header('Location', '/')
        handler.end_headers()