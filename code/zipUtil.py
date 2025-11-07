import os
import zipfile
import tempfile
import traceback

import re
import platform
import subprocess

def run_zip_job(temp_zip_directory, abs_path, job_id, progress_store, zip_paths, cancelled_jobs):
    try:
        create_zip_with_progress(temp_zip_directory, abs_path, job_id, progress_store, zip_paths, cancelled_jobs)
    except Exception as e:
        print(f"[Thread Error] Job {job_id}: {e}")
        traceback.print_exc()
        progress_store[job_id] = -1

def create_zip_with_progress(temp_zip_directory, abs_path, job_id, progress_store, zip_paths, cancelled_jobs):
    try:
        folder_name = os.path.basename(abs_path)
        file_list = []
        for root, dirs, files in os.walk(abs_path):
            for file in files:
                file_list.append(os.path.join(root, file))
        total_files = len(file_list)
        progress_store[job_id] = 0

        os.makedirs(temp_zip_directory, exist_ok=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=temp_zip_directory) as tmp_zip:
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

def run_zip_job_bulk(temp_zip_directory, paths, job_id, progress_store, zip_paths, cancelled_jobs):
    try:
        create_zip_bulk_with_progress(temp_zip_directory, paths, job_id, progress_store, zip_paths, cancelled_jobs)
    except Exception as e:
        print(f"[Thread Error] Job {job_id}: {e}")
        traceback.print_exc()
        progress_store[job_id] = -1

def create_zip_bulk_with_progress(temp_zip_directory, paths, job_id, progress_store, zip_paths, cancelled_jobs):
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
        os.makedirs(temp_zip_directory, exist_ok=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=temp_zip_directory) as tmp_zip:
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
