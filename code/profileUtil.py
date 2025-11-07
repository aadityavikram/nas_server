import os
from urllib.parse import quote
from errorUtil import send_error_page

def get_profile_dir(handler, profile_root):
    # Get profile from cookie
    cookies = handler.headers.get("Cookie", "")
    profile = None
    for part in cookies.split(";"):
        if part.strip().startswith("profile="):
            profile = part.strip().split("=")[1]
            break

    if not profile:
        return None

    profile_path = os.path.join(profile_root, profile)
    if not os.path.isdir(profile_path):
        return None

    return profile_path

def send_profile_selection(handler, profile_root, profile_list, code_directory):
    try:
        profile_dirs = [d for d in os.listdir(profile_root)
                        if os.path.isdir(os.path.join(profile_root, d)) and d in profile_list]
    except Exception as e:
        send_error_page(handler, 500, "Failed to read profiles", code_directory)
        return

    template_path = os.path.join(code_directory, "html", "profile.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        send_error_page(handler, 500, "Profile selection template not found", code_directory)
        return

    # Build list of profiles
    profiles_html = ""
    profile_dirs.sort()
    for prof in profile_dirs:
        profiles_html += f'<a href="/?set_profile={quote(prof)}">{prof.split("_")[0]}</a>\n'

    # Insert into template
    html = html.replace("{{profiles}}", profiles_html)

    encoded = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-type", "text/html")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)

def send_add_profile_form(handler, error_msg, code_directory):
    template_path = os.path.join(code_directory, "html", "profileAdd.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        send_error_page(handler, 500, "Add profile template not found", code_directory)
        return

    if error_msg:
        error_html = f'<div class="error">{error_msg}</div>'
    else:
        error_html = ''

    html = html.replace("{{error_msg}}", error_html)

    encoded = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-type", "text/html")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)