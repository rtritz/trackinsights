document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('searchForm');
  const searchInput = document.getElementById('searchInput') || document.getElementById('search-box');
  const resultsDiv = document.getElementById('results');
  if (!form || !searchInput || !resultsDiv) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = searchInput.value.trim();
    if (!query) {
      resultsDiv.innerHTML = '<div class="no-results">Please enter a search query</div>';
      return;
    }
    resultsDiv.innerHTML = '<div class="loading">Searching...</div>';
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
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
          btn.className = 'btn btn-ghost m-2 p-2 px-4 bg-gray-100 rounded-full w-full text-left justify-between flex';

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
      resultsDiv.innerHTML = '<div class="no-results" style="color: #dc3545;">Error performing search. Please try again.</div>';
    }
  });

  // Helper function to escape HTML
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
});