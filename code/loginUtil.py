from urllib.parse import parse_qs
from errorUtil import send_error_page
from profileLoginUtil import send_login_form

def login(handler, profile_passwords, code_directory):
    content_length = int(handler.headers.get('Content-Length', 0))
    post_data = handler.rfile.read(content_length).decode('utf-8')
    params = parse_qs(post_data)

    profile = params.get("profile", [None])[0]
    password = params.get("password", [None])[0]

    if not profile or not password:
        send_error_page(handler, 400, "Missing profile or password", code_directory)
        return

    expected_password = profile_passwords.get(profile)
    if expected_password is not None and password == expected_password:
        # Password is correct - set authenticated cookie and redirect to /
        handler.send_response(302)
        handler.send_header("Set-Cookie", f"profile={profile}; Path=/")
        handler.send_header("Set-Cookie", "authenticated=yes; Path=/")
        handler.send_header("Location", "/")
        handler.end_headers()
    else:
        # Wrong password - show password form with error
        send_login_form(handler, profile, "Incorrect password", code_directory)
    return