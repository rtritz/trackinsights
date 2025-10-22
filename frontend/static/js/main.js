document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('searchForm');
    if (!form) return;
    // Dummy data for testing
        // Dummy data for testing (schools and athletes)
        const dummyAthletes = [
            { type: 'School', name: 'Park Tudor School' },
            { type: 'B', name: 'Justin Li', class_year: '26', school: 'Park Tudor School' },
            { type: 'B', name: 'Owen Zhang', class_year: '26', school: 'Park Tudor School' },
            { type: 'G', name: 'Kylie Ritz', class_year: '27', school: 'Park Tudor School' }
        ];
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const q = new FormData(form).get('q');
        if (!q) return;
        // Use dummy data instead of fetch for testing
        // const res = await fetch(`/api/athletes`);
        // const data = await res.json();
        const data = dummyAthletes;
            // Filter for both school and athlete name
            const results = data.filter(a => {
                if (a.type === 'School') {
                    return a.name.toLowerCase().includes(q.toLowerCase());
                } else {
                    return a.name.toLowerCase().includes(q.toLowerCase()) || (a.school && a.school.toLowerCase().includes(q.toLowerCase()));
                }
            });
            const out = document.getElementById('results');
            out.innerHTML = results.map(a => {
                if (a.type === 'School') {
                    return `<div><span class="font-bold">S</span> ${a.name}</div>`;
                } else {
                    return `<div><span class="font-bold">${a.type}</span> ${a.name} '${a.class_year} - ${a.school}</div>`;
                }
            }).join('');
    });
});

document.getElementById('search-btn').addEventListener('click', () => {
    const searchTerm = document.getElementById('search-box').value;

    fetch(`/search?query=${encodeURIComponent(searchTerm)}`)
        .then(response => response.json())
        .then(data => showResults(data));
});

function showResults(results) {
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = ''; // Clear previous results
    
    if (results.length === 0) {
        resultsDiv.innerHTML = '<p>No results found.</p>';
        return;
    }

    results.forEach(item => {
        const div = document.createElement('div');
    
        if (item.type === 'School') {
            // For schools, show type and name
            div.textContent = `${item.type}: ${item.name}`;
        } else {
            // For athletes, show type, name, class year, and school
            div.textContent = `${item.type}: ${item.name} '${item.class_year} - ${item.school}`;
        }
    
        resultsDiv.appendChild(div);
    });

}