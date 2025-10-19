#!/usr/bin/env python3

import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import quote, unquote, urlparse, parse_qs
from io import BytesIO
import cgi
import socketserver
import traceback
import shutil
import zipfile
import tempfile
from datetime import datetime

# Directory to serve
DIRECTORY = "/nas/storage/files"

# Files you want to hide from the listing
HIDDEN_FILES = {"app.py", "server.py", "template.html", "style.css", "main.js"}

class FileHandler(SimpleHTTPRequestHandler):

    def send_head_with_range(self):
        """Serve a GET request supporting Range header for partial content."""
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            self.send_error(404, "File not found")
            return None

        ctype = self.guess_type(path)
        fs = os.stat(path)
        size = fs.st_size

        range_header = self.headers.get('Range')
        if range_header:
            # Example: Range: bytes=1000-2000
            import re
            m = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if m:
                start = int(m.group(1))
                end = m.group(2)
                if end:
                    end = int(end)
                else:
                    end = size - 1
                if start >= size:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    return None
                self.send_response(206)
                self.send_header("Content-type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(end - start + 1))
                self.end_headers()
                return open(path, 'rb'), start, end
            else:
                # Malformed Range header
                self.send_error(400, "Bad Range header")
                return None
        else:
            self.send_response(200)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Length", str(size))
            self.end_headers()
            return open(path, 'rb'), 0, size - 1

    def list_directory(self, path):
        try:
            with open(os.path.join(DIRECTORY, "template.html"), "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            self.send_error(500, "Missing template.html")
            return None

        try:
            file_list = os.listdir(path)
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None

        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        search_query = query_params.get("q", [""])[0].strip().lower()

        file_list.sort()
        items = ""
        
        rel_path = os.path.relpath(path, DIRECTORY)

        # Normalize rel_path for URL
        url_rel_path = rel_path.replace(os.sep, '/')

        # If we're already at root, keep it "/"
        back_link = f'/{url_rel_path}' if rel_path != "." else '/'

        back_to_root_html = (
            f'<div class="back-to-root"><a href="{back_link}">Back to current directory</a></div>'
            if search_query != ''
            else ''
        )
        
        items += '''
            <table class="file-table">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Size</th>
                        <th>Modified</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        if rel_path != ".":
            items += '''
                <tr class="folder">
                    <td><a href="../"><strong>Parent Directory</strong></a></td>
                    <td>Folder</td>
                    <td>-</td>
                    <td>-</td>
                    <td></td>
                </tr>
            '''

        for name in file_list:
            if name in HIDDEN_FILES or name.startswith("."):
                continue
            if search_query and search_query not in name.lower():
                continue

            full_path = os.path.join(path, name)
            try:
                stat = os.stat(full_path)
                size = stat.st_size
                mtime = stat.st_mtime
                last_modified = os.path.getmtime(full_path)
                last_modified_str = datetime.fromtimestamp(last_modified).strftime("%Y-%m-%d %H:%M")
            except Exception:
                size = 0
                last_modified_str = "Unknown"

            size_kb = f"{size / 1024:.1f} KB" if os.path.isfile(full_path) else "-"
            is_folder = os.path.isdir(full_path)
            type_str = "Folder" if is_folder else "File"

            href = quote(name) + "/" if is_folder else quote(name)
            target_attr = ' target="_blank"' if not is_folder else ""
            name_html = f'<a href="{href}"{target_attr}><strong>{name}</strong></a>'
            
            if is_folder:
                actions_html = f'''
                    <div class="dropdown">
                        <button class="dots-btn" onclick="toggleDropdown(event)">&#8942;</button>
                        <div class="dropdown-content">
                            <a href="/download-zip?folder={quote(os.path.join(rel_path, name))}" class="dropdown-link">Download ZIP</a>
                            <button class="delete-btn" onclick="deleteFile('{name}', false)">Delete</button>
                        </div>
                    </div>
                '''
            else:
                actions_html = f'''
                    <div class="dropdown">
                        <button class="dots-btn" onclick="toggleDropdown(event)">&#8942;</button>
                        <div class="dropdown-content">
                            <a href="{quote(name)}" download class="dropdown-link">Download</a>
                            <button class="preview-btn" onclick="previewFile('{name}')">Preview</button>
                            <button class="delete-btn" onclick="deleteFile('{name}', false)">Delete</button>
                        </div>
                    </div>
                '''

            items += f'''
                <tr>
                    <td>{name_html}</td>
                    <td>{type_str}</td>
                    <td>{size_kb}</td>
                    <td>{last_modified_str}</td>
                    <td>{actions_html}</td>
                </tr>
            '''
        items += '''
                </tbody>
            </table>
        '''


        currentFolderName = rel_path.split("/")[-1] if rel_path != "." else "Home"
        currentFolderPath = f'<div class="currentFolder">Currently in: Home/{rel_path}</div>' if rel_path != "." else f'<div class="currentFolder">Currently in: Home</div>'
        
        html = template.replace("{{currentFolderName}}", currentFolderName)
        html = html.replace("{{currentFolderPath}}", currentFolderPath)
        html = html.replace("{{file_table}}", items)
        html = html.replace("{{query}}", search_query)
        html = html.replace("{{backToRootHTML}}", back_to_root_html)

        encoded = html.encode("utf-8", "surrogateescape")
        f = BytesIO()
        f.write(encoded)
        f.seek(0)

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

    def translate_path(self, path):
        # Make sure it serves from our directory
        path = super().translate_path(path)
        rel_path = os.path.relpath(path, os.getcwd())
        return os.path.join(DIRECTORY, rel_path)
        
    def do_POST(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/create-folder":
            query = parse_qs(parsed_url.query)
            folder_name = query.get("name", [None])[0]

            if not folder_name:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing folder name")
                return

            # Sanitize and create folder
            rel_path = os.path.normpath(unquote(folder_name)).lstrip("/")
            file_path = os.path.abspath(os.path.join(DIRECTORY, rel_path))
            print("Path of new folder: ", file_path)

            try:
                os.makedirs(file_path, mode=0o755, exist_ok=False)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Folder created")
            except FileExistsError:
                self.send_response(409)
                self.end_headers()
                self.wfile.write(b"Folder already exists")
            except Exception as e:
                print("Error creating folder:", e)
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to create folder")
                
        elif parsed_url.path == "/upload":
            query = parse_qs(parsed_url.query)
            ctype, pdict = cgi.parse_header(self.headers.get('Content-Type'))
            if ctype == 'multipart/form-data':
                pdict['boundary'] = bytes(pdict['boundary'], "utf-8")
                pdict['CONTENT-LENGTH'] = int(self.headers.get('Content-Length'))
                try:
                    form = cgi.FieldStorage(fp=self.rfile,
                                            headers=self.headers,
                                            environ={'REQUEST_METHOD': 'POST'},
                                            keep_blank_values=True)
                except Exception as e:
                    self.send_error(400, f"Error parsing form data: {e}")
                    return

                if "file" not in form:
                    self.send_error(400, "No file field in form")
                    return

                file_item = form["file"]

                if not file_item.filename:
                    self.send_error(400, "No filename provided")
                    return

                # Sanitize filename to avoid directory traversal attacks
                filename = os.path.basename(file_item.filename)

                # Save file to DIRECTORY
                upload_path = query.get("path", ["/"])[0]  # Default to root if not provided
                safe_rel_path = os.path.normpath(unquote(upload_path)).lstrip("/")

                # Prevent escaping out of DIRECTORY
                abs_upload_dir = os.path.abspath(os.path.join(DIRECTORY, safe_rel_path))

                # Make sure it's still inside the DIRECTORY
                if not abs_upload_dir.startswith(os.path.abspath(DIRECTORY)):
                    self.send_error(400, "Invalid upload path")
                    return

                try:
                    os.makedirs(abs_upload_dir, exist_ok=True)
                except Exception as e:
                    self.send_error(500, f"Failed to create directories: {e}")
                    return

                filepath = os.path.join(abs_upload_dir, filename)

                try:
                    with open(filepath, 'wb') as f:
                        data = file_item.file.read()
                        f.write(data)
                except Exception as e:
                    self.send_error(500, f"Failed to save file: {e}")
                    return

                # Redirect back to the main page (file listing)
                self.send_response(303)  # See Other
                self.send_header('Location', '/')
                self.end_headers()
        
        else:
            self.send_response(404)
            self.end_headers()
            
    def do_DELETE(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/delete":
            query = parse_qs(parsed_url.query)
            filename = query.get("file", [None])[0]

            if not filename:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing file parameter")
                return

            rel_path = os.path.normpath(unquote(filename)).lstrip("/")
            file_path = os.path.abspath(os.path.join(DIRECTORY, rel_path))
            
            print(f"Request to delete: {rel_path}")
            print(f"Resolved path: {file_path}")

            if not file_path.startswith(os.path.abspath(DIRECTORY)):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid file path")
                return

            if not os.path.exists(file_path):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"File or folder not found")
                return

            # Prevent deletion of root directory
            if os.path.abspath(file_path) == os.path.abspath(DIRECTORY):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Cannot delete root directory")
                return

            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)  # recursive delete
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Invalid file type")
                    return

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Deleted")
            except Exception as e:
                print("Error while deleting: ", e)
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to delete")

        else:
            self.send_response(404)
            self.end_headers()
            
    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/download-zip":
            query = parse_qs(parsed_url.query)
            folder = query.get("folder", [None])[0]

            if not folder:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing folder parameter")
                return

            rel_path = os.path.normpath(unquote(folder)).lstrip("/")
            abs_path = os.path.abspath(os.path.join(DIRECTORY, rel_path))

            if not abs_path.startswith(os.path.abspath(DIRECTORY)) or not os.path.isdir(abs_path):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid folder path")
                return

            try:
                folder_name = os.path.basename(abs_path)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_zip:
                    with zipfile.ZipFile(tmp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(abs_path):
                            for file in files:
                                abs_file = os.path.join(root, file)
                                rel_file = os.path.relpath(abs_file, abs_path)
                                zipf.write(abs_file, arcname=os.path.join(folder_name, rel_file))

                    tmp_zip_path = tmp_zip.name

                # Serve the zip file
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{folder_name}.zip"')
                fs = os.stat(tmp_zip_path)
                self.send_header("Content-Length", str(fs.st_size))
                self.end_headers()

                with open(tmp_zip_path, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)

                # Clean up
                os.remove(tmp_zip_path)

            except Exception as e:
                print("Error zipping folder:", e)
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to create ZIP file")
        else:
            # Default file serving with Range support
            try:
                f = None
                # Only handle Range requests for files, not directories or special URLs
                path = self.translate_path(self.path)
                if os.path.isfile(path):
                    result = self.send_head_with_range()
                    if result is None:
                        return  # error already sent
                    f, start, end = result

                    f.seek(start)
                    remaining = end - start + 1
                    bufsize = 64*1024
                    while remaining > 0:
                        read_len = min(bufsize, remaining)
                        data = f.read(read_len)
                        if not data:
                            break
                        self.wfile.write(data)
                        remaining -= len(data)
                    f.close()
                else:
                    # Let superclass handle directories or other requests
                    super().do_GET()
            except BrokenPipeError:
                print("Client disconnected during response (BrokenPipeError)")
            except ConnectionResetError:
                print("Client disconnected early (ConnectionResetError)")
            except Exception as e:
                print("Unexpected error in do_GET():", e)

            
class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True  # threads exit when main thread exits

if __name__ == "__main__":
    os.chdir(DIRECTORY)
    server_address = ("", 8888)
    httpd = ThreadedHTTPServer(server_address, FileHandler)
    print("Serving Server on port 8888...")
    httpd.serve_forever()
