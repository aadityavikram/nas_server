import os
import json
import uuid
import traceback
import threading
from profileUtil import get_profile_dir
from urllib.parse import unquote, parse_qs
from zipUtil import run_zip_job, run_zip_job_bulk

def download_zip(handler, parsed_url, profile_root, temp_zip_directory, progress_store, zip_paths, cancelled_jobs):
    try:
        query = parse_qs(parsed_url.query)
        folder = query.get("folder", [None])[0]

        if not folder:
          handler.send_response(400)
          handler.end_headers()
          handler.wfile.write(b"Missing folder parameter")
          return

        rel_path = os.path.normpath(unquote(folder)).lstrip("/")
        abs_path = os.path.abspath(os.path.join(get_profile_dir(handler, profile_root), rel_path))

        if not abs_path.startswith(os.path.abspath(get_profile_dir(handler, profile_root))) or not os.path.isdir(abs_path):
          handler.send_response(400)
          handler.end_headers()
          handler.wfile.write(b"Invalid folder path")
          return

        # Generate a job id
        job_id = str(uuid.uuid4())

        # Start zip creation in a thread
        threading.Thread(target=run_zip_job, args=(temp_zip_directory, abs_path, job_id, progress_store, zip_paths, cancelled_jobs)).start()

        # Respond immediately with job_id
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(f'{{"job_id": "{job_id}"}}'.encode())
    except Exception as e:
        print("Error initiating zip:", e)
        traceback.print_exc()
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(b"Failed to initiate zip")

def bulk_download_zip(handler, profile_root, temp_zip_directory, progress_store, zip_paths, cancelled_jobs):
    try:
        # Expect JSON POST
        content_length = int(handler.headers.get("Content-Length", 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body.decode())

        paths = data.get("paths", [])
        if not paths or not isinstance(paths, list):
            handler.send_response(400)
            handler.end_headers()
            handler.wfile.write(b"Missing or invalid paths parameter")
            return

        abs_paths = []
        for p in paths:
            rel_path = os.path.normpath(unquote(p)).lstrip("/")
            abs_path = os.path.abspath(os.path.join(get_profile_dir(handler, profile_root), rel_path))
            if not abs_path.startswith(os.path.abspath(get_profile_dir(handler, profile_root))):
                continue
            if not os.path.exists(abs_path):
                continue
            abs_paths.append(abs_path)

        if not abs_paths:
            handler.send_response(400)
            handler.end_headers()
            handler.wfile.write(b"No valid files or folders to zip")
            return

        # Generate a job id
        job_id = str(uuid.uuid4())

        # Start zip creation in a thread
        threading.Thread(target=run_zip_job_bulk, args=(temp_zip_directory, abs_paths, job_id, progress_store, zip_paths, cancelled_jobs)).start()

        # Respond immediately with job_id
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(f'{{"job_id": "{job_id}"}}'.encode())

    except Exception as e:
        print("Error initiating bulk zip:", e)
        traceback.print_exc()
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(b"Failed to initiate bulk zip")