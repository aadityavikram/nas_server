import os
from urllib.parse import parse_qs
from errorUtil import send_error_page

def send_login_form(handler, profile, error_msg, code_directory):
    template_path = os.path.join(code_directory, "html", "profileLogin.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        send_error_page(handler, 500, "Login template not found", code_directory)
        return

    # Simple replacement
    html = html.replace("{{profile}}", profile)
    html = html.replace("{{profileSplit}}", profile.split("_")[0])
    html = html.replace("{{error_msg}}", error_msg or "")
    if error_msg:
        html = html.replace("{% if error_msg %}", "").replace("{% endif %}", "")
    else:
        # Remove the error block if no error
        html = html.replace("{% if error_msg %}", "<!--").replace("{% endif %}", "-->")

    encoded = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-type", "text/html")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)

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