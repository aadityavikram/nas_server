import os
import re
import mimetypes
from errorUtil import send_error_page

def send_file_with_range(handler, file_path, code_directory):
    """Stream file with HTTP Range support for seeking."""
    try:
        file_size = os.path.getsize(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        # Check if client sent a Range header
        range_header = handler.headers.get("Range")
        if range_header:
            # Parse Range: bytes=start-end
            m = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if not m:
                send_error_page(handler, 400, "Invalid Range header", code_directory)
                return

            start, end = m.groups()
            start = int(start) if start else 0
            end = int(end) if end else file_size - 1

            if start >= file_size:
                send_error_page(handler, 416, "Requested Range Not Satisfiable", code_directory)
                return

            # Clamp end to file size
            end = min(end, file_size - 1)
            chunk_size = end - start + 1

            handler.send_response(206)  # Partial Content
            handler.send_header("Content-Type", mime_type)
            handler.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            handler.send_header("Content-Length", str(chunk_size))
            handler.send_header("Accept-Ranges", "bytes")
            handler.end_headers()

            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    read_size = min(32 * 1024, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    try:
                        handler.wfile.write(data)
                        handler.wfile.flush()
                    except BrokenPipeError:
                        print("Client disconnected during range transfer.")
                        break
                    remaining -= len(data)

        else:
            # No Range header — send full file
            handler.send_response(200)
            handler.send_header("Content-Type", mime_type)
            handler.send_header("Content-Length", str(file_size))
            handler.send_header("Accept-Ranges", "bytes")
            handler.end_headers()

            with open(file_path, "rb") as f:
                while True:
                    data = f.read(32 * 1024)
                    if not data:
                        break
                    try:
                        handler.wfile.write(data)
                        handler.wfile.flush()
                    except BrokenPipeError:
                        print("Client disconnected during full transfer.")
                        break

    except Exception as e:
        try:
            send_error_page(handler, 500, f"Error streaming file: {e}", code_directory)
        except BrokenPipeError:
            pass