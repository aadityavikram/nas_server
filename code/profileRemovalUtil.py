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