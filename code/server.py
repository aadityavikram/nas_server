#!/usr/bin/env python3

import os
import cgi
import json
import shutil
import traceback
import socketserver
from io import BytesIO
from datetime import datetime
from urllib.parse import quote, unquote, urlparse, parse_qs
from http.server import HTTPServer, SimpleHTTPRequestHandler

import re
import time
import uuid
import signal
import threading

import mimetypes

from renameUtil import rename
from uploadUtil import upload
from errorUtil import send_error_page
from folderCreationUtil import create_folder
from profileRemovalUtil import remove_profile
from profileCreationUtil import create_profile
from streamingUtil import send_file_with_range
from publicFolderUtil import share_public_folder
from profileLoginUtil import send_login_form, login
from zipDownloadUtil import download_zip, bulk_download_zip
from profileUtil import get_profile_dir, send_profile_selection, send_add_profile_form

# Directory to serve storage
PROFILE_ROOT = "/nas/storage/profiles"

PROFILE_PASSWORDS_FILE = "/nas/storage/code/profiles.json"

# Directory to serve code
CODE_DIRECTORY = "/nas/storage/code"

TEMP_ZIP_DIRECTORY = "/nas/storage/temp/zips"

PORT = 8888

progress_store = {}  # progress %
zip_paths = {}       # zip file path
cancelled_jobs = set()

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

class FileHandler(SimpleHTTPRequestHandler):

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
                send_file_with_range(self, file_path, CODE_DIRECTORY)
            except Exception as e:
                send_error_page(self, 500, f"Error reading file: {e}", CODE_DIRECTORY)
                return
            return
        else:
            send_error_page(self, 404, "File not found", CODE_DIRECTORY)
            return

    def list_directory(self, path):
        try:
            with open(os.path.join(CODE_DIRECTORY, "html", "template.html"), "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            send_error_page(self, 500, "Application template not found", CODE_DIRECTORY)
            return None

        try:
            file_list = os.listdir(path)
        except OSError:
            send_error_page(self, 404, "No permission to list directory", CODE_DIRECTORY)
            return None

        profile_dir = get_profile_dir(self, PROFILE_ROOT)
        profile_name = os.path.basename(profile_dir) if profile_dir else ""

        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        search_query = query_params.get("q", [""])[0].strip().lower()

        file_list.sort()
        items = ""
        
        rel_path = os.path.relpath(path, get_profile_dir(self, PROFILE_ROOT))

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
        full_path = os.path.join(get_profile_dir(self, PROFILE_ROOT), path)
        abs_base = os.path.abspath(get_profile_dir(self, PROFILE_ROOT))
        abs_path = os.path.abspath(full_path)

        if not abs_path.startswith(abs_base):
            return abs_base

        return abs_path
        
    def do_POST(self):
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/login":
            login(self, PROFILE_PASSWORDS, CODE_DIRECTORY)

        if parsed_url.path == "/add-profile":
            response = create_profile(self, PROFILE_ROOT, CODE_DIRECTORY)
            if response is None:
                return
            profile_name, profile_password = response

            # Update the password dictionary and save back
            PROFILE_PASSWORDS[profile_name] = profile_password
            try:
                with open(PROFILE_PASSWORDS_FILE, "w", encoding="utf-8") as f:
                    json.dump(PROFILE_PASSWORDS, f, indent=2)
            except Exception as e:
                return send_add_profile_form(self, "Failed to save profile password.", CODE_DIRECTORY)

            get_profiles_list()

            # Redirect to profile selection after creation
            self.send_response(302)
            self.send_header("Location", "/switch")
            self.end_headers()
            return

        if parsed_url.path == "/remove-profile":
            response = remove_profile(self, PROFILE_ROOT, PROFILE_PASSWORDS, CODE_DIRECTORY)
            if response is None:
                return
            profile_path, profile_to_remove = response

            try:
                shutil.rmtree(profile_path)
                if profile_to_remove in PROFILE_PASSWORDS:
                    PROFILE_PASSWORDS.pop(profile_to_remove, None)
                    try:
                        with open(PROFILE_PASSWORDS_FILE, "w", encoding="utf-8") as f:
                            json.dump(PROFILE_PASSWORDS, f, indent=2)
                    except Exception as e:
                        return send_add_profile_form(self, "Failed to remove profile password.", CODE_DIRECTORY)
            except Exception as e:
                send_error_page(self, 500, f"Failed to remove profile: {e}", CODE_DIRECTORY)
                return

            # Redirect back to profile selection page after removal
            self.send_response(302)
            self.send_header("Location", "/switch")
            self.end_headers()
            return

        if parsed_url.path == "/create-folder":
            create_folder(self, parsed_url, PROFILE_ROOT)

        elif parsed_url.path == "/upload":
            upload(self, parsed_url, PROFILE_ROOT, CODE_DIRECTORY)

        elif parsed_url.path == "/rename":
            rename(self, PROFILE_ROOT)

        elif parsed_url.path == "/logout":
            threading.Thread(target=shutdown_and_kill).start()
            self.send_response(303)
            self.send_header("Set-Cookie", "profile=; Max-Age=0; Path=/")  # Clear cookie
            self.send_header("Set-Cookie", "authenticated=; Max-Age=0; Path=/")  # Clear auth cookie
            self.end_headers()
            return
        elif parsed_url.path == "/bulk-download-zip":
            bulk_download_zip(self, PROFILE_ROOT, TEMP_ZIP_DIRECTORY, progress_store, zip_paths, cancelled_jobs)

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
            file_path = os.path.abspath(os.path.join(get_profile_dir(self, PROFILE_ROOT), rel_path))
            
            print(f"Request to delete: {rel_path}")
            print(f"Resolved path: {file_path}")

            if not file_path.startswith(os.path.abspath(get_profile_dir(self, PROFILE_ROOT))):
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
            if os.path.abspath(file_path) == os.path.abspath(get_profile_dir(self, PROFILE_ROOT)):
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
        abs_path = os.path.normpath(os.path.join(get_profile_dir(self, PROFILE_ROOT), file_path.lstrip("/")))

        if not abs_path.startswith(get_profile_dir(self, PROFILE_ROOT)) or not os.path.exists(abs_path):
            send_error_page(self, 404, "Not found", CODE_DIRECTORY)
            return

        profile_dir = get_profile_dir(self, PROFILE_ROOT)
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

        profile_dir = get_profile_dir(self, PROFILE_ROOT)
        profile_name = os.path.basename(profile_dir) if profile_dir else ""

        # --- New: Handle /share?profile=<profile>&folder=<relative_path> ---
        if requested_path == "/share":
            share_public_folder(self, qs, PROFILE_ROOT, CODE_DIRECTORY)

        # ---  Serve files from public profile without authentication ---
        if requested_path.startswith(f"/{PUBLIC_PROFILE}/"):
            relpath = requested_path[len(PUBLIC_PROFILE) + 2:]  # remove "/public/"
            print(f"Rel Path: {relpath}")
            file_path = os.path.join(PROFILE_ROOT, PUBLIC_PROFILE, relpath)
            print(f"File Path: {file_path}")

            # Prevent path traversal attacks (like /public/../secret.txt)
            file_path = os.path.realpath(file_path)
            if not file_path.startswith(os.path.realpath(os.path.join(PROFILE_ROOT, PUBLIC_PROFILE))):
                send_error_page(self, 403, "You are not authorised", CODE_DIRECTORY)
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
                    send_error_page(self, 403, "You are not authorised", CODE_DIRECTORY)
                    return

                relpath = requested_path[len(profile) + 2:]
                print(f"Rel Path: {relpath}")
                file_path = os.path.join(PROFILE_ROOT, profile, relpath)
                print(f"File Path: {file_path}")

                # Prevent path traversal attacks (like /public/../secret.txt)
                file_path = os.path.realpath(file_path)
                if not file_path.startswith(os.path.realpath(os.path.join(PROFILE_ROOT, profile))):
                    send_error_page(self, 403, "You are not authorised", CODE_DIRECTORY)
                    return

                self.load_profile_file_dir(file_path)
                break

        if parsed_url.path == "/remove-profile":
            # Read profiles again
            try:
                profile_dirs = [d for d in os.listdir(PROFILE_ROOT)
                                if os.path.isdir(os.path.join(PROFILE_ROOT, d))]
            except Exception as e:
                send_error_page(self, 500, "Failed to read profiles", CODE_DIRECTORY)
                return

            # Build HTML to let user select which profile to delete
            profiles_html = ""
            profile_dirs.sort()
            for prof in profile_dirs:
                profiles_html += f'<li><a href="/confirm-remove?profile={quote(prof)}">{prof.split("_")[0]}</a></li>'

            template_path = os.path.join(CODE_DIRECTORY, "html", "profileRemove.html")
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
                send_error_page(self, 400, "Profile not specified", CODE_DIRECTORY)
                return

            profile_to_remove = qs["profile"][0]
            if profile_to_remove.startswith(f"{PUBLIC_PROFILE}"):
                send_error_page(self, 400, "Cannot delete Public profile", CODE_DIRECTORY)
                return
            profile_path = os.path.join(PROFILE_ROOT, profile_to_remove)

            if not os.path.isdir(profile_path):
                send_error_page(self, 404, "Profile not found", CODE_DIRECTORY)
                return

            # Get error message from query string (if any)
            error_msg = qs.get("error", [None])[0]
            error_html = f'<p style="color:#ff4444; font-weight:bold;">{error_msg}</p>' if error_msg else ""

            template_path = os.path.join(CODE_DIRECTORY, "html", "profileRemoveConfirm.html")
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    html = f.read()
            except FileNotFoundError:
                send_error_page(self, 500, "Profile removal confirmation template not found", CODE_DIRECTORY)
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
            send_add_profile_form(self, None, CODE_DIRECTORY)
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
                send_error_page(self, 403, "Invalid profile name", CODE_DIRECTORY)
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
            return send_profile_selection(self, PROFILE_ROOT, PROFILE_LIST, CODE_DIRECTORY)

        # Check if profile requires password
        profile_password = PROFILE_PASSWORDS.get(profile)

        if profile_password is None:
            # No password required — treat as authenticated
            authenticated = True

        elif not authenticated:
            # User not authenticated for the profile, show password form
            return send_login_form(self, profile, None, CODE_DIRECTORY)

        self.profile_dir = get_profile_dir(self, PROFILE_ROOT)
        if not self.profile_dir:
            return send_profile_selection(self, PROFILE_ROOT, PROFILE_LIST, CODE_DIRECTORY)

        self.base_path = self.profile_dir

        # Serve static files from /nas/storage/code (e.g., style.css, main.js)
        if parsed_url.path.startswith("/static/"):
            file_name = parsed_url.path[len("/static/"):]
            static_path = os.path.join(CODE_DIRECTORY, file_name)

            if not os.path.isfile(static_path):
                send_error_page(self, 404, "Static file not found", CODE_DIRECTORY)
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
                send_error_page(self, 500, "Error serving static file", CODE_DIRECTORY)
                return
        if parsed_url.path == "/details":
            return self.handle_details(parsed_url)

        elif parsed_url.path == "/download-zip":
            download_zip(self, parsed_url, PROFILE_ROOT, TEMP_ZIP_DIRECTORY, progress_store, zip_paths, cancelled_jobs)

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
                        send_file_with_range(self, path, CODE_DIRECTORY)
                    except Exception as e:
                        send_error_page(self, 500, f"Error reading file: {e}", CODE_DIRECTORY)
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
