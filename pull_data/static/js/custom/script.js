// Sample session data - Replace with your actual data source
const sessions = [
    {
        id: 1,
        title: "",
        date: "2026-01-15",
        time: "08:00 AM - 09:30 AM",
        available: true
    },
    {
        id: 2,
        title: "",
        date: "2026-01-15",
        time: "10:00 AM - 12:00 PM",
        available: true
    },
    {
        id: 3,
        title: "",
        date: "2026-01-16",
        time: "02:00 PM - 05:00 PM",
        available: true
    },
    {
        id: 4,
        title: "",
        date: "2026-01-17",
        time: "09:00 AM - 11:00 AM",
        available: false
    },
    {
        id: 5,
        title: "",
        date: "2026-01-18",
        time: "03:00 PM - 05:00 PM",
        available: true
    },
    {
        id: 6,
        title: "",
        date: "2026-01-19",
        time: "10:30 AM - 12:30 PM",
        available: true
    },
    {
        id: 7,
        title: "",
        date: "2026-01-20",
        time: "01:00 PM - 03:00 PM",
        available: true
    },
    {
        id: 8,
        title: "",
        date: "2026-01-22",
        time: "11:00 AM - 01:00 PM",
        available: true
    },
    {
        id: 9,
        title: "",
        date: "2026-01-23",
        time: "04:00 PM - 06:00 PM",
        available: false
    }
];

// State management
let selectedSessions = [];

// DOM Elements
const sessionsGrid = document.getElementById('sessionsGrid');
const summaryContent = document.getElementById('summaryContent');
const selectedCount = document.getElementById('selectedCount');
const confirmBooking = document.getElementById('confirmBooking');
const successModal = document.getElementById('successModal');
const closeModal = document.getElementById('closeModal');

// Initialize the application
function init() {
    renderSessions();
    updateSummary();
    attachEventListeners();
}

// Render all sessions
function renderSessions() {
    sessionsGrid.innerHTML = '';

    sessions.forEach(session => {
        const sessionCard = createSessionCard(session);
        sessionsGrid.appendChild(sessionCard);
    });
}

// Create a session card element
function createSessionCard(session) {
    const card = document.createElement('div');
    card.className = `session-card ${!session.available ? 'booked' : ''}`;
    card.id = `session-${session.id}`;

    const formattedDate = formatDate(session.date);

    card.innerHTML = `
        <div class="session-content">
            <div class="session-header">
                <h3 class="session-title">${session.title}</h3>
                <span class="session-status ${session.available ? 'available' : 'booked'}">
                    ${session.available ? 'Available' : 'Booked'}
                </span>
            </div>
            <div class="session-info">
                <div class="session-detail">
                    <svg class="session-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" stroke-width="2"/>
                        <line x1="16" y1="2" x2="16" y2="6" stroke-width="2" stroke-linecap="round"/>
                        <line x1="8" y1="2" x2="8" y2="6" stroke-width="2" stroke-linecap="round"/>
                        <line x1="3" y1="10" x2="21" y2="10" stroke-width="2"/>
                    </svg>
                    <span>${formattedDate}</span>
                </div>
                <div class="session-detail">
                    <svg class="session-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <circle cx="12" cy="12" r="10" stroke-width="2"/>
                        <polyline points="12 6 12 12 16 14" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                    <span>${session.time}</span>
                </div>
            </div>
            ${session.available ? `
                <div class="checkbox-wrapper">
                    <input type="checkbox" 
                           class="custom-checkbox" 
                           id="checkbox-${session.id}"
                           data-session-id="${session.id}">
                    <label for="checkbox-${session.id}" class="checkbox-label">
                        Select this session
                    </label>
                </div>
            ` : ''}
        </div>
    `;

    if (session.available) {
        const checkbox = card.querySelector('.custom-checkbox');
        checkbox.addEventListener('change', (e) => handleSessionSelection(e, session));

        card.addEventListener('click', (e) => {
            if (e.target !== checkbox && !e.target.classList.contains('checkbox-label')) {
                checkbox.checked = !checkbox.checked;
                checkbox.dispatchEvent(new Event('change'));
            }
        });
    }

    return card;
}

// Handle session selection (single selection only)
function handleSessionSelection(event, session) {
    const isChecked = event.target.checked;

    if (isChecked) {
        // Deselect all previously selected sessions
        selectedSessions.forEach(s => {
            const prevCheckbox = document.getElementById(`checkbox-${s.id}`);
            if (prevCheckbox) {
                prevCheckbox.checked = false;
            }
            const prevCard = document.getElementById(`session-${s.id}`);
            if (prevCard) {
                prevCard.classList.remove('selected');
            }
        });

        // Clear the array and add only the new selection
        selectedSessions = [session];
        document.getElementById(`session-${session.id}`).classList.add('selected');
    } else {
        selectedSessions = selectedSessions.filter(s => s.id !== session.id);
        document.getElementById(`session-${session.id}`).classList.remove('selected');
    }

    updateSummary();
    updateSelectedCount();
}

// Update the booking summary
function updateSummary() {
    if (selectedSessions.length === 0) {
        summaryContent.innerHTML = '<p class="empty-state">No sessions selected yet</p>';
        confirmBooking.disabled = true;
    } else {
        const summaryList = document.createElement('div');
        summaryList.className = 'summary-list';

        selectedSessions.forEach(session => {
            const summaryItem = createSummaryItem(session);
            summaryList.appendChild(summaryItem);
        });

        summaryContent.innerHTML = '';
        summaryContent.appendChild(summaryList);
        confirmBooking.disabled = false;
    }
}

// Create a summary item element
function createSummaryItem(session) {
    const item = document.createElement('div');
    item.className = 'summary-item';
    item.id = `summary-${session.id}`;

    const formattedDate = formatDate(session.date);

    item.innerHTML = `
        <div class="summary-item-info">
            <h4>${session.title}</h4>
            <p>${formattedDate} • ${session.time}</p>
        </div>
        <button class="remove-btn" data-session-id="${session.id}" aria-label="Remove session">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <line x1="18" y1="6" x2="6" y2="18" stroke-width="2" stroke-linecap="round"/>
                <line x1="6" y1="6" x2="18" y2="18" stroke-width="2" stroke-linecap="round"/>
            </svg>
        </button>
    `;

    const removeBtn = item.querySelector('.remove-btn');
    removeBtn.addEventListener('click', () => removeSession(session.id));

    return item;
}

// Remove a session from selection
function removeSession(sessionId) {
    selectedSessions = selectedSessions.filter(s => s.id !== sessionId);

    const checkbox = document.getElementById(`checkbox-${sessionId}`);
    if (checkbox) {
        checkbox.checked = false;
    }

    const sessionCard = document.getElementById(`session-${sessionId}`);
    if (sessionCard) {
        sessionCard.classList.remove('selected');
    }

    updateSummary();
    updateSelectedCount();
}

// Update the selected count badge
function updateSelectedCount() {
    selectedCount.textContent = selectedSessions.length;

    // Add pulse animation
    selectedCount.parentElement.classList.add('pulse');
    setTimeout(() => {
        selectedCount.parentElement.classList.remove('pulse');
    }, 400);
}

// Handle booking confirmation
function handleConfirmBooking() {
    if (selectedSessions.length === 0) return;

    // Here you would typically send the booking data to your backend
    console.log('Booking confirmed for sessions:', selectedSessions);

    // Show success modal
    successModal.classList.add('show');

    // Reset selections after a delay
    setTimeout(() => {
        resetBooking();
    }, 500);
}

// Reset the booking state
function resetBooking() {
    selectedSessions.forEach(session => {
        const checkbox = document.getElementById(`checkbox-${session.id}`);
        if (checkbox) {
            checkbox.checked = false;
        }

        const sessionCard = document.getElementById(`session-${session.id}`);
        if (sessionCard) {
            sessionCard.classList.remove('selected');
        }
    });

    selectedSessions = [];
    updateSummary();
    updateSelectedCount();
}

// Close the success modal
function handleCloseModal() {
    successModal.classList.remove('show');
}

// Format date to readable string
function formatDate(dateString) {
    const date = new Date(dateString);
    const options = { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' };
    return date.toLocaleDateString('en-US', options);
}

// Attach global event listeners
function attachEventListeners() {
    confirmBooking.addEventListener('click', handleConfirmBooking);
    closeModal.addEventListener('click', handleCloseModal);

    // Close modal when clicking outside
    successModal.addEventListener('click', (e) => {
        if (e.target === successModal) {
            handleCloseModal();
        }
    });

    // Keyboard accessibility for modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && successModal.classList.contains('show')) {
            handleCloseModal();
        }
    });
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

// Export functions for potential external use
window.BookingApp = {
    getSessions: () => sessions,
    getSelectedSessions: () => selectedSessions,
    addSession: (session) => {
        sessions.push(session);
        renderSessions();
    },
    removeSessionById: (id) => removeSession(id)
};
