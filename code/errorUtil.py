import os

def send_error_page(handler, code, message=None, code_directory="."):
    """Send a generic HTML error page using the provided HTTP handler."""
    messages = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        500: "Internal Server Error",
    }

    title = messages.get(code, "Error")
    description = message or f"An error occurred: {title}"

    handler.send_response(code)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.end_headers()

    template_path = os.path.join(code_directory, "html", "error.html")

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        # Fallback: inline error message if the template doesn't exist
        fallback_html = f"""
        <html><head><title>{code} {title}</title></head>
        <body><h1>{code} {title}</h1><p>{description}</p></body></html>
        """
        handler.wfile.write(fallback_html.encode("utf-8"))
        return

    # Replace placeholders
    html = html.replace("{{code}}", str(code))
    html = html.replace("{{title}}", title)
    html = html.replace("{{message}}", description)

    encoded = html.encode("utf-8")
    handler.wfile.write(encoded)