def switch(handler):
    handler.send_response(302)
    handler.send_header("Set-Cookie", "profile=; Max-Age=0; Path=/")  # Clear cookie
    handler.send_header("Set-Cookie", "authenticated=; Max-Age=0; Path=/")  # Clear auth cookie
    handler.send_header("Location", "/")
    handler.end_headers()
    return