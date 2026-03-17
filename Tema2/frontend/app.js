const API_BASE = 'http://127.0.0.1:8090/api';
let currentFilter = 'all';

const cityInput = document.getElementById('cityInput');
const weatherBox = document.getElementById('weatherBox');
const factBox = document.getElementById('factBox');
const errorBox = document.getElementById('errorBox');
const taskList = document.getElementById('taskList');
const formMessage = document.getElementById('formMessage');

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  let data = null;
  try {
    data = await response.json();
  } catch (_) {
    data = null;
  }
  return { ok: response.ok, status: response.status, data };
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderWeather(weather) {
  if (!weather) {
    weatherBox.textContent = 'Datele despre vreme nu sunt disponibile.';
    return;
  }
  weatherBox.innerHTML = `
    <p><strong>Oraș:</strong> ${escapeHtml(weather.city || '-')} ${weather.country ? `(${escapeHtml(weather.country)})` : ''}</p>
    <p><strong>Temperatură:</strong> ${weather.temperature ?? '-'} °C</p>
    <p><strong>Se simte ca:</strong> ${weather.feelsLike ?? '-'} °C</p>
    <p><strong>Descriere:</strong> ${escapeHtml(weather.description || '-')}</p>
    <p><strong>Umiditate:</strong> ${weather.humidity ?? '-'}%</p>
    <p><strong>Vânt:</strong> ${weather.windSpeed ?? '-'} m/s</p>
  `;
}

function renderFact(factObj) {
  if (!factObj || !factObj.fact) {
    factBox.textContent = 'Fact-ul random nu este disponibil.';
    return;
  }
  factBox.textContent = factObj.fact;
}

function renderErrors(errors) {
  if (!errors || Object.keys(errors).length === 0) {
    errorBox.textContent = 'Nu există erori.';
    return;
  }
  errorBox.textContent = JSON.stringify(errors, null, 2);
}

function buildTaskItem(task) {
  const li = document.createElement('li');
  li.className = 'task-item';

  const titleClass = task.done ? 'task-title done' : 'task-title';
  li.innerHTML = `
    <div class="task-main">
      <div class="${titleClass}">${escapeHtml(task.title)}</div>
      <div class="task-meta">ID: ${task.id} | Created: ${escapeHtml(task.createdAt || '-')} | Status: ${task.done ? 'done' : 'open'}</div>
    </div>
    <div class="task-actions">
      <button class="secondary" data-action="toggle">${task.done ? 'Marchează open' : 'Marchează done'}</button>
      <button class="secondary" data-action="rename">Redenumește</button>
      <button class="danger" data-action="delete">Șterge</button>
    </div>
  `;

  li.querySelector('[data-action="toggle"]').addEventListener('click', () => toggleTask(task));
  li.querySelector('[data-action="rename"]').addEventListener('click', () => renameTask(task));
  li.querySelector('[data-action="delete"]').addEventListener('click', () => removeTask(task.id));
  return li;
}

function renderTasks(tasks) {
  taskList.innerHTML = '';
  if (!Array.isArray(tasks) || tasks.length === 0) {
    taskList.innerHTML = '<li class="task-item">Nu există task-uri pentru filtrul selectat.</li>';
    return;
  }
  tasks.forEach(task => taskList.appendChild(buildTaskItem(task)));
}

async function loadDashboard() {
  const city = cityInput.value.trim() || 'Bucharest';
  weatherBox.textContent = 'Se încarcă...';
  factBox.textContent = 'Se încarcă...';
  const result = await apiFetch(`/dashboard?city=${encodeURIComponent(city)}`);

  if (!result.ok || !result.data) {
    renderWeather(null);
    renderFact(null);
    renderErrors({ app: { error: 'Nu s-a putut încărca dashboard-ul.' } });
    return;
  }

  renderWeather(result.data.weather);
  renderFact(result.data.fact);
  renderErrors(result.data.errors);
  applyFilter(currentFilter, result.data.tasks || []);
}

function applyFilter(filter, tasks = null) {
  currentFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === filter);
  });

  const existing = tasks || Array.from(taskList.querySelectorAll('.task-item-data')).map(x => JSON.parse(x.dataset.task));
  let filtered = existing;
  if (filter === 'open') filtered = existing.filter(t => !t.done);
  if (filter === 'done') filtered = existing.filter(t => t.done);

  taskList.innerHTML = '';
  if (!filtered.length) {
    taskList.innerHTML = '<li class="task-item">Nu există task-uri pentru filtrul selectat.</li>';
    return;
  }

  filtered.forEach(task => {
    const li = buildTaskItem(task);
    li.classList.add('task-item-data');
    li.dataset.task = JSON.stringify(task);
    taskList.appendChild(li);
  });
}

async function addTask() {
  const titleInput = document.getElementById('taskTitle');
  const doneInput = document.getElementById('taskDone');
  const title = titleInput.value.trim();
  const done = doneInput.checked;

  if (!title) {
    formMessage.textContent = 'Titlul task-ului este obligatoriu.';
    return;
  }

  const result = await apiFetch('/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, done })
  });

  if (!result.ok) {
    formMessage.textContent = result.data?.error || 'Eroare la adăugarea task-ului.';
    return;
  }

  titleInput.value = '';
  doneInput.checked = false;
  formMessage.textContent = 'Task adăugat cu succes.';
  await loadDashboard();
}

async function toggleTask(task) {
  const result = await apiFetch(`/tasks/${task.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: task.title, done: !task.done })
  });

  if (!result.ok) {
    alert(result.data?.error || 'Eroare la actualizarea task-ului.');
    return;
  }
  await loadDashboard();
}

async function renameTask(task) {
  const newTitle = prompt('Noul titlu al task-ului:', task.title);
  if (newTitle === null) return;
  if (!newTitle.trim()) {
    alert('Titlul nu poate fi gol.');
    return;
  }

  const result = await apiFetch(`/tasks/${task.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: newTitle.trim(), done: task.done })
  });

  if (!result.ok) {
    alert(result.data?.error || 'Eroare la redenumirea task-ului.');
    return;
  }
  await loadDashboard();
}

async function removeTask(taskId) {
  const confirmed = confirm('Sigur vrei să ștergi task-ul?');
  if (!confirmed) return;

  const result = await apiFetch(`/tasks/${taskId}`, { method: 'DELETE' });
  if (!result.ok) {
    alert(result.data?.error || 'Eroare la ștergerea task-ului.');
    return;
  }
  await loadDashboard();
}

document.getElementById('reloadBtn').addEventListener('click', loadDashboard);
document.getElementById('addTaskBtn').addEventListener('click', addTask);
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => loadDashboard().then(() => {
    currentFilter = btn.dataset.filter;
    applyFilter(currentFilter, Array.from(taskList.querySelectorAll('.task-item-data')).map(x => JSON.parse(x.dataset.task)));
  }));
});

loadDashboard();
