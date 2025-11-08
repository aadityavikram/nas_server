import os
import uuid
from urllib.parse import parse_qs
from profileUtil import send_add_profile_form

def create_profile(handler, profile_root, code_directory):
    profile_dirs = [d for d in os.listdir(profile_root)
                                if os.path.isdir(os.path.join(profile_root, d))]

    content_length = int(handler.headers.get('Content-Length', 0))
    post_data = handler.rfile.read(content_length).decode('utf-8')
    post_params = parse_qs(post_data)

    profile_name = post_params.get("profileName", [""])[0].strip()
    profile_name = f"{profile_name}_{uuid.uuid4()}"
    profile_password = post_params.get("profilePassword", [None])[0] or None

    if not profile_name:
        return send_add_profile_form(handler, "Profile name is required.", code_directory)

    if not profile_name or "/" in profile_name or "\\" in profile_name:
        send_add_profile_form(handler, "Invalid profile name.", code_directory)
        return

    for prof in profile_dirs:
        if prof.split("_")[0] == profile_name.split("_")[0]:
            send_add_profile_form(handler, "Profile already exists.", code_directory)
            return

    profile_path = os.path.join(profile_root, profile_name)

    if os.path.exists(profile_path):
        send_add_profile_form(handler, "Profile already exists.", code_directory)
        return

    try:
        os.mkdir(profile_path)
    except Exception as e:
        send_add_profile_form(handler, f"Failed to create profile: {e}", code_directory)
        return

    return profile_name, profile_password