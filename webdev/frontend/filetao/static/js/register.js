document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('show-fields').addEventListener('click', function() {
        var extraFields = document.getElementById('extra-fields');
        if (extraFields.style.display === 'none') {
            extraFields.style.display = 'block';
        } else {
            extraFields.style.display = 'none';
        }
    });
});