CKEDITOR.plugins.add('wasabifilebrowser', {
    init: function(editor) {
        // Add a button to the editor toolbar.
        editor.addCommand('wasabifilebrowser', {
            exec: function(editor) {
                console.log("DEBUG-PLUGIN: editor.name =", editor.name);
                console.log("DEBUG-PLUGIN: editor.id =", editor.id);
                // Open the Wasabi file browser URL in a new window.
                // The URL is taken from CKEDITOR.config.filebrowserBrowseUrl
                // This URL should point to our Django view that renders the HTML file browser.
                // Force CKEditor parameter to 'id_body' as it's the known instance name.
                var url = CKEDITOR.tools.addQueryString(editor.config.filebrowserBrowseUrl, 'CKEditor=id_body&CKEditorFuncNum=' + editor._.filebrowserFn + '&langCode=' + editor.langCode);
                editor.popup(url, '80%', '70%', 'WasabiFileBrowser', function() {
                    // Optional callback after popup closes
                });
            }
        });

        // Add the button to the toolbar.
        editor.ui.addButton('WasabiFileBrowser', {
            label: 'Browse Wasabi',
            command: 'wasabifilebrowser',
            toolbar: 'insert', // You can change the toolbar group
            icon: this.path + 'icons/wasabi.png' // Path to your icon
        });
    }
});