# NAS Server on Ubuntu

Network Attached Storage on a Python server running in Ubuntu

## Functionalities

- Launcher GUI
- Password locked profiles
- Public profile for public link sharing
- Profile add / remove
- File access
- Search in current directory
- Subfolder access with function to go back to previous directory
- Create new folder, upload file and folder in current directory
- Progress bar on upload file
- Drag and Drop upload
- Link Sharing
- Public folder sharing as separate HTML page with gallery
- Download and delete file
- Download folder as zip and delete folder
- Bulk download using checkbox
- Rename file and folder
- Delete file and folder
- Bulk delete using checkbox
- View file details
- Preview Files with navigation and thumbnail preview for images and videos
- Gallery functionality for current folder
- Range request for video display to enable seek forward or jump to a timeline
- Logout feature that kills server process and redirects to login page

## If low on storage
- ssh user@ip
- Check /nas/storage/temp/zips. There may be temporary zip files present due to failed folder downloads
- In such case, run command sudo rm /nas/storage/temp/zips/*zip to remove temporary zip files

## Steps

- Initial setup on Ubuntu
  - Create a directory /nas/storage/code on Ubuntu
  - Create a directory /nas/storage/files on Ubuntu
  - This will serve as root directory for the NAS
  - Give permission to current user to read and write from it with command sudo chmod 0755 /nas/storage/code and /nas/storage/files
  - Transfer app.py, server.py, template.html, style.css and main.js to /nas/storage/code

- To access server on Windows through login page
  - Run python3 /nas/storage/code/app.py on Ubuntu
  - Open http://<ubuntu_ip>:5000 in browser on any device on same Wi-Fi to open Launcher
  - Enter credentials and wait for http://<ubuntu_ip>:8888 to open
  - Now the app is running on server and can be accessed from any device on same Wi-Fi at http://<ubuntu_ip>:8888
  - To logout and kill process, click on Logout button. It will redirect to login page and kill process on 8888
  - app.py should always be running in a terminal window in Ubuntu
  - To get Ubuntu IP, in terminal type ip addr and search for wlan0. There will be an inet with IP in the form 192.168.x.x

- To access server without login
  - Run python3 /nas/storage/code/server.py
  - Open http://<ubuntu_ip>:8888 in browser on any device on same Wi-Fi to access the server without entering credentials
  - server.py should be running in a terminal window in Ubuntu always
  - To kill process in Ubuntu
    - sudo netstat | -tulnp grep 8888 to get process ID
    - sudo kill -9 <process_id>
  - To get Ubuntu IP, in terminal type ip addr and search for wlan0. There will be an inet with IP in the form 192.168.x.x

![Ubuntu_IP](assets/Ubuntu_IP.png)

## NAS Launcher

![Nas_Launcher](assets/Nas_Launcher.png)

## Profile Selection

![Profile_Selection](assets/Profile_Selection.png)

## Profile Login

![Profile_Login](assets/Profile_Login.png)

## Profile Addition

![Profile_Add](assets/Profile_Add.png)

## Profile Removal

![Profile_Remove](assets/Profile_Remove.png)
![Profile_Remove_Confirmation](assets/Profile_Remove_Confirmation.png)

## Root Directory

![Root_Directory](assets/Root_Directory.png)

## Bulk Features

![Bulk_Features](assets/Bulk_Features.png)

## Subfolder with Parent Traversal

![Subfolder_with_Parent_Traversal](assets/Subfolder_with_Parent_Traversal.png)

## More options in Current Directory

![Current_Directory_More_Options](assets/Current_Directory_More_Options.png)

## Upload Progress Bar

![Upload_Progress_Bar](assets/Upload_Progress_Bar.png)

## Drag and Drop Upload

![Drag_and_Drop_Upload](assets/Drag_and_Drop_Upload.png)

## Link Sharing

![Link_Sharing](assets/Link_Sharing.png)

## Public Folder Sharing

![Public_Folder_Sharing](assets/Public_Folder_Sharing.png)

## Public Folder Gallery

![Public_Folder_Gallery](assets/Public_Folder_Gallery.png)

## More options on a File

![File_More_Options](assets/File_More_Options.png)

## File Details

![File_Details](assets/File_Details.png)

## More options on a Folder

![Folder_More_Options](assets/Folder_More_Options.png)

## Folder download as zip

![Folder_Download_Zip](assets/Folder_Download_Zip.png)

## Rename Functionality

![Rename_Functionality](assets/Rename_Functionality.png)

## Delete Functionality

![Delete_Functionality](assets/Delete_Functionality.png)

## Gallery Functionality. Image and Video can be opened in new tab by clicking in gallery

![Gallery_Functionality](assets/Gallery_Functionality.png)

## Preview Functionality (Video) with Navigation and Preview

![Preview_Functionality_Video](assets/Preview_Functionality_Video.png)

## Preview Functionality (Image) with Navigation and Preview. Image can be opened in new tab by clicking in preview

![Preview_Functionality_Image](assets/Preview_Functionality_Image.png)

## Preview Functionality (Text)

![Preview_Functionality_Text](assets/Preview_Functionality_Text.png)

## Preview Functionality (PDF)

![Preview_Functionality_Pdf](assets/Preview_Functionality_Pdf.png)

## Logout functionality

![Logout_Functionality](assets/Logout_Functionality.png)

## Android file access

![Android_Access](assets/Android_Access.jpg)

## Android file viewing

![Android_File_Viewing](assets/Android_File_Viewing.jpg)

