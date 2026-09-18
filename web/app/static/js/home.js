/* Home
 *
 * Moved out of home.html, where it sat as 77 lines inside a <script> tag.
 * Here it gets syntax checking, the browser can cache it, and "where is the
 * code for this page?" has the obvious answer: the file named after the page.
 *
 * It reads what it needs from the DOM rather than from Jinja, which is what
 * made moving it safe. Keep it that way -- pass values in with data- attributes
 * rather than templating them into the JavaScript.
 */

(function () {
  // Define all background images
  const licensedImageCount = 12;
  const licensedImages = Array.from({ length: licensedImageCount }, (_, i) => `../static/images/background_images_licensed/bg_${i + 1}.webp`);
  const allImages = [...licensedImages];

  // Shuffle array
  function shuffle(array) {
    const shuffled = [...array];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
  }

  const shuffledImages = shuffle(allImages);
  let currentIndex = 0;
  let currentImageElement = 1; // Toggle between 1 and 2

  const img1 = document.getElementById('bg-image-1');
  const img2 = document.getElementById('bg-image-2');

  // Set first image
  img1.src = shuffledImages[0];

  // Preload next image
  function preloadNext() {
    const nextIndex = (currentIndex + 1) % shuffledImages.length;
    const img = new Image();
    img.src = shuffledImages[nextIndex];
  }

  // Transition to next image
  function nextImage() {
    currentIndex = (currentIndex + 1) % shuffledImages.length;

    if (currentImageElement === 1) {
      // Preload the image first to avoid gaps
      const tempImg = new Image();
      tempImg.onload = function () {
        // Load the new image into img2 (underneath)
        img2.src = shuffledImages[currentIndex];
        img2.style.opacity = '1';
        img2.style.zIndex = '0';

        // Fade out img1 (on top) to reveal img2
        img1.style.zIndex = '1';
        img1.style.opacity = '0';
      };
      tempImg.src = shuffledImages[currentIndex];
      currentImageElement = 2;
    } else {
      // Preload the image first to avoid gaps
      const tempImg = new Image();
      tempImg.onload = function () {
        // Load the new image into img1 (underneath)
        img1.src = shuffledImages[currentIndex];
        img1.style.opacity = '1';
        img1.style.zIndex = '0';

        // Fade out img2 (on top) to reveal img1
        img2.style.zIndex = '1';
        img2.style.opacity = '0';
      };
      tempImg.src = shuffledImages[currentIndex];
      currentImageElement = 1;
    }

    preloadNext();
  }

  // Change image every 5 seconds
  setInterval(nextImage, 7500);
  preloadNext();
})();
