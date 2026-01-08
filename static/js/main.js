// Main JavaScript file

// Search functionality
document.addEventListener('DOMContentLoaded', function() {
    // Auto-focus search input on page load
    const searchInput = document.querySelector('.search-box input');
    if (searchInput) {
        searchInput.focus();
    }
    
    // Anime card hover effects
    const animeCards = document.querySelectorAll('.anime-card');
    animeCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-10px)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });
    
    // Load more functionality (placeholder)
    const seeAllButtons = document.querySelectorAll('.see-all');
    seeAllButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            if (this.getAttribute('href') === '#') {
                e.preventDefault();
                alert('Fitur "Lihat Semua" akan dikembangkan lebih lanjut!');
            }
        });
    });
    
    // Lazy load images
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.add('loaded');
                    observer.unobserve(img);
                }
            });
        });
        
        document.querySelectorAll('img[data-src]').forEach(img => {
            imageObserver.observe(img);
        });
    }
});

// Utility functions
function formatEpisodeNumber(epNum) {
    return `Episode ${String(epNum).padStart(2, '0')}`;
}

function truncateText(text, maxLength) {
    if (text.length > maxLength) {
        return text.substring(0, maxLength) + '...';
    }
    return text;
}