import os
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