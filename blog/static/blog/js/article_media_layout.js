// blog/static/blog/js/article_media_layout.js

document.addEventListener('DOMContentLoaded', function() {
    // Find all article media galleries on the page
    const galleries = document.querySelectorAll('.article-media-gallery');

    galleries.forEach(gallery => {
        // Find all image and video elements within the gallery, regardless of nesting
        const mediaElements = gallery.querySelectorAll('img, video');

        // The `article_media_layout.js` should no longer move or clear content.
        // Its primary role is to apply layout classes based on the presence of media.
        // The actual image pagination and loading is handled by article_detail.html's script.
        // Ensure the content inside the gallery div is not accidentally cleared.

        const isIndexView = gallery.dataset.isIndex === 'true';
        const maxItemsIndexView = 9; // Maximum items to show in list view

        let visibleMediaElements = Array.from(mediaElements); // Start with all media elements

        if (isIndexView) {
            // In list view, hide elements beyond the maximum limit
            if (visibleMediaElements.length > maxItemsIndexView) {
                for (let i = maxItemsIndexView; i < visibleMediaElements.length; i++) {
                    visibleMediaElements[i].style.display = 'none';
                }
                // Filter to get only the currently visible elements after hiding
                 visibleMediaElements = visibleMediaElements.filter(el => el.style.display !== 'none');
            }
        }

        // Count the number of visible media elements
        const visibleCount = visibleMediaElements.length;

        // Apply column class based on visible count
        if (visibleCount >= 3) {
            gallery.classList.add('gallery-three-col');
            gallery.classList.remove('gallery-two-col'); // Ensure only one is applied
        } else if (visibleCount > 0 && visibleCount < 3) {
            gallery.classList.add('gallery-two-col');
            gallery.classList.remove('gallery-three-col'); // Ensure only one is applied
        } else {
            // No media elements, remove any gallery classes
            gallery.classList.remove('gallery-two-col', 'gallery-three-col');
        }

        // Optional: If you want to specifically hide the gallery container if there are no visible images/videos after truncation
        if (visibleCount === 0 && isIndexView) {
             gallery.style.display = 'none';
        }

    });
});