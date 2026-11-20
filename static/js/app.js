// =============================================================
//  WanderPulse – Client-Side Application (Upgraded with Live Data)
//  Renders: Live OWM weather badges, Google Places ratings,
//           open status chips, photo thumbnails in Leaflet popups
// =============================================================

// ─── Wizard State ────────────────────────────────────────────
const wizardState = {
    step: 1,
    destinationType: 'Domestic',
    userCountry: 'India',
    budgetRange: 'Budget',
    travelCompanion: 'Solo',
    vibes: ['Relaxation'],
    duration: 5,
    pace: 'Relaxed',
};

let currentRecommendations = [];
let activeDestination      = null;
let leafletMap             = null;
let activeSavedTripId      = null;

// ─── Bootstrap ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initWizardEvents();
    initChatbot();
    updateTripsNavBadge();
});

// =============================================================
//  WIZARD & MODAL EVENT LOGIC
// =============================================================
function initWizardEvents() {
    const wizardModal   = document.getElementById('wizardModal');
    const detailOverlay = document.getElementById('detailModalOverlay');

    document.getElementById('openWizardBtn').onclick  = showWizard;
    document.getElementById('heroStartBtn').onclick   = showWizard;
    document.getElementById('closeWizardBtn').onclick = () => wizardModal.classList.add('hidden');

    // ── Click outside modal overlay to close ──────────────────
    if (detailOverlay) {
        detailOverlay.addEventListener('click', (e) => {
            if (e.target === detailOverlay) {
                closeDetailModal();
            }
        });
    }

    if (wizardModal) {
        wizardModal.addEventListener('click', (e) => {
            if (e.target === wizardModal) {
                wizardModal.classList.add('hidden');
            }
        });
    }

    // ── ESC key listener to close modals ──────────────────────
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeDetailModal();
            if (wizardModal) wizardModal.classList.add('hidden');
        }
    });

    // ── Single-select (.opt-btn) ──────────────────────────────
    document.querySelectorAll('.opt-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const key = btn.dataset.key;
            const val = btn.dataset.val;
            if (!key || !val) return;
            wizardState[key] = val;
            btn.parentElement.querySelectorAll('.opt-btn').forEach(b =>
                b.classList.remove('active-opt', 'border-amber-500'));
            btn.classList.add('active-opt', 'border-amber-500');
        });
    });

    // ── Multi-select vibes (.vibe-btn) ────────────────────────
    document.querySelectorAll('.vibe-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const val = btn.dataset.val;
            if (wizardState.vibes.includes(val)) {
                if (wizardState.vibes.length > 1) {
                    wizardState.vibes = wizardState.vibes.filter(v => v !== val);
                    btn.classList.remove('active-vibe', 'border-amber-500');
                }
            } else {
                wizardState.vibes.push(val);
                btn.classList.add('active-vibe', 'border-amber-500');
            }
        });
    });

    // ── Duration slider ────────────────────────────────────────
    const slider = document.getElementById('durationRange');
    if (slider) {
        slider.oninput = e => {
            const v = parseInt(e.target.value);
            wizardState.duration = v;
            document.getElementById('durationValue').innerText = `${v} ${v === 1 ? 'Day' : 'Days'}`;
        };
    }

    // ── Navigation ─────────────────────────────────────────────
    document.getElementById('nextBtn').onclick = () => {
        if (wizardState.step < 4) {
            wizardState.step++;
            updateWizardStep();
        } else {
            wizardModal.classList.add('hidden');
            fetchRecommendations();
        }
    };

    document.getElementById('prevBtn').onclick = () => {
        if (wizardState.step > 1) {
            wizardState.step--;
            updateWizardStep();
        }
    };
}

function showWizard() {
    wizardState.step = 1;
    updateWizardStep();
    document.getElementById('wizardModal').classList.remove('hidden');
}

function updateWizardStep() {
    document.querySelectorAll('.wizard-step').forEach(el => {
        el.classList.toggle('hidden', parseInt(el.dataset.step) !== wizardState.step);
    });

    const prev = document.getElementById('prevBtn');
    const next = document.getElementById('nextBtn');
    prev.disabled = (wizardState.step === 1);
    next.innerHTML = wizardState.step === 4
        ? `<span>Get Recommendations ✨</span>`
        : `<span>Next Step</span> <i class="fa-solid fa-chevron-right text-xs ml-1"></i>`;

    const titles = ["DESTINATION & BUDGET", "TRAVEL COMPANION", "VIBES & INTERESTS", "DURATION & PACE"];
    document.getElementById('stepCounter').innerText = `STEP ${wizardState.step} OF 4`;
    document.getElementById('stepTitle').innerText   = titles[wizardState.step - 1];
    document.getElementById('progressBar').style.width = `${(wizardState.step / 4) * 100}%`;
}

function resetToHome() {
    document.getElementById('heroSection').classList.remove('hidden');
    document.getElementById('resultsSection').classList.add('hidden');
    document.getElementById('loadingState').classList.add('hidden');
    document.getElementById('myTripsSection').classList.add('hidden');
    document.getElementById('savedTripDetailSection').classList.add('hidden');
}

// =============================================================
//  RECOMMENDATION FETCH & CARD RENDERING
// =============================================================
async function fetchRecommendations() {
    document.getElementById('heroSection').classList.add('hidden');
    document.getElementById('resultsSection').classList.add('hidden');

    const loadingState = document.getElementById('loadingState');
    const stepText = document.getElementById('loadingStepText');
    loadingState.classList.remove('hidden');

    const steps = [
        "Filtering candidate cities from database...",
        "Querying Gemini AI for custom itineraries...",
        "Enriching live OpenWeatherMap data...",
        "Fetching Google Places ratings & photos..."
    ];
    let stepIdx = 0;
    if (stepText) stepText.innerText = steps[0];
    const stepInterval = setInterval(() => {
        stepIdx = (stepIdx + 1) % steps.length;
        if (stepText) stepText.innerText = steps[stepIdx];
    }, 1500);

    try {
        const resp = await fetch('/api/recommend', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(wizardState),
        });
        const res = await resp.json();
        clearInterval(stepInterval);
        loadingState.classList.add('hidden');

        if (res.success && res.data && res.data.length > 0) {
            currentRecommendations = res.data;
            renderCards(currentRecommendations);
            document.getElementById('resultsSection').classList.remove('hidden');
        } else {
            alert('Could not generate recommendations. Please try again.\n\n' + (res.error || ''));
            document.getElementById('heroSection').classList.remove('hidden');
        }
    } catch (err) {
        clearInterval(stepInterval);
        console.error('API Error:', err);
        loadingState.classList.add('hidden');
        alert('Network error connecting to AI services. Please check the server is running.');
        document.getElementById('heroSection').classList.remove('hidden');
    }
}

// ─── Live Weather Badge HTML ──────────────────────────────────
function buildWeatherBadge(lw) {
    if (!lw || lw.condition === 'Unavailable') {
        return `<div class="flex items-center space-x-2 text-xs text-slate-500 italic">
            <i class="fa-solid fa-triangle-exclamation text-slate-600"></i>
            <span>Live weather unavailable</span>
        </div>`;
    }
    const icon = lw.icon_url
        ? `<img src="${lw.icon_url}" alt="${lw.condition}" class="w-8 h-8 object-contain">`
        : `<span class="text-2xl">${lw.emoji}</span>`;

    return `
        <div class="flex items-center space-x-3">
            ${icon}
            <div>
                <div class="font-extrabold text-amber-400 text-sm">${lw.temp}°C</div>
                <div class="text-[11px] text-slate-300">${lw.description}</div>
            </div>
            <div class="ml-auto text-right text-[11px] text-slate-400 space-y-0.5">
                <div><i class="fa-solid fa-droplet text-blue-400 mr-1"></i>${lw.humidity}% humidity</div>
                <div><i class="fa-solid fa-wind text-slate-400 mr-1"></i>${lw.wind_speed} m/s</div>
                <div class="text-[10px] text-slate-600">${lw.source}</div>
            </div>
        </div>
    `;
}

// ─── Render Destination Cards ──────────────────────────────────
function renderCards(list) {
    document.getElementById('resultsBadge').innerText = `${list.length} Destinations`;
    document.getElementById('cardsGrid').innerHTML = list.map(dest => {
        const lw = dest.live_weather || {};
        const saved = isBookmarked(dest.id);
        const weatherBlock = `
            <div class="bg-slate-950/80 p-3 rounded-2xl border border-slate-800/80 mb-4">
                <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
                    Live Weather <span class="text-green-500 ml-1">• ${lw.source || 'N/A'}</span>
                </div>
                ${buildWeatherBadge(lw)}
            </div>`;

        const attractionTags = (dest.attractions || []).slice(0, 3).map(att => {
            const lp    = att.live_places || {};
            const stars = lp.rating ? `⭐ ${lp.rating}` : '';
            return `<span class="px-2.5 py-1 rounded-lg bg-slate-800 text-[11px] text-slate-300 border border-slate-700/50 font-medium">
                📍 ${att.name} ${stars}
            </span>`;
        }).join('');

        return `
        <div class="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden hover:border-amber-500/50 transition duration-300 shadow-2xl flex flex-col justify-between group">
            <div class="p-6">
                <div class="flex justify-between items-start mb-4">
                    <div>
                        <span class="text-[10px] font-bold uppercase tracking-wider text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-md border border-amber-500/20 inline-block mb-1">
                            <i class="fa-solid fa-location-dot mr-1"></i>${dest.location}
                        </span>
                        <h3 class="text-2xl font-extrabold text-slate-100 group-hover:text-amber-400 transition">${dest.name}</h3>
                    </div>
                    <div class="flex items-center space-x-2 shrink-0">
                        <span class="px-3 py-1.5 rounded-full bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 font-black text-xs shadow-md">
                            ${dest.matchPercentage}% Match
                        </span>
                        <button
                            id="bm-${dest.id}"
                            onclick="toggleBookmark('${dest.id}')"
                            title="${saved ? 'Remove from My Trips' : 'Save to My Trips'}"
                            class="bookmark-btn ${saved ? 'bookmarked' : ''}">
                            <i class="fa-${saved ? 'solid' : 'regular'} fa-bookmark text-xs"></i>
                        </button>
                    </div>
                </div>

                <p class="text-slate-300 text-xs sm:text-sm leading-relaxed mb-5">${dest.pitch}</p>
                ${weatherBlock}

                <div class="flex flex-wrap gap-1.5">${attractionTags}</div>
            </div>

            <div class="px-6 pb-6 pt-2 border-t border-slate-800/50">
                <button onclick="openDetail('${dest.id}')"
                    class="w-full py-3 rounded-2xl bg-slate-800 hover:bg-amber-500 hover:text-slate-950 text-slate-200 font-bold text-xs transition duration-200 flex items-center justify-center space-x-2">
                    <span>Explore Itinerary & Map</span>
                    <i class="fa-solid fa-arrow-right text-xs"></i>
                </button>
            </div>
        </div>`;
    }).join('');
}

// =============================================================
//  DETAIL MODAL  (Leaflet map + live data)
// =============================================================

/**
 * closeDetailModal()
 * - Hides the detail view modal.
 * - Properly destroys/removes the Leaflet map instance (map.remove())
 *   to avoid memory leaks and re-initialization errors when opening another city.
 * - Unlocks background body scroll.
 */
function closeDetailModal() {
    const overlay = document.getElementById('detailModalOverlay');
    if (overlay) overlay.classList.add('hidden');
    document.body.classList.remove('modal-open');

    if (leafletMap) {
        leafletMap.remove();
        leafletMap = null;
    }
}

function openDetail(id) {
    activeDestination = currentRecommendations.find(d => d.id === id);
    if (!activeDestination) return;

    const dest = activeDestination;
    const lw = dest.live_weather || {};
    const container = document.getElementById('detailContent');
    if (!container) return;

    // Update AI Chatbot context tag
    document.getElementById('chatContextTag').innerText = dest.name;

    // ── Show the overlay, lock background scroll ──────────────────────────
    const overlay = document.getElementById('detailModalOverlay');
    overlay.classList.remove('hidden');
    document.body.classList.add('modal-open');

    // Scroll the modal body back to top on each open
    const modalBody = document.getElementById('detailModalBody');
    if (modalBody) modalBody.scrollTop = 0;

    // ── Weather panel ──────────────────────────────────────────
    const liveWeatherPanel = `
        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 mb-6">
            <div class="flex justify-between items-center mb-2">
                <span class="font-bold text-xs uppercase tracking-wider text-slate-400">Live Weather Now</span>
                <span class="text-[10px] font-bold ${lw.source === 'OpenWeatherMap Live' ? 'text-green-400' : 'text-slate-500'}">
                    ${lw.source === 'OpenWeatherMap Live' ? '● Live' : '○ Unavailable'}
                </span>
            </div>
            ${buildWeatherBadge(lw)}
            <div class="mt-3 pt-3 border-t border-slate-800 text-[11px] text-slate-400 leading-relaxed">
                <i class="fa-solid fa-calendar-check text-amber-400 mr-1"></i>
                ${dest.weatherInsight || ''}
            </div>
        </div>`;

    // ── Attractions with Places data ───────────────────────────
    const attractionCards = (dest.attractions || []).map(att => {
        const lp        = att.live_places || {};
        const ratingHTML = lp.rating
            ? `<span class="flex items-center space-x-1 text-[11px] font-bold text-amber-400">
                    <i class="fa-solid fa-star text-[10px]"></i>
                    <span>${lp.rating}/5</span>
               </span>`
            : '';
        const openHTML   = lp.open_now === true
            ? `<span class="text-[10px] font-bold text-green-400 bg-green-500/10 px-2 py-0.5 rounded-full border border-green-500/20">Open Now</span>`
            : lp.open_now === false
            ? `<span class="text-[10px] font-bold text-red-400 bg-red-500/10 px-2 py-0.5 rounded-full border border-red-500/20">Closed</span>`
            : '';
        const photoHTML  = lp.photo_url
            ? `<img src="${lp.photo_url}" alt="${att.name}" class="w-full h-24 object-cover rounded-lg mt-2 border border-slate-700/60" onerror="this.remove()">`
            : '';
        const addressHTML = lp.address
            ? `<div class="text-[10px] text-slate-500 mt-1 flex items-center"><i class="fa-solid fa-map-pin mr-1 text-slate-600"></i>${lp.address}</div>`
            : '';
        const sourceBadge = lp.source === 'Google Places Live'
            ? `<span class="text-[9px] text-blue-400 font-bold">Google Places</span>`
            : `<span class="text-[9px] text-slate-600">${lp.source || ''}</span>`;

        return `
            <div class="p-3 rounded-xl bg-slate-900 border border-slate-800/80">
                <div class="flex justify-between items-start">
                    <div class="font-bold text-xs text-slate-100">${att.name}
                        <span class="text-[10px] text-slate-400 font-normal">(${att.category})</span>
                    </div>
                    <div class="flex items-center space-x-1">${ratingHTML} ${openHTML}</div>
                </div>
                <div class="text-[11px] text-slate-400 mt-0.5">${att.description}</div>
                ${addressHTML}
                ${photoHTML}
                <div class="mt-1.5">${sourceBadge}</div>
            </div>`;
    }).join('');

    // ── Food delicacies ────────────────────────────────────────
    const foodCards = (dest.localDelicacies || []).map(f => `
        <div class="p-2.5 rounded-xl bg-slate-900 border border-slate-800/80">
            <div class="font-bold text-xs text-slate-100">${f.name}
                <span class="text-[10px] text-amber-400 font-normal">(${f.type})</span>
            </div>
            <div class="text-[11px] text-slate-400 mt-0.5">${f.description}</div>
        </div>`).join('');

    // ── Budget bars ────────────────────────────────────────────
    const budgetBars = Object.entries(dest.budgetSplit || {}).map(([cat, pct]) => `
        <div>
            <div class="flex justify-between text-xs mb-1">
                <span class="capitalize text-slate-300 font-semibold">${cat}</span>
                <span class="font-bold text-amber-400">${pct}%</span>
            </div>
            <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div class="bg-gradient-to-r from-amber-500 to-yellow-400 h-full rounded-full" style="width:${pct}%"></div>
            </div>
        </div>`).join('');

    // ── Itinerary ──────────────────────────────────────────────
    const itineraryDays = (dest.itinerary || []).map(day => `
        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800">
            <div class="font-bold text-amber-400 text-xs mb-2 uppercase tracking-wider">
                Day ${day.day}: ${day.title}
            </div>
            <ul class="space-y-1.5 text-xs text-slate-300">
                ${(day.activities || []).map(a => `
                    <li class="flex items-start space-x-2">
                        <i class="fa-solid fa-circle-check text-amber-400 text-[10px] mt-1 shrink-0"></i>
                        <span>${a}</span>
                    </li>`).join('')}
            </ul>
        </div>`).join('');

    // ── Packing checklist ──────────────────────────────────────
    const checklistItems = (dest.packingChecklist || []).map(item => `
        <label class="flex items-center space-x-3 bg-slate-950 p-3 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500/50 transition">
            <input type="checkbox" onchange="toggleChecklistItem(this)" class="w-4 h-4 accent-amber-500 rounded cursor-pointer">
            <span class="text-xs text-slate-300 font-medium">${item.item}
                <span class="text-[10px] text-slate-500">(${item.category})</span>
            </span>
        </label>`).join('');

    // ── Assemble modal content ─────────────────────────────────
    container.innerHTML = `
        <!-- Header -->
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-6 pb-4 border-b border-slate-800">
            <div>
                <span class="px-3 py-1 rounded-full bg-amber-500/10 text-amber-400 text-xs font-bold border border-amber-500/20 inline-block mb-2">
                    🎯 ${dest.matchPercentage}% Personal Match
                </span>
                <h2 class="text-3xl font-black">${dest.name}</h2>
                <p class="text-slate-400 text-xs mt-0.5"><i class="fa-solid fa-location-dot text-amber-400 mr-1"></i>${dest.location}</p>
            </div>
            <button onclick="setChatDestination('${dest.name}')"
                class="px-4 py-2 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-400 text-xs font-bold transition flex items-center space-x-2">
                <i class="fa-solid fa-robot"></i>
                <span>Ask WanderBuddy</span>
            </button>
        </div>

        ${liveWeatherPanel}

        <!-- Map + Budget Grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div>
                <div class="flex justify-between items-center mb-2">
                    <h4 class="font-bold text-xs uppercase tracking-wider text-slate-400">Interactive Map & Pins</h4>
                    <span class="text-[10px] text-amber-400 font-bold">Leaflet.js + OSM</span>
                </div>
                <div id="map" class="rounded-2xl border border-slate-800 overflow-hidden shadow-inner"></div>
            </div>
            <div>
                <h4 class="font-bold text-xs uppercase tracking-wider text-slate-400 mb-2">Budget Breakdown</h4>
                <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-3">${budgetBars}</div>
            </div>
        </div>

        <!-- Attractions + Food -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800">
                <h4 class="font-bold text-sm text-amber-400 mb-3 flex items-center space-x-2">
                    <i class="fa-solid fa-landmark"></i>
                    <span>Key Attractions</span>
                    <span class="text-[10px] text-blue-400 font-bold ml-auto">Google Places Live</span>
                </h4>
                <div class="space-y-3">${attractionCards}</div>
            </div>
            <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800">
                <h4 class="font-bold text-sm text-amber-400 mb-3 flex items-center space-x-2">
                    <i class="fa-solid fa-utensils"></i>
                    <span>Famous Delicacies</span>
                </h4>
                <div class="space-y-2">${foodCards}</div>
            </div>
        </div>

        <!-- Itinerary -->
        <div class="mb-8">
            <h4 class="font-extrabold text-lg mb-4 flex items-center space-x-2">
                <i class="fa-solid fa-calendar-days text-amber-400"></i>
                <span>Day-by-Day Itinerary</span>
            </h4>
            <div class="space-y-3">${itineraryDays}</div>
        </div>

        <!-- Packing Checklist -->
        <div>
            <h4 class="font-extrabold text-lg mb-4 flex items-center space-x-2">
                <i class="fa-solid fa-suitcase text-amber-400"></i>
                <span>AI Packing Checklist</span>
            </h4>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">${checklistItems}</div>
        </div>
    `;

    _initLeafletMap(dest);
}

// ─── Leaflet Map with Rich Popups ────────────────────────────
function _initLeafletMap(dest) {
    setTimeout(() => {
        if (leafletMap) { leafletMap.remove(); leafletMap = null; }

        const c = dest.coordinates || { lat: 0, lng: 0 };
        const mapEl = document.getElementById('map');
        if (!mapEl) return;

        leafletMap = L.map('map').setView([c.lat, c.lng], 12);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 18,
            attribution: '© OpenStreetMap contributors',
        }).addTo(leafletMap);

        // ── Centre pin ────────────────────────────────────────
        L.marker([c.lat, c.lng])
            .addTo(leafletMap)
            .bindPopup(`
                <div style="font-family:'Outfit',sans-serif;min-width:140px">
                    <b style="color:#f59e0b;font-size:13px">${dest.name}</b><br>
                    <span style="font-size:11px;color:#94a3b8">${dest.location}</span>
                </div>`)
            .openPopup();

        // ── Attraction pins with live data ────────────────────
        const allMarkers = [];
        (dest.attractions || []).forEach(att => {
            const ac = att.coordinates;
            if (!ac || !ac.lat || !ac.lng) return;
            const lp       = att.live_places || {};
            const photoImg = lp.photo_url
                ? `<img src="${lp.photo_url}" style="width:100%;height:80px;object-fit:cover;border-radius:6px;margin-top:6px" onerror="this.remove()">`
                : '';
            const ratingEl = lp.rating
                ? `<span style="color:#f59e0b;font-size:11px;font-weight:700">⭐ ${lp.rating}/5</span>`
                : '';
            const openEl   = lp.open_now === true
                ? `<span style="color:#4ade80;font-size:10px;font-weight:700;background:rgba(74,222,128,0.1);padding:2px 6px;border-radius:10px">Open Now</span>`
                : lp.open_now === false
                ? `<span style="color:#f87171;font-size:10px;font-weight:700;background:rgba(248,113,113,0.1);padding:2px 6px;border-radius:10px">Closed</span>`
                : '';

            const marker = L.marker([ac.lat, ac.lng])
                .addTo(leafletMap)
                .bindPopup(`
                    <div style="font-family:'Outfit',sans-serif;max-width:200px">
                        <b style="font-size:12px">${att.name}</b>
                        <div style="font-size:10px;color:#94a3b8;margin:2px 0">${att.category}</div>
                        <div style="display:flex;align-items:center;gap:6px;margin-top:4px">${ratingEl} ${openEl}</div>
                        <div style="font-size:10px;color:#64748b;margin-top:3px">${att.description}</div>
                        ${photoImg}
                        ${lp.address ? `<div style="font-size:9px;color:#475569;margin-top:4px">${lp.address}</div>` : ''}
                    </div>`);
            allMarkers.push(marker);
        });

        // Fit map bounds to all markers
        if (allMarkers.length > 0) {
            const group = L.featureGroup(allMarkers);
            leafletMap.fitBounds(group.getBounds().pad(0.2));
        }

        // Trigger map.invalidateSize() inside a short setTimeout so Leaflet resizes correctly
        setTimeout(() => {
            if (leafletMap) {
                leafletMap.invalidateSize();
            }
        }, 300);

    }, 150);
}

// ─── Checklist toggle ─────────────────────────────────────────
function toggleChecklistItem(checkbox) {
    const span = checkbox.nextElementSibling;
    span.classList.toggle('line-through', checkbox.checked);
    span.classList.toggle('opacity-50',    checkbox.checked);
}

// =============================================================
//  AI TRAVEL BUDDY CHATBOT
// =============================================================
function initChatbot() {
    const toggleBtn   = document.getElementById('toggleChatBtn');
    const closeBtn    = document.getElementById('closeChatBtn');
    const chatWindow  = document.getElementById('chatWindow');
    const chatForm    = document.getElementById('chatForm');
    const chatInput   = document.getElementById('chatInput');
    const chatMsgs    = document.getElementById('chatMessages');

    if (toggleBtn) toggleBtn.onclick = () => chatWindow.classList.toggle('hidden');
    if (closeBtn) closeBtn.onclick  = () => chatWindow.classList.add('hidden');

    if (chatForm) {
        chatForm.onsubmit = async e => {
            e.preventDefault();
            const msg = chatInput.value.trim();
            if (!msg) return;

            // User bubble
            chatMsgs.innerHTML += `
                <div class="bg-amber-500 text-slate-950 p-3 rounded-2xl max-w-[85%] ml-auto text-xs font-semibold shadow-md">
                    ${escHtml(msg)}
                </div>`;
            chatInput.value = '';
            chatMsgs.scrollTop = chatMsgs.scrollHeight;

            // Loading bubble
            const loadId = `cld-${Date.now()}`;
            chatMsgs.innerHTML += `
                <div id="${loadId}" class="bg-slate-800/70 p-3 rounded-2xl max-w-[85%] text-slate-400 text-xs italic">
                    <i class="fa-solid fa-spinner animate-spin text-amber-400 mr-1"></i> WanderBuddy is thinking…
                </div>`;
            chatMsgs.scrollTop = chatMsgs.scrollHeight;

            try {
                const ctx = activeDestination ? JSON.stringify(activeDestination).slice(0, 3500) : '';
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        destinationName: activeDestination?.name ?? 'General Travel',
                        context: ctx,
                        message: msg,
                    }),
                });
                const data = await res.json();
                document.getElementById(loadId)?.remove();

                if (data.success && data.reply) {
                    // Convert markdown-style bullets and bold for readability
                    const html = data.reply
                        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                        .replace(/\n\*\s/g, '\n• ')
                        .replace(/\n/g, '<br>');
                    chatMsgs.innerHTML += `
                        <div class="bg-slate-800/90 p-3 rounded-2xl max-w-[85%] text-slate-200 text-xs border border-slate-700/60 leading-relaxed">
                            ${html}
                        </div>`;
                } else {
                    chatMsgs.innerHTML += `
                        <div class="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-2xl max-w-[85%] text-xs">
                            Sorry, WanderBuddy hit an error. Please try again.
                        </div>`;
                }
            } catch (err) {
                console.error('Chat error:', err);
                document.getElementById(loadId)?.remove();
            }
            chatMsgs.scrollTop = chatMsgs.scrollHeight;
        };
    }
}

function setChatDestination(name) {
    document.getElementById('chatWindow').classList.remove('hidden');
    document.getElementById('chatContextTag').innerText = name;
    document.getElementById('chatInput').focus();
}

// ─── XSS-safe HTML escape ─────────────────────────────────────
function escHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// =============================================================
//  MY TRIPS — localStorage Persistence Engine
// =============================================================

const TRIPS_KEY = 'wanderpulse_saved_trips';

/** Return all saved trips from localStorage (array) */
function getSavedTrips() {
    try {
        return JSON.parse(localStorage.getItem(TRIPS_KEY) || '[]');
    } catch {
        return [];
    }
}

/** Persist trips array to localStorage */
function _persistTrips(trips) {
    localStorage.setItem(TRIPS_KEY, JSON.stringify(trips));
    updateTripsNavBadge();
}

/** Check if a destination id is already saved */
function isBookmarked(id) {
    return getSavedTrips().some(t => t.id === id);
}

/** Save a destination to My Trips */
function saveTrip(dest) {
    const trips = getSavedTrips();
    if (trips.some(t => t.id === dest.id)) return; // already saved
    trips.unshift({
        ...dest,
        _savedAt: new Date().toISOString(),
    });
    _persistTrips(trips);
}

/** Remove a destination from My Trips by id */
function removeTrip(id) {
    const trips = getSavedTrips().filter(t => t.id !== id);
    _persistTrips(trips);
}

/** Toggle bookmark on a recommendation card */
function toggleBookmark(id) {
    const dest = currentRecommendations.find(d => d.id === id);
    if (!dest) return;

    const btn = document.getElementById(`bm-${id}`);
    if (!btn) return;

    if (isBookmarked(id)) {
        removeTrip(id);
        btn.classList.remove('bookmarked');
        btn.innerHTML = '<i class="fa-regular fa-bookmark text-xs"></i>';
        btn.title = 'Save to My Trips';
        showToast('Trip removed from My Trips', 'info', 'fa-bookmark');
    } else {
        saveTrip(dest);
        btn.classList.add('bookmarked');
        btn.innerHTML = '<i class="fa-solid fa-bookmark text-xs"></i>';
        btn.title = 'Remove from My Trips';
        // Pop animation
        btn.classList.remove('pop-anim');
        void btn.offsetWidth; // reflow to restart animation
        btn.classList.add('pop-anim');
        showToast(`${dest.name} saved to My Trips! ✈️`, 'success', 'fa-bookmark');
    }
}

/** Update nav badge count */
function updateTripsNavBadge() {
    const count = getSavedTrips().length;
    const badge = document.getElementById('tripsNavBadge');
    if (!badge) return;
    if (count > 0) {
        badge.textContent = count;
        badge.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
    }
}

// =============================================================
//  MY TRIPS — Dashboard View
// =============================================================

/** Show the My Trips section, hide all others */
function showMyTrips() {
    document.getElementById('heroSection').classList.add('hidden');
    document.getElementById('resultsSection').classList.add('hidden');
    document.getElementById('loadingState').classList.add('hidden');
    document.getElementById('savedTripDetailSection').classList.add('hidden');
    document.getElementById('myTripsSection').classList.remove('hidden');
    renderSavedTrips();
}

/** Render saved trips grid */
function renderSavedTrips() {
    const trips = getSavedTrips();
    const grid    = document.getElementById('savedTripsGrid');
    const empty   = document.getElementById('myTripsEmpty');
    const badge   = document.getElementById('savedTripsBadge');
    const clearBtn = document.getElementById('clearAllTripsBtn');

    badge.textContent = `${trips.length} Saved`;

    if (trips.length === 0) {
        grid.innerHTML = '';
        empty.classList.remove('hidden');
        clearBtn.classList.add('hidden');
        return;
    }

    empty.classList.add('hidden');
    clearBtn.classList.remove('hidden');

    grid.innerHTML = trips.map(dest => {
        const savedDate = dest._savedAt
            ? new Date(dest._savedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
            : '';
        const vibeTag = (dest.vibes || []).slice(0, 2).map(v =>
            `<span class="trip-stat-pill">${v}</span>`
        ).join('');

        return `
        <div class="saved-trip-card group" id="stcard-${dest.id}">
            <div class="saved-trip-header-accent"></div>
            <div class="p-6 flex flex-col flex-1">
                <!-- Card Header -->
                <div class="flex justify-between items-start mb-3">
                    <div class="flex-1 min-w-0 pr-3">
                        <span class="text-[10px] font-bold uppercase tracking-wider text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-md border border-amber-500/20 inline-block mb-1.5">
                            <i class="fa-solid fa-location-dot mr-1"></i>${dest.location || ''}
                        </span>
                        <h3 class="text-xl font-extrabold text-slate-100 group-hover:text-amber-400 transition truncate">${dest.name}</h3>
                    </div>
                    <div class="flex flex-col items-end gap-1.5 shrink-0">
                        <span class="px-2.5 py-1 rounded-full bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 font-black text-[10px] shadow">
                            ${dest.matchPercentage || '—'}% Match
                        </span>
                        <span class="trip-saved-date">Saved ${savedDate}</span>
                    </div>
                </div>

                <!-- Pitch -->
                <p class="text-slate-400 text-xs leading-relaxed mb-4 line-clamp-2">${dest.pitch || ''}</p>

                <!-- Stat Pills -->
                <div class="flex flex-wrap gap-1.5 mb-4">
                    ${dest.budgetRange ? `<span class="trip-stat-pill"><i class="fa-solid fa-wallet"></i>${dest.budgetRange}</span>` : ''}
                    ${dest.duration ? `<span class="trip-stat-pill"><i class="fa-solid fa-clock"></i>${dest.duration} Days</span>` : ''}
                    ${dest.travelCompanion ? `<span class="trip-stat-pill"><i class="fa-solid fa-user-group"></i>${dest.travelCompanion}</span>` : ''}
                    ${vibeTag}
                </div>

                <!-- Attraction chips -->
                <div class="flex flex-wrap gap-1 mb-5">
                    ${(dest.attractions || []).slice(0,3).map(a =>
                        `<span class="px-2 py-0.5 rounded-lg bg-slate-800 border border-slate-700/50 text-[10px] text-slate-400 font-medium">📍 ${a.name}</span>`
                    ).join('')}
                </div>

                <!-- Action Buttons -->
                <div class="mt-auto flex space-x-2">
                    <button onclick="openSavedTripDetail('${dest.id}')"
                        class="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-amber-500 hover:text-slate-950 text-slate-200 font-bold text-xs transition flex items-center justify-center space-x-2">
                        <i class="fa-solid fa-eye"></i>
                        <span>View Details</span>
                    </button>
                    <button onclick="deleteSavedTrip('${dest.id}')"
                        title="Remove trip"
                        class="px-3 py-2.5 rounded-xl border border-red-500/20 bg-red-500/5 hover:bg-red-500/20 text-red-400 text-xs font-bold transition">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
        </div>`;
    }).join('');
}

/** Open full detail view for a saved trip */
function openSavedTripDetail(id) {
    const trips = getSavedTrips();
    const dest  = trips.find(t => t.id === id);
    if (!dest) return;
    activeSavedTripId = id;

    document.getElementById('myTripsSection').classList.add('hidden');
    const detailSection = document.getElementById('savedTripDetailSection');
    detailSection.classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Wire up delete button
    const delBtn = document.getElementById('savedDetailDeleteBtn');
    delBtn.onclick = () => deleteSavedTripFromDetail(id);

    // Render rich detail content (reuse same structure as the main detail modal)
    const lw = dest.live_weather || {};
    const container = document.getElementById('savedTripDetailContent');

    // --- Reuse the same builder helpers from the main openDetail() ---
    const liveWeatherPanel = `
        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 mb-6">
            <div class="flex justify-between items-center mb-2">
                <span class="font-bold text-xs uppercase tracking-wider text-slate-400">Live Weather (at time of saving)</span>
                <span class="text-[10px] font-bold ${lw.source === 'OpenWeatherMap Live' ? 'text-green-400' : 'text-slate-500'}">
                    ${lw.source === 'OpenWeatherMap Live' ? '● Live' : '○ Unavailable'}
                </span>
            </div>
            ${buildWeatherBadge(lw)}
            <div class="mt-3 pt-3 border-t border-slate-800 text-[11px] text-slate-400 leading-relaxed">
                <i class="fa-solid fa-calendar-check text-amber-400 mr-1"></i>
                ${dest.weatherInsight || ''}
            </div>
        </div>`;

    const attractionCards = (dest.attractions || []).map(att => {
        const lp = att.live_places || {};
        const ratingHTML = lp.rating ? `<span class="flex items-center space-x-1 text-[11px] font-bold text-amber-400"><i class="fa-solid fa-star text-[10px]"></i><span>${lp.rating}/5</span></span>` : '';
        const openHTML = lp.open_now === true
            ? `<span class="text-[10px] font-bold text-green-400 bg-green-500/10 px-2 py-0.5 rounded-full border border-green-500/20">Open Now</span>`
            : lp.open_now === false
            ? `<span class="text-[10px] font-bold text-red-400 bg-red-500/10 px-2 py-0.5 rounded-full border border-red-500/20">Closed</span>`
            : '';
        const photoHTML = lp.photo_url ? `<img src="${lp.photo_url}" alt="${att.name}" class="w-full h-24 object-cover rounded-lg mt-2 border border-slate-700/60" onerror="this.remove()">` : '';
        const addressHTML = lp.address ? `<div class="text-[10px] text-slate-500 mt-1 flex items-center"><i class="fa-solid fa-map-pin mr-1 text-slate-600"></i>${lp.address}</div>` : '';
        return `
            <div class="p-3 rounded-xl bg-slate-900 border border-slate-800/80">
                <div class="flex justify-between items-start">
                    <div class="font-bold text-xs text-slate-100">${att.name}<span class="text-[10px] text-slate-400 font-normal"> (${att.category})</span></div>
                    <div class="flex items-center space-x-1">${ratingHTML} ${openHTML}</div>
                </div>
                <div class="text-[11px] text-slate-400 mt-0.5">${att.description}</div>
                ${addressHTML}${photoHTML}
            </div>`;
    }).join('');

    const foodCards = (dest.localDelicacies || []).map(f => `
        <div class="p-2.5 rounded-xl bg-slate-900 border border-slate-800/80">
            <div class="font-bold text-xs text-slate-100">${f.name}<span class="text-[10px] text-amber-400 font-normal"> (${f.type})</span></div>
            <div class="text-[11px] text-slate-400 mt-0.5">${f.description}</div>
        </div>`).join('');

    const budgetBars = Object.entries(dest.budgetSplit || {}).map(([cat, pct]) => `
        <div>
            <div class="flex justify-between text-xs mb-1">
                <span class="capitalize text-slate-300 font-semibold">${cat}</span>
                <span class="font-bold text-amber-400">${pct}%</span>
            </div>
            <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div class="bg-gradient-to-r from-amber-500 to-yellow-400 h-full rounded-full" style="width:${pct}%"></div>
            </div>
        </div>`).join('');

    const itineraryDays = (dest.itinerary || []).map(day => `
        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800">
            <div class="font-bold text-amber-400 text-xs mb-2 uppercase tracking-wider">Day ${day.day}: ${day.title}</div>
            <ul class="space-y-1.5 text-xs text-slate-300">
                ${(day.activities || []).map(a =>
                    `<li class="flex items-start space-x-2"><i class="fa-solid fa-circle-check text-amber-400 text-[10px] mt-1 shrink-0"></i><span>${a}</span></li>`
                ).join('')}
            </ul>
        </div>`).join('');

    const checklistItems = (dest.packingChecklist || []).map(item => `
        <label class="flex items-center space-x-3 bg-slate-950 p-3 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500/50 transition">
            <input type="checkbox" onchange="toggleChecklistItem(this)" class="w-4 h-4 accent-amber-500 rounded cursor-pointer">
            <span class="text-xs text-slate-300 font-medium">${item.item}<span class="text-[10px] text-slate-500"> (${item.category})</span></span>
        </label>`).join('');

    container.innerHTML = `
        <!-- Destination Header -->
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6 pb-4 border-b border-slate-800">
            <div>
                <span class="px-3 py-1 rounded-full bg-amber-500/10 text-amber-400 text-xs font-bold border border-amber-500/20 inline-block mb-2">
                    🎯 ${dest.matchPercentage}% Personal Match
                </span>
                <h2 class="text-3xl font-black">${dest.name}</h2>
                <p class="text-slate-400 text-xs mt-0.5"><i class="fa-solid fa-location-dot text-amber-400 mr-1"></i>${dest.location}</p>
            </div>
            <div class="flex flex-wrap gap-2">
                ${dest.budgetRange ? `<span class="trip-stat-pill"><i class="fa-solid fa-wallet"></i>${dest.budgetRange}</span>` : ''}
                ${dest.duration ? `<span class="trip-stat-pill"><i class="fa-solid fa-clock"></i>${dest.duration} Days</span>` : ''}
                ${dest.travelCompanion ? `<span class="trip-stat-pill"><i class="fa-solid fa-user-group"></i>${dest.travelCompanion}</span>` : ''}
            </div>
        </div>

        ${liveWeatherPanel}

        <!-- Budget & Attractions/Food -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div>
                <h4 class="font-bold text-xs uppercase tracking-wider text-slate-400 mb-2">Budget Breakdown</h4>
                <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-3">${budgetBars}</div>
            </div>
            <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800">
                <h4 class="font-bold text-sm text-amber-400 mb-3 flex items-center space-x-2">
                    <i class="fa-solid fa-utensils"></i><span>Famous Delicacies</span>
                </h4>
                <div class="space-y-2">${foodCards}</div>
            </div>
        </div>

        <!-- Attractions -->
        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 mb-8">
            <h4 class="font-bold text-sm text-amber-400 mb-3 flex items-center space-x-2">
                <i class="fa-solid fa-landmark"></i><span>Key Attractions</span>
            </h4>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">${attractionCards}</div>
        </div>

        <!-- Itinerary -->
        <div class="mb-8">
            <h4 class="font-extrabold text-lg mb-4 flex items-center space-x-2">
                <i class="fa-solid fa-calendar-days text-amber-400"></i><span>Day-by-Day Itinerary</span>
            </h4>
            <div class="space-y-3">${itineraryDays}</div>
        </div>

        <!-- Packing Checklist -->
        <div>
            <h4 class="font-extrabold text-lg mb-4 flex items-center space-x-2">
                <i class="fa-solid fa-suitcase text-amber-400"></i><span>AI Packing Checklist</span>
            </h4>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">${checklistItems}</div>
        </div>
    `;
}

/** Close saved trip detail, go back to My Trips */
function closeSavedTripDetail() {
    document.getElementById('savedTripDetailSection').classList.add('hidden');
    document.getElementById('myTripsSection').classList.remove('hidden');
    activeSavedTripId = null;
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

/** Delete trip from the card in the grid */
function deleteSavedTrip(id) {
    removeTrip(id);
    const card = document.getElementById(`stcard-${id}`);
    if (card) {
        card.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        card.style.opacity = '0';
        card.style.transform = 'scale(0.95)';
        setTimeout(() => { card.remove(); renderSavedTrips(); }, 320);
    }
    showToast('Trip removed from My Trips', 'info', 'fa-bookmark');
    // Sync bookmark buttons on results page if visible
    const bmBtn = document.getElementById(`bm-${id}`);
    if (bmBtn) {
        bmBtn.classList.remove('bookmarked');
        bmBtn.innerHTML = '<i class="fa-regular fa-bookmark text-xs"></i>';
    }
}

/** Delete trip from inside the detail view */
function deleteSavedTripFromDetail(id) {
    removeTrip(id);
    showToast('Trip removed from My Trips', 'info', 'fa-trash');
    closeSavedTripDetail();
    renderSavedTrips();
    // Sync bookmark buttons on results page
    const bmBtn = document.getElementById(`bm-${id}`);
    if (bmBtn) {
        bmBtn.classList.remove('bookmarked');
        bmBtn.innerHTML = '<i class="fa-regular fa-bookmark text-xs"></i>';
    }
}

/** Open confirmation modal to clear all trips */
function confirmClearAllTrips() {
    document.getElementById('confirmClearModal').classList.remove('hidden');
}

/** Wipe all saved trips */
function clearAllTrips() {
    localStorage.removeItem(TRIPS_KEY);
    updateTripsNavBadge();
    document.getElementById('confirmClearModal').classList.add('hidden');
    showToast('All saved trips cleared', 'info', 'fa-trash');
    renderSavedTrips();
    // Sync all bookmark buttons
    document.querySelectorAll('.bookmark-btn').forEach(btn => {
        btn.classList.remove('bookmarked');
        btn.innerHTML = '<i class="fa-regular fa-bookmark text-xs"></i>';
    });
}

// =============================================================
//  TOAST NOTIFICATION UTILITY
// =============================================================

let _toastTimeout = null;

function showToast(message, type = 'info', icon = 'fa-info-circle') {
    // Remove existing toast if any
    const existing = document.getElementById('wanderToast');
    if (existing) existing.remove();
    clearTimeout(_toastTimeout);

    const toast = document.createElement('div');
    toast.id = 'wanderToast';
    toast.className = `wander-toast ${type}`;
    toast.innerHTML = `<i class="fa-solid ${icon} toast-icon"></i><span>${message}</span>`;
    document.body.appendChild(toast);

    // Trigger show
    requestAnimationFrame(() => {
        requestAnimationFrame(() => toast.classList.add('show'));
    });

    _toastTimeout = setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 350);
    }, 3000);
}
