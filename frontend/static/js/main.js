document.addEventListener('DOMContentLoaded', function () {
  // Mobile menu toggle
  const mobileMenuBtn = document.getElementById('mobile-menu-btn');
  const mobileMenu = document.getElementById('mobile-menu');
  const hamburgerIcon = document.getElementById('hamburger-icon');
  const closeIcon = document.getElementById('close-icon');
  
  if (mobileMenuBtn && mobileMenu) {
    const menuLinks = mobileMenu.querySelectorAll('.menu-link');
    
    mobileMenuBtn.addEventListener('click', function() {
      const isOpen = mobileMenu.classList.contains('menu-open');
      
      if (!isOpen) {
        // Show menu - slide in from right
        mobileMenu.classList.add('flex', 'menu-open');
        mobileMenu.classList.remove('pointer-events-none');
        mobileMenu.classList.add('menu-slide-in');
        mobileMenu.classList.remove('menu-slide-out');
        hamburgerIcon.classList.add('hidden');
        closeIcon.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        
        // Float in menu items with stagger (like Track/Insights)
        menuLinks.forEach((link, index) => {
          setTimeout(() => {
            link.classList.add('menu-item-float-in');
            link.classList.remove('menu-item-float-out');
          }, 250 + (index * 100)); // Stagger by 100ms each
        });
      } else {
        // Hide menu - float out items first
        menuLinks.forEach((link, index) => {
          setTimeout(() => {
            link.classList.add('menu-item-float-out');
            link.classList.remove('menu-item-float-in');
          }, index * 50);
        });
        
        // Then slide out menu
        setTimeout(() => {
          mobileMenu.classList.add('menu-slide-out');
          mobileMenu.classList.remove('menu-slide-in');
          hamburgerIcon.classList.remove('hidden');
          closeIcon.classList.add('hidden');
          
          setTimeout(() => {
            mobileMenu.classList.add('pointer-events-none');
            mobileMenu.classList.remove('menu-open');
            document.body.style.overflow = '';
          }, 600);
        }, 200);
      }
    });
    
    // Close menu when a link is clicked
    menuLinks.forEach(link => {
      link.addEventListener('click', function() {
        // Float out items
        menuLinks.forEach((l, index) => {
          setTimeout(() => {
            l.classList.add('menu-item-float-out');
            l.classList.remove('menu-item-float-in');
          }, index * 50);
        });
        
        // Slide out menu
        setTimeout(() => {
          mobileMenu.classList.add('menu-slide-out');
          mobileMenu.classList.remove('menu-slide-in');
          hamburgerIcon.classList.remove('hidden');
          closeIcon.classList.add('hidden');
          
          setTimeout(() => {
            mobileMenu.classList.add('pointer-events-none');
            mobileMenu.classList.remove('menu-open');
            document.body.style.overflow = '';
          }, 600);
        }, 200);
      });
    });
  }
  
  const form = document.getElementById('searchForm');
  const searchInput = document.getElementById('searchInput') || document.getElementById('search-box');
  const resultsDiv = document.getElementById('results');
  if (!form || !searchInput || !resultsDiv) return;
  
  // Track ongoing search request to cancel if needed
  let abortController = null;
  
  // Debounce timer
  let searchTimeout = null;
  
  // Perform search function
  async function performSearch(query) {
    // Cancel any ongoing request
    if (abortController) {
      abortController.abort();
    }
    
    // Clear any pending search
    if (searchTimeout) {
      clearTimeout(searchTimeout);
      searchTimeout = null;
    }
    
    if (!query) {
      resultsDiv.innerHTML = '<div class="no-results">Please enter a search query</div>';
      return;
    }
    
    resultsDiv.innerHTML = '<div class="loading">Searching...</div>';
    
    // Create new abort controller for this request
    abortController = new AbortController();
    
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
        signal: abortController.signal
      });
      if (!res.ok) throw new Error('Search request failed');
      const data = await res.json();
      if (data.length === 0) {
        resultsDiv.innerHTML = '<div class="no-results">No results found for "' + escapeHtml(query) + '"</div>';
      } else {
        // Clear previous results
        resultsDiv.innerHTML = '';

        // Create ul element
        const ul = document.createElement('ul');
        ul.className = 'list-none p-0 m-0';

        // Build list items
        data.forEach(item => {
          const li = document.createElement('li');
          li.className = 'mb-2';

          const btn = document.createElement('button');
          btn.className = 'btn btn-ghost p-2 px-4 bg-gray-100 rounded-full w-full text-left justify-between flex';

          if (item.type === 'school') {
            btn.innerHTML = `
                            ${escapeHtml(item.name)}
                            <span class="font-bold px-2 py-0.5 border-2 border-green-500 rounded-full text-green-600" style="margin-right:4px;">School</span>
                        `.trim();

            btn.addEventListener('click', () => {
              window.location.href = `/school-dashboard/${item.id}`;
              console.log('Navigating to school ID:', item.id);
            });
          } else if (item.type === 'athlete') {
            let gender = (item.gender || '').toLowerCase();
            let genderBadgeClass = '';
            let genderLabel = '';

            if (gender === 'b' || gender === 'boys') {
              genderBadgeClass = 'border-blue-500 text-blue-600';
              genderLabel = 'Boys';
            } else if (gender === 'g' || gender === 'girls') {
              genderBadgeClass = 'border-pink-500 text-pink-600';
              genderLabel = 'Girls';
            } else {
              genderBadgeClass = 'border-gray-400 text-gray-600';
              genderLabel = escapeHtml(item.gender || 'A');
            }

            const classYear = item.graduation_year ? escapeHtml(item.graduation_year) : '00';
            btn.innerHTML = `
                            ${escapeHtml(item.name)}, Class of ${classYear} - ${escapeHtml(item.school || '')}
                            <span class="font-bold px-2 py-0.5 border-2 ${genderBadgeClass} rounded-full" style="margin-right:4px;">${genderLabel}</span>
                        `.trim();

            btn.addEventListener('click', () => {
              window.location.href = `/athlete-dashboard/${item.id}`;
              console.log('Navigating to athlete ID:', item.id);
            });
          }

          li.appendChild(btn);
          ul.appendChild(li);
        });

        resultsDiv.appendChild(ul);
      }
    } catch (error) {
      // Don't show error if request was aborted (user is typing)
      if (error.name === 'AbortError') {
        return;
      }
      resultsDiv.innerHTML = '<div class="no-results" style="color: #dc3545;">Error performing search. Please try again.</div>';
    }
  }
  
  // Form submit handler
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    // Get the CURRENT value at submit time
    const query = searchInput.value.trim();
    await performSearch(query);
  });
  
  // Optional: Add live search as user types (debounced)
  searchInput.addEventListener('input', function() {
    const query = this.value.trim();
    
    // Clear existing timeout
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }
    
    // Don't search if empty
    if (!query) {
      resultsDiv.innerHTML = '';
      return;
    }
    
    // Debounce: wait 500ms after user stops typing
    searchTimeout = setTimeout(() => {
      performSearch(query);
    }, 500);
  });

  // Helper function to escape HTML
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
});