// Scarlet Scheduler AI - Frontend JavaScript v3.0.0

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
    initializeSearchableDropdowns();
    
    // Scroll to bottom of chat
    if (chatContainer) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    // Handle chat form submission
    if (chatForm) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = userInput.value.trim();
            const chatId = document.getElementById('current-chat-id').value;
            
            if (!text) return;

            // Show user message immediately
            appendMessage('user', text);
            userInput.value = '';
            userInput.disabled = true;

            // Show thinking animation
            const thinkingId = showThinkingAnimation();

            try {
                const response = await fetch('/api/send_message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: chatId, text: text })
                });
                
                // Remove thinking animation
                removeThinkingAnimation(thinkingId);
                
                const data = await response.json();
                appendMessage('ai', data.ai_message.text, data.ai_message.schedules);
                
                // Update URL if chat ID changed
                if (chatId != data.chat_id) {
                    window.history.pushState({}, '', `/chat?id=${data.chat_id}`);
                }
            } catch (err) {
                console.error(err);
                removeThinkingAnimation(thinkingId);
                appendMessage('ai', "Sorry, I encountered an error. Please try again.");
            } finally {
                userInput.disabled = false;
                userInput.focus();
            }
        });
    }

    // Handle new chat button
    if (newChatBtn) {
        newChatBtn.addEventListener('click', createNewChat);
    }
});

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

// Make it globally available
window.createNewChat = createNewChat;

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

// Multi-Tracker Logic
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
        card.className = 'data-card tracker-card';
        card.id = trackerId;
        
        // Check if we have structured requirements
        const hasStructured = data.core_requirements && data.electives;
        
        let contentHtml = '';
        
        if (hasStructured) {
            // Display structured requirements
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
                <button class="tracker-remove" onclick="removeTracker('${trackerId}')"><i class="fas fa-times"></i></button>
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

// Schedule button initialization
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

// Delete chat button initialization
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

// Append message to chat
function appendMessage(role, text, schedules = null) {
    const container = document.getElementById('chat-container');
    if (!container) return;
    
    // Remove empty state if present
    const emptyState = container.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }
    
    const msgDiv = document.createElement('div');
    msgDiv.className = `message message-${role}`;
    
    let contentHtml = `<div class="message-content">${escapeHtml(text)}`;
    
    if (schedules && schedules.length > 0) {
        const scheduleId = 'sched_' + Date.now() + '_' + Math.floor(Math.random() * 10000);
        window.scheduleCache[scheduleId] = schedules;
        
        contentHtml += `
            <div class="schedule-preview">
                <button class="btn btn-sm btn-outline view-schedule-btn" 
                        style="margin-top:10px" 
                        data-schedule-id="${scheduleId}"
                        onclick="viewSchedule('${scheduleId}')">
                    View ${schedules.length} Schedule${schedules.length > 1 ? 's' : ''}
                </button>
            </div>`;
    }
    
    contentHtml += `</div><div class="message-time">Just now</div>`;
    msgDiv.innerHTML = contentHtml;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

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
        document.getElementById('import-modal').style.display = 'none';
        
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
    const term = document.getElementById('manual-term').value.trim();
    const grade = document.getElementById('manual-grade').value.trim();
    
    if (!code) {
        alert("Course code is required.");
        return;
    }

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

// Show thinking animation
function showThinkingAnimation() {
    const container = document.getElementById('chat-container');
    if (!container) return null;
    
    const thinkingId = 'thinking_' + Date.now();
    const thinkingDiv = document.createElement('div');
    thinkingDiv.id = thinkingId;
    thinkingDiv.className = 'message message-ai thinking-message';
    thinkingDiv.innerHTML = `
        <div class="message-content">
            <div class="thinking-animation">
                <div class="thinking-dot"></div>
                <div class="thinking-dot"></div>
                <div class="thinking-dot"></div>
            </div>
            <span class="thinking-text">Thinking...</span>
        </div>
    `;
    container.appendChild(thinkingDiv);
    container.scrollTop = container.scrollHeight;
    return thinkingId;
}

// Remove thinking animation
function removeThinkingAnimation(thinkingId) {
    if (!thinkingId) return;
    const thinkingEl = document.getElementById(thinkingId);
    if (thinkingEl) {
        thinkingEl.remove();
    }
}

// View schedule modal with pagination
window.viewSchedule = function(scheduleId) {
    const list = document.getElementById('schedules-list');
    if (!list) return;
    
    list.innerHTML = '';
    const schedules = window.scheduleCache[scheduleId];
    if (!schedules) return;
    
    window.currentScheduleId = scheduleId;
    window.currentScheduleIndex = 0;
    window.totalSchedules = schedules.length;

    // Render single schedule
    function renderSchedule(index) {
        if (index < 0 || index >= schedules.length) return;
        
        list.innerHTML = '';
        const sched = schedules[index];
        
        // Handle both old format (array) and new format (object with courses/benefits)
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
        list.appendChild(card);
    }
    
    // Initial render
    renderSchedule(0);
    
    // Store render function globally for navigation
    window.renderSchedule = renderSchedule;
    
    document.getElementById('schedule-modal').style.display = 'flex';
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

// GPA Calculator
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