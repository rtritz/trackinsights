document.addEventListener('DOMContentLoaded', function () {
  const setupSearch = (form, searchInput, resultsDiv) => {
    if (!form || !searchInput || !resultsDiv) {
      return;
    }

    let abortController = null;
    let searchTimeout = null;

    const performSearch = async (query) => {
      if (abortController) {
        abortController.abort();
      }

      if (searchTimeout) {
        clearTimeout(searchTimeout);
        searchTimeout = null;
      }

      if (!query) {
        resultsDiv.innerHTML = '';
        resultsDiv.classList.remove('open');
        return;
      }

      resultsDiv.innerHTML = '<div class="loading">Searching...</div>';
      resultsDiv.classList.add('open');

      abortController = new AbortController();

      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
          signal: abortController.signal,
        });
        if (!res.ok) throw new Error('Search request failed');
        const data = await res.json();
        if (data.length === 0) {
          resultsDiv.innerHTML = '<div class="no-results">No results found for "' + escapeHtml(query) + '"</div>';
          resultsDiv.classList.add('open');
        } else {
          resultsDiv.innerHTML = '';
          const ul = document.createElement('ul');
          ul.className = 'list-none p-0 m-0';

          data.forEach(item => {
            const li = document.createElement('li');
            li.className = 'mb-2';
            const btn = document.createElement('button');
            btn.className = 'btn btn-ghost p-2 px-4 bg-gray-100 rounded-full w-full text-left justify-between flex';

            if (item.type === 'school') {
              btn.innerHTML = `
                            <span class="result-text">${escapeHtml(item.name)}</span>
                            <span class="result-badge font-bold border-2 border-green-500 text-green-600 rounded-full" style="margin-right:4px;">School</span>
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
              <span class="result-text">${escapeHtml(item.name)}, Class of ${classYear} - ${escapeHtml(item.school || '')}</span>
              <span class="result-badge font-bold border-2 rounded-full px-1 ${genderBadgeClass}" style="margin-right:4px;">${genderLabel}</span>
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
          resultsDiv.classList.add('open');
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          return;
        }
        resultsDiv.innerHTML = '<div class="no-results" style="color: #dc3545;">Error performing search. Please try again.</div>';
        resultsDiv.classList.add('open');
      }
    };

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const query = searchInput.value.trim();
      await performSearch(query);
    });

    searchInput.addEventListener('input', function () {
      const query = this.value.trim();
      if (searchTimeout) {
        clearTimeout(searchTimeout);
      }

      if (!query) {
        resultsDiv.innerHTML = '';
        resultsDiv.classList.remove('open');
        return;
      }

      searchTimeout = setTimeout(() => {
        performSearch(query);
      }, 500);
    });
  };

  setupSearch(
    document.getElementById('navSearchForm'),
    document.getElementById('navSearchInput'),
    document.getElementById('nav-search-results'),
  );

  setupSearch(
    document.getElementById('searchForm'),
    document.getElementById('searchInput') || document.getElementById('search-box'),
    document.getElementById('results'),
  );

  // Helper function to escape HTML
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
});