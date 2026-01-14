document.addEventListener('DOMContentLoaded', () => {
    const chatBox = document.getElementById('chat-box');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    
    const inputArea = document.querySelector('.input-area');
    const importBtn = document.createElement('button');
    importBtn.innerHTML = '<i class="fas fa-file-import"></i>';
    importBtn.title = "Import Course History";
    importBtn.style.marginLeft = "10px";
    importBtn.style.backgroundColor = "#555";
    
    const historyBtn = document.createElement('button');
    historyBtn.innerHTML = '<i class="fas fa-history"></i>';
    historyBtn.title = "View Imported History";
    historyBtn.style.marginLeft = "10px";
    historyBtn.style.backgroundColor = "#007bff";
    historyBtn.style.display = "none"; 

    // NEW: Clear History Button
    const clearBtn = document.createElement('button');
    clearBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
    clearBtn.title = "Clear History";
    clearBtn.style.marginLeft = "10px";
    clearBtn.style.backgroundColor = "#dc3545";
    clearBtn.style.display = "none";

    inputArea.insertBefore(importBtn, sendBtn);
    inputArea.insertBefore(historyBtn, sendBtn);
    inputArea.insertBefore(clearBtn, sendBtn);

    let currentHistory = [];

    historyBtn.addEventListener('click', () => {
        showHistoryModal(currentHistory);
    });
    
    clearBtn.addEventListener('click', async () => {
        if(confirm("Are you sure you want to clear your course history?")) {
            await fetch('/api/clear_history', { method: 'POST' });
            currentHistory = [];
            historyBtn.style.display = "none";
            clearBtn.style.display = "none";
            addMessage("History cleared.", 'bot-message');
        }
    });

    function showHistoryModal(courses) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.style.position = 'fixed';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.width = '100%';
        overlay.style.height = '100%';
        overlay.style.backgroundColor = 'rgba(0,0,0,0.85)';
        overlay.style.display = 'flex';
        overlay.style.justifyContent = 'center';
        overlay.style.alignItems = 'center';
        overlay.style.zIndex = '2000';

        const modal = document.createElement('div');
        modal.className = 'modal-content';
        modal.style.background = 'white';
        modal.style.padding = '30px';
        modal.style.borderRadius = '12px';
        modal.style.width = '95%';
        modal.style.height = '90%';
        modal.style.maxWidth = '1400px';
        modal.style.display = 'flex';
        modal.style.flexDirection = 'column';
        modal.innerHTML = '<button id="close-history" style="align-self:flex-end;">Close</button>';
        
        const list = document.createElement('div');
        list.style.overflowY = 'auto';
        courses.forEach(c => {
            const d = document.createElement('div');
            d.innerText = `${c.code} - ${c.grade} (${c.semester})`;
            list.appendChild(d);
        });
        modal.appendChild(list);
        
        modal.querySelector('#close-history').onclick = () => overlay.remove();
        document.body.appendChild(overlay);
    }

    importBtn.addEventListener('click', async () => {
        const text = prompt("Paste your Degree Navigator history here:");
        if (!text) return;
        addMessage("Importing history...", 'bot-message', true);
        try {
            const response = await fetch('/api/parse_history', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            });
            const data = await response.json();
            const loadingMsg = document.querySelector('div[id^="loading-"]');
            if (loadingMsg) loadingMsg.remove();

            if (data.courses && data.courses.length > 0) {
                currentHistory = data.courses;
                historyBtn.style.display = "inline-block";
                clearBtn.style.display = "inline-block";
                addMessage(`✅ Imported ${data.courses.length} courses.`, 'bot-message');
            } else {
                addMessage("No courses found.", 'bot-message error');
            }
        } catch (e) {
            console.error(e);
            addMessage("Error importing.", 'bot-message error');
        }
    });

    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    sendBtn.addEventListener('click', sendMessage);

    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        addMessage(text, 'user-message');
        userInput.value = '';
        const loadingId = addMessage('Thinking...', 'bot-message', true);

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });
            const data = await response.json();
            removeMessage(loadingId);

            if (data.message) {
                addMessage(data.message, 'bot-message');
            }

            if (data.schedules && data.schedules.length > 0) {
                displaySchedules(data.schedules);
            }

        } catch (error) {
            removeMessage(loadingId);
            addMessage("Server Error.", 'bot-message error');
            console.error('Error:', error);
        }
    }

    function addMessage(text, className, isLoading = false) {
        const div = document.createElement('div');
        div.className = `message ${className}`;
        div.innerText = text;
        if (isLoading) div.id = 'loading-' + Date.now();
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
        return div.id;
    }

    function removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    // --- VISUALIZER ---
    function displaySchedules(schedules) {
        const container = document.createElement('div');
        container.className = 'schedule-results';
        
        const limit = Math.min(schedules.length, 5);
        
        for (let i = 0; i < limit; i++) {
            const sched = schedules[i];
            const schedDiv = document.createElement('div');
            schedDiv.className = 'schedule-card';
            schedDiv.innerHTML = `
                <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                    <strong>Option ${i + 1}</strong>
                    <button class="view-grid-btn" style="font-size:0.8em; padding:2px 8px;">View Calendar</button>
                </div>
            `;
            
            const ul = document.createElement('ul');
            sched.forEach(section => {
                const li = document.createElement('li');
                let timeDisplay = section.times.length > 0 ? section.times.join(', ') : "Online / By Arrangement";
                const title = section.title || section.course;
                
                li.innerHTML = `
                    <span class="course-code" style="font-weight:bold;">${title}</span> 
                    <small style="color:#666;">(${section.course})</small>
                    <span class="section-idx" style="margin-left:5px; background:#eee; padding:1px 4px; border-radius:3px;">Sec ${section.index}</span>
                    <br><span style="color:#666; font-size:0.85em;">${timeDisplay}</span>
                `;
                ul.appendChild(li);
            });
            schedDiv.appendChild(ul);
            
            const calendarDiv = createCalendarGrid(sched);
            calendarDiv.style.display = 'none';
            schedDiv.appendChild(calendarDiv);
            
            const btn = schedDiv.querySelector('.view-grid-btn');
            btn.onclick = () => {
                if (calendarDiv.style.display === 'none') {
                    calendarDiv.style.display = 'grid';
                    ul.style.display = 'none';
                    btn.innerText = "View List";
                } else {
                    calendarDiv.style.display = 'none';
                    ul.style.display = 'block';
                    btn.innerText = "View Calendar";
                }
            };

            container.appendChild(schedDiv);
        }
        
        if (schedules.length > limit) {
            const moreDiv = document.createElement('div');
            moreDiv.className = 'more-results';
            moreDiv.innerText = `+ ${schedules.length - limit} more options available.`;
            container.appendChild(moreDiv);
        }

        chatBox.appendChild(container);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function createCalendarGrid(schedule) {
        const grid = document.createElement('div');
        grid.className = 'calendar-grid';
        grid.style.marginTop = '10px';
        grid.style.border = '1px solid #ddd';
        
        const startHour = 8;
        const endHour = 22;
        const days = ['M', 'T', 'W', 'TH', 'F'];
        
        grid.style.gridTemplateColumns = '50px repeat(5, 1fr)';
        grid.style.gridTemplateRows = `30px repeat(${(endHour - startHour) * 2}, 20px)`; 
        
        const timeHeader = document.createElement('div');
        timeHeader.innerText = "";
        grid.appendChild(timeHeader);
        
        days.forEach(day => {
            const d = document.createElement('div');
            d.innerText = day;
            d.style.textAlign = 'center';
            d.style.fontWeight = 'bold';
            d.style.borderBottom = '1px solid #ccc';
            grid.appendChild(d);
        });
        
        for (let h = startHour; h < endHour; h++) {
            const label = document.createElement('div');
            label.innerText = `${h > 12 ? h - 12 : h} ${h >= 12 ? 'PM' : 'AM'}`;
            label.style.fontSize = '0.7em';
            label.style.textAlign = 'right';
            label.style.paddingRight = '5px';
            label.style.gridColumn = '1';
            label.style.gridRow = `${(h - startHour) * 2 + 2} / span 2`;
            grid.appendChild(label);
        }
        
        const colors = ['#e3f2fd', '#fce4ec', '#f3e5f5', '#e8f5e9', '#fff3e0', '#e0f7fa'];
        let colorIdx = 0;

        schedule.forEach(section => {
            const color = colors[colorIdx++ % colors.length];
            const blockTitle = section.title || section.course;
            
            section.times.forEach(timeStr => {
                const match = timeStr.match(/([A-Z]+)\s+(\d{4})-(\d{4})/);
                if (!match) return;
                
                const day = match[1];
                const start = match[2];
                const end = match[3];
                
                const parseTime = (t) => {
                    const h = parseInt(t.substring(0, 2));
                    const m = parseInt(t.substring(2));
                    return h + (m / 60);
                };
                
                let sH = parseTime(start);
                let eH = parseTime(end);
                
                if (sH < 8) sH += 12;
                if (eH < 8) eH += 12;
                
                const colIdx = days.indexOf(day) + 2; 
                if (colIdx < 2) return; 
                
                const rowStart = Math.floor((sH - startHour) * 2) + 2;
                const rowSpan = Math.ceil((eH - sH) * 2);
                
                const block = document.createElement('div');
                block.innerText = `${blockTitle}\n${start}-${end}`;
                block.style.backgroundColor = color;
                block.style.gridColumn = `${colIdx}`;
                block.style.gridRow = `${rowStart} / span ${rowSpan}`;
                block.style.fontSize = '0.75em';
                block.style.padding = '2px';
                block.style.borderRadius = '4px';
                block.style.border = '1px solid #ccc';
                block.style.overflow = 'hidden';
                grid.appendChild(block);
            });
        });
        
        return grid;
    }
});
