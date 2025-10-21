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
import json

import platform
import subprocess
import re
import signal
import time
import threading
import uuid

# Directory to serve storage
DIRECTORY = "/nas/storage/files"

# Directory to serve code
CODE_DIRECTORY = "/nas/storage/code"

PORT = 8888

progress_store = {}  # progress %
zip_paths = {}       # zip file path
cancelled_jobs = set()

TEMP_ZIP_DIRECTORY = "/nas/storage/temp/zips"

def run_zip_job(abs_path, job_id):
    try:
        create_zip_with_progress(abs_path, job_id)
    except Exception as e:
        print(f"[Thread Error] Job {job_id}: {e}")
        traceback.print_exc()
        progress_store[job_id] = -1

def create_zip_with_progress(abs_path, job_id):
    try:
        folder_name = os.path.basename(abs_path)
        file_list = []
        for root, dirs, files in os.walk(abs_path):
            for file in files:
                file_list.append(os.path.join(root, file))
        total_files = len(file_list)
        progress_store[job_id] = 0

        os.makedirs(TEMP_ZIP_DIRECTORY, exist_ok=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=TEMP_ZIP_DIRECTORY) as tmp_zip:
            with zipfile.ZipFile(tmp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for i, abs_file in enumerate(file_list):
                    if job_id in cancelled_jobs:
                        print(f"[Zip Cancelled] Job {job_id}")
                        progress_store[job_id] = -1

                        # cleanup
                        cancelled_jobs.remove(job_id)
                        progress_store.pop(job_id, None)
                        return

                    rel_file = os.path.relpath(abs_file, abs_path)
                    zipf.write(abs_file, arcname=os.path.join(folder_name, rel_file))

                    # Update progress
                    progress_store[job_id] = int((i+1) / total_files * 100) if total_files else 100
        zip_paths[job_id] = tmp_zip.name
    except Exception as e:
        print(f"Error in create_zip_with_progress: {e}")
        traceback.print_exc()
        progress_store[job_id] = -1  # Error indicator

# --- Add helper functions for process‐killing ---
def kill_process_on_port(port):
    system = platform.system()

    if system == "Windows":
        # Get PID listening on port
        try:
            result = subprocess.check_output(
                f"netstat -ano | findstr :{port}", shell=True, text=True)
            lines = result.strip().split('\n')
            pids = set()
            for line in lines:
                parts = line.strip().split()
                if parts[-1].isdigit():
                    pids.add(parts[-1])
            if not pids:
                print(f"No process found on port {port}")
                return
            for pid in pids:
                print(f"Killing process {pid} on port {port}")
                subprocess.run(f"taskkill /PID {pid} /F", shell=True)
        except subprocess.CalledProcessError:
            print(f"No process found on port {port}")

    else:  # Linux/macOS
        try:
            # Run netstat to find processes listening on the port
            result = subprocess.check_output(f"netstat -nlp | grep :{port}", shell=True, universal_newlines=True)

            # Each line looks like:
            # tcp        0      0 0.0.0.0:8888            0.0.0.0:*               LISTEN      1234/python3
            # Extract PIDs from output lines
            pids = set()
            for line in result.strip().split('\n'):
                match = re.search(r'LISTEN\s+(\d+)/', line)
                if match:
                    pids.add(match.group(1))

            if not pids:
                print(f"No process found on port {port}")
                return

            for pid in pids:
                print(f"Killing process {pid} on port {port}")
                subprocess.run(f"kill -9 {pid}", shell=True)

        except subprocess.CalledProcessError:
            print(f"No process found on port {port}")

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
            m = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if m:
                start = int(m.group(1))
                end_str = m.group(2)
                if end_str:
                    end = int(end_str)
                else:
                    end = size - 1

                # Clamp end to file size
                if end >= size:
                    end = size - 1
                if start >= size or start > end:
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
            with open(os.path.join(CODE_DIRECTORY, "template.html"), "r", encoding="utf-8") as f:
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
                        <th><input type="checkbox" id="selectAll"></th>
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
                    <td></td>
                    <td><a href="../"><strong>Parent Directory</strong></a></td>
                    <td>Folder</td>
                    <td>-</td>
                    <td>-</td>
                    <td></td>
                </tr>
            '''

        for name in file_list:
            if name.startswith("."):
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
                            <a href="javascript:void(0)" class="dropdown-link" onclick="startZipDownload('{quote(os.path.join(rel_path, name))}')">Download ZIP</a>
                            <button class="rename-btn" onclick="renameItem('{name}')">Rename</button>
                            <button class="delete-btn" onclick="deleteFile('{name}', false)">Delete</button>
                            <button class="share-btn" onclick="showShareLink('{name}')">Share Link</button>
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
                            <button class="rename-btn" onclick="renameItem('{name}')">Rename</button>
                            <button class="delete-btn" onclick="deleteFile('{name}', false)">Delete</button>
                            <button class="detail-btn" onclick="showDetails('{name}')">Details</button>
                            <button class="share-btn" onclick="showShareLink('{name}')">Share Link</button>
                        </div>
                    </div>
                '''

            items += f'''
                <tr>
                    <td><input type="checkbox" class="fileCheckbox" data-name="{name}"></td>
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


        # Build breadcrumb navigation
        parts = [] if rel_path == "." else rel_path.split(os.sep)
        breadcrumb_html = '<a href="/">Home</a>'
        cumulative_path = ""

        for i, part in enumerate(parts):
            cumulative_path = os.path.join(cumulative_path, part)
            url_path = "/" + cumulative_path.replace(os.sep, "/")
            breadcrumb_html += f'/<a href="{quote(url_path)}">{part}</a>'

        currentFolderName = parts[-1] if parts else "Home"
        currentFolderPath = f'<div class="currentFolder">Currently in: {breadcrumb_html}</div>'
        
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
        # Remove query parameters and normalize
        path = urlparse(path).path
        path = os.path.normpath(unquote(path))
        # Prevent going above the base directory
        full_path = os.path.join(DIRECTORY, path.lstrip('/\\'))
        if not full_path.startswith(os.path.abspath(DIRECTORY)):
            # Deny paths outside of DIRECTORY root
            return os.path.abspath(DIRECTORY)
        return full_path
        
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
        elif parsed_url.path == "/rename":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            try:
                data = json.loads(body)
                old_path = data.get("old_path")
                new_path = data.get("new_path")

                if not old_path or not new_path:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing old_path or new_path")
                    return

                # Sanitize paths
                old_rel = os.path.normpath(unquote(old_path)).lstrip("/")
                new_rel = os.path.normpath(unquote(new_path)).lstrip("/")

                old_abs = os.path.abspath(os.path.join(DIRECTORY, old_rel))
                new_abs = os.path.abspath(os.path.join(DIRECTORY, new_rel))

                # Security check: ensure both are inside DIRECTORY
                if not old_abs.startswith(os.path.abspath(DIRECTORY)) or not new_abs.startswith(os.path.abspath(DIRECTORY)):
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Invalid path")
                    return

                # Check existence and perform rename
                if not os.path.exists(old_abs):
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Source file or folder does not exist")
                    return

                if os.path.exists(new_abs):
                    self.send_response(409)
                    self.end_headers()
                    self.wfile.write(b"Target name already exists")
                    return

                os.rename(old_abs, new_abs)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Renamed successfully")

            except Exception as e:
                print("Error renaming:", e)
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Rename failed")
        elif parsed_url.path == "/logout":
            threading.Thread(target=shutdown_and_kill).start()
            self.send_response(303)
            self.end_headers()
            return
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

    def handle_details(self, parsed):
        params = parse_qs(parsed.query)
        file_path = params.get("path", [""])[0]
        abs_path = os.path.normpath(os.path.join(DIRECTORY, file_path.lstrip("/")))

        if not abs_path.startswith(DIRECTORY) or not os.path.exists(abs_path):
            self.send_error(404, "Not found")
            return

        stat = os.stat(abs_path)
        file_type = "folder" if os.path.isdir(abs_path) else "file"
        size = stat.st_size if file_type == "file" else "-"
        created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        data = {
            "name": os.path.basename(abs_path),
            "type": file_type,
            "size": f"{size} bytes" if size != "-" else "-",
            "created": created,
            "modified": modified,
            "path": file_path
        }

        json_str = json.dumps(data)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(json_str)))
        self.end_headers()
        self.wfile.write(json_str.encode("utf-8"))
            
    def do_GET(self):
        parsed_url = urlparse(self.path)
        # Serve static files from /nas/storage/code (e.g., style.css, main.js)
        if parsed_url.path.startswith("/static/"):
            file_name = parsed_url.path[len("/static/"):]
            static_path = os.path.join(CODE_DIRECTORY, file_name)

            if not os.path.isfile(static_path):
                self.send_error(404, "Static file not found")
                return

            try:
                ctype = self.guess_type(static_path)
                self.send_response(200)
                self.send_header("Content-type", ctype)
                fs = os.stat(static_path)
                self.send_header("Content-Length", str(fs.st_size))
                self.end_headers()
                with open(static_path, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
                return
            except Exception as e:
                print("Error serving static file:", e)
                self.send_error(500, "Error serving static file")
                return
        if parsed_url.path == "/details":
            return self.handle_details(parsed_url)
        elif parsed_url.path == "/download-zip":
            try:
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

                # Generate a job id
                job_id = str(uuid.uuid4())

                # Start zip creation in a thread
                threading.Thread(target=run_zip_job, args=(abs_path, job_id)).start()

                # Respond immediately with job_id
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"job_id": "{job_id}"}}'.encode())
            except Exception as e:
                print("Error initiating zip:", e)
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to initiate zip")
        elif parsed_url.path == "/zip-progress":
            try:
                query = parse_qs(parsed_url.query)
                job_id = query.get("job_id", [None])[0]

                if not job_id or job_id not in progress_store:
                  self.send_response(404)
                  self.end_headers()
                  self.wfile.write(b"Job not found")
                  return

                prog = progress_store[job_id]
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"progress": {prog}}}'.encode())
            except Exception as e:
                print("Error fetching zip progress:", e)
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to fetch zip progress")
        elif parsed_url.path == "/download-zip-file":
            zip_path = None
            try:
                query = parse_qs(parsed_url.query)
                job_id = query.get("job_id", [None])[0]
                print(f"Query: {query}")
                print(f"Job ID: {job_id}")

                # Wait for the zip file to be ready (up to 30 seconds)
                max_wait_time = 30  # seconds
                wait_interval = 1   # seconds
                waited = 0

                while job_id not in zip_paths and waited < max_wait_time:
                    time.sleep(wait_interval)
                    waited += wait_interval
                    print(f"Waiting for zip file... ({waited}s)")

                if job_id not in zip_paths:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"File not found (zip not ready)")
                    return

                zip_path = zip_paths[job_id]
                print(f"Zip Path: {zip_path}")
                folder_name = os.path.splitext(os.path.basename(zip_path))[0]

                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{folder_name}.zip"')
                fs = os.stat(zip_path)
                self.send_header("Content-Length", str(fs.st_size))
                self.end_headers()

                with open(zip_path, "rb") as f:
                  shutil.copyfileobj(f, self.wfile)

                # Clean up
                print(f"Zip path: {zip_path}")
                os.remove(zip_path)
                del zip_paths[job_id]
                del progress_store[job_id]
            except Exception as e:
                print("Error downloading zipped folder:", e)
                if zip_path and os.path.exists(zip_path):
                    os.remove(zip_path)
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to download ZIP file")
        elif parsed_url.path == "/cancel-zip":
            try:
                query = parse_qs(parsed_url.query)
                job_id = query.get("job_id", [None])[0]

                if not job_id or job_id not in progress_store:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Job not found")
                    return

                cancelled_jobs.add(job_id)

                # Remove zip file if it already exists
                zip_path = zip_paths.get(job_id)
                print(f"Zip path in /cancel: {zip_path}")
                if zip_path and os.path.exists(zip_path):
                    os.remove(zip_path)
                    print(f"Removed partially created zip for job {job_id}")

                # Clean up all job state
                cancelled_jobs.discard(job_id)
                zip_paths.pop(job_id, None)
                progress_store.pop(job_id, None)

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Zip job cancelled")
            except Exception as e:
                print("Error cancelling zip:", e)
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to cancel zip job")
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
                    bufsize = 32*1024
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

def shutdown_and_kill():
    # Wait a moment so response is sent before killing
    time.sleep(1)

    # Kill this server's process or process on port 8888
    # Assuming current process:
    print(f'Process ID: {os.getpid}')
    os.kill(os.getpid(), signal.SIGTERM)

class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True  # threads exit when main thread exits

if __name__ == "__main__":
    os.makedirs(DIRECTORY, exist_ok=True)
    os.makedirs(CODE_DIRECTORY, exist_ok=True)
    os.chdir(DIRECTORY)
    server_address = ("", 8888)
    httpd = ThreadedHTTPServer(server_address, FileHandler)
    print("Serving Server on port 8888...")
    httpd.serve_forever()
