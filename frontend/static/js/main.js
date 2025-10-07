document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('searchForm');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = new FormData(form).get('q');
    if (!q) return;
    const res = await fetch(`/api/athletes`);
    const data = await res.json();
    const results = data.filter(a => (a.first_name + ' ' + a.last_name).toLowerCase().includes(q.toLowerCase()));
    const out = document.getElementById('results');
    out.innerHTML = results.map(a => `<div>${a.first_name} ${a.last_name} ${a.school ? '— ' + a.school : ''}</div>`).join('');
  });
});
