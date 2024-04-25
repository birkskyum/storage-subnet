document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('file-upload').addEventListener('change', function() {
            var fileName = this.files[0] ? this.files[0].name : 'Choose file';
            document.getElementById('file-name').textContent = fileName;
    });
});