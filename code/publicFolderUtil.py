import os
import json
from urllib.parse import quote

from errorUtil import send_error_page

def build_folder_listing(profile_root, folder_path, profile, rel_folder=""):
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
            rel_path = os.path.relpath(full_path, os.path.join(profile_root, profile))

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

def share_public_folder(handler, qs, profile_root, code_directory):
    profile = qs.get("profile", [""])[0]
    folder = qs.get("folder", [""])[0]

    if not profile:
        send_error_page(handler, 400, "Missing 'profile' parameter", code_directory)
        return

    base_dir = os.path.join(profile_root, profile)
    folder_path = os.path.realpath(os.path.join(base_dir, folder))

    if not folder_path.startswith(os.path.realpath(base_dir)):
        send_error_page(handler, 403, "You are not authorised", code_directory)
        return

    if not os.path.exists(folder_path):
        send_error_page(handler, 404, "Folder not found", code_directory)
        return

    # Build *non-recursive* listing
    html_listing, json_folder_files = build_folder_listing(profile_root, folder_path, profile, folder)

    template_path = os.path.join(code_directory, "html", "sharePublicFolder.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    html = template.replace("{{profile}}", profile.split("_")[0])
    html = html.replace("{{folder}}", folder)
    html = html.replace("{{folder_listing}}", html_listing)
    html = html.replace("{{json_folder_files}}", json_folder_files)

    encoded = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)
    return