const marquee = document.getElementById('marquee');
const flightList = document.getElementById('flight-list');
const countEl = document.getElementById('count');

let flights = [];
let currentIndex = 0;
let idleMessage = 'Scanning the skies...';

async function fetchFlights() {
    try {
        const resp = await fetch('/api/flights');
        const data = await resp.json();
        flights = data.flights || [];
        idleMessage = data.idle_message || 'Scanning the skies...';
        updateList();
        updateCount();
    } catch (e) {
        console.error('Failed to fetch flights:', e);
    }
}

function updateMarquee() {
    if (flights.length === 0) {
        marquee.textContent = idleMessage;
        setScrollDuration(idleMessage.length);
        return;
    }

    currentIndex = currentIndex % flights.length;
    const text = flights[currentIndex];
    marquee.textContent = text;
    setScrollDuration(text.length);

    // Highlight active in list
    document.querySelectorAll('.flight-item').forEach((el, i) => {
        el.classList.toggle('active', i === currentIndex);
    });

    currentIndex++;
}

function setScrollDuration(textLength) {
    // ~8 chars per second for readable scroll speed
    const duration = Math.max(textLength / 8, 4);
    marquee.style.animationDuration = duration + 's';
}

function updateList() {
    if (flights.length === 0) {
        flightList.innerHTML = '<div class="idle">' + idleMessage + '</div>';
        return;
    }

    let html = '<div class="flight-list-title">NEARBY AIRCRAFT</div>';
    flights.forEach((f, i) => {
        const activeClass = i === (currentIndex % flights.length) ? ' active' : '';
        html += `<div class="flight-item${activeClass}">
            <span class="index">${i + 1}.</span>
            <span>${f}</span>
        </div>`;
    });
    flightList.innerHTML = html;
}

function updateCount() {
    if (flights.length === 0) {
        countEl.textContent = '';
    } else {
        countEl.textContent = flights.length + ' aircraft';
    }
}

// Poll API every 5 seconds
fetchFlights();
setInterval(fetchFlights, 5000);

// Cycle marquee text when animation ends
marquee.addEventListener('animationiteration', updateMarquee);

// Initial marquee setup
updateMarquee();
