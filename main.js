const currentPath = window.location.pathname;
let currentXHR = null;
let wasCancelled = false;
let folderUploadXHRs = [];
let folderUploadCancelled = false;
let mediaFiles = [];
let currentMediaIndex = -1;

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
        setTimeout(() => {
            window.location.reload();
        }, 1000);
		
//		const input = document.getElementById('fileInput');
//        const file = input.files[0];
//        const filename = file ? file.name : null;
//
//        if (filename) {
//            setTimeout(() => {
//                deleteFile(filename, true);
//                window.location.reload();
//            }, 1000);
//        } else {
//            window.location.reload();
//        }
    }

    // Cancel folder upload if active
    else if (folderUploadXHRs.length > 0) {
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
        if (!input.files.length) return;

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
    if (mediaFiles.length === 0) return;

    currentMediaIndex = (currentMediaIndex - 1 + mediaFiles.length) % mediaFiles.length;
    previewMediaAtIndex(currentMediaIndex);
    updateCarousel();
}

function showNextMedia() {
    if (mediaFiles.length === 0) return;

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
            // Optional: add extra styling for focus
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
    if (index < 0 || index >= mediaFiles.length) return;

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
    if (!fileName) return;

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