document.addEventListener('DOMContentLoaded', (event) => {
    const toggleDarkMode = document.querySelector('#toggle-dark-mode');

    // toggle checkbox based on user preference
    if (localStorage.getItem('darkMode') === 'true') {
        toggleDarkMode.checked = true;
    }

    toggleDarkMode.addEventListener('change', () => {
        document.body.classList.toggle('dark-mode');

        // save user preference for dark mode
        localStorage.setItem('darkMode', toggleDarkMode.checked);
    });
});