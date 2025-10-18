const currentPath = window.location.pathname;
let currentXHR = null;
let wasCancelled = false; 

function triggerFileUpload() {
    const input = document.getElementById('fileInput');
    input.click();

    input.onchange = () => {
        if (input.files.length === 0) return;

        const file = input.files[0];
        const formData = new FormData();
        formData.append("file", file);

        const xhr = new XMLHttpRequest();
		currentXHR = xhr;
		wasCancelled = false;

        xhr.upload.addEventListener("progress", (e) => {
            if (e.lengthComputable) {
                const percent = (e.loaded / e.total) * 100;
                document.getElementById("progressBar").style.width = percent + "%";
				document.getElementById("progressText").textContent = Math.round(percent) + "%";
            }
        });

        xhr.onloadstart = () => {
            // Show progress bar
            document.getElementById("progressWrapper").style.display = "flex";
			document.getElementById("cancelUploadBtn").style.display = "inline";
            document.getElementById("progressBar").style.width = "0%";
        };

        xhr.onloadend = () => {
            // Reset progress bar and show button again after delay
            setTimeout(() => {
                document.getElementById("progressWrapper").style.display = "none";
				document.getElementById("cancelUploadBtn").style.display = "none";
                document.getElementById("progressBar").style.width = "0%";
            }, 1000);
			currentXHR = null;
        };

        xhr.onreadystatechange = () => {
            if (xhr.readyState === 4 && xhr.status >= 200 && xhr.status < 300) {
                window.location.reload();
            } else if (xhr.readyState === 4 && !wasCancelled) {
				console.log("XHR Status: " + xhr.status);
                alert("Upload failed");
            }
        };

        const currentPath = window.location.pathname;
		xhr.open("POST", `/upload?path=${encodeURIComponent(currentPath)}`, true);
        xhr.send(formData);
    };
}

document.getElementById("cancelUploadBtn").addEventListener("click", () => {
    if (currentXHR) {
		wasCancelled = true;
        currentXHR.abort();
        currentXHR = null;
        document.getElementById("progressContainer").style.display = "none";
        document.getElementById("progressBar").style.width = "0%";
        document.getElementById("cancelUploadBtn").style.display = "none";
        alert("Upload cancelled.");
		
		const input = document.getElementById('fileInput');
        const file = input.files[0];
        const filename = file ? file.name : null;

        if (filename) {
            setTimeout(() => {
                deleteFile(filename, true);
                window.location.reload();
            }, 1000);
        } else {
            window.location.reload();
        }
    }
});

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

function deleteFile(name, uploadCancelled = false) {
    const baseName = name.replace(/\/$/, '');

	if (!uploadCancelled) {
		let confirmMsg = `Are you sure you want to delete "${baseName}"?`;
		if (!confirm(confirmMsg)) return;
	}

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
			if (!uploadCancelled) {
				alert(`Deleted "${baseName}"`);
			}
            window.location.reload();
        } else {
            response.text().then(text => {
				if (!uploadCancelled) {
					alert(`Failed to delete: ${text}`);
				}
            });
        }
    })
    .catch((error) => {
		console.error('Error deleting:', error);
		if (!uploadCancelled) {
			alert('Error deleting: ' + error.message);
		}
	});
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

function previewFile(fileName) {
    const ext = fileName.split('.').pop().toLowerCase();
    const fullPath = currentPath.endsWith("/") ? currentPath + fileName : currentPath + "/" + fileName;

    let content = "";

    const fileUrl = fullPath;
	console.log("File URL for Preview: " + fileUrl);

    if (["png", "jpg", "jpeg", "gif", "bmp", "webp"].includes(ext)) {
        content = `<img src="${fileUrl}" alt="Image Preview" style="max-width: 100%; max-height: 80vh;" />`;
    } else if (["mp4", "webm", "ogg"].includes(ext)) {
        content = `<video controls style="max-width: 100%; max-height: 80vh;"><source src="${fileUrl}" type="video/${ext}">Your browser does not support the video tag.</video>`;
    } else if (["mp3", "wav", "ogg"].includes(ext)) {
        content = `<audio controls><source src="${fileUrl}" type="audio/${ext}">Your browser does not support the audio element.</audio>`;
    } else if (["pdf"].includes(ext)) {
        content = `<iframe src="${fileUrl}" style="width:100%; height:80vh;" frameborder="0"></iframe>`;
    } else if (["txt", "md", "json", "log", "js", "py", "html", "css"].includes(ext)) {
        // Load text content via fetch
        fetch(fileUrl)
            .then(response => response.text())
            .then(text => {
                const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                document.getElementById("previewContent").innerHTML = `<pre style="white-space: pre-wrap; max-height: 80vh; overflow-y: auto;">${escaped}</pre>`;
                document.getElementById("previewModal").style.display = "flex";
            })
            .catch(err => {
                alert("Failed to load file for preview.");
                console.error(err);
            });
        return;
    } else {
        content = `<p>Preview not supported for this file type.</p><a href="${fileUrl}" download>Download File</a>`;
    }

    document.getElementById("previewContent").innerHTML = content;
    document.getElementById("previewModal").style.display = "flex";
}

function closeModal() {
    const modal = document.getElementById('previewModal');
    const video = modal.querySelector('video');
    if (video) {
        video.pause();
        // video.currentTime = 0;
    }
    modal.style.display = 'none';
}
