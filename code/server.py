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

from switchUtil import switch
from deleteUtil import delete
from logoutUtil import logout
from renameUtil import rename
from uploadUtil import upload
from errorUtil import send_error_page
from folderCreationUtil import create_folder
from profileCreationUtil import create_profile
from streamingUtil import send_file_with_range
from publicFolderUtil import share_public_folder
from profileLoginUtil import send_login_form, login
from loadDirectoryUtil import listDirectory, translatePath
from zipDownloadUtil import download_zip, bulk_download_zip
from loadProfileUtil import load_public_profile, load_profile
from profileUtil import get_profile_dir, send_profile_selection, send_add_profile_form
from profileRemovalUtil import remove_profile, remove_profile_get, remove_profile_confirm_get

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

    def list_directory(self, path):
        return listDirectory(self, path, PROFILE_ROOT, CODE_DIRECTORY)

    def translate_path(self, path):
        return translatePath(self, path, PROFILE_ROOT)
        
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
            logout(self, os.getpid())

        elif parsed_url.path == "/bulk-download-zip":
            bulk_download_zip(self, PROFILE_ROOT, TEMP_ZIP_DIRECTORY, progress_store, zip_paths, cancelled_jobs)

        else:
            self.send_response(404)
            self.end_headers()
            
    def do_DELETE(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/delete":
            delete(self, parsed_url, PROFILE_ROOT)

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
            return load_public_profile(self, requested_path, PUBLIC_PROFILE, PROFILE_ROOT, CODE_DIRECTORY)

        for profile in PROFILE_LIST:
            if requested_path.startswith(f"/{profile}/"):
                return load_profile(self, profile, profile_name, requested_path, PROFILE_ROOT, CODE_DIRECTORY)

        if parsed_url.path == "/remove-profile":
            return remove_profile_get(self, PROFILE_ROOT, CODE_DIRECTORY)

        if parsed_url.path == "/confirm-remove":
            return remove_profile_confirm_get(self, qs, PUBLIC_PROFILE, PROFILE_ROOT, CODE_DIRECTORY)

        if parsed_url.path == "/switch":
            return switch(self)

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
