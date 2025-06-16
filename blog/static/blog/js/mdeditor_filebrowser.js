/*
 * Custom JavaScript for integrating batch file upload with Mdeditor in Django Admin.
 *
 * This script is designed to be included in the change_form.html template
 * for models that use Mdeditor.
 *
 * It uses jQuery File Upload (assumed to be loaded elsewhere) to handle uploads
 * and interacts with the Mdeditor instance to insert the resulting file URLs.
 *
 * Author: Gemini (with user assistance)
 * Date: 2024-07-31
 */

// Use a self-executing anonymous function to avoid polluting the global scope
(function($) {
    "use strict";

    // Console log helper with timestamp and script identifier
    function log(message, ...args) {
        console.log(`[mdeditor_filebrowser.js] ${new Date().toLocaleTimeString()} ${message}`, ...args);
    }

    log("Script loaded, starting initialization process.");

    // --- Constants and Configuration ---

    // Selector for the file upload input element
    const FILE_UPLOAD_SELECTOR = '#batchfileupload';
    // Selector for the Mdeditor wrapper element (used to identify the instance)
    const EDITOR_WRAPPER_SELECTOR = '#id_body-wmd-wrapper'; // Adjust if your Mdeditor field name is different
    // The UPLOAD_URL will be defined inside setupFileUpload now.

    // --- Core Functions ---

    // Function to set up the jQuery File Upload widget
    function setupFileUpload() {
        const $fileupload = $(FILE_UPLOAD_SELECTOR);
        log(`setupFileUpload: Called. Looking for file upload element: ${FILE_UPLOAD_SELECTOR}`);

        if (!$fileupload.length) {
            log(`setupFileUpload: File upload element ${FILE_UPLOAD_SELECTOR} not found.`);
            return; // Exit if the file upload element is not present
        }

        // Destroy existing fileupload instance if it exists
        if ($fileupload.data('blueimp-fileupload')) {
            log('setupFileUpload: Destroying existing fileupload instance.');
            $fileupload.fileupload('destroy');
        }

        log('setupFileUpload: Initializing new fileupload instance.');

        // Define UPLOAD_URL here, where window.batchUploadUrl is guaranteed to be available
        const UPLOAD_URL = window.batchUploadUrl;

        // --- Debugging: Log the UPLOAD_URL and window.batchUploadUrl before initializing fileupload ---
        log(`setupFileUpload: UPLOAD_URL is ${UPLOAD_URL}`);
        log(`setupFileUpload: window.batchUploadUrl is ${window.batchUploadUrl}`);
        // ---------------------------------------------------------------------------------------------------

        // Check if UPLOAD_URL is valid
        if (!UPLOAD_URL) {
             log('setupFileUpload: UPLOAD_URL is not defined. File upload cannot be initialized.');
             alert('文件上传URL未定义，批量上传功能无法使用。请检查模板配置。');
             return;
        }

        // Initialize the file upload widget
        $fileupload.fileupload({
            dataType: 'json',
            url: UPLOAD_URL,
            add: function(e, data) {
                log('File added for upload.', data.files[0].name);
                // Automatically submit the file once added
                data.submit();
            },
            done: function(e, data) {
                // This is called when a file upload is successful
                log('Upload done.', data);
                if (data.result && data.result.url) {
                    const fileUrl = data.result.url;
                    const fileType = data.result.type; // Get file type from server response
                    const fileName = data.result.name || fileUrl.split('/').pop(); // Get file name
                    log(`Upload successful. File URL: ${fileUrl}, Type: ${fileType}, Name: ${fileName}`);
                    // Insert the media URL into the Mdeditor instance
                    insertMedia(fileUrl, fileType, fileName);
                } else if (data.result && data.result.error) {
                    log(`Upload failed with error: ${data.result.error}`);
                    alert('Upload failed: ' + data.result.error);
                } else {
                     log('Upload failed with unknown response.', data.result);
                     alert('Upload failed with unknown response.');
                }
            },
            fail: function(e, data) {
                // This is called when a file upload fails
                log('Upload failed.', data);
                let errorMessage = 'Upload failed.';
                if (data.jqXHR && data.jqXHR.statusText) {
                    errorMessage += ' Status: ' + data.jqXHR.statusText;
                }
                 if (data.jqXHR && data.jqXHR.responseJSON && data.jqXHR.responseJSON.error) {
                    errorMessage += ' Error: ' + data.jqXHR.responseJSON.error;
                } else if (data.errorThrown) {
                     errorMessage += ' Error: ' + data.errorThrown;
                }

                log(errorMessage);
                alert(errorMessage);
            },
            progressall: function(e, data) {
                // Update progress bar if you have one
                // var progress = parseInt(data.loaded / data.total * 100, 10);
                // log('Upload progress:', progress + '%');
            }
        });
    }

    // Function to insert media URL (image, video, etc.) into the Mdeditor
    // We will attempt to directly interact with the Mdeditor instance
    function insertMedia(url, type, name) {
        log(`insertMedia: Called with URL: ${url}, Type: ${type}, Name: ${name}`);

        const maxInstanceAttempts = 50; // Maximum attempts to find Mdeditor instance
        const instanceAttemptInterval = 100; // Interval in milliseconds
        let instanceAttempts = 0;

        function findAndInsert() {
            instanceAttempts++;
            log(`insertMedia: Attempt ${instanceAttempts}/${maxInstanceAttempts} to find Mdeditor instance for insertion.`);

            // Try to find the Editor.md instance using the same methods as before, focusing on container.editormd or window.editormd.instances
            // Assuming the instance is attached to the wrapper element or a global registry
            let editorInstance = null;
            const $container = $(EDITOR_WRAPPER_SELECTOR);
            const container = $container[0];

             if (container && container.editormd) {
                 // Method 1: Check container.editormd property (less common for recent versions)
                 editorInstance = container.editormd;
                 log('insertMedia: Found via container.editormd', editorInstance);
             } else if (window.editormd && window.editormd.instances && window.editormd.instances[EDITOR_WRAPPER_SELECTOR.replace('#id_', '')]) {
                 // Method 2: Check window.editormd.instances registry
                 editorInstance = window.editormd.instances[EDITOR_WRAPPER_SELECTOR.replace('#id_', '')];
                 log('insertMedia: Found via window.editormd.instances', editorInstance);
             } else if ($container.data('editormd')) {
                 // Method 3: Check jQuery data with key 'editormd'
                 editorInstance = $container.data('editormd');
                 log("insertMedia: Found via jQuery data('editormd')", editorInstance);
             } else if (container) {
                 // Method 4: More aggressive search on the container DOM element itself
                 // Check if the instance is stored as a direct property or on a child element
                 if (container._editormd) { // Example: Check for a hidden property (less likely but possible)
                     editorInstance = container._editormd;
                     log('insertMedia: Found via container._editormd', editorInstance);
             } else {
                     // Check for CodeMirror instance on the CodeMirror element, which is a child of the wrapper
                     const cmElement = container.querySelector('.CodeMirror');
                     if (cmElement && cmElement.CodeMirror) {
                         // Found CodeMirror instance - this might be sufficient for insertion
                         editorInstance = cmElement.CodeMirror;
                         log('insertMedia: Found CodeMirror instance via .CodeMirror element', editorInstance);
                         // Note: editorInstance is a CodeMirror instance here, not the full Editor.md instance
                     }
                 }
             }
             // Add other potential finding methods if necessary, though these two are most common.

            if (editorInstance) {
                log('insertMedia: Mdeditor instance found (or CodeMirror). Attempting insertion.', editorInstance);

                let contentToInsert = '';
                const fileExtension = url.split('.').pop().toLowerCase();

                // Simple check for image and video types based on MIME type or extension
                if (type && type.startsWith('image/') || ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(fileExtension)) {
                    // Insert as image using HTML img tag with a class
                    contentToInsert = `<img src="${url}" class="media-item">\n`; // Add newline for basic vertical stacking initially
                    log('insertMedia: Detected image type, preparing HTML img tag.');
                } else if (type && type.startsWith('video/') || ['mp4', 'webm', 'ogg'].includes(fileExtension)) {
                     // Insert as video using HTML video tag with controls and a class
                     contentToInsert = `<video src="${url}" controls class="media-item"></video>\n`; // Add newline
                     log('insertMedia: Detected video type, preparing HTML video tag.');
                 } else if (name) {
                    // Default to a simple link if not image or video, using the file name if available
                    contentToInsert = `[${name}](${url})\n`;
                    log('insertMedia: Detected other file type, preparing Markdown link.');
                 } else {
                    // Fallback to just the URL if no name is available
                    contentToInsert = `${url}\n`;
                     log('insertMedia: Could not determine file type or name, inserting URL directly.');
                 }

                // Prefer insertValue if available, otherwise fallback to CodeMirror or textarea manipulation
                if (editorInstance.insertValue && typeof editorInstance.insertValue === 'function') {
                    log('insertMedia: Using editorInstance.insertValue.');
                    editorInstance.insertValue(contentToInsert);
                    log('insertMedia: Insertion via insertValue successful.');
                } else if (editorInstance.getCodeMirror && typeof editorInstance.getCodeMirror === 'function') {
                    const cmInstance = editorInstance.getCodeMirror();
                    if (cmInstance && typeof cmInstance.replaceSelection === 'function') {
                         log('insertMedia: Using CodeMirror replaceSelection.');
                         cmInstance.replaceSelection(contentToInsert);
                         // Optional: Set cursor after inserted text and focus
                         const cursor = cmInstance.getCursor();
                         cmInstance.setCursor({
                             line: cursor.line,
                             ch: cursor.ch + contentToInsert.length
                         });
                         cmInstance.focus();
                         log('insertMedia: Insertion via replaceSelection successful.');
                    } else {
                        log('insertMedia: CodeMirror instance or replaceSelection not found on getCodeMirror result.');
                         // Fallback to textarea manipulation if CodeMirror method is not available
                        insertIntoTextarea(editorInstance.getTextarea ? editorInstance.getTextarea() : $(EDITOR_WRAPPER_SELECTOR).find('textarea')[0], contentToInsert);
                    }
                } else if (typeof editorInstance.replaceSelection === 'function') {
                     // If it's a CodeMirror instance directly (as found by our search)
                     log('insertMedia: Using CodeMirror instance replaceSelection directly.');
                     const cmInstance = editorInstance; // Assume it's a CodeMirror instance
                      const cursor = cmInstance.getCursor();
                      cmInstance.replaceSelection(contentToInsert);
                      cmInstance.setCursor({
                          line: cursor.line,
                          ch: cursor.ch + contentToInsert.length
                      });
                      cmInstance.focus();
                      log('insertMedia: Insertion via direct CodeMirror replaceSelection successful.');
                }else {
                     log('insertMedia: insertValue and getCodeMirror not found, and not a direct CodeMirror instance.');
                     // Fallback to textarea manipulation if neither method is available
                     insertIntoTextarea(editorInstance.getTextarea ? editorInstance.getTextarea() : $(EDITOR_WRAPPER_SELECTOR).find('textarea')[0], contentToInsert);
                }

            } else if (instanceAttempts < maxInstanceAttempts) {
                // If not found and max attempts not reached, retry after a delay
                setTimeout(findAndInsert, instanceAttemptInterval);
        } else {
                // If not found after max attempts, log error and alert user
                log(`insertMedia: Mdeditor instance not found after ${maxInstanceAttempts} attempts. Cannot insert URL automatically.`);
                alert('Could not automatically insert media URL. Please manually insert: ' + url);
            }
        }

         // Fallback function for direct textarea manipulation
        function insertIntoTextarea(textarea, text) {
             if (!textarea) {
                 log('insertMedia: Textarea element not found for insertion fallback.');
                 alert('Cannot find textarea to insert media URL manually.');
                 return;
             }

             log('insertMedia: Falling back to directly manipulating textarea.', textarea);
             const start = textarea.selectionStart;
             const end = textarea.selectionEnd;
             const value = textarea.value;

             textarea.value = value.substring(0, start) + text + value.substring(end);
             textarea.selectionStart = textarea.selectionEnd = start + text.length;

              // Attempt to trigger input/change events to notify Mdeditor/Django form
             try {
                 const inputEvent = new Event('input', { bubbles: true });
                 textarea.dispatchEvent(inputEvent);
                 log('insertMedia: Dispatched input event.');
             } catch (e) {
                 log("Error dispatching input event:", e);
             }
             try {
                 const changeEvent = new Event('change', { bubbles: true });
                 textarea.dispatchEvent(changeEvent);
                 log('insertMedia: Dispatched change event.');
             } catch (e) {
                 log("Error dispatching change event:", e);
             }
        }

        // Start the process to find instance and insert
        findAndInsert();
    }

    // --- Initialization ---

    // Wait for the DOM to be fully loaded before initializing
    $(document).ready(function() {
        log('Document ready. Initializing batch upload setup.');
        // Directly setup file upload, relying on insertMedia for insertion
        setupFileUpload();
    });

    log("Initialization logic setup.");

})(jQuery);