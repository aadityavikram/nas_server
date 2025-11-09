import os
import mimetypes
from errorUtil import send_error_page
from streamingUtil import send_file_with_range

def load_profile_file_dir(handler, file_path, code_directory):
    if os.path.isdir(file_path):
        print("Is directory")
        f = handler.list_directory(file_path)
        if f:
            handler.wfile.write(f.read())
        return

    elif os.path.isfile(file_path):
        print("Is file")
        # Guess MIME type automatically
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        try:
            send_file_with_range(handler, file_path, code_directory)
        except Exception as e:
            send_error_page(handler, 500, f"Error reading file: {e}", code_directory)
            return
        return
    else:
        send_error_page(handler, 404, "File not found", code_directory)
        return

def load_public_profile(handler, requested_path, public_profile, profile_root, code_directory):
    relpath = requested_path[len(public_profile) + 2:]  # remove "/public/"
    print(f"Rel Path: {relpath}")
    file_path = os.path.join(profile_root, public_profile, relpath)
    print(f"File Path: {file_path}")

    # Prevent path traversal attacks (like /public/../secret.txt)
    file_path = os.path.realpath(file_path)
    if not file_path.startswith(os.path.realpath(os.path.join(profile_root, public_profile))):
        send_error_page(handler, 403, "You are not authorised", code_directory)
        return

    load_profile_file_dir(handler, file_path, code_directory)

def load_profile(handler, profile, requested_path, profile_root, code_directory):
    parts = requested_path.strip("/").split("/", 1)
    if len(parts) >= 1:
        profileNameActual = parts[0]
    else:
        profileNameActual = ""

    print(f"{profile_name} {profileNameActual}")

    if profile_name != profileNameActual:
        send_error_page(self, 403, "You are not authorised", code_directory)
        return

    relpath = requested_path[len(profile) + 2:]
    print(f"Rel Path: {relpath}")
    file_path = os.path.join(profile_root, profile, relpath)
    print(f"File Path: {file_path}")

    # Prevent path traversal attacks (like /public/../secret.txt)
    file_path = os.path.realpath(file_path)
    if not file_path.startswith(os.path.realpath(os.path.join(profile_root, profile))):
        send_error_page(self, 403, "You are not authorised", code_directory)
        return

    load_profile_file_dir(handler, file_path, code_directory)