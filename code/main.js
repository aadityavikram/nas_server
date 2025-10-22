const currentPath = window.location.pathname;
let currentXHR = null;
let wasCancelled = false;
let folderUploadXHRs = [];
let folderUploadCancelled = false;
let mediaFiles = [];
let currentMediaIndex = -1;
let allFiles = [];
let currentFileIndex = 0;
let currentZipJobId = null;
let zipProgressIntervalId = null;
const ip = window.location.hostname;
const port = 5000;

function triggerFileUpload() {
    const input = document.getElementById('fileInput');
    input.click();

    input.onchange = () => {
        if (input.files.length === 0) {
            return;
        }

        allFiles = Array.from(input.files);
        currentFileIndex = 0;
        wasCancelled = false;
        uploadFilesSequentially();
    };
}

function uploadFilesSequentially() {
    if (wasCancelled) {
        return;
    }

    if (currentFileIndex >= allFiles.length) {
        // All files done, hide the progress UI
        setTimeout(() => {
            document.getElementById("progressWrapper").style.display = "none";
            document.getElementById("cancelUploadBtn").style.display = "none";
            document.getElementById("progressBar").style.width = "0%";
            document.getElementById("progressText").textContent = "";
            document.getElementById("uploadSpeedText").textContent = "";
            document.getElementById("uploadFilename").textContent = "";
            document.getElementById("uploadedFilesContent").innerHTML = "";
            localStorage.setItem("showUploadModal", "true");
            window.location.reload();
        }, 1000);
        return;
    }

    const file = allFiles[currentFileIndex];

    // Show modal if it's the first file being uploaded
    if (currentFileIndex === 0) {
        openUploadModal();
    }

    document.getElementById("uploadFilename").textContent = `Uploading: ${file.name}`;

    const formData = new FormData();
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    currentXHR = xhr;

    uploadStartTime = Date.now();

    xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
            const percent = (e.loaded / e.total) * 100;
            document.getElementById("progressBar").style.width = percent + "%";
            document.getElementById("progressText").textContent = Math.round(percent) + "%";

            // Calculate speed
            const now = Date.now();
            const elapsedSeconds = (now - uploadStartTime) / 1000;
            const speedBps = e.loaded / elapsedSeconds;
            const speedText = formatSpeed(speedBps);

            document.getElementById("uploadSpeedText").textContent = speedText;
        }
    });

    xhr.onloadstart = () => {
        document.getElementById("progressWrapper").style.display = "flex";
        document.getElementById("cancelUploadBtn").style.display = "inline";
        document.getElementById("progressBar").style.width = "0%";
        document.getElementById("uploadSpeedText").textContent = "";
    };

    xhr.onloadend = () => {
        currentXHR = null;
        if (wasCancelled) {
            return;
        }
    };

    xhr.onreadystatechange = () => {
        if (xhr.readyState === 4) {
            if (wasCancelled) {
                console.log("Upload cancelled, skipping next file.");
                return;
            }

            if (xhr.status >= 200 && xhr.status < 300) {
                appendUploadedFileToList(file.name, `${encodeURIComponent(file.name)}`);

                ++currentFileIndex;
                uploadFilesSequentially(); // Only proceed if not cancelled
            } else {
                console.log("XHR Status: " + xhr.status);
                alert("Upload failed");
            }
        }
    };

    xhr.open("POST", `/upload?path=${encodeURIComponent(currentPath)}`, true);
    xhr.send(formData);
}

document.addEventListener("DOMContentLoaded", () => {
    if (localStorage.getItem("showUploadModal") === "true") {
        openUploadModal();

        // Rebuild uploaded files list
        const uploadedFiles = JSON.parse(localStorage.getItem("uploadedFiles") || "[]");
        const container = document.getElementById("uploadedFilesContent");

        uploadedFiles.forEach(({ fileName, downloadUrl }) => {
            const fileBox = document.createElement("div");
            fileBox.className = "upload-file-box";

            fileBox.innerHTML = `
                <a href="${downloadUrl}" target="_blank" title="${fileName}">
                    <div class="file-thumb"></div>
                    <div class="file-name">${fileName}</div>
                </a>
            `;

            container.appendChild(fileBox);
        });

        // Optional: Clear the modal flag but keep file list
        localStorage.removeItem("showUploadModal");

        // Optional: Clear file list after display (or do it on modal close)
         localStorage.removeItem("uploadedFiles");
    }
});

function appendUploadedFileToList(fileName, downloadUrl = "#") {
    const container = document.getElementById("uploadedFilesContent");
    if (!container) {
        return;
    }

    const fileBox = document.createElement("div");
    fileBox.className = "upload-file-box";

    fileBox.innerHTML = `
        <a href="${downloadUrl}" target="_blank" title="${fileName}">
            <div class="file-thumb"></div>
            <div class="file-name">${fileName}</div>
        </a>
    `;

    container.appendChild(fileBox);

    const uploadedFiles = JSON.parse(localStorage.getItem("uploadedFiles") || "[]");
    uploadedFiles.push({ fileName, downloadUrl });
    localStorage.setItem("uploadedFiles", JSON.stringify(uploadedFiles));
}

// Helper to convert bytes per second to readable string
function formatSpeed(bytesPerSecond) {
    const kb = 1024;
    const mb = kb * 1024;

    if (bytesPerSecond >= mb) {
        return (bytesPerSecond / mb).toFixed(2) + " MB/s";
    } else if (bytesPerSecond >= kb) {
        return (bytesPerSecond / kb).toFixed(2) + " KB/s";
    } else {
        return bytesPerSecond.toFixed(2) + " B/s";
    }
}

document.getElementById("cancelUploadBtn").addEventListener("click", () => {
    console.log("Cancel upload triggered")
    wasCancelled = true;

    if (currentXHR) {
        currentXHR.abort();
        currentXHR = null;
    }

    localStorage.removeItem("uploadedFiles");
    localStorage.removeItem("showUploadModal");

    // Hide UI
    document.getElementById("progressWrapper").style.display = "none";
    document.getElementById("progressBar").style.width = "0%";
    document.getElementById("progressText").textContent = "0%";
    document.getElementById("cancelUploadBtn").style.display = "none";

    alert("Upload cancelled.");

    const filename = allFiles[currentFileIndex].name;
    allFiles = []; // Clear upload queue
    currentFileIndex = 0;
    console.log("Last uploaded file: " + filename);
    if (filename) {
        console.log("Will attempt to delete: " + filename);
        setTimeout(() => {
            console.log("Deleting file after cancel: " + filename);
            deleteFile(filename, true);
            window.location.reload();
        }, 1000);
    }

    // Cancel folder upload if active
    if (typeof folderUploadXHRs !== 'undefined' && folderUploadXHRs.length > 0) {
        folderUploadCancelled = true;
        folderUploadXHRs.forEach(xhr => {
            try {
                xhr.abort();
            } catch (e) {
                console.error("Error aborting XHR", e);
            }
        });
        folderUploadXHRs = [];

        document.getElementById("progressWrapper").style.display = "none";
        document.getElementById("progressBar").style.width = "0%";
        document.getElementById("progressText").textContent = "0%";
        document.getElementById("cancelUploadBtn").style.display = "none";

        alert("Folder upload cancelled.");
        setTimeout(() => {
            window.location.reload();
        }, 1000);
    }
});

function triggerFolderUpload() {
    const input = document.createElement('input');
    input.type = 'file';
    input.webkitdirectory = true;  // Enable folder selection in Chrome/Edge
    input.directory = true;        // Allow only folder select
    input.multiple = true;         // Allow multiple files inside folders

    input.onchange = () => {
        if (!input.files.length) {
            return;
        }

        const files = Array.from(input.files);
        const currentPath = window.location.pathname;

        const totalSize = files.reduce((acc, f) => acc + f.size, 0);
        let uploadedSize = 0;
        folderUploadXHRs = [];
        folderUploadCancelled = false;

        // Show progress bar UI
        document.getElementById("progressWrapper").style.display = "flex";
        document.getElementById("cancelUploadBtn").style.display = "inline";
        document.getElementById("progressBar").style.width = "0%";
        document.getElementById("progressText").textContent = "0%";

        const uploadFile = (file, relativePath) => {
            return new Promise((resolve, reject) => {
                if (folderUploadCancelled) {
                    reject("Upload cancelled.");
                    return;
                }

                const formData = new FormData();
                formData.append("file", file);

                const uploadPath = `${currentPath}${relativePath.substring(0, relativePath.lastIndexOf("/"))}`;
                const xhr = new XMLHttpRequest();

                folderUploadXHRs.push(xhr); // Keep track for cancel

                xhr.open("POST", `/upload?path=${encodeURIComponent(uploadPath)}`, true);

                xhr.upload.onprogress = (e) => {
                    if (e.lengthComputable) {
                        if (!xhr._lastLoaded) xhr._lastLoaded = 0;
                        const delta = e.loaded - xhr._lastLoaded;
                        xhr._lastLoaded = e.loaded;
                        uploadedSize += delta;
                        const percent = (uploadedSize / totalSize) * 100;
                        document.getElementById("progressBar").style.width = percent + "%";
                        document.getElementById("progressText").textContent = Math.round(percent) + "%";
                    }
                };

                xhr.onreadystatechange = () => {
                    if (xhr.readyState === 4) {
                        if (folderUploadCancelled) {
                            reject("Upload cancelled.");
                        } else if (xhr.status >= 200 && xhr.status < 300) {
                            resolve();
                        } else {
                            reject(`Upload failed for ${file.name}: ${xhr.statusText}`);
                        }
                    }
                };

                xhr.send(formData);
            });
        };

        (async () => {
            try {
                for (const file of files) {
                    const relativePath = file.webkitRelativePath;
                    if (relativePath) {
                        await uploadFile(file, relativePath);
                    }
                    if (folderUploadCancelled) break;
                }

                if (!folderUploadCancelled) {
                    setTimeout(() => {
                        document.getElementById("progressWrapper").style.display = "none";
                        document.getElementById("cancelUploadBtn").style.display = "none";
                        document.getElementById("progressBar").style.width = "0%";
                        document.getElementById("progressText").textContent = "0%";
                        window.location.reload();
                    }, 1000);
                }
            } catch (err) {
                if (folderUploadCancelled) {
                    alert("Upload cancelled.");
                } else {
                    alert(err);
                }
                document.getElementById("progressWrapper").style.display = "none";
                document.getElementById("cancelUploadBtn").style.display = "none";
                document.getElementById("progressBar").style.width = "0%";
                document.getElementById("progressText").textContent = "0%";
            }
        })();
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
    document.querySelectorAll('.dropdown-content-main, .dropdown-content, .dropdown-content-bulk').forEach(menu => {
        if (menu !== dropdown) {
            menu.style.display = 'none';
        }
    });

    // Toggle this one
    dropdown.style.display = dropdown.style.display === 'block' ? 'none' : 'block';
}

// Toggle display of bulk dropdown based on checkbox selection
function toggleBulkDeleteButton() {
    const checked = document.querySelectorAll(".fileCheckbox:checked").length > 0;
    const bulkDropdown = document.getElementById("bulkActionsDropdown");
    bulkDropdown.style.display = checked ? "inline-block" : "none";
}

// Toggle dropdown visibility on click
function toggleDropdownBulk(event) {
    event.stopPropagation();

    const parent = event.currentTarget.closest('.dropdown-bulk');
    const dropdown = parent.querySelector('.dropdown-content-bulk');

    // Close all other dropdowns
    document.querySelectorAll('.dropdown-content-main, .dropdown-content, .dropdown-content-bulk').forEach(menu => {
        if (menu !== dropdown) {
            menu.style.display = 'none';
        }
    });

    // Toggle this dropdown
    dropdown.style.display = dropdown.style.display === 'block' ? 'none' : 'block';
}

// Close all dropdowns when clicking outside
document.addEventListener("click", function () {
    document.querySelectorAll('.dropdown-content-main, .dropdown-content, .dropdown-content-bulk').forEach(menu => {
        menu.style.display = 'none';
    });
});

// Toggle select all
document.getElementById("selectAll").addEventListener("change", function () {
    const checkboxes = document.querySelectorAll(".fileCheckbox");
    checkboxes.forEach(cb => cb.checked = this.checked);
    toggleBulkDeleteButton();
});

// Attach change listener to individual checkboxes
document.addEventListener("change", function (e) {
    if (e.target.classList.contains("fileCheckbox")) {
        toggleBulkDeleteButton();
    }
});

// Handle bulk delete
document.getElementById("bulkDelete-btn").addEventListener("click", function () {
    const selected = Array.from(document.querySelectorAll(".fileCheckbox:checked"))
                          .map(cb => cb.getAttribute("data-name"));

    if (selected.length === 0) {
        return;
    }

    console.log("Selected: " + selected);

    if (!confirm(`Are you sure you want to delete ${selected.length} item(s)?`)) {
        return;
    }

    // Send individual delete requests
    selected.map(name => {
        deleteFile(name, true);
    });
    alert("Selected items deleted.");
});

function deleteFile(name, uploadCancelled = false) {
    const baseName = name.replace(/\/$/, '');

	if (!uploadCancelled) {
		let confirmMsg = `Are you sure you want to delete "${baseName}"?`;
		if (!confirm(confirmMsg)) {
		    return;
		}
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
		window.location.reload();
	});
}

function createFolder() {
    const folderName = prompt("Enter new folder name:");

    if (!folderName) {
        return;
    }
	
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

    const imageExtensions = ["png", "jpg", "jpeg", "gif", "bmp", "webp"];
    const videoExtensions = ["mp4", "webm", "ogg"];

    // Show navigation buttons only if image or video
    if (imageExtensions.includes(ext) || videoExtensions.includes(ext)) {
        document.getElementById("navButtons").style.display = "block";
    } else {
        document.getElementById("navButtons").style.display = "none";
    }

    const fullPath = currentPath.endsWith("/") ? currentPath + fileName : currentPath + "/" + fileName;

    document.getElementById("previewFileName").textContent = fileName;

	// Get all image links on the page
    const links = Array.from(document.querySelectorAll('.file-table td a'));
    const hrefs = links
        .map(link => link.getAttribute('href'))
        .filter(href => href && /\.(png|jpe?g|gif|bmp|webp|mp4|webm|ogg)$/i.test(href))
        .map(href => decodeURIComponent(href));

    // Remove duplicates using Set
    mediaFiles = Array.from(new Set(hrefs));

    // Find index of current media
    currentMediaIndex = mediaFiles.findIndex(f => {
        const decodedName = decodeURIComponent(f).split('/').pop().toLowerCase();
        return decodedName === fileName.toLowerCase();
    });

    if (["png", "jpg", "jpeg", "gif", "bmp", "webp"].includes(ext)) {
        document.getElementById("previewContent").innerHTML = `<img src="${fullPath}" alt="Image Preview" style="max-width: 100%; max-height: 80vh;" />`;
        updateCarousel();
        document.getElementById("previewModal").style.display = "flex";
    } else if (["mp4", "webm", "ogg"].includes(ext)) {
        document.getElementById("previewContent").innerHTML = `
            <video controls autoplay style="max-width: 100%; max-height: 80vh;">
                <source src="${fullPath}" type="video/${ext}">
                Your browser does not support the video tag.
            </video>
        `;
        updateCarousel();
        document.getElementById("previewModal").style.display = "flex";
    } else if (["mp3", "wav", "ogg"].includes(ext)) {
        // existing audio preview code...
        // hide carousel for audio files
        document.getElementById("mediaCarousel").style.display = "none";
        // your existing code for audio below ...
        const content = `<audio controls><source src="${fullPath}" type="audio/${ext}">Your browser does not support the audio element.</audio>`;
        document.getElementById("previewContent").innerHTML = content;
        document.getElementById("previewModal").style.display = "flex";
    } else if (["pdf"].includes(ext)) {
        document.getElementById("mediaCarousel").style.display = "none";
        const content = `<iframe src="${fullPath}" style="width:100%; height:300vh;" frameborder="0"></iframe>`;
        document.getElementById("previewContent").innerHTML = content;
        document.getElementById("previewModal").style.display = "flex";
    } else if (["txt", "md", "json", "log", "js", "py", "html", "css"].includes(ext)) {
        document.getElementById("mediaCarousel").style.display = "none";
        fetch(fullPath)
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
    } else {
        document.getElementById("mediaCarousel").style.display = "none";
        const content = `<p>Preview not supported for this file type.</p><a href="${fullPath}" download>Download File</a>`;
        document.getElementById("previewContent").innerHTML = content;
        document.getElementById("previewModal").style.display = "flex";
    }
}

// Update showPrevMedia and showNextMedia to also update carousel selection
function showPrevMedia() {
    if (mediaFiles.length === 0) {
        return;
    }

    currentMediaIndex = (currentMediaIndex - 1 + mediaFiles.length) % mediaFiles.length;
    previewMediaAtIndex(currentMediaIndex);
    updateCarousel();
}

function showNextMedia() {
    if (mediaFiles.length === 0) {
        return;
    }

    currentMediaIndex = (currentMediaIndex + 1) % mediaFiles.length;
    previewMediaAtIndex(currentMediaIndex);
    updateCarousel();
}

document.addEventListener('keydown', (e) => {
    const modal = document.getElementById('previewModal');
    if (modal.style.display === 'flex') {
        if (e.key === 'ArrowRight') {
            showNextMedia();
        } else if (e.key === 'ArrowLeft') {
            showPrevMedia();
        } else if (e.key === 'Escape') {
            closeModal();
        }
    }
});

function updateCarousel() {
    const carousel = document.getElementById("mediaCarousel");
    carousel.innerHTML = "";

    if (mediaFiles.length < 2) {
        carousel.style.display = "none";
        return;
    }

    carousel.style.display = "block";

    const total = mediaFiles.length;

    // Calculate window start and end indices
    // Want currentMediaIndex -1 (before), currentMediaIndex (current), +1 and +2 after
    // Clamp indices to array bounds
    let start = currentMediaIndex - 1;
    let end = currentMediaIndex + 2;

    // Adjust if start < 0
    if (start < 0) {
        end += -start; // shift right side window
        start = 0;
    }
    // Adjust if end >= total
    if (end >= total) {
        let diff = end - (total - 1);
        start = Math.max(0, start - diff);
        end = total - 1;
    }

    for (let index = start; index <= end; index++) {
        const mediaPath = mediaFiles[index];
        const fileName = mediaPath.split('/').pop();
        const ext = fileName.split('.').pop().toLowerCase();

        let thumb;

        if (["png", "jpg", "jpeg", "gif", "bmp", "webp"].includes(ext)) {
            thumb = document.createElement("img");
            thumb.src = mediaPath;
            thumb.alt = fileName;
        } else if (["mp4", "webm", "ogg"].includes(ext)) {
            thumb = document.createElement("video");
            thumb.src = mediaPath;
            thumb.muted = true;
            thumb.loop = true;
            thumb.playsInline = true;
            thumb.style.height = "80px";
            thumb.style.width = "auto";
            thumb.autoplay = true;
        } else {
            // Skip unsupported thumbnails
            continue;
        }

        thumb.classList.add("carousel-thumb");
        if (index === currentMediaIndex) {
            thumb.classList.add("selected");
        }

        thumb.addEventListener("click", () => {
            currentMediaIndex = index;
            previewMediaAtIndex(currentMediaIndex);
            updateCarousel();
        });

        carousel.appendChild(thumb);
    }
}

function previewMediaAtIndex(index) {
    if (index < 0 || index >= mediaFiles.length) {
        return;
    }

    const mediaPath = mediaFiles[index];
    const fileName = mediaPath.split('/').pop();
    const ext = fileName.split('.').pop().toLowerCase();

    document.getElementById("previewFileName").textContent = fileName;

    let content = "";

    if (["png", "jpg", "jpeg", "gif", "bmp", "webp"].includes(ext)) {
        content = `<img src="${mediaPath}" alt="${fileName}" style="max-width: 100%; max-height: 80vh;" />`;
    } else if (["mp4", "webm", "ogg"].includes(ext)) {
        content = `
            <video controls autoplay style="max-width: 100%; max-height: 80vh;">
                <source src="${mediaPath}" type="video/${ext}">
                Your browser does not support the video tag.
            </video>
        `;
    } else {
        content = `<p>Unsupported media type.</p>`;
    }

    document.getElementById("previewContent").innerHTML = content;
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

document.getElementById('previewContent').addEventListener('click', (e) => {
    const fileName = document.getElementById('previewFileName').textContent;
    if (!fileName) {
        return;
    }

    const imageExtensions = ["png", "jpg", "jpeg", "gif", "bmp", "webp"];
    const ext = fileName.split('.').pop().toLowerCase();

    if (!imageExtensions.includes(ext)) {
        // Only open for images
        return;
    }

    // Optional: ignore clicks on interactive elements inside previewContent (like <img> itself)
    if (e.target.tagName.toLowerCase() !== 'img') {
        return;
    }

    let fullPath = currentPath;
    if (!fullPath.endsWith('/')) {
        fullPath += '/';
    }
    fullPath += fileName;

    window.open(fullPath, '_blank');
});

function showDetails(name) {
    let fullPath = currentPath;
    if (!fullPath.endsWith("/")) fullPath += "/";
    fullPath += name;

    fetch(`/details?path=${fullPath}`)
        .then(res => {
            if (!res.ok) throw new Error("Failed to fetch details");
            return res.json();
        })
        .then(data => {
            document.getElementById("detailName").textContent = data.name;
            document.getElementById("detailType").textContent = data.type;
            document.getElementById("detailSize").textContent = data.size;
            document.getElementById("detailCreated").textContent = data.created;
            document.getElementById("detailModified").textContent = data.modified;
            document.getElementById("detailPath").textContent = data.path;
            document.getElementById("detailModal").style.display = "flex";
        })
        .catch(err => {
            alert(err.message);
            console.error(err);
        });
}

function closeDetailModal() {
    document.getElementById("detailModal").style.display = "none";
}

document.getElementById("detailModal").addEventListener("click", function(event) {
    if (event.target === this) {
        closeDetailModal();
    }
});

function openGallery() {
    const mediaExtensions = /\.(png|jpe?g|gif|bmp|webp|mp4|webm|ogg)$/i;
    const links = Array.from(document.querySelectorAll('.file-table td a'));
    const mediaLinksList = links
        .map(link => link.getAttribute('href'))
        .filter(href => href && mediaExtensions.test(href))
        .map(href => decodeURIComponent(href));

    // Remove duplicates using Set
    mediaLinks = Array.from(new Set(mediaLinksList));

    // Dynamically set number of columns
    const modalContent = document.querySelector(".gallery-modal-content");
    const columnCount = Math.min(mediaLinks.length, 4);
    modalContent.style.setProperty('--columns', columnCount);
    const thumbMaxSize = columnCount < 4 ? 480 : 240;
    galleryModal.style.setProperty('--thumb-size', `${thumbMaxSize}px`);

    const gallery = document.getElementById("galleryContent");
    gallery.innerHTML = "";

    if (mediaLinks.length === 0) {
        gallery.innerHTML = "<p>No images or videos found in this folder.</p>";
        return;
    }

    mediaLinks.forEach(href => {
        const fileName = href.split("/").pop();
        const ext = fileName.split(".").pop().toLowerCase();
        let thumb;

        if (["png", "jpg", "jpeg", "gif", "bmp", "webp"].includes(ext)) {
            thumb = document.createElement("img");
            thumb.src = href;
        } else if (["mp4", "webm", "ogg"].includes(ext)) {
            thumb = document.createElement("video");
            thumb.src = href;
            thumb.muted = true;
            thumb.loop = true;
            thumb.playsInline = true;
            thumb.autoplay = true;
        }

        thumb.title = fileName;
        thumb.addEventListener("click", () => {
            console.log("Href: " + href);
            window.open(href, '_blank');
        });

        gallery.appendChild(thumb);
    });

    document.getElementById("galleryModal").style.display = "flex";
}

function closeGallery() {
    document.getElementById("galleryModal").style.display = "none";
}

document.getElementById("galleryModal").addEventListener("click", function(event) {
    if (event.target === this) {
        closeGallery();
    }
});

function showShareLink(name) {
    let fullPath = currentPath;
    if (!fullPath.endsWith("/")) {
        fullPath += "/";
    }
    fullPath += encodeURIComponent(name);
    fullPath = fullPath.substring(fullPath.indexOf("/") + 1);

    const shareURL = `${window.location.origin}/${fullPath}`;

    document.getElementById("shareFileName").textContent = name;
    document.getElementById("shareLinkInput").value = shareURL;
    document.getElementById("shareLinkModal").style.display = "flex";
}

function closeShareModal() {
    document.getElementById("shareLinkModal").style.display = "none";
}

function copyShareLink() {
    const input = document.getElementById("shareLinkInput");
    input.select();
    input.setSelectionRange(0, 99999); // for mobile
    document.execCommand("copy");
//    alert("Link copied to clipboard!");
}

document.getElementById("shareLinkModal").addEventListener("click", function(event) {
    if (event.target === this) {
        closeShareModal();
    }
});

function openUploadModal() {
    const modal = document.getElementById("uploadModal");
    modal.style.display = "block";
}

function closeUploadModal() {
    const modal = document.getElementById("uploadModal");
    modal.style.display = "none";
}

document.getElementById("logout-btn").addEventListener("click", async () => {
    try {
        const confirmLogout = confirm("Are you sure you want to logout?");
        if (!confirmLogout) {
            return;
        }

        // Call backend logout route
        fetch("/logout", { method: "POST" });
        window.location.href = `http://${ip}:${port}`;
    } catch (err) {
        console.error("Logout error:", err);
        alert("Logout failed: " + err.message);
    }
});

function renameItem(name) {
    const baseName = name.replace(/\/$/, ''); // strip trailing slash
    const newName = prompt(`Rename "${baseName}" to:`, baseName);

    if (!newName || newName === baseName) {
        return;
    }

    let fullPath = currentPath;
    if (!fullPath.endsWith("/")) fullPath += "/";
    const oldPath = fullPath + name;
    const newPath = fullPath + newName;

    fetch(`/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_path: oldPath, new_path: newPath })
    })
    .then(res => {
        if (res.ok) {
            alert("Renamed successfully.");
            window.location.reload();
        } else {
            res.text().then(text => alert(`Rename failed: ${text}`));
        }
    })
    .catch(err => {
        console.error("Rename error:", err);
        alert("Error renaming: " + err.message);
    });
}

// Start ZIP download with progress bar updates
function startZipDownload(folderPath) {
    const progressWrapper = document.getElementById('zipProgressWrapper');
    const progressBar = document.getElementById('zipProgressBar');
    const progressText = document.getElementById('zipProgressText');
    const filenameLabel = document.getElementById('zipDownloadFilename');
    const cancelZipBtn = document.getElementById('cancelZipBtn');

    progressWrapper.style.display = 'block';
    cancelZipBtn.style.display = 'inline-block';
    progressBar.style.width = '0%';
    progressText.textContent = '0%';

    // Show folder name in progress bar
    const folderName = folderPath.split('/').filter(Boolean).pop() || folderPath;
    filenameLabel.textContent = `Zipping: ${decodeURIComponent(folderName)}`;

    // Step 1: Start zip creation job
    fetch(`/download-zip?folder=${encodeURIComponent(folderPath)}`)
        .then(response => response.json())
        .then(data => {
            const jobId = data.job_id;
            currentZipJobId = jobId;

            if (zipProgressIntervalId) {
                clearInterval(zipProgressIntervalId);
            }

            // Step 2: Poll progress every 500ms
            zipProgressIntervalId = setInterval(() => {
                fetch(`/zip-progress?job_id=${jobId}`)
                    .then(res => res.json())
                    .then(progressData => {
                        const prog = progressData.progress;
                        if (prog < 0) {
                            clearInterval(zipProgressIntervalId);
                            zipProgressIntervalId = null;
                            alert("Error creating zip file.");
                            progressWrapper.style.display = 'none';
                            cancelZipBtn.style.display = 'none';
                            currentZipJobId = null;
                            return;
                        }
                        progressBar.style.width = prog + '%';
                        progressText.textContent = prog + '%';

                        if (prog >= 100) {
                            clearInterval(zipProgressIntervalId);
                            zipProgressIntervalId = null;
                            // Step 3: Trigger file download
                            window.location.href = `/download-zip-file?job_id=${jobId}`;
                            progressWrapper.style.display = 'none';
                            cancelZipBtn.style.display = 'none';
                            currentZipJobId = null;
                        }
                    })
                    .catch(() => {
                        clearInterval(zipProgressIntervalId);
                        zipProgressIntervalId = null;
                        alert("Error fetching zip progress.");
                        progressWrapper.style.display = 'none';
                        cancelZipBtn.style.display = 'none';
                        currentZipJobId = null;
                    });
            }, 500);
        })
        .catch(() => {
            alert("Failed to start zip download.");
            progressWrapper.style.display = 'none';
            cancelZipBtn.style.display = 'none';
        });
}

document.getElementById("cancelZipBtn").addEventListener("click", () => {
  if (!currentZipJobId) {
    return;
  }

  fetch(`/cancel-zip?job_id=${currentZipJobId}`, { method: "POST" })
    .then(res => res.text())
    .then(msg => {
      console.log("Canceled:", msg);
      // Stop progress polling
      if (zipProgressIntervalId) {
          clearInterval(zipProgressIntervalId);
          zipProgressIntervalId = null;
      }

      // Reset job ID so no download triggers
      currentZipJobId = null;

      // Hide UI
      document.getElementById("zipProgressWrapper").style.display = "none";
      document.getElementById("cancelZipBtn").style.display = "none";
    })
    .catch(err => {
      console.error("Cancel error:", err);
    });
});

const dropZoneModal = document.getElementById("dropZone");
const folderWarning = document.querySelector(".folder-warning");

let dragCounter = 0;

window.addEventListener("dragenter", (e) => {
    dragCounter++;
    if (e.dataTransfer.types.includes("Files")) {
        dropZoneModal.style.display = "flex";

        const hasFolder = Array.from(e.dataTransfer.items).some(item => {
            const entry = item.webkitGetAsEntry?.();
            return entry && entry.isDirectory;
        });

        if (hasFolder) {
            dropZoneModal.classList.add("folder-drag");
        } else {
            dropZoneModal.classList.remove("folder-drag");
        }
    }
});

window.addEventListener("dragleave", (e) => {
    dragCounter--;
    if (dragCounter === 0) {
        dropZoneModal.style.display = "none";
        dropZoneModal.classList.remove("folder-drag");
    }
});

window.addEventListener("dragover", (e) => {
    e.preventDefault();
});

window.addEventListener("drop", (e) => {
    e.preventDefault();
    dragCounter = 0;
    dropZoneModal.style.display = "none";
    dropZoneModal.classList.remove("folder-drag");

    const items = Array.from(e.dataTransfer.items);

    const hasFolder = items.some(item => {
        const entry = item.webkitGetAsEntry?.();
        return entry && entry.isDirectory;
    });

    if (hasFolder) {
        // Do not proceed with upload
        alert("Folder upload via drag-and-drop is not supported.");
        return;
    }

    const droppedFiles = Array.from(e.dataTransfer.files);
    if (!droppedFiles.length) return;

    // Use existing upload flow
    allFiles = droppedFiles;
    currentFileIndex = 0;
    wasCancelled = false;
    uploadFilesSequentially();
});