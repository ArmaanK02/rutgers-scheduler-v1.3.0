// Global cache for schedule data
if (!window.scheduleCache) {
    window.scheduleCache = {};
}

let activeTrackers = 0;
const MAX_TRACKERS = 5;

document.addEventListener('DOMContentLoaded', () => {
    const chatContainer = document.getElementById('chat-container');
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const newChatBtn = document.getElementById('new-chat-btn');
    
    initializeScheduleButtons();
    initializeDeleteButtons();
    initializeSearchableDropdowns(); // New function for search UI
    
    if(chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;

    if (chatForm) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = userInput.value.trim();
            const chatId = document.getElementById('current-chat-id').value;
            
            if (!text) return;

            appendMessage('user', text);
            userInput.value = '';

            try {
                const response = await fetch('/api/send_message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: chatId, text: text })
                });
                
                const data = await response.json();
                appendMessage('ai', data.ai_message.text, data.ai_message.schedules);
                
                if (chatId != data.chat_id) {
                    window.history.pushState({}, '', `/chat?id=${data.chat_id}`);
                }
            } catch (err) {
                console.error(err);
                appendMessage('ai', "Sorry, I encountered an error connecting to the server.");
            }
        });
    }

    if (newChatBtn) {
        newChatBtn.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/new_chat', { method: 'POST' });
                const data = await res.json();
                if (data.message === 'Redirected to existing empty chat') { }
                window.location.href = `/chat?id=${data.id}`;
            } catch (err) { console.error(err); }
        });
    }
});

// --- Searchable Dropdown Logic ---
function initializeSearchableDropdowns() {
    const input = document.getElementById('major-search');
    const list = document.getElementById('major-dropdown-list');
    
    if (!input || !list) return; // Only run on progress page
    
    const items = Array.from(list.children);
    
    // Filter logic
    input.addEventListener('input', () => {
        const val = input.value.toLowerCase();
        let visibleCount = 0;
        
        items.forEach(item => {
            if (item.innerText.toLowerCase().includes(val)) {
                item.style.display = 'block';
                visibleCount++;
            } else {
                item.style.display = 'none';
            }
        });
        
        list.style.display = visibleCount > 0 ? 'block' : 'none';
    });
    
    // Selection logic
    items.forEach(item => {
        item.addEventListener('click', () => {
            input.value = item.getAttribute('data-value');
            list.style.display = 'none';
        });
    });
    
    // Close when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.searchable-dropdown')) {
            list.style.display = 'none';
        }
    });
    
    // Show on focus
    input.addEventListener('focus', () => {
        if(input.value) input.dispatchEvent(new Event('input'));
        else list.style.display = 'block';
    });
}

// --- Multi-Tracker Logic ---
async function addTracker() {
    const majorInput = document.getElementById('major-search');
    const major = majorInput.value;
    const container = document.getElementById('active-trackers');
    
    if (!major) {
        alert("Please select a major, minor, or certificate.");
        return;
    }
    
    if (activeTrackers >= MAX_TRACKERS) {
        alert("Maximum of 5 trackers allowed.");
        return;
    }
    
    try {
        const res = await fetch('/api/check_progress', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({major})
        });
        
        const data = await res.json();
        
        // Build the tracker card HTML
        const trackerId = 'tracker-' + Date.now();
        const card = document.createElement('div');
        card.className = 'data-card tracker-card';
        card.id = trackerId;
        
        const completedHtml = data.completed.length ? 
            data.completed.map(c => `<li><i class="fas fa-check-circle text-success"></i> ${c}</li>`).join('') :
            '<li style="color:#666">No requirements met yet</li>';
            
        const remainingHtml = data.remaining.length ?
            data.remaining.slice(0, 5).map(c => `<li><i class="fas fa-circle text-secondary"></i> ${c}</li>`).join('') + (data.remaining.length > 5 ? `<li>...and ${data.remaining.length - 5} more</li>` : '') :
            '<li><i class="fas fa-star text-success"></i> All done!</li>';

        card.innerHTML = `
            <button class="tracker-remove" onclick="removeTracker('${trackerId}')"><i class="fas fa-times"></i></button>
            <h3><i class="fas fa-graduation-cap"></i> ${major}</h3>
            
            <div class="progress-bar-container">
                <div class="progress-bar-fill" style="width: ${data.progress}%"></div>
            </div>
            <p style="text-align: right; margin-top: 10px; font-weight: bold;">${data.progress}% Completed</p>
            
            <div class="progress-grid">
                <div class="bg-darker">
                    <h4>Completed</h4>
                    <ul class="req-list" style="max-height: 150px; overflow-y: auto;">${completedHtml}</ul>
                </div>
                <div class="bg-darker">
                    <h4>Missing</h4>
                    <ul class="req-list" style="max-height: 150px; overflow-y: auto;">${remainingHtml}</ul>
                </div>
            </div>
        `;
        
        container.insertBefore(card, container.firstChild);
        activeTrackers++;
        majorInput.value = ''; // Reset input
        
    } catch (err) {
        console.error(err);
        alert("Could not load requirements for: " + major);
    }
}

function removeTracker(id) {
    const el = document.getElementById(id);
    if (el) {
        el.remove();
        activeTrackers--;
    }
}

// --- Standard Functions (Unchanged mostly) ---

function initializeScheduleButtons() {
    document.querySelectorAll('.view-schedule-btn').forEach(btn => {
        if (btn.dataset.listening) return;
        const jsonStr = btn.getAttribute('data-schedule-json');
        const schedId = btn.getAttribute('data-schedule-id');
        if (jsonStr && schedId) {
            try {
                const scheduleData = JSON.parse(jsonStr);
                window.scheduleCache[schedId] = scheduleData;
                btn.addEventListener('click', () => viewSchedule(schedId));
                btn.dataset.listening = "true";
            } catch (e) { console.error("Failed to parse schedule data", e); }
        }
    });
}

function initializeDeleteButtons() {
    document.querySelectorAll('.delete-chat-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!confirm("Are you sure you want to delete this chat?")) return;
            const chatId = btn.dataset.chatId;
            try {
                const res = await fetch('/api/delete_chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({chat_id: chatId})
                });
                if (res.ok) {
                    const urlParams = new URLSearchParams(window.location.search);
                    if (urlParams.get('id') == chatId) window.location.href = '/chat';
                    else window.location.reload();
                }
            } catch (err) { console.error(err); }
        });
    });
}

function appendMessage(role, text, schedules = null) {
    const container = document.getElementById('chat-container');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message message-${role}`;
    let contentHtml = `<div class="message-content">${text}`;
    if (schedules && schedules.length > 0) {
        const scheduleId = 'sched_' + Date.now() + '_' + Math.floor(Math.random() * 10000);
        const jsonStr = JSON.stringify(schedules).replace(/"/g, '&quot;');
        contentHtml += `
            <div class="schedule-preview">
                <button class="btn btn-sm btn-outline view-schedule-btn" 
                        style="margin-top:10px" 
                        data-schedule-id="${scheduleId}"
                        data-schedule-json="${jsonStr}">
                    View ${schedules.length} Schedules
                </button>
            </div>`;
    }
    contentHtml += `</div><div class="message-time">Just now</div>`;
    msgDiv.innerHTML = contentHtml;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
    initializeScheduleButtons();
}

async function uploadHistory() {
    const text = document.getElementById('history-text').value;
    if (!text) return;
    try {
        const res = await fetch('/api/parse_history', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: text})
        });
        const data = await res.json();
        alert(data.message);
        document.getElementById('import-modal').style.display = 'none';
        if (window.location.pathname === '/history') window.location.reload();
    } catch (err) { alert("Import failed"); }
}

async function clearHistory() {
    if (!confirm("Are you sure you want to clear your entire course history? This cannot be undone.")) return;
    try {
        const res = await fetch('/api/clear_history', { method: 'POST', headers: {'Content-Type': 'application/json'} });
        if (res.ok) window.location.reload();
        else alert("Failed to clear history.");
    } catch (err) { console.error(err); alert("Error clearing history."); }
}

async function addManualCourse() {
    const code = document.getElementById('manual-code').value.trim();
    let title = document.getElementById('manual-title').value.trim();
    const credits = document.getElementById('manual-credits').value;
    const term = document.getElementById('manual-term').value.trim();
    const grade = document.getElementById('manual-grade').value.trim();
    
    if(!code) { alert("Course code is required."); return; }

    const termPattern = /^(Fall|Winter|Spring|Summer)?\s*\d{4}$/i;
    if (term && !termPattern.test(term)) {
        alert("Invalid term format. Use 'Fall 2024', 'Spring 2025', etc.");
        return;
    }

    try {
        const res = await fetch('/api/add_manual_course', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({code, title, credits, term, grade})
        });
        const data = await res.json();

        if (data.status === 'title_needed') {
            const userTitle = prompt(`We found course code ${code}, but couldn't verify the title. Please enter the course title:`, title || "");
            if (userTitle !== null) { 
                 const retryRes = await fetch('/api/add_manual_course', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({code, title: userTitle, credits, term, grade, force: true})
                });
                if (retryRes.ok) window.location.reload();
            }
        } else if (data.status === 'success') {
            window.location.reload();
        } else {
            alert(data.message || "Failed to add course");
        }
    } catch (err) {
        alert("Failed to add course");
        console.error(err);
    }
}

// Check Progress is now handled by addTracker for multi-track support
// But we keep this if needed for legacy single mode or refactored into addTracker
async function checkProgress() {
    // This function is effectively replaced by addTracker for the new UI
    // Leaving empty or redirecting logic to avoid errors if called elsewhere
    addTracker(); 
}

function sortHistory() {
    const table = document.getElementById('history-table').querySelector('tbody');
    const rows = Array.from(table.rows);
    const key = document.getElementById('sort-key').value;
    const order = document.getElementById('sort-order').value;
    if (rows.length <= 1) return; 

    rows.sort((a, b) => {
        let valA = a.getAttribute(`data-${key}`);
        let valB = b.getAttribute(`data-${key}`);
        
        if (key === 'term') {
            valA = parseTerm(valA);
            valB = parseTerm(valB);
        } else if (key === 'credits') {
            valA = parseFloat(valA) || 0;
            valB = parseFloat(valB) || 0;
        } else {
            valA = valA ? valA.toLowerCase() : '';
            valB = valB ? valB.toLowerCase() : '';
        }
        
        if (valA < valB) return order === 'asc' ? -1 : 1;
        if (valA > valB) return order === 'asc' ? 1 : -1;
        return 0;
    });
    rows.forEach(row => table.appendChild(row));
}

function parseTerm(termStr) {
    if (!termStr || termStr === 'Unknown') return 0;
    const yearMatch = termStr.match(/\d{4}/);
    const year = yearMatch ? parseInt(yearMatch[0]) : 0;
    let seasonWeight = 0;
    const lowerTerm = termStr.toLowerCase();
    if (lowerTerm.includes('fall')) seasonWeight = 4;
    else if (lowerTerm.includes('summer')) seasonWeight = 3;
    else if (lowerTerm.includes('spring')) seasonWeight = 2;
    else if (lowerTerm.includes('winter')) seasonWeight = 1;
    return year * 10 + seasonWeight;
}

window.viewSchedule = function(scheduleId) {
    const list = document.getElementById('schedules-list');
    list.innerHTML = '';
    const schedules = window.scheduleCache[scheduleId];
    if (!schedules) return;
    
    // Add export button logic to modal if not present
    const modalContent = document.querySelector('#schedule-modal .modal-content');
    if (!document.getElementById('export-schedule-btn')) {
        const btn = document.createElement('button');
        btn.id = 'export-schedule-btn';
        btn.className = 'btn btn-primary';
        btn.style.marginTop = '20px';
        btn.innerText = 'Copy Schedule to Clipboard';
        btn.onclick = () => copyScheduleToClipboard(scheduleId);
        modalContent.appendChild(btn);
    }
    window.currentScheduleId = scheduleId;

    schedules.forEach((sched, i) => {
        const card = document.createElement('div');
        card.className = 'schedule-card';
        let html = `<h4>Option ${i+1}</h4>`;
        sched.forEach(cls => {
            html += `
                <div class="course-row">
                    <span><strong>${cls.course}</strong></span>
                    <span>${cls.times.join(', ')}</span>
                </div>
            `;
        });
        card.innerHTML = html;
        list.appendChild(card);
    });
    document.getElementById('schedule-modal').style.display = 'flex';
};

window.copyScheduleToClipboard = function(scheduleId) {
    const schedules = window.scheduleCache[scheduleId || window.currentScheduleId];
    if (!schedules || schedules.length === 0) return;
    const option1 = schedules[0];
    let text = "My Scarlet Scheduler Plan:\n\n";
    option1.forEach(cls => { text += `${cls.course} (${cls.title})\n  ${cls.times.join(', ')}\n\n`; });
    navigator.clipboard.writeText(text).then(() => { alert("Schedule copied to clipboard!"); });
};

function addGpaRow() {
    const div = document.createElement('div');
    div.className = 'course-input-row';
    div.innerHTML = `
        <input type="text" placeholder="Course Name" class="course-name">
        <input type="number" placeholder="Credits" class="course-credits" value="3">
        <select class="course-grade">
            <option value="4.0">A</option>
            <option value="3.5">B+</option>
            <option value="3.0">B</option>
            <option value="2.5">C+</option>
            <option value="2.0">C</option>
            <option value="1.0">D</option>
            <option value="0.0">F</option>
        </select>
    `;
    document.getElementById('semester-courses').appendChild(div);
}

function calculateGpa() {
    const currentGpa = parseFloat(document.getElementById('current-gpa').value) || 0;
    const completedCredits = parseFloat(document.getElementById('credits-completed').value) || 0;
    
    let totalPoints = currentGpa * completedCredits;
    let totalCredits = completedCredits;
    
    const rows = document.querySelectorAll('.course-input-row');
    rows.forEach(row => {
        const credits = parseFloat(row.querySelector('.course-credits').value) || 0;
        const grade = parseFloat(row.querySelector('.course-grade').value) || 0;
        if (credits > 0) {
            totalPoints += (credits * grade);
            totalCredits += credits;
        }
    });
    
    const predicted = totalCredits > 0 ? (totalPoints / totalCredits).toFixed(3) : "0.000";
    document.getElementById('predicted-gpa').innerText = predicted;
    document.getElementById('gpa-result').style.display = 'block';
}