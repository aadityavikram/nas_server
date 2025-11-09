import os
from errorUtil import send_error_page
from urllib.parse import quote, parse_qs

def remove_profile(handler, profile_root, profile_passwords, code_directory):
    content_length = int(handler.headers.get('Content-Length', 0))
    post_data = handler.rfile.read(content_length).decode('utf-8')
    post_params = parse_qs(post_data)

    if "profile" not in post_params:
        send_error_page(handler, 400, "Profile not specified", code_directory)
        return

    profile_to_remove = post_params["profile"][0]
    password = None
    if "password" in post_params:
        password = post_params["password"][0]
    profile_path = os.path.join(profile_root, profile_to_remove)

    if not os.path.isdir(profile_path):
        send_error_page(handler, 404, "Profile not found", code_directory)
        return

    expected_password = profile_passwords.get(profile_to_remove)

    # Check password if a password is required
    if expected_password is not None:
        if password != expected_password or password is None:
            # Redirect back to confirmation with error
            handler.send_response(302)
            handler.send_header("Location", f"/confirm-remove?profile={quote(profile_to_remove)}&error=Invalid+password")
            handler.end_headers()
            return

    return profile_path, profile_to_remove

def remove_profile_get(handler, profile_root, code_directory):
    # Read profiles again
    try:
        profile_dirs = [d for d in os.listdir(profile_root)
                        if os.path.isdir(os.path.join(profile_root, d))]
    except Exception as e:
        send_error_page(handler, 500, "Failed to read profiles", code_directory)
        return

    # Build HTML to let user select which profile to delete
    profiles_html = ""
    profile_dirs.sort()
    for prof in profile_dirs:
        profiles_html += f'<li><a href="/confirm-remove?profile={quote(prof)}">{prof.split("_")[0]}</a></li>'

    template_path = os.path.join(code_directory, "html", "profileRemove.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # Replace placeholder with actual profiles HTML
    html = template.replace("{{profiles_html}}", profiles_html)

    encoded = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)
    return

def remove_profile_confirm_get(handler, qs, public_profile, profile_root, code_directory):
    # Confirm removal page for the selected profile
    if "profile" not in qs:
        send_error_page(handler, 400, "Profile not specified", code_directory)
        return

    profile_to_remove = qs["profile"][0]
    if profile_to_remove.startswith(f"{public_profile}"):
        send_error_page(handler, 400, "Cannot delete Public profile", code_directory)
        return
    profile_path = os.path.join(profile_root, profile_to_remove)

    if not os.path.isdir(profile_path):
        send_error_page(handler, 404, "Profile not found", code_directory)
        return

    # Get error message from query string (if any)
    error_msg = qs.get("error", [None])[0]
    error_html = f'<p style="color:#ff4444; font-weight:bold;">{error_msg}</p>' if error_msg else ""

    template_path = os.path.join(code_directory, "html", "profileRemoveConfirm.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        send_error_page(handler, 500, "Profile removal confirmation template not found", code_directory)
        return

    html = html.replace("{{profile_name_to_remove}}", profile_to_remove.split("_")[0])
    html = html.replace("{{profile_to_remove}}", profile_to_remove)
    html = html.replace("{{error_html}}", error_html)

    encoded = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)
    return