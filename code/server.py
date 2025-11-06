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

import mimetypes

# Directory to serve storage
PROFILE_ROOT = "/nas/storage/profiles"

PROFILE_PASSWORDS_FILE = "/nas/storage/code/profiles.json"

# Directory to serve code
CODE_DIRECTORY = "/nas/storage/code"

PORT = 8888

progress_store = {}  # progress %
zip_paths = {}       # zip file path
cancelled_jobs = set()

TEMP_ZIP_DIRECTORY = "/nas/storage/temp/zips"

def load_profile_passwords():
    global PROFILE_PASSWORDS
    try:
        with open(PROFILE_PASSWORDS_FILE, "r", encoding="utf-8") as f:
            PROFILE_PASSWORDS = json.load(f)
    except FileNotFoundError:
        PROFILE_PASSWORDS = {}
    except json.JSONDecodeError:
        PROFILE_PASSWORDS = {}

def get_profiles_list():
    global PROFILE_LIST
    global PUBLIC_PROFILE
    PROFILE_LIST = list(PROFILE_PASSWORDS.keys())
    for profile in PROFILE_LIST:
        if profile.startswith("Public"):
            PUBLIC_PROFILE = profile
            break

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

def run_zip_job_bulk(paths, job_id):
    try:
        create_zip_bulk_with_progress(paths, job_id)
    except Exception as e:
        print(f"[Thread Error] Job {job_id}: {e}")
        traceback.print_exc()
        progress_store[job_id] = -1

def create_zip_bulk_with_progress(paths, job_id):
    try:
        # Collect all files along with their relative path inside ZIP
        files_to_zip = []

        for path in paths:
            abs_path = os.path.abspath(path)
            name_in_zip = os.path.basename(abs_path)  # top-level folder or file name
            if os.path.isdir(abs_path):
                for root, dirs, files in os.walk(abs_path):
                    for file in files:
                        abs_file = os.path.join(root, file)
                        rel_path_in_zip = os.path.join(
                            name_in_zip,
                            os.path.relpath(abs_file, abs_path)
                        )
                        files_to_zip.append((abs_file, rel_path_in_zip))
            elif os.path.isfile(abs_path):
                files_to_zip.append((abs_path, name_in_zip))  # single file at root

        total_files = len(files_to_zip)
        progress_store[job_id] = 0
        os.makedirs(TEMP_ZIP_DIRECTORY, exist_ok=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=TEMP_ZIP_DIRECTORY) as tmp_zip:
            with zipfile.ZipFile(tmp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for i, (abs_file, rel_path_in_zip) in enumerate(files_to_zip):
                    if job_id in cancelled_jobs:
                        print(f"[Zip Cancelled] Job {job_id}")
                        progress_store[job_id] = -1
                        cancelled_jobs.remove(job_id)
                        progress_store.pop(job_id, None)
                        return

                    zipf.write(abs_file, arcname=rel_path_in_zip)
                    progress_store[job_id] = int((i+1) / total_files * 100) if total_files else 100

        zip_paths[job_id] = tmp_zip.name

    except Exception as e:
        print(f"Error in create_zip_bulk_with_progress: {e}")
        traceback.print_exc()
        progress_store[job_id] = -1

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

    def build_folder_listing(self, folder_path, profile, rel_folder=""):
        """
        List only files & immediate subfolders (no recursion).
        Returns:
            - html listing string
            - json array of files for gallery
        """
        html = ""
        gallery_files = []

        try:
            # --- Up one level link ---
            html += "<ul>"

            for item in sorted(os.listdir(folder_path)):
                full_path = os.path.join(folder_path, item)
                rel_path = os.path.relpath(full_path, os.path.join(PROFILE_ROOT, profile))

                if os.path.isdir(full_path):
                    # Folder link
                    folder_url = f"/share?profile={quote(profile)}&folder={quote(rel_path)}"
                    html += f'<li class="folder"><strong><a href="{folder_url}">{item}/</a></strong></li>'
                else:
                    # File link
                    file_url = f"/{profile}/{quote(rel_path)}"
                    html += f'<li><a href="{file_url}" target="_blank">{item}</a></li>'

                    # Collect gallery files (images only)
                    if item.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')):
                        gallery_files.append({
                            "name": item,
                            "url": file_url,
                            "type": "image"
                        })
                    elif item.lower().endswith(('.mp4', '.webm', '.ogg')):
                        gallery_files.append({
                            "name": item,
                            "url": file_url,
                            "type": "video"
                        })

        except Exception as e:
            html += f"<li>Error reading directory: {e}</li>"

        html += "</ul>"

        # Return HTML + JSON array for gallery
        return html, json.dumps(gallery_files)

    def send_error_page(self, code, message=None):
        """Send a generic HTML error page."""
        messages = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            500: "Internal Server Error",
        }

        title = messages.get(code, "Error")
        description = message or f"An error occurred: {title}"

        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        template_path = os.path.join(CODE_DIRECTORY, "error.html")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_error_page(500, "Error template not found")
            return

        # Replace placeholders
        html = html.replace("{{code}}", str(code))
        html = html.replace("{{title}}", title)
        html = html.replace("{{message}}", description)

        encoded = html.encode("utf-8")
        self.send_response(code)
        self.wfile.write(encoded)

    def get_profile_dir(self):
        # Get profile from cookie
        cookies = self.headers.get("Cookie", "")
        profile = None
        for part in cookies.split(";"):
            if part.strip().startswith("profile="):
                profile = part.strip().split("=")[1]
                break

        if not profile:
            return None

        profile_path = os.path.join(PROFILE_ROOT, profile)
        if not os.path.isdir(profile_path):
            return None

        return profile_path

    def send_profile_selection(self):
        try:
            profile_dirs = [d for d in os.listdir(PROFILE_ROOT)
                            if os.path.isdir(os.path.join(PROFILE_ROOT, d))]
        except Exception as e:
            self.send_error_page(500, "Failed to read profiles")
            return

        template_path = os.path.join(CODE_DIRECTORY, "profile.html")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_error_page(500, "Profile selection template not found")
            return

        # Build list of profiles
        profiles_html = ""
        profile_dirs.sort()
        for prof in profile_dirs:
            profiles_html += f'<a href="/?set_profile={quote(prof)}">{prof.split("_")[0]}</a>\n'

        # Insert into template
        html = html.replace("{{profiles}}", profiles_html)

        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_add_profile_form(self, error_msg=None):
        template_path = os.path.join(CODE_DIRECTORY, "profileAdd.html")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_error_page(500, "Add profile template not found")
            return

        if error_msg:
            error_html = f'<div class="error">{error_msg}</div>'
        else:
            error_html = ''

        html = html.replace("{{error_msg}}", error_html)

        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_password_form(self, profile, error_msg=None):
        template_path = os.path.join(CODE_DIRECTORY, "profileLogin.html")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            self.send_error_page(500, "Login template not found")
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
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_file_with_range(self, file_path):
        """Stream file with HTTP Range support for seeking."""
        try:
            file_size = os.path.getsize(file_path)
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"

            # Check if client sent a Range header
            range_header = self.headers.get("Range")
            if range_header:
                # Parse Range: bytes=start-end
                m = re.match(r"bytes=(\d*)-(\d*)", range_header)
                if not m:
                    self.send_error(400, "Invalid Range header")
                    return

                start, end = m.groups()
                start = int(start) if start else 0
                end = int(end) if end else file_size - 1

                if start >= file_size:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    return

                # Clamp end to file size
                end = min(end, file_size - 1)
                chunk_size = end - start + 1

                self.send_response(206)  # Partial Content
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(chunk_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        read_size = min(32 * 1024, remaining)
                        data = f.read(read_size)
                        if not data:
                            break
                        try:
                            self.wfile.write(data)
                            self.wfile.flush()
                        except BrokenPipeError:
                            print("Client disconnected during range transfer.")
                            break
                        remaining -= len(data)

            else:
                # No Range header — send full file
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                with open(file_path, "rb") as f:
                    while True:
                        data = f.read(32 * 1024)
                        if not data:
                            break
                        try:
                            self.wfile.write(data)
                            self.wfile.flush()
                        except BrokenPipeError:
                            print("Client disconnected during full transfer.")
                            break

        except Exception as e:
            try:
                self.send_error(500, f"Error streaming file: {e}")
            except BrokenPipeError:
                pass

    def load_profile_file_dir(self, file_path):
        if os.path.isdir(file_path):
            print("Is directory")
            f = self.list_directory(file_path)
            if f:
                self.wfile.write(f.read())
            return

        elif os.path.isfile(file_path):
            print("Is file")
            # Guess MIME type automatically
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"

            try:
                self.send_file_with_range(file_path)
            except Exception as e:
                self.send_error_page(500, f"Error reading file: {e}")
                return
            return
        else:
            self.send_error_page(404, "File not found")
            return

    def list_directory(self, path):
        try:
            with open(os.path.join(CODE_DIRECTORY, "template.html"), "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            self.send_error_page(500, "Application template not found")
            return None

        try:
            file_list = os.listdir(path)
        except OSError:
            self.send_error_page(404, "No permission to list directory")
            return None

        profile_dir = self.get_profile_dir()
        profile_name = os.path.basename(profile_dir) if profile_dir else ""

        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        search_query = query_params.get("q", [""])[0].strip().lower()

        file_list.sort()
        items = ""
        
        rel_path = os.path.relpath(path, self.get_profile_dir())

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
                            <button class="share-btn" onclick="showShareLink('{name}', '{profile_name}', 'folder')">Share Link</button>
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
                            <button class="share-btn" onclick="showShareLink('{name}', '{profile_name}', 'file')">Share Link</button>
                        </div>
                    </div>
                '''

            items += f'''
                <tr>
                    <td><input type="checkbox" class="fileCheckbox" data-name="{name}" data-path="{quote(name)}" data-type="{'folder' if is_folder else 'file'}"></td>
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
        html = html.replace("{{profileName}}", profile_name.split("_")[0])
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
        path = urlparse(path).path
        path = os.path.normpath(unquote(path)).lstrip("/\\")
        full_path = os.path.join(self.get_profile_dir(), path)
        abs_base = os.path.abspath(self.get_profile_dir())
        abs_path = os.path.abspath(full_path)

        if not abs_path.startswith(abs_base):
            return abs_base

        return abs_path
        
    def do_POST(self):
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/login":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            params = parse_qs(post_data)

            profile = params.get("profile", [None])[0]
            password = params.get("password", [None])[0]

            if not profile or not password:
                self.send_error_page(400, "Missing profile or password")
                return

            expected_password = PROFILE_PASSWORDS.get(profile)
            if expected_password is not None and password == expected_password:
                # Password is correct - set authenticated cookie and redirect to /
                self.send_response(302)
                self.send_header("Set-Cookie", f"profile={profile}; Path=/")
                self.send_header("Set-Cookie", "authenticated=yes; Path=/")
                self.send_header("Location", "/")
                self.end_headers()
            else:
                # Wrong password - show password form with error
                self.send_password_form(profile, error_msg="Incorrect password")
            return

        if parsed_url.path == "/add-profile":
            profile_dirs = [d for d in os.listdir(PROFILE_ROOT)
                                        if os.path.isdir(os.path.join(PROFILE_ROOT, d))]

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            post_params = parse_qs(post_data)

            profile_name = post_params.get("profileName", [""])[0].strip()
            profile_name = f"{profile_name}_{uuid.uuid4()}"
            profile_password = post_params.get("profilePassword", [None])[0] or None

            if not profile_name:
                return self.send_add_profile_form(error_msg="Profile name is required.")

            if not profile_name or "/" in profile_name or "\\" in profile_name:
                self.send_add_profile_form(error_msg="Invalid profile name.")
                return

            for prof in profile_dirs:
                if prof.split("_")[0] == profile_name.split("_")[0]:
                    self.send_add_profile_form(error_msg="Profile already exists.")
                    return

            profile_path = os.path.join(PROFILE_ROOT, profile_name)

            if os.path.exists(profile_path):
                self.send_add_profile_form(error_msg="Profile already exists.")
                return

            try:
                os.mkdir(profile_path)
            except Exception as e:
                self.send_add_profile_form(error_msg=f"Failed to create profile: {e}")
                return

            # Update the password dictionary and save back
            PROFILE_PASSWORDS[profile_name] = profile_password
            try:
                with open(PROFILE_PASSWORDS_FILE, "w", encoding="utf-8") as f:
                    json.dump(PROFILE_PASSWORDS, f, indent=2)
            except Exception as e:
                return self.send_add_profile_form(error_msg="Failed to save profile password.")

            # Redirect to profile selection after creation
            self.send_response(302)
            self.send_header("Location", "/switch")
            self.end_headers()
            return

        if parsed_url.path == "/remove-profile":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            post_params = parse_qs(post_data)

            if "profile" not in post_params:
                self.send_error_page(400, "Profile not specified")
                return

            profile_to_remove = post_params["profile"][0]
            password = None
            if "password" in post_params:
                password = post_params["password"][0]
            profile_path = os.path.join(PROFILE_ROOT, profile_to_remove)

            if not os.path.isdir(profile_path):
                self.send_error_page(404, "Profile not found")
                return

            expected_password = PROFILE_PASSWORDS.get(profile_to_remove)

            # Check password if a password is required
            if expected_password is not None:
                if password != expected_password:
                    # Redirect back to confirmation with error
                    self.send_response(302)
                    self.send_header("Location", f"/confirm-remove?profile={quote(profile_to_remove)}&error=Invalid+password")
                    self.end_headers()
                    return

            try:
                shutil.rmtree(profile_path)
                if profile_to_remove in PROFILE_PASSWORDS:
                    PROFILE_PASSWORDS.pop(profile_to_remove, None)
                    try:
                        with open(PROFILE_PASSWORDS_FILE, "w", encoding="utf-8") as f:
                            json.dump(PROFILE_PASSWORDS, f, indent=2)
                    except Exception as e:
                        return self.send_add_profile_form(error_msg="Failed to remove profile password.")
            except Exception as e:
                self.send_error_page(500, f"Failed to remove profile: {e}")
                return

            # Redirect back to profile selection page after removal
            self.send_response(302)
            self.send_header("Location", "/switch")
            self.end_headers()
            return

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
            file_path = os.path.abspath(os.path.join(self.get_profile_dir(), rel_path))
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
            self.profile_dir = self.get_profile_dir()
            if not self.profile_dir:
                self.send_error_page(403, "Profile not selected")
                return
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
                    self.send_error_page(400, f"Error parsing form data: {e}")
                    return

                if "file" not in form:
                    self.send_error_page(400, "No file field in form")
                    return

                file_item = form["file"]

                if not file_item.filename:
                    self.send_error_page(400, "No filename provided")
                    return

                # Sanitize filename to avoid directory traversal attacks
                filename = os.path.basename(file_item.filename)

                # Save file to DIRECTORY
                upload_path = query.get("path", ["/"])[0]  # Default to root if not provided
                safe_rel_path = os.path.normpath(unquote(upload_path)).lstrip("/")

                # Prevent escaping out of DIRECTORY
                abs_upload_dir = os.path.abspath(os.path.join(self.get_profile_dir(), safe_rel_path))

                # Make sure it's still inside the DIRECTORY
                if not abs_upload_dir.startswith(os.path.abspath(self.get_profile_dir())):
                    self.send_error_page(400, "Invalid upload path")
                    return

                try:
                    os.makedirs(abs_upload_dir, exist_ok=True)
                except Exception as e:
                    self.send_error_page(500, f"Failed to create directories: {e}")
                    return

                filepath = os.path.join(abs_upload_dir, filename)

                try:
                    with open(filepath, 'wb') as f:
                        data = file_item.file.read()
                        f.write(data)
                except Exception as e:
                    self.send_error_page(500, f"Failed to save file: {e}")
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

                old_abs = os.path.abspath(os.path.join(self.get_profile_dir(), old_rel))
                new_abs = os.path.abspath(os.path.join(self.get_profile_dir(), new_rel))

                # Security check: ensure both are inside DIRECTORY
                if not old_abs.startswith(os.path.abspath(self.get_profile_dir())) or not new_abs.startswith(os.path.abspath(self.get_profile_dir())):
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
            self.send_header("Set-Cookie", "profile=; Max-Age=0; Path=/")  # Clear cookie
            self.send_header("Set-Cookie", "authenticated=; Max-Age=0; Path=/")  # Clear auth cookie
            self.end_headers()
            return
        elif parsed_url.path == "/bulk-download-zip":
            try:
                # Expect JSON POST
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode())

                paths = data.get("paths", [])
                if not paths or not isinstance(paths, list):
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing or invalid paths parameter")
                    return

                abs_paths = []
                for p in paths:
                    rel_path = os.path.normpath(unquote(p)).lstrip("/")
                    abs_path = os.path.abspath(os.path.join(self.get_profile_dir(), rel_path))
                    if not abs_path.startswith(os.path.abspath(self.get_profile_dir())):
                        continue
                    if not os.path.exists(abs_path):
                        continue
                    abs_paths.append(abs_path)

                if not abs_paths:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"No valid files or folders to zip")
                    return

                # Generate a job id
                job_id = str(uuid.uuid4())

                # Start zip creation in a thread
                threading.Thread(target=run_zip_job_bulk, args=(abs_paths, job_id)).start()

                # Respond immediately with job_id
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"job_id": "{job_id}"}}'.encode())

            except Exception as e:
                print("Error initiating bulk zip:", e)
                traceback.print_exc()
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to initiate bulk zip")
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
            file_path = os.path.abspath(os.path.join(self.get_profile_dir(), rel_path))
            
            print(f"Request to delete: {rel_path}")
            print(f"Resolved path: {file_path}")

            if not file_path.startswith(os.path.abspath(self.get_profile_dir())):
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
            if os.path.abspath(file_path) == os.path.abspath(self.get_profile_dir()):
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
        abs_path = os.path.normpath(os.path.join(self.get_profile_dir(), file_path.lstrip("/")))

        if not abs_path.startswith(self.get_profile_dir()) or not os.path.exists(abs_path):
            self.send_error_page(404, "Not found")
            return

        profile_dir = self.get_profile_dir()
        profile_name = os.path.basename(profile_dir) if profile_dir else ""
        profile_name = profile_name.split("_")[0]

        stat = os.stat(abs_path)
        file_type = "folder" if os.path.isdir(abs_path) else "file"
        size = stat.st_size if file_type == "file" else "-"
        created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        file_path = f"{profile_name}{file_path}"

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
        qs = parse_qs(parsed_url.query)
        requested_path = unquote(parsed_url.path)

        profile_dir = self.get_profile_dir()
        profile_name = os.path.basename(profile_dir) if profile_dir else ""

        # --- New: Handle /share?profile=<profile>&folder=<relative_path> ---
        if requested_path == "/share":
            profile = qs.get("profile", [""])[0]
            folder = qs.get("folder", [""])[0]

            if not profile:
                self.send_error_page(400, "Missing 'profile' parameter")
                return

            base_dir = os.path.join(PROFILE_ROOT, profile)
            folder_path = os.path.realpath(os.path.join(base_dir, folder))

            if not folder_path.startswith(os.path.realpath(base_dir)):
                self.send_error_page(403, "You are not authorised")
                return

            if not os.path.exists(folder_path):
                self.send_error_page(404, "Folder not found")
                return

            # Build *non-recursive* listing
            html_listing, json_folder_files = self.build_folder_listing(folder_path, profile, folder)

            template_path = os.path.join(CODE_DIRECTORY, "sharePublicFolder.html")
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()

            html = template.replace("{{profile}}", profile.split("_")[0])
            html = html.replace("{{folder}}", folder)
            html = html.replace("{{folder_listing}}", html_listing)
            html = html.replace("{{json_folder_files}}", json_folder_files)

            encoded = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        # ---  Serve files from public profile without authentication ---
        if requested_path.startswith(f"/{PUBLIC_PROFILE}/"):
            relpath = requested_path[len(PUBLIC_PROFILE) + 2:]  # remove "/public/"
            print(f"Rel Path: {relpath}")
            file_path = os.path.join(PROFILE_ROOT, PUBLIC_PROFILE, relpath)
            print(f"File Path: {file_path}")

            # Prevent path traversal attacks (like /public/../secret.txt)
            file_path = os.path.realpath(file_path)
            if not file_path.startswith(os.path.realpath(os.path.join(PROFILE_ROOT, PUBLIC_PROFILE))):
                self.send_error_page(403, "You are not authorised")
                return

            self.load_profile_file_dir(file_path)

        for profile in PROFILE_LIST:
            if requested_path.startswith(f"/{profile}/"):
                parts = requested_path.strip("/").split("/", 1)
                if len(parts) >= 1:
                    profileNameActual = parts[0]
                else:
                    profileNameActual = ""

                print(f"{profile_name} {profileNameActual}")

                if profile_name != profileNameActual:
                    self.send_error_page(403, "You are not authorised")
                    return

                relpath = requested_path[len(profile) + 2:]
                print(f"Rel Path: {relpath}")
                file_path = os.path.join(PROFILE_ROOT, profile, relpath)
                print(f"File Path: {file_path}")

                # Prevent path traversal attacks (like /public/../secret.txt)
                file_path = os.path.realpath(file_path)
                if not file_path.startswith(os.path.realpath(os.path.join(PROFILE_ROOT, profile))):
                    self.send_error_page(403, "You are not authorised")
                    return

                self.load_profile_file_dir(file_path)
                break

        if parsed_url.path == "/remove-profile":
            # Read profiles again
            try:
                profile_dirs = [d for d in os.listdir(PROFILE_ROOT)
                                if os.path.isdir(os.path.join(PROFILE_ROOT, d))]
            except Exception as e:
                self.send_error_page(500, "Failed to read profiles")
                return

            # Build HTML to let user select which profile to delete
            profiles_html = ""
            profile_dirs.sort()
            for prof in profile_dirs:
                profiles_html += f'<li><a href="/confirm-remove?profile={quote(prof)}">{prof.split("_")[0]}</a></li>'

            template_path = os.path.join(CODE_DIRECTORY, "profileRemove.html")
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()

            # Replace placeholder with actual profiles HTML
            html = template.replace("{{profiles_html}}", profiles_html)

            encoded = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        if parsed_url.path == "/confirm-remove":
            # Confirm removal page for the selected profile
            if "profile" not in qs:
                self.send_error_page(400, "Profile not specified")
                return

            profile_to_remove = qs["profile"][0]
            if profile_to_remove.startswith(f"{PUBLIC_PROFILE}"):
                self.send_error_page(400, "Cannot delete Public profile")
                return
            profile_path = os.path.join(PROFILE_ROOT, profile_to_remove)

            if not os.path.isdir(profile_path):
                self.send_error_page(404, "Profile not found")
                return

            # Get error message from query string (if any)
            error_msg = qs.get("error", [None])[0]
            error_html = f'<p style="color:#ff4444; font-weight:bold;">{error_msg}</p>' if error_msg else ""

            template_path = os.path.join(CODE_DIRECTORY, "profileRemoveConfirm.html")
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    html = f.read()
            except FileNotFoundError:
                self.send_error_page(500, "Profile removal confirmation template not found")
                return

            html = html.replace("{{profile_name_to_remove}}", profile_to_remove.split("_")[0])
            html = html.replace("{{profile_to_remove}}", profile_to_remove)
            html = html.replace("{{error_html}}", error_html)

            encoded = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        if parsed_url.path == "/switch":
            self.send_response(302)
            self.send_header("Set-Cookie", "profile=; Max-Age=0; Path=/")  # Clear cookie
            self.send_header("Set-Cookie", "authenticated=; Max-Age=0; Path=/")  # Clear auth cookie
            self.send_header("Location", "/")
            self.end_headers()
            return

        if parsed_url.path == "/add-profile":
            self.send_add_profile_form()
            return

        if "set_profile" in qs:
            new_profile = qs["set_profile"][0]
            profile_path = os.path.join(PROFILE_ROOT, new_profile)
            if os.path.isdir(profile_path):
                # Set profile cookie but not authenticated yet
                self.send_response(302)
                self.send_header("Set-Cookie", f"profile={new_profile}; Path=/")
                self.send_header("Set-Cookie", "authenticated=; Max-Age=0; Path=/")  # Clear auth
                self.send_header("Location", "/")
                self.end_headers()
            else:
                self.send_error_page(403, "Invalid profile name")
            return

        cookies = self.headers.get("Cookie", "")
        profile = None
        authenticated = False
        for part in cookies.split(";"):
            part = part.strip()
            if part.startswith("profile="):
                profile = part.split("=")[1]
            if part.startswith("authenticated="):
                if part.split("=")[1] == "yes":
                    authenticated = True

        if not profile:
            return self.send_profile_selection()

        # Check if profile requires password
        profile_password = PROFILE_PASSWORDS.get(profile)

        if profile_password is None:
            # No password required — treat as authenticated
            authenticated = True

        elif not authenticated:
            # User not authenticated for the profile, show password form
            return self.send_password_form(profile)

        self.profile_dir = self.get_profile_dir()
        if not self.profile_dir:
            return self.send_profile_selection()

        self.base_path = self.profile_dir

        # Serve static files from /nas/storage/code (e.g., style.css, main.js)
        if parsed_url.path.startswith("/static/"):
            file_name = parsed_url.path[len("/static/"):]
            static_path = os.path.join(CODE_DIRECTORY, file_name)

            if not os.path.isfile(static_path):
                self.send_error_page(404, "Static file not found")
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
                self.send_error_page(500, "Error serving static file")
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
                abs_path = os.path.abspath(os.path.join(self.get_profile_dir(), rel_path))

                if not abs_path.startswith(os.path.abspath(self.get_profile_dir())) or not os.path.isdir(abs_path):
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
                    try:
                        self.send_file_with_range(path)
                    except Exception as e:
                        self.send_error_page(500, f"Error reading file: {e}")
                        return
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
    os.makedirs(PROFILE_ROOT, exist_ok=True)
    os.makedirs(CODE_DIRECTORY, exist_ok=True)
    load_profile_passwords()
    get_profiles_list()
    server_address = ("", PORT)
    httpd = ThreadedHTTPServer(server_address, FileHandler)
    print(f"Serving on port {PORT}...")
    httpd.serve_forever()
