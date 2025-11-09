import os
from io import BytesIO
from datetime import datetime
from errorUtil import send_error_page
from profileUtil import get_profile_dir
from urllib.parse import quote, unquote, urlparse, parse_qs

def listDirectory(handler, path, profile_root, code_directory):
    """Generate the HTML directory listing."""
    try:
        with open(os.path.join(code_directory, "html", "template.html"), "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        send_error_page(handler, 500, "Application template not found", code_directory)
        return None

    try:
        file_list = os.listdir(path)
    except OSError:
        send_error_page(handler, 404, "No permission to list directory", code_directory)
        return None

    profile_dir = get_profile_dir(handler, profile_root)
    profile_name = os.path.basename(profile_dir) if profile_dir else ""

    parsed_url = urlparse(handler.path)
    query_params = parse_qs(parsed_url.query)
    search_query = query_params.get("q", [""])[0].strip().lower()

    file_list.sort()
    items = ""
    rel_path = os.path.relpath(path, get_profile_dir(handler, profile_root))
    url_rel_path = rel_path.replace(os.sep, '/')
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

    parts = [] if rel_path == "." else rel_path.split(os.sep)
    breadcrumb_html = '<a href="/">Home</a>'
    cumulative_path = ""

    for part in parts:
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

    handler.send_response(200)
    handler.send_header("Content-type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    return f


def translatePath(handler, path, profile_root):
    """Translate a URL path into a filesystem path restricted to the user's profile."""
    path = urlparse(path).path
    path = os.path.normpath(unquote(path)).lstrip("/\\")
    full_path = os.path.join(get_profile_dir(handler, profile_root), path)
    abs_base = os.path.abspath(get_profile_dir(handler, profile_root))
    abs_path = os.path.abspath(full_path)

    if not abs_path.startswith(abs_base):
        return abs_base
    return abs_path