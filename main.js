const currentPath = window.location.pathname;

function triggerFileUpload() {
    const input = document.getElementById('fileInput');
    input.click();

    input.onchange = () => {
        if (input.files.length === 0) return;

        const file = input.files[0];
        const formData = new FormData();
        formData.append("file", file);

        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener("progress", (e) => {
            if (e.lengthComputable) {
                const percent = (e.loaded / e.total) * 100;
                document.getElementById("progressBar").style.width = percent + "%";
				document.getElementById("progressText").textContent = Math.round(percent) + "%";
            }
        });

        xhr.onloadstart = () => {
            // Show progress bar
            document.getElementById("progressContainer").style.display = "block";
            document.getElementById("progressBar").style.width = "0%";
        };

        xhr.onloadend = () => {
            // Reset progress bar and show button again after delay
            setTimeout(() => {
                document.getElementById("progressContainer").style.display = "none";
                document.getElementById("progressBar").style.width = "0%";
            }, 1000);
        };

        xhr.onreadystatechange = () => {
            if (xhr.readyState === 4 && xhr.status >= 200 && xhr.status < 300) {
                window.location.reload();
            } else if (xhr.readyState === 4) {
				console.log("XHR Status: " + xhr.status);
                alert("Upload failed");
            }
        };

        const currentPath = window.location.pathname;
		xhr.open("POST", `/upload?path=${encodeURIComponent(currentPath)}`, true);
        xhr.send(formData);
    };
}

function triggerFolderUpload() {
    const input = document.createElement('input');
    input.type = 'file';
    input.webkitdirectory = true;  // Enable folder selection in Chrome/Edge
    input.directory = true;        // Allow only folder select
    input.multiple = true;         // Allow multiple files inside folders

    input.onchange = () => {
        if (!input.files.length) return;

        const files = input.files;
        const currentPath = window.location.pathname;

        const uploadFile = (file, relativePath) => {
            const formData = new FormData();
            formData.append("file", file);

            // Upload with original folder structure
            const uploadPath = `${currentPath}${relativePath.substring(0, relativePath.lastIndexOf("/"))}`;
            const xhr = new XMLHttpRequest();

            xhr.open("POST", `/upload?path=${encodeURIComponent(uploadPath)}`, true);

            xhr.onreadystatechange = () => {
                if (xhr.readyState === 4 && xhr.status >= 400) {
                    console.error(`Upload failed for ${file.name}: ${xhr.responseText}`);
                }
            };

            xhr.send(formData);
        };

        for (const file of files) {
            const relativePath = file.webkitRelativePath;
            if (relativePath) {
                uploadFile(file, relativePath);
            }
        }

        // Refresh after a short delay to allow uploads to complete
        setTimeout(() => window.location.reload(), 1500);
    };

    input.click();
}


// Toggle dropdown menu visibility
function toggleDropdown(event) {
    event.stopPropagation();

    const parent = event.currentTarget.closest('.dropdown');
    const dropdown = parent.querySelector('.dropdown-content');

    // Close all other dropdowns
    document.querySelectorAll('.dropdown-content').forEach(menu => {
        if (menu !== dropdown) {
            menu.style.display = 'none';
        }
    });

    dropdown.style.display = dropdown.style.display === 'block' ? 'none' : 'block';
}

// Toggle dropdown menu visibility
function toggleDropdownMain(event) {
    event.stopPropagation();

    const parent = event.currentTarget.closest('.dropdown-main');
    const dropdown = parent.querySelector('.dropdown-content-main');

    // Close all other dropdowns
    document.querySelectorAll('.dropdown-content-main').forEach(menu => {
        if (menu !== dropdown) {
            menu.style.display = 'none';
        }
    });

    // Toggle this one
    dropdown.style.display = dropdown.style.display === 'block' ? 'none' : 'block';
}


// Close all dropdowns when clicking outside
window.addEventListener('click', () => {
	closeMainDropdown();
    closeAllDropdowns();
});

function closeMainDropdown() {
    document.querySelectorAll('.dropdown-content-main').forEach(menu => {
        menu.style.display = 'none';
    });
}

function closeAllDropdowns() {
    document.querySelectorAll('.dropdown-content').forEach(menu => {
        menu.style.display = 'none';
    });
}

function deleteFile(name) {
    const baseName = name.replace(/\/$/, '');

    let confirmMsg = `Are you sure you want to delete "${baseName}"?`;

    if (!confirm(confirmMsg)) return;

    let fullPath = currentPath;
    if (!fullPath.endsWith("/")) {
        fullPath += "/";
    }

    fullPath += name;

    fetch('/delete?file=' + encodeURIComponent(fullPath), {
        method: 'DELETE',
    })
    .then(response => {
        if (response.ok) {
            alert(`Deleted "${baseName}"`);
            window.location.reload();
        } else {
            response.text().then(text => {
                alert(`Failed to delete: ${text}`);
            });
        }
    })
    .catch(() => alert('Error deleting'));
}

function createFolder() {
    const folderName = prompt("Enter new folder name:");

    if (!folderName) return;
	
	let fullPath = currentPath;

    if (!fullPath.endsWith("/")) {
        fullPath += "/";
    }

    fullPath += folderName;

    fetch(`/create-folder?name=${encodeURIComponent(fullPath)}`, {
        method: 'POST',
    })
    .then(res => {
        if (res.ok) {
            alert("Folder created.");
            window.location.reload();
        } else {
            alert("Failed to create folder.");
        }
    })
    .catch(error => {
		console.error("Error creating folder:", error);
		alert("Error creating folder: " + error.message);
	});
}
