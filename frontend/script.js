// ============================================================
// LOCAL TESTING (active right now)
// ============================================================
const API_BASE = 'http://localhost:8000/api';
const WS_URL = 'ws://localhost:8000/ws';

// ============================================================
// ONRENDER DEPLOYMENT
// When ready to deploy, comment out the two lines above and
// uncomment the two lines below. Replace the URL with your
// actual Render app URL.
// ============================================================
// const API_BASE = 'https://your-app-name.onrender.com/api';
// const WS_URL  = 'wss://your-app-name.onrender.com/ws';

const grid = document.getElementById('parkingGrid');
const modal = document.getElementById('qrModal');
const loading = document.getElementById('loadingOverlay');
const closeBtn = document.getElementById('closeModal');
const qrImage = document.getElementById('qrImage');
const tokenText = document.getElementById('tokenText');

// Connect WebSocket
let ws;
function connectWebSocket() {
    ws = new WebSocket(WS_URL);
    
    ws.onmessage = (event) => {
        const slotsState = JSON.parse(event.data);
        renderSlots(slotsState);
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected. Reconnecting in 3s...');
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        ws.close();
    };
}

// Initial fetch & render
function renderSlots(slots) {
    grid.innerHTML = '';
    
    Object.keys(slots).forEach(slotId => {
        const data = slots[slotId];
        
        const card = document.createElement('div');
        card.className = `slot-card glass-panel ${data.status}`;
        card.onclick = () => handleSlotClick(slotId, data.status);
        
        const idElem = document.createElement('div');
        idElem.className = 'slot-id';
        idElem.textContent = `Slot ${slotId}`;
        
        const statusElem = document.createElement('div');
        statusElem.className = 'slot-status';
        statusElem.textContent = data.status;
        
        const icon = document.createElement('div');
        icon.className = 'car-icon';
        
        card.appendChild(idElem);
        card.appendChild(statusElem);
        card.appendChild(icon);
        
        grid.appendChild(card);
    });
}

// Handle booking
async function handleSlotClick(slotId, status) {
    if (status !== 'empty') {
        // Can't book if booked or occupied
        return;
    }
    
    // Confirm booking
    const confirmBook = confirm(`Do you want to book Slot ${slotId}?`);
    if (!confirmBook) return;
    
    loading.classList.add('active');
    
    try {
        const response = await fetch(`${API_BASE}/book`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ slot_id: parseInt(slotId) })
        });
        
        const result = await response.json();
        
        if (response.ok && !result.error) {
            // Show QR code
            qrImage.src = result.qr_code;
            tokenText.textContent = result.token;
            modal.classList.add('active');
        } else {
            alert('Failed to book: ' + (result.error || 'Unknown error'));
        }
    } catch (err) {
        console.error(err);
        alert('Network error while booking.');
    } finally {
        loading.classList.remove('active');
    }
}

// Modal closing
closeBtn.onclick = () => {
    modal.classList.remove('active');
};

// Start
connectWebSocket();
