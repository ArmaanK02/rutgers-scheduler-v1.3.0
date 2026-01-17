// Scarlet Scheduler AI - Intelligent Frontend v4.1 (Complete)

// Global cache for schedule data
if (!window.scheduleCache) {
    window.scheduleCache = {};
}

let activeTrackers = 0;
const MAX_TRACKERS = 5;

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Core UI Features
    initializeToS();
    initializeTheme();
    initializeChat();

    // 2. Initialize Legacy/Functional Features
    initializeScheduleButtons();
    initializeDeleteButtons();
    initializeSearchableDropdowns();

    // 3. Auto-scroll chat on load
    const chatContainer = document.getElementById('chat-container');
    if (chatContainer) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    // 4. Handle "New Chat" button if present
    const newChatBtn = document.getElementById('new-chat-btn'); // Sidebar button
    if (newChatBtn) {
        newChatBtn.addEventListener('click', createNewChat);
    }

    // 5. Check for Demo Mode
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('demo') === 'true') {
        // If we are on the chat page
        if (document.getElementById('chat-container')) {
            startDemo();
        }
    }
});

/* =========================================
   SECTION 1: NEW UI FEATURES (Theme, ToS)
   ========================================= */

// --- Terms of Service (Safe Harbor) ---
function initializeToS() {
    const modal = document.getElementById('tos-modal');
    const btn = document.getElementById('accept-tos-btn');
    
    // Check if modal exists first
    if (!modal) return;
    
    if (!localStorage.getItem('tos_accepted_v4')) {
        modal.classList.add('active');
    }

    if (btn) {
        btn.addEventListener('click', () => {
            localStorage.setItem('tos_accepted_v4', 'true');
            modal.classList.remove('active');
        });
    }
}

// --- Theme Toggle (Dark/Light) ---
function initializeTheme() {
    const toggle = document.getElementById('theme-toggle');
    const icon = toggle ? toggle.querySelector('.fa-toggle-on') : null;
    const html = document.documentElement;

    // Check saved preference or default to dark
    const savedTheme = localStorage.getItem('theme') || 'dark';
    html.setAttribute('data-theme', savedTheme);
    updateToggleIcon(savedTheme);

    if (toggle) {
        toggle.addEventListener('click', () => {
            const current = html.getAttribute('data-theme');
            const newTheme = current === 'dark' ? 'light' : 'dark';
            
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateToggleIcon(newTheme);
        });
    }

    function updateToggleIcon(theme) {
        if (!icon) return;
        if (theme === 'dark') {
            icon.className = 'fa-solid fa-toggle-on';
            icon.style.color = 'var(--accent-primary)';
        } else {
            icon.className = 'fa-solid fa-toggle-off';
            icon.style.color = 'var(--text-muted)';
        }
    }
}

/* =========================================
   SECTION 2: CHAT LOGIC & DEMO MODE
   ========================================= */

function initializeChat() {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('user-input');
    // Note: The new UI uses ID "chat-container" for the history list, 
    // ensuring compatibility with old logic
    const container = document.getElementById('chat-container');

    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;

        // UI: Add User Message
        addMessage(text, 'user');
        input.value = '';
        input.disabled = true;
        
        // UI: Add Thinking Indicator
        const thinkingId = addThinkingIndicator();

        try {
            // API Call
            const chatId = document.getElementById('current-chat-id').value;
            const response = await fetch('/api/send_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: chatId, text: text })
            });
            const data = await response.json();

            // UI: Remove Thinking, Add AI Response
            removeThinkingIndicator(thinkingId);
            addMessage(data.ai_message.text, 'ai', data.ai_message.schedules);

            // Update URL if new chat
            if (chatId != data.chat_id) {
                const hiddenInput = document.getElementById('current-chat-id');
                if (hiddenInput) hiddenInput.value = data.chat_id;
                window.history.pushState({}, '', `/chat?id=${data.chat_id}`);
                
                // Refresh to show new chat in sidebar if needed (simple way)
                // Or ideally, update DOM dynamically. For now, we update history state.
            }

        } catch (err) {
            console.error(err);
            removeThinkingIndicator(thinkingId);
            addMessage("I'm having trouble connecting to the advising server. Please try again.", 'ai');
        } finally {
            input.disabled = false;
            input.focus();
        }
    });
}

function addMessage(text, role, schedules = null) {
    const container = document.getElementById('chat-container');
    if (!container) return;

    const div = document.createElement('div');
    div.className = `message ${role}`;
    
    let avatarIcon = role === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot" style="color:var(--accent-primary)"></i>';
    
    let html = `
        <div class="msg-avatar">${avatarIcon}</div>
        <div class="msg-content">
            ${escapeHtml(text)}
    `;

    // If schedules exist, append a "Superior" preview card
    if (schedules && schedules.length > 0) {
        const schedId = 'sched_' + Date.now();
        window.scheduleCache = window.scheduleCache || {};
        window.scheduleCache[schedId] = schedules;

        html += `
            <div class="schedule-preview-card">
                <div class="schedule-header-row">
                    <span style="font-weight:600; color:var(--accent-primary)">
                        <i class="fa-solid fa-layer-group"></i> ${schedules.length} Options Found
                    </span>
                    <span class="badge-benefit">AI Optimized</span>
                </div>
                <div style="font-size:0.85rem; color:var(--text-muted); margin-bottom:15px;">
                    I've analyzed constraints and found ${schedules.length} conflict-free paths.
                </div>
                <button class="btn-action" onclick="viewSchedule('${schedId}')" style="width:100%">
                    <i class="fa-regular fa-eye"></i> View & Compare Schedules
                </button>
            </div>
        `;
    }

    html += `</div>`;
    div.innerHTML = html;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function addThinkingIndicator() {
    const container = document.getElementById('chat-container');
    if (!container) return null;

    const id = 'thinking-' + Date.now();
    const div = document.createElement('div');
    div.className = 'message ai';
    div.id = id;
    div.innerHTML = `
        <div class="msg-avatar"><i class="fa-solid fa-robot" style="color:var(--accent-primary)"></i></div>
        <div class="msg-content">
            <div class="typing-dots">
                <div class="dot"></div><div class="dot"></div><div class="dot"></div>
            </div>
        </div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return id;
}

function removeThinkingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML.replace(/\n/g, '<br>');
}

// --- Demo Mode Logic ---
function startDemo() {
    const demoSteps = [
        { text: "Find me an easy schedule for Computer Science.", delay: 1000 },
        { text: "Building schedule... Finding CS 111, Math 151...", role: "ai", delay: 2000 },
        { text: "I found 3 schedules. Option 1 has no Friday classes!", role: "ai", schedules: [{id: 1, courses: []}], delay: 3500 }
    ];

    let currentStep = 0;
    
    function playStep() {
        if (currentStep >= demoSteps.length) return;
        
        const step = demoSteps[currentStep];
        setTimeout(() => {
            if (step.role === 'ai') {
                addMessage(step.text, 'ai', step.schedules);
            } else {
                addMessage(step.text, 'user');
            }
            currentStep++;
            playStep();
        }, step.delay);
    }
    
    // Clear chat first
    const container = document.getElementById('chat-container');
    if (container) {
        container.innerHTML = ''; 
        playStep();
    }
}
window.startDemo = startDemo;

// Create new chat
async function createNewChat() {
    try {
        const res = await fetch('/api/new_chat', { method: 'POST' });
        const data = await res.json();
        window.location.href = `/chat?id=${data.id}`;
    } catch (err) {
        console.error(err);
    }
}
window.createNewChat = createNewChat;

/* =========================================
   SECTION 3: UTILITY FEATURES (History, Dropdowns)
   ========================================= */

// Delete chat button initialization
function initializeDeleteButtons() {
    document.querySelectorAll('.delete-chat-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!confirm("Are you sure you want to delete this chat?")) return;
            
            const chatId = btn.getAttribute('data-chat-id');
            try {
                const res = await fetch('/api/delete_chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({chat_id: chatId})
                });
                
                if (res.ok) {
                    const urlParams = new URLSearchParams(window.location.search);
                    if (urlParams.get('id') == chatId) {
                        window.location.href = '/chat';
                    } else {
                        window.location.reload();
                    }
                }
            } catch (err) {
                console.error(err);
            }
        });
    });
}

// Searchable Dropdown Logic
function initializeSearchableDropdowns() {
    const input = document.getElementById('major-search');
    const list = document.getElementById('major-dropdown-list');
    
    if (!input || !list) return;
    
    const items = Array.from(list.children);
    
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
    
    items.forEach(item => {
        item.addEventListener('click', () => {
            input.value = item.getAttribute('data-value');
            list.style.display = 'none';
        });
    });
    
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.searchable-dropdown')) {
            list.style.display = 'none';
        }
    });
    
    input.addEventListener('focus', () => {
        if (input.value) {
            input.dispatchEvent(new Event('input'));
        } else {
            list.style.display = 'block';
        }
    });
}

/* =========================================
   SECTION 4: TRACKER & PROGRESS LOGIC
   ========================================= */

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
        
        const trackerId = 'tracker-' + Date.now();
        const card = document.createElement('div');
        card.className = 'clean-card tracker-card'; // Changed to clean-card
        card.id = trackerId;
        
        // Check if we have structured requirements
        const hasStructured = data.core_requirements && data.electives;
        
        let contentHtml = '';
        
        if (hasStructured) {
            // Display structured requirements (New complex format)
            const coreCompleted = data.core_requirements.completed || [];
            const coreRemaining = data.core_requirements.remaining || [];
            const coreTotal = data.core_requirements.total || 0;
            
            const coreHtml = `
                <div class="requirement-section">
                    <h4><i class="fas fa-book"></i> Core Requirements (${coreCompleted.length}/${coreTotal})</h4>
                    <div class="req-grid">
                        <div>
                            <h5 style="color: #4caf50; margin-bottom: 10px;">Completed</h5>
                            <ul class="req-list">
                                ${coreCompleted.length ? coreCompleted.map(c => 
                                    `<li><i class="fas fa-check-circle text-success"></i> ${c.code}${c.name ? ` - ${c.name}` : ''}</li>`
                                ).join('') : '<li style="color:#666">None yet</li>'}
                            </ul>
                        </div>
                        <div>
                            <h5 style="color: #ff9800; margin-bottom: 10px;">Remaining</h5>
                            <ul class="req-list">
                                ${coreRemaining.length ? coreRemaining.slice(0, 10).map(c => 
                                    `<li><i class="fas fa-circle text-secondary"></i> ${c.code}${c.name ? ` - ${c.name}` : ''}</li>`
                                ).join('') + (coreRemaining.length > 10 ? `<li>...and ${coreRemaining.length - 10} more</li>` : '') : '<li><i class="fas fa-star text-success"></i> All done!</li>'}
                            </ul>
                        </div>
                    </div>
                </div>
            `;
            
            // Electives section
            let electivesHtml = '<div class="requirement-section" style="margin-top: 20px;"><h4><i class="fas fa-list"></i> Electives</h4>';
            
            ['lower_level', 'upper_level', 'general'].forEach(level => {
                const levelData = data.electives[level] || {};
                const required = levelData.required || 0;
                const completed = levelData.completed || [];
                const remaining = levelData.remaining || [];
                const progress = levelData.progress || 0;
                
                if (required > 0 || completed.length > 0 || remaining.length > 0) {
                    const levelName = level.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
                    electivesHtml += `
                        <div class="elective-category" style="margin-top: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                            <h5>${levelName} Electives (${completed.length}/${required} required)</h5>
                            <div class="progress-bar-container" style="margin: 10px 0;">
                                <div class="progress-bar-fill" style="width: ${progress}%"></div>
                            </div>
                            <div class="req-grid">
                                <div>
                                    <h6 style="color: #4caf50; font-size: 0.9rem;">Completed</h6>
                                    <ul class="req-list" style="font-size: 0.85rem;">
                                        ${completed.length ? completed.map(c => 
                                            `<li><i class="fas fa-check-circle text-success"></i> ${c.code}${c.name ? ` - ${c.name}` : ''}</li>`
                                        ).join('') : '<li style="color:#666">None yet</li>'}
                                    </ul>
                                </div>
                                <div>
                                    <h6 style="color: #ff9800; font-size: 0.9rem;">Available</h6>
                                    <ul class="req-list" style="font-size: 0.85rem; max-height: 100px; overflow-y: auto;">
                                        ${remaining.length ? remaining.slice(0, 8).map(c => 
                                            `<li><i class="fas fa-circle text-secondary"></i> ${c.code}${c.name ? ` - ${c.name}` : ''}</li>`
                                        ).join('') + (remaining.length > 8 ? `<li>...and ${remaining.length - 8} more</li>` : '') : '<li>No options available</li>'}
                                    </ul>
                                </div>
                            </div>
                        </div>
                    `;
                }
            });
            
            electivesHtml += '</div>';
            
            contentHtml = `
                <button class="tracker-remove" onclick="removeTracker('${trackerId}')" style="position:absolute; top:20px; right:20px; background:transparent; border:none; color:#666; cursor:pointer;"><i class="fas fa-times"></i></button>
                <h3><i class="fas fa-graduation-cap"></i> ${major}</h3>
                
                <div class="progress-bar-container">
                    <div class="progress-bar-fill" style="width: ${data.progress}%"></div>
                </div>
                <p style="text-align: right; margin-top: 10px; font-weight: bold;">${data.progress}% Completed</p>
                
                ${coreHtml}
                ${electivesHtml}
                
                ${data.notes ? `<div style="margin-top: 15px; padding: 10px; background: rgba(204,0,51,0.1); border-left: 3px solid var(--accent-red); border-radius: 4px; font-size: 0.9rem;"><strong>Note:</strong> ${data.notes}</div>` : ''}
            `;
        } else {
            // Fallback to simple display
            const completedHtml = data.completed.length ? 
                data.completed.map(c => `<li><i class="fas fa-check-circle text-success"></i> ${c}</li>`).join('') :
                '<li style="color:#666">No requirements met yet</li>';
                
            const remainingHtml = data.remaining.length ?
                data.remaining.slice(0, 5).map(c => `<li><i class="fas fa-circle text-secondary"></i> ${c}</li>`).join('') + 
                (data.remaining.length > 5 ? `<li>...and ${data.remaining.length - 5} more</li>` : '') :
                '<li><i class="fas fa-star text-success"></i> All done!</li>';

            contentHtml = `
                <button class="tracker-remove" onclick="removeTracker('${trackerId}')" style="position:absolute; top:20px; right:20px; background:transparent; border:none; color:#666; cursor:pointer;"><i class="fas fa-times"></i></button>
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
        }
        
        card.innerHTML = contentHtml;
        container.insertBefore(card, container.firstChild);
        activeTrackers++;
        majorInput.value = '';
        
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

// Make globally available
window.addTracker = addTracker;
window.removeTracker = removeTracker;


/* =========================================
   SECTION 5: COURSE HISTORY FUNCTIONS
   ========================================= */

// Upload course history
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
        
        const modal = document.getElementById('import-modal');
        if (modal) modal.classList.remove('active'); // Use new class toggle
        
        if (window.location.pathname === '/history') {
            window.location.reload();
        }
    } catch (err) {
        alert("Import failed");
    }
}

// Clear course history
async function clearHistory() {
    if (!confirm("Are you sure you want to clear your entire course history? This cannot be undone.")) return;
    
    try {
        const res = await fetch('/api/clear_history', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        if (res.ok) {
            window.location.reload();
        } else {
            alert("Failed to clear history.");
        }
    } catch (err) {
        console.error(err);
        alert("Error clearing history.");
    }
}

// Add manual course
async function addManualCourse() {
    const code = document.getElementById('manual-code').value.trim();
    let title = document.getElementById('manual-title').value.trim();
    const credits = document.getElementById('manual-credits').value;
    const term = document.getElementById('manual-term') ? document.getElementById('manual-term').value.trim() : ''; // Optional in new modal
    const grade = document.getElementById('manual-grade') ? document.getElementById('manual-grade').value.trim() : ''; // Optional
    
    if (!code) {
        alert("Course code is required.");
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
            const userTitle = prompt(`Course ${code} found, but title unknown. Enter title:`, title || "");
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

// Sort history table
function sortHistory() {
    const table = document.getElementById('history-table');
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.rows);
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
    
    rows.forEach(row => tbody.appendChild(row));
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

// Expose history functions globally
window.uploadHistory = uploadHistory;
window.clearHistory = clearHistory;
window.addManualCourse = addManualCourse;
window.sortHistory = sortHistory;


/* =========================================
   SECTION 6: SCHEDULE & GPA UTILS
   ========================================= */

// Initialize Schedule Button Listeners
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
            } catch (e) {
                console.error("Failed to parse schedule data", e);
            }
        }
    });
}

// Make viewSchedule global
window.viewSchedule = function(scheduleId) {
    
    const list = document.getElementById('schedules-list');
    
    if (!list) {
        createScheduleModal();
        if (!document.getElementById('schedules-list')) {
             console.error("Schedule modal list container not found!");
             return;
        }
    }
    
    function createScheduleModal() {
        if (document.getElementById('schedule-modal')) return;
        const modalHtml = `
            <div class="modal-overlay" id="schedule-modal">
                <div class="modal-window" style="max-width:1200px; width:95%;">
                    <div class="modal-title" style="justify-content:space-between;">
                        <span>Schedule Viewer</span>
                        <span style="cursor:pointer;" onclick="document.getElementById('schedule-modal').classList.remove('active')">&times;</span>
                    </div>
                    <div class="modal-body" style="max-height:80vh; overflow-y:auto;" id="schedules-list"></div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }
    
    // Ensure modal is active
    const modal = document.getElementById('schedule-modal');
    if (modal) modal.classList.add('active'); // Use new class toggle
    
    const containerList = document.getElementById('schedules-list');
    containerList.innerHTML = '';

    const schedules = window.scheduleCache[scheduleId];
    if (!schedules) return;
    
    window.currentScheduleId = scheduleId;
    window.currentScheduleIndex = 0;
    window.totalSchedules = schedules.length;

    // Render single schedule
    function renderSchedule(index) {
        if (index < 0 || index >= schedules.length) return;
        
        containerList.innerHTML = '';
        const sched = schedules[index];
        
        const scheduleCourses = sched.courses || sched;
        const scheduleBenefits = sched.benefits || {};
        
        // Campus legend
        const campusLegend = `
            <div class="campus-legend">
                <span class="legend-label">Campus Legend:</span>
                <span class="campus-badge campus-online">Online</span>
                <span class="campus-badge campus-busch">Busch</span>
                <span class="campus-badge campus-college-ave">College Avenue</span>
                <span class="campus-badge campus-douglass">Douglass / Cook</span>
                <span class="campus-badge campus-livingston">Livingston</span>
                <span class="campus-badge campus-downtown">Downtown</span>
                <span class="campus-badge campus-camden">Camden</span>
                <span class="campus-badge campus-newark">Newark</span>
                <span class="campus-badge campus-other">Other/Unknown</span>
            </div>
        `;
        
        // Benefits breakdown
        let benefitsHtml = '';
        if (scheduleBenefits.benefits && scheduleBenefits.benefits.length > 0) {
            benefitsHtml = `
                <div class="schedule-benefits">
                    <h5><i class="fas fa-star"></i> Schedule Benefits</h5>
                    <div class="benefits-list">
                        ${scheduleBenefits.benefits.map(b => `<span class="benefit-badge">${b}</span>`).join('')}
                    </div>
                    <div class="schedule-stats">
                        <span><strong>Total Credits:</strong> ${scheduleBenefits.total_credits || 'N/A'}</span>
                        <span><strong>Campuses:</strong> ${scheduleBenefits.campuses ? scheduleBenefits.campuses.join(', ') : 'N/A'}</span>
                    </div>
                </div>
            `;
        }
        
        // Group by day
        const scheduleByDay = {};
        let totalCredits = 0;
        
        scheduleCourses.forEach(cls => {
            totalCredits += cls.credits || 3;
            (cls.times || []).forEach(timeInfo => {
                const day = typeof timeInfo === 'string' ? timeInfo.match(/^([M|T|W|TH|F]+)/)?.[1] : timeInfo.day;
                if (day) {
                    if (!scheduleByDay[day]) {
                        scheduleByDay[day] = [];
                    }
                    scheduleByDay[day].push({
                        course: cls.course,
                        title: cls.title,
                        section: cls.section_number || 'N/A',
                        credits: cls.credits || 3,
                        timeInfo: typeof timeInfo === 'string' ? {time_str: timeInfo} : timeInfo,
                        campus: cls.campus || (typeof timeInfo === 'object' ? timeInfo.campus : ''),
                        room: typeof timeInfo === 'object' ? timeInfo.room : '',
                        instructors: cls.instructors || []
                    });
                }
            });
        });
        
        // Build schedule card
        const card = document.createElement('div');
        card.className = 'schedule-card-detailed';
        
        let html = `
            ${campusLegend}
            <div class="schedule-header">
                <h4>Schedule Option ${index + 1} of ${schedules.length}</h4>
                <div class="schedule-nav">
                    <button class="btn-nav" onclick="navigateSchedule(-1)" ${index === 0 ? 'disabled' : ''}>
                        <i class="fas fa-chevron-left"></i> Previous
                    </button>
                    <span class="schedule-counter">${index + 1} / ${schedules.length}</span>
                    <button class="btn-nav" onclick="navigateSchedule(1)" ${index === schedules.length - 1 ? 'disabled' : ''}>
                        Next <i class="fas fa-chevron-right"></i>
                    </button>
                </div>
            </div>
            ${benefitsHtml}
            <div class="schedule-week-view">
        `;
        
        const days = ['M', 'T', 'W', 'TH', 'F'];
        days.forEach(day => {
            const dayName = {'M': 'Monday', 'T': 'Tuesday', 'W': 'Wednesday', 'TH': 'Thursday', 'F': 'Friday'}[day];
            html += `<div class="schedule-day-column">`;
            html += `<div class="schedule-day-header">${dayName}</div>`;
            if (scheduleByDay[day]) {
                scheduleByDay[day].forEach(item => {
                    const campusClass = `campus-${item.campus.toLowerCase().replace(/\s+/g, '-')}`;
                    html += `
                        <div class="schedule-course-block ${campusClass}">
                            <div class="schedule-course-code"><strong>${item.course}</strong> <span class="section-number">Sec ${item.section}</span></div>
                            <div class="schedule-course-title">${item.title || ''}</div>
                            <div class="schedule-course-time">${item.timeInfo.time_str || item.timeInfo}</div>
                            <div class="schedule-course-details">
                                <span class="credits-badge">${item.credits} credits</span>
                                ${item.room ? `<span class="room-info"><i class="fas fa-map-marker-alt"></i> ${item.room}</span>` : ''}
                            </div>
                            ${item.campus ? `<div class="schedule-course-campus campus-${item.campus.toLowerCase().replace(/\s+/g, '-')}">${item.campus}</div>` : ''}
                            ${item.instructors && item.instructors.length > 0 ? `<div class="schedule-instructor"><i class="fas fa-user"></i> ${item.instructors[0]}</div>` : ''}
                        </div>
                    `;
                });
            } else {
                html += '<div class="schedule-empty-day">No classes</div>';
            }
            html += `</div>`;
        });
        
        html += '</div>';
        html += `<div class="schedule-footer"><strong>Total Credits:</strong> ${totalCredits}</div>`;
        
        card.innerHTML = html;
        containerList.appendChild(card);
    }
    
    // Initial render
    renderSchedule(0);
    window.renderSchedule = renderSchedule;
};

// Navigate between schedules
window.navigateSchedule = function(direction) {
    if (window.currentScheduleIndex === undefined) return;
    const newIndex = window.currentScheduleIndex + direction;
    if (newIndex >= 0 && newIndex < window.totalSchedules) {
        window.currentScheduleIndex = newIndex;
        if (window.renderSchedule) {
            window.renderSchedule(newIndex);
        }
    }
};

// GPA Calculator Functions
window.addGpaRow = function() {
    const container = document.getElementById('semester-courses');
    if (!container) return;
    
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
    container.appendChild(div);
}

window.calculateGpa = function() {
    const currentGpaEl = document.getElementById('current-gpa');
    const creditsCompletedEl = document.getElementById('credits-completed');
    if (!currentGpaEl || !creditsCompletedEl) return;

    const currentGpa = parseFloat(currentGpaEl.value) || 0;
    const completedCredits = parseFloat(creditsCompletedEl.value) || 0;
    
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