CKEDITOR.plugins.add('wasabifilebrowser', {
    init: function(editor) {
        editor.addCommand('wasabifilebrowserDialog', {
            exec: function(editor) {
                var funcNum = CKEDITOR.tools.addFunction(function(url) {
                    editor.insertHtml('<img src="' + url + '" alt="" />');
                });
                var url = '/wasabi-file-browser/?CKEditorFuncNum=' + funcNum;
                editor.popup(url, '800', '600');
            }
        });

        editor.ui.addButton('WasabiFileBrowser', {
            label: 'Wasabi 文件浏览器',
            command: 'wasabifilebrowserDialog',
            toolbar: 'insert',
            icon: this.path + 'icons/wasabi.png' // You'll need to create this icon
        });
    }
}); 