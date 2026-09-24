const state = {
    profile: {
        displayName: "",
        loaded: false,
        firstRun: false,
        editing: false,
        personalization: {
            avatar: null,
            background: null,
            accent: "purple"
        }
    },
    setup: {
        active: false,
        status: null,
        busy: false,
        malMessage: "",
        malAttemptId: 0,
        serializdMessage: ""
    },
    route: "home",
    search: {
        query: "",
        isAnime: null,
        mediaType: null,
        catalog: null,
        mal: null,
        serializd: null
    },
    watch: {
        query: "",
        isAnime: null,
        mediaType: null,
        catalog: null,
        mal: null,
        serializd: null,
        serviceMode: null,
        seasons: null,
        season: null,
        episodes: null,
        selectedEpisodes: [],
        malStartEpisode: 1,
        malEpisodeCount: 1,
        malEpisodes: [],
        status: "watching",
        serializdCompleted: false,
        serializdCurrentlyWatching: null,
        serializdWatchingChoice: null,
        serializdRewatch: null,
        confirmation: false
    },
    review: {
        query: "",
        catalog: null,
        serializd: null,
        target: null,
        seasons: null,
        season: null,
        episodes: null,
        episode: null,
        stars: "",
        text: "",
        isRewatch: false,
        containsSpoiler: false,
        like: false,
        allowsComments: true,
        backdate: null,
        existing: null,
        editing: false,
        reviewId: null,
        focus: "review",
        confirmation: false
    },
    home: {
        history: null,
        library: null,
        loading: false,
        requestId: 0,
        featuredIndex: 0
    },
    rate: {
        query: "",
        isAnime: null,
        mediaType: null,
        catalog: null,
        mal: null,
        serializd: null,
        service: null,
        malStatus: null,
        malRating: "",
        malProgress: 0,
        malTotal: 0,
        malOriginal: null,
        serializdTarget: null,
        seasons: null,
        season: null,
        episodes: null,
        serializdRating: "",
        serializdProgressTarget: "",
        serializdExisting: null,
        serializdRatingTouched: false,
        confirmation: false,
        pending: null
    },
    timer: null
};

const view = document.getElementById("view");
const label = document.getElementById("page-label");
const toast = document.getElementById("toast");
let watchSerializdSelectionGeneration = 0;

function esc(value) {
    const text = String(value ?? "")
        .replace(/â€”/g, "—")
        .replace(/â€“/g, "–")
        .replace(/â€¢/g, "•")
        .replace(/â€™/g, "’")
        .replace(/â€œ/g, "“")
        .replace(/â€/g, "”")
        .replace(/Â/g, "");
    return text.replace(/[&<>"']/g, c => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    }[c]));
}

function msg(text) {
    toast.textContent = text;
    toast.classList.add("show");
    clearTimeout(state.timer);
    state.timer = setTimeout(() => toast.classList.remove("show"), 2400);
}

async function call(action, payload = {}) {
    if (!window.waymark?.invoke) {
        throw new Error("WAYMARK desktop bridge is unavailable.");
    }
    const response = await window.waymark.invoke(action, payload);
    if (!response?.ok) {
        throw new Error(response?.error || "WAYMARK request failed");
    }
    return response.result;
}

function setRoute(route) {
    state.route = route;
    document.querySelectorAll("[data-route]").forEach(button => {
        button.classList.toggle("active", button.dataset.route === route);
    });
    label.textContent = route.charAt(0).toUpperCase() + route.slice(1);
    render();
}



const PERSONALIZATION_ACCENTS = {
    purple: { color: "#9b6cff", strong: "#b18aff", text: "#100b18", glow: "rgba(155,108,255,.28)" },
    blue: { color: "#4f8cff", strong: "#72a5ff", text: "#07101f", glow: "rgba(79,140,255,.28)" },
    cyan: { color: "#27c7e8", strong: "#63dbf2", text: "#06151a", glow: "rgba(39,199,232,.25)" },
    green: { color: "#3bd98c", strong: "#70e8aa", text: "#06150d", glow: "rgba(59,217,140,.24)" },
    yellow: { color: "#e8c94a", strong: "#f1d96b", text: "#171204", glow: "rgba(232,201,74,.22)" },
    orange: { color: "#f28a42", strong: "#ffa86e", text: "#1b0c03", glow: "rgba(242,138,66,.24)" },
    red: { color: "#ef5d70", strong: "#ff8494", text: "#1a060a", glow: "rgba(239,93,112,.24)" },
    pink: { color: "#e86bb8", strong: "#f38bca", text: "#180914", glow: "rgba(232,107,184,.24)" }
};

const PERSONALIZATION_DB_NAME = "waymark-personalization";
const PERSONALIZATION_DB_VERSION = 1;
const PERSONALIZATION_STORE = "preferences";
const PERSONALIZATION_KEY = "profile";
let personalizationDbPromise = null;

function openPersonalizationDb() {
    if (personalizationDbPromise) return personalizationDbPromise;
    personalizationDbPromise = new Promise((resolve, reject) => {
        if (!window.indexedDB) {
            reject(new Error("WAYMARK personalization storage is unavailable."));
            return;
        }
        const request = window.indexedDB.open(PERSONALIZATION_DB_NAME, PERSONALIZATION_DB_VERSION);
        request.onupgradeneeded = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains(PERSONALIZATION_STORE)) {
                db.createObjectStore(PERSONALIZATION_STORE);
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error || new Error("Could not open personalization storage."));
    });
    return personalizationDbPromise;
}

async function loadPersonalization() {
    try {
        const db = await openPersonalizationDb();
        const value = await new Promise((resolve, reject) => {
            const tx = db.transaction(PERSONALIZATION_STORE, "readonly");
            const request = tx.objectStore(PERSONALIZATION_STORE).get(PERSONALIZATION_KEY);
            request.onsuccess = () => resolve(request.result || null);
            request.onerror = () => reject(request.error || new Error("Could not read personalization storage."));
        });
        if (value && typeof value === "object") {
            state.profile.personalization = {
                avatar: typeof value.avatar === "string" ? value.avatar : null,
                background: typeof value.background === "string" ? value.background : null,
                accent: PERSONALIZATION_ACCENTS[value.accent] ? value.accent : "purple"
            };
        }
    } catch (error) {
        console.warn("[WAYMARK] personalization storage unavailable:", error);
    }
}

async function savePersonalization() {
    const snapshot = {
        avatar: state.profile.personalization.avatar || null,
        background: state.profile.personalization.background || null,
        accent: PERSONALIZATION_ACCENTS[state.profile.personalization.accent] ? state.profile.personalization.accent : "purple"
    };
    try {
        const db = await openPersonalizationDb();
        await new Promise((resolve, reject) => {
            const tx = db.transaction(PERSONALIZATION_STORE, "readwrite");
            tx.objectStore(PERSONALIZATION_STORE).put(snapshot, PERSONALIZATION_KEY);
            tx.oncomplete = resolve;
            tx.onerror = () => reject(tx.error || new Error("Could not save personalization."));
            tx.onabort = () => reject(tx.error || new Error("Could not save personalization."));
        });
        return true;
    } catch (error) {
        console.warn("[WAYMARK] personalization save failed:", error);
        msg("Appearance could not be saved permanently.");
        return false;
    }
}

function profileInitial(name) {
    const value = String(name || "").trim();
    return value ? value.charAt(0).toUpperCase() : "W";
}

function applyPersonalization() {
    const root = document.documentElement;
    const accent = PERSONALIZATION_ACCENTS[state.profile.personalization.accent] || PERSONALIZATION_ACCENTS.purple;
    root.style.setProperty("--accent", accent.color);
    root.style.setProperty("--accent-strong", accent.strong);
    root.style.setProperty("--accent-text", accent.text);
    root.style.setProperty("--accent-glow", accent.glow);
    root.style.setProperty("--accent-soft", `${hexToRgba(accent.color, 0.14)}`);
    root.style.setProperty("--accent-strong-soft", `${hexToRgba(accent.color, 0.20)}`);
    if (state.profile.personalization.background) {
        root.style.setProperty("--waymark-background-image", `url("${state.profile.personalization.background}")`);
        document.body.classList.add("has-waymark-background");
    } else {
        root.style.setProperty("--waymark-background-image", "none");
        document.body.classList.remove("has-waymark-background");
    }
    updateProfileChrome();
}

function hexToRgba(hex, alpha) {
    const value = String(hex || "").replace("#", "");
    if (value.length !== 6) return `rgba(155,108,255,${alpha})`;
    const number = Number.parseInt(value, 16);
    const r = (number >> 16) & 255;
    const g = (number >> 8) & 255;
    const b = number & 255;
    return `rgba(${r},${g},${b},${alpha})`;
}

function personalizationPreviewStyle(type) {
    if (type === "avatar" && state.profile.personalization.avatar) {
        return `background-image:url("${state.profile.personalization.avatar}");`;
    }
    if (type === "background" && state.profile.personalization.background) {
        return `background-image:url("${state.profile.personalization.background}");`;
    }
    return "";
}

function updateProfileChrome() {
    const profile = document.querySelector(".profile");
    if (!profile) return;
    const nameNode = profile.querySelector("span:not(.profile-chevron)");
    const markNode = profile.querySelector(".profile-mark");
    const name = state.profile.displayName.trim();
    if (nameNode) nameNode.textContent = name || "WAYMARK";
    if (markNode) {
        markNode.textContent = state.profile.personalization.avatar ? "" : profileInitial(name);
        markNode.classList.toggle("has-avatar", !!state.profile.personalization.avatar);
        markNode.style.backgroundImage = state.profile.personalization.avatar
            ? `url("${state.profile.personalization.avatar}")`
            : "";
    }
    profile.title = name ? `Profile: ${name}` : "WAYMARK profile";
}

async function loadProfile() {
    try {
        const profile = await call("profile_get");
        state.profile.displayName = String(profile?.display_name || "").trim();
        await loadPersonalization();
        state.profile.loaded = true;
        applyPersonalization();
        return state.profile;
    } catch (error) {
        console.error("[WAYMARK] profile unavailable:", error);
        await loadPersonalization();
        state.profile.loaded = true;
        applyPersonalization();
        return state.profile;
    }
}

function accentChoices() {
    return Object.entries(PERSONALIZATION_ACCENTS).map(([key, value]) => `
        <button type="button" class="accent-swatch ${state.profile.personalization.accent === key ? "selected" : ""}" data-action="profile-accent" data-accent="${key}" title="${key.charAt(0).toUpperCase() + key.slice(1)}" aria-label="${key} accent color">
            <span style="background:${value.color}"></span>
        </button>
    `).join("");
}

function renderPersonalizationFields({ firstRun = false } = {}) {
    const name = esc(state.profile.displayName);
    const avatar = state.profile.personalization.avatar;
    const background = state.profile.personalization.background;
    return `
        <div class="personalization-grid">
            <section class="personalization-card personalization-avatar-card">
                <div class="personalization-card-copy">
                    <div class="eyebrow">PROFILE PICTURE</div>
                    <h2>Make it yours</h2>
                    <p>Use a picture or keep your initial. You can change it anytime.</p>
                </div>
                <div class="avatar-preview ${avatar ? "has-avatar" : ""}">${avatar ? `<img src="${esc(avatar)}" alt="Profile picture" draggable="false">` : esc(profileInitial(state.profile.displayName))}</div>
                <div class="personalization-actions">
                    <input id="profile-avatar-input" class="visually-hidden-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif">
                    <button class="btn" type="button" data-action="profile-pick-avatar">${avatar ? "Change picture" : "Upload picture"}</button>
                    ${avatar ? `<button class="btn btn-quiet" type="button" data-action="profile-remove-avatar">Remove</button>` : `<button class="btn btn-quiet" type="button" data-action="profile-skip-avatar">Skip</button>`}
                </div>
            </section>

            <section class="personalization-card personalization-name-card">
                <div class="eyebrow">YOUR PROFILE</div>
                <h2>What should we call you?</h2>
                <label class="setup-field">
                    <span>Display name</span>
                    <input id="profile-name-input" type="text" maxlength="40" autocomplete="name" value="${name}" placeholder="Enter your name">
                    <small>${firstRun ? "This is how you'll appear throughout WAYMARK." : "Stored locally on this computer."}</small>
                </label>
            </section>

            <section class="personalization-card personalization-background-card">
                <div class="personalization-card-copy">
                    <div class="eyebrow">BACKGROUND</div>
                    <h2>Set the atmosphere</h2>
                    <p>Choose an image for a more personal WAYMARK. A dark overlay keeps the interface readable.</p>
                </div>
                <div class="background-preview ${background ? "has-background" : ""}">
                    ${background ? `<img class="background-preview-image" src="${esc(background)}" alt="" aria-hidden="true" draggable="false">` : `<span>YOUR BACKGROUND</span>`}
                </div>
                <div class="personalization-actions">
                    <input id="profile-background-input" class="visually-hidden-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif">
                    <button class="btn" type="button" data-action="profile-pick-background">${background ? "Change image" : "Upload background"}</button>
                    ${background ? `<button class="btn btn-quiet" type="button" data-action="profile-remove-background">Remove</button>` : `<button class="btn btn-quiet" type="button" data-action="profile-skip-background">Skip</button>`}
                </div>
            </section>

            <section class="personalization-card personalization-accent-card">
                <div class="eyebrow">ACCENT COLOR</div>
                <h2>Choose your style</h2>
                <p>One controlled accent color is used across buttons, navigation, progress, and highlights.</p>
                <div class="accent-choice-row" role="group" aria-label="Accent color">${accentChoices()}</div>
                <div class="accent-preview"><span class="accent-preview-dot"></span><span>This is how your accent will look.</span></div>
            </section>
        </div>
    `;
}

function renderProfileSetup() {
    document.body.classList.remove("waymark-setup-mode");
    view.innerHTML = `
        <div class="view-inner personalization-view">
            <div class="screen-header personalization-header">
                <div class="eyebrow">PERSONALIZE WAYMARK</div>
                <h1>Let's make it yours.</h1>
                <p>Set up the look of your WAYMARK profile. Everything here is optional except your display name.</p>
            </div>
            ${renderPersonalizationFields({ firstRun: true })}
            <div class="personalization-footer">
                <span>Your profile picture, background, accent, and name are saved on this device.</span>
                <button class="btn btn-primary" data-action="profile-save">Continue →</button>
            </div>
            <div id="profile-message" class="setup-message"></div>
        </div>
    `;
    document.getElementById("profile-name-input")?.focus();
    applyPersonalization();
}

function renderProfileSettings() {
    view.innerHTML = `
        <div class="view-inner personalization-view">
            <div class="screen-header personalization-header">
                <div class="eyebrow">SETTINGS · PERSONALIZATION</div>
                <h1>Your WAYMARK profile</h1>
                <p>Change your display name and visual identity. Your MAL and Serializd credentials remain separate.</p>
            </div>
            ${renderPersonalizationFields()}
            <div class="personalization-footer">
                <span>Changes are saved automatically on this device and apply immediately.</span>
                <button class="btn btn-primary" data-action="profile-save">Save & apply →</button>
            </div>
            <div id="profile-message" class="setup-message"></div>
        </div>
    `;
    applyPersonalization();
}

async function saveProfile() {
    const input = document.getElementById("profile-name-input");
    const name = input?.value?.trim() || "";
    const message = document.getElementById("profile-message");
    if (!name) {
        if (message) {
            message.textContent = "Enter a name first.";
            message.classList.add("show");
        }
        input?.focus();
        return;
    }
    try {
        const result = await call("profile_set", { display_name: name });
        state.profile.displayName = String(result?.display_name || name).trim();
        state.profile.firstRun = false;
        state.profile.editing = false;
        applyPersonalization();
        const saved = await savePersonalization();
        msg(saved ? "Profile and appearance saved." : "Profile saved, but appearance could not be saved.");
        if (state.route === "settings") {
            renderProfileSettings();
        } else {
            render();
        }
    } catch (error) {
        if (message) {
            message.textContent = error.message || "Could not save your profile name.";
            message.classList.add("show");
        }
    }
}

async function readProfileImage(file, maxBytes, kind) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
        msg(`Choose an image file for your ${kind}.`);
        return;
    }
    if (file.size > maxBytes) {
        msg(`${kind === "profile picture" ? "Profile pictures" : "Background images"} must be ${Math.round(maxBytes / 1024 / 1024)} MB or smaller.`);
        return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
        if (kind === "profile picture") state.profile.personalization.avatar = String(reader.result || "");
        else state.profile.personalization.background = String(reader.result || "");
        applyPersonalization();
        const saved = await savePersonalization();
        if (state.profile.firstRun) renderProfileSetup();
        else renderProfileSettings();
        if (!saved) msg(`${kind === "profile picture" ? "Profile picture" : "Background image"} is active, but could not be saved permanently.`);
    };
    reader.onerror = () => msg(`Could not read that ${kind}.`);
    reader.readAsDataURL(file);
}


function openProfileEditor() {
    state.profile.editing = true;
    if (!state.profile.displayName) {
        state.profile.firstRun = true;
        renderProfileSetup();
        return;
    }
    renderProfileSettings();
}

async function loadSetupStatus() {
    state.setup.status = await call("setup_status");
    return state.setup.status;
}

function setupServiceRow(service, connected, title, description, extra = "") {
    const statusText = connected ? "Connected" : "Not connected";
    const statusClass = connected ? "setup-connected" : "setup-disconnected";
    const action = service === "mal" ? "setup-connect-mal" : "setup-connect-serializd";
    return `
        <div class="setup-service">
            <div class="setup-service-copy">
                <div class="setup-service-title">
                    <strong>${title}</strong>
                    <span class="setup-status ${statusClass}">${connected ? "✓" : "○"} ${statusText}</span>
                </div>
                <p>${description}</p>
                ${extra}
            </div>
            <button class="btn ${connected ? "" : "btn-primary"}" data-action="${action}" ${state.setup.busy && service !== "mal" ? "disabled" : ""}>
                ${connected ? "Reconnect" : (service === "mal" && state.setup.busy ? "Retry MAL" : "Connect")}
            </button>
        </div>
    `;
}

function renderSetup() {
    const status = state.setup.status || {};
    const mal = status.mal || {};
    const serializd = status.serializd || {};
    const malConnected = !!mal.connected;
    const complete = !!status.complete;

    document.body.classList.add("waymark-setup-mode");
    document.body.innerHTML = `
        <main class="setup-shell">
            <section class="setup-card">
                <div class="setup-brand"><span class="brand-mark logo-mark"><img src="assets/waymark-icon.png" alt="" aria-hidden="true"></span><span>WAYMARK</span></div>
                <div class="setup-eyebrow">FIRST-RUN SETUP</div>
                <h1>Connect your services.</h1>
                <p class="setup-lead">WAYMARK keeps your accounts separate and stores authentication data in your Windows user profile.</p>

                <div class="setup-services">
                    ${setupServiceRow(
                        "mal",
                        !!mal.connected,
                        "MyAnimeList",
                        "Connect your MAL account so WAYMARK can read and update your anime list.",
                        !malConnected ? `
                            <label class="setup-field">
                                <span>MAL Client ID</span>
                                <input id="setup-mal-client-id" type="text" autocomplete="off" value="${esc(mal.client_id || "")}" placeholder="Enter your MAL OAuth client ID">
                                <small>This is the public client ID from your MAL developer application. It is not your account password or token.</small>
                            </label>
                        ` : `<small class="setup-note">MAL is connected.</small>`
                    )}
                    ${setupServiceRow(
                        "serializd",
                        !!serializd.connected,
                        "Serializd",
                        "Connect your Serializd account using its authenticated session token.",
                        !serializd.connected ? `
                            <label class="setup-field">
                                <span>Serializd session token</span>
                                <input id="setup-serializd-token" type="password" autocomplete="off" placeholder="Paste your Serializd bearer token">
                                <small>Your token is encrypted and stored locally. It is never written into the WAYMARK application files.</small>
                            </label>
                        ` : `<small class="setup-note">${serializd.username ? `Connected as ${esc(serializd.username)}.` : "Serializd is connected."}</small>`
                    )}
                </div>

                <div class="setup-message ${state.setup.malMessage || state.setup.serializdMessage ? "show" : ""}">
                    ${esc(state.setup.malMessage || state.setup.serializdMessage || "Connect both services to continue.")}
                </div>

                <div class="setup-footer">
                    <span>${complete ? "All required services are connected." : "Both services are required for the current WAYMARK release."}</span>
                    <button class="btn btn-primary" data-action="setup-finish" ${complete ? "" : "disabled"}>Enter WAYMARK</button>
                </div>
            </section>
        </main>
    `;
}

async function handleSetupMal() {
    // Capture the current value before renderSetup() replaces document.body.
    const clientInput = document.getElementById("setup-mal-client-id");
    const clientId = clientInput?.value?.trim() || undefined;

    // Each click owns one frontend attempt. A newer retry supersedes the
    // previous polling loop so an old OAuth attempt cannot reset the UI.
    const attemptId = (state.setup.malAttemptId || 0) + 1;
    state.setup.malAttemptId = attemptId;
    state.setup.busy = true;
    state.setup.malMessage = "Opening MyAnimeList authorization…";
    renderSetup();

    try {
        const result = await call("mal_auth_start", { client_id: clientId });

        if (state.setup.malAttemptId !== attemptId) return;

        state.setup.malMessage = result?.message || "Complete authorization in your browser. Waiting for MAL…";
        renderSetup();

        for (let attempt = 0; attempt < 240; attempt += 1) {
            await new Promise(resolve => setTimeout(resolve, 1000));

            if (state.setup.malAttemptId !== attemptId) return;

            const status = await call("mal_auth_status");
            state.setup.status = await call("setup_status");

            if (state.setup.malAttemptId !== attemptId) return;

            if (status.status === "connected" || state.setup.status?.mal?.connected) {
                state.setup.malMessage = "MyAnimeList connected successfully.";
                state.setup.busy = false;
                renderSetup();
                return;
            }

            if (status.status === "error") {
                throw new Error(status.error || "MyAnimeList authorization failed.");
            }
        }

        throw new Error("MyAnimeList authorization timed out. Please try again.");
    } catch (error) {
        if (state.setup.malAttemptId !== attemptId) return;

        state.setup.malMessage = error.message || "MyAnimeList connection failed.";
        state.setup.busy = false;
        state.setup.status = await call("setup_status").catch(() => state.setup.status);
        renderSetup();
    }
}

async function handleSetupSerializd() {
    const input = document.getElementById("setup-serializd-token");
    const token = input?.value?.trim() || "";
    if (!token) {
        state.setup.serializdMessage = "Paste your Serializd session token first.";
        renderSetup();
        return;
    }

    state.setup.busy = true;
    state.setup.serializdMessage = "Verifying Serializd…";
    renderSetup();
    try {
        const result = await call("serializd_connect", { token });
        state.setup.serializdMessage = result?.username
            ? `Serializd connected as ${result.username}.`
            : "Serializd connected successfully.";
        state.setup.status = await call("setup_status");
    } catch (error) {
        state.setup.serializdMessage = error.message || "Serializd connection failed.";
    } finally {
        state.setup.busy = false;
        renderSetup();
    }
}

async function handleSetupFinish() {
    const status = await call("setup_status");
    if (!status.complete) {
        state.setup.status = status;
        state.setup.malMessage = "Connect both MyAnimeList and Serializd before continuing.";
        renderSetup();
        return;
    }
    window.location.reload();
}

async function bootstrap() {
    try {
        const status = await call("setup_status");
        if (!status.complete) {
            state.setup.active = true;
            state.setup.status = status;
            renderSetup();
            return;
        }
    } catch (error) {
        // Preserve the existing application shell if setup status cannot be read.
        console.error("[WAYMARK] setup status unavailable:", error);
    }

    await loadProfile();
    if (!state.profile.displayName) {
        state.profile.firstRun = true;
        renderProfileSetup();
        return;
    }
    render();
}

function card(icon, title, description, action) {
    return `
        <button class="action-card" data-action="${action}">
            <div class="action-top">
                <span class="mini-icon">${icon}</span>
                <span>→</span>
            </div>
            <h3>${title}</h3>
            <p>${description}</p>
        </button>
    `;
}

function homeActivityRow(entry) {
    const service = entry?.service || "Service";
    const show = entry?.show || "Unknown show";
    const item = entry?.item || "";
    const date = homeFormatDate(entry?.date);
    const rating = entry?.rating;

    return `
        <div class="home-activity-row">
            <div class="home-activity-main">
                <span class="home-activity-service">${esc(service)}</span>
                <strong>${esc(show)}</strong>
                ${item ? `<span>${esc(item)}</span>` : ""}
            </div>
            <div class="home-activity-meta">
                ${date ? `<span>${esc(date)}</span>` : ""}
                ${rating != null ? `<span>★ ${esc(rating)}</span>` : ""}
            </div>
        </div>
    `;
}

function homeFormatDate(value) {
    if (!value) return "";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric"
    });
}

function homeContinueRows(library) {
    const mal = Array.isArray(library?.mal) ? library.mal : [];
    const serializd = Array.isArray(library?.serializd) ? library.serializd : [];
    const malWatching = mal.filter(item => {
        const status = String(item?.status || "").toLowerCase();
        return status === "watching" || status === "rewatching";
    });
    const serializdWatching = serializd.filter(item => {
        const status = String(item?.status || "").toLowerCase();
        return status === "watching" || item?.currently_watching === true;
    });

    // Keep the existing MAL ordering first, then append Serializd's live
    // currently-watching titles. Both sources are already loaded by the
    // library call; switching Home slides never makes another network request.
    return [...malWatching, ...serializdWatching].slice(0, 8);
}

function homeServiceKey(item) {
    return String(item?.service || "MAL").toLowerCase() === "serializd" ? "serializd" : "mal";
}

function homeTitle(item, service) {
    return service === "mal"
        ? ((item?.node || item)?.title || item?.title || "Untitled")
        : (item?.name || item?.title || "Untitled");
}

function homeProgressMeta(item, service) {
    if (service === "mal") {
        const watched = Number(item?.watched ?? 0);
        const total = Number(item?.total ?? 0);
        if (total > 0) {
            return {
                watched,
                total,
                progress: Math.min(100, Math.round((watched / total) * 100)),
                label: `Episode ${watched} of ${total}`
            };
        }
        return { watched, total: 0, progress: null, label: `${watched} episodes watched` };
    }

    const watchedSeasons = Number(item?.watched_seasons ?? 0);
    const totalSeasons = Number(item?.total_seasons ?? item?.seasons ?? 0);
    if (totalSeasons > 0 && (watchedSeasons > 0 || item?.completed === true)) {
        return {
            watched: watchedSeasons,
            total: totalSeasons,
            progress: Math.min(100, Math.round((watchedSeasons / totalSeasons) * 100)),
            label: `Season ${watchedSeasons} of ${totalSeasons}`
        };
    }
    if (totalSeasons > 0) {
        return { watched: 0, total: totalSeasons, progress: null, label: `Currently watching · ${totalSeasons} season${totalSeasons === 1 ? "" : "s"}` };
    }
    return { watched: 0, total: 0, progress: null, label: "Currently watching" };
}

function homeContinueRow(item) {
    const watched = Number(item?.watched ?? 0);
    const total = Number(item?.total ?? 0);
    const hasTotal = Number.isFinite(total) && total > 0;
    const progress = hasTotal ? Math.min(100, Math.round((watched / total) * 100)) : null;
    const status = String(item?.status || "watching").replace("_", " ");

    return `
        <button class="home-continue-row" data-action="home-continue" data-title="${esc(item?.title || "")}">
            <div class="home-continue-copy">
                <div class="home-continue-top">
                    <strong>${esc(item?.title || "Untitled")}</strong>
                    <span>${esc(status)}</span>
                </div>
                <div class="home-progress-line">
                    <span>${hasTotal ? `Episode ${watched} of ${total}` : `${watched} episodes watched`}</span>
                    ${progress != null ? `<b>${progress}%</b>` : ""}
                </div>
                ${progress != null ? `
                    <div class="home-progress-track">
                        <i style="width:${progress}%"></i>
                    </div>
                ` : ""}
            </div>
            <span class="home-continue-arrow">→</span>
        </button>
    `;
}

function mediaCardMarkup(item, service, options = {}) {
    const serviceKey = service === "serializd" ? "serializd" : "mal";
    const title = homeTitle(item, serviceKey);
    const poster = catalogPoster(item, serviceKey);
    const status = String(item?.status || "").replace(/_/g, " ");
    const progressMeta = homeProgressMeta(item, serviceKey);
    const progress = progressMeta.progress;
    const subtitle = options.subtitle || progressMeta.label || status || (serviceKey === "mal" ? "MyAnimeList" : "Serializd");
    const badge = options.badge || (status ? status : "");
    const action = options.action || "";
    const content = `
        <div class="media-card-art${poster ? "" : " is-missing"}">
            ${poster ? `<img src="${esc(poster)}" alt="${esc(title)} poster" loading="lazy" decoding="async" onerror="this.closest('.media-card-art')?.classList.add('is-missing'); this.remove();">` : ""}
            <div class="media-card-art-fallback"><span>${esc(title.slice(0, 1).toUpperCase())}</span></div>
            ${badge ? `<span class="media-card-badge">${esc(badge)}</span>` : ""}
            ${action ? `<span class="media-card-play">▶</span>` : ""}
        </div>
        <div class="media-card-copy">
            <strong>${esc(title)}</strong>
            <span>${esc(subtitle)}</span>
            ${progress != null ? `<div class="media-card-progress"><i style="width:${progress}%"></i></div>` : ""}
        </div>
    `;
    return action
        ? `<button class="media-card" data-action="${esc(action)}" data-title="${esc(title)}">${content}</button>`
        : `<article class="media-card">${content}</article>`;
}

function homeFeaturedMarkup(items) {
    if (!Array.isArray(items) || !items.length) return `
        <section class="home-featured home-featured-empty">
            <div class="home-featured-copy">
                <div class="eyebrow">YOUR NEXT WATCH</div>
                <h2>Start something worth remembering.</h2>
                <p>Search for a title or log something you've watched to build your personal media journey.</p>
                <div class="home-featured-actions">
                    <button class="btn btn-primary" data-action="home-search">Find a title <span>→</span></button>
                    <button class="btn" data-action="home-watch">Log something</button>
                </div>
            </div>
        </section>
    `;

    const index = Math.max(0, Math.min(Number(state.home.featuredIndex || 0), items.length - 1));
    const item = items[index];
    const service = homeServiceKey(item);
    const title = homeTitle(item, service);
    const poster = catalogPoster(item, service);
    const progressMeta = homeProgressMeta(item, service);
    const status = String(item?.status || "watching").replace(/_/g, " ");

    return `
        <section class="home-featured" data-action="home-continue" data-title="${esc(title)}">
            <div class="home-featured-backdrop" style="${poster ? `background-image: linear-gradient(90deg, rgba(8,6,12,.96) 0%, rgba(8,6,12,.72) 42%, rgba(8,6,12,.18) 100%), url('${esc(poster)}')` : ""}"></div>
            <div class="home-featured-copy">
                <div class="eyebrow">CONTINUE WATCHING · ${service === "mal" ? "MYANIMELIST" : "SERIALIZD"}</div>
                <h2>${esc(title)}</h2>
                <p>${esc(progressMeta.label)} · ${esc(status)}</p>
                ${progressMeta.progress != null ? `<div class="home-featured-progress"><span style="width:${progressMeta.progress}%"></span></div>` : ""}
                <div class="home-featured-actions">
                    <button class="btn btn-primary" data-action="home-continue" data-title="${esc(title)}">Continue <span>→</span></button>
                    <button class="btn" data-action="home-library">View library</button>
                </div>
            </div>
            ${poster ? `<img class="home-featured-poster" src="${esc(poster)}" alt="${esc(title)} poster" loading="eager" decoding="async" onerror="this.remove();">` : ""}
            ${items.length > 1 ? `
                <button class="home-featured-nav home-featured-prev" data-action="home-featured-prev" aria-label="Previous continue watching title">‹</button>
                <button class="home-featured-nav home-featured-next" data-action="home-featured-next" aria-label="Next continue watching title">›</button>
                <div class="home-featured-dots" aria-label="Continue watching position">
                    ${items.map((_, dotIndex) => `<button class="home-featured-dot ${dotIndex === index ? "is-active" : ""}" data-action="home-featured-go" data-index="${dotIndex}" aria-label="Show ${dotIndex + 1} of ${items.length}"></button>`).join("")}
                </div>
            ` : ""}
        </section>
    `;
}

function homeDashboardShell() {
    const history = state.home.history;
    const library = state.home.library;
    const entries = Array.isArray(history?.entries) ? history.entries : [];
    const errors = [
        ...(Array.isArray(history?.errors) ? history.errors : []),
        ...(Array.isArray(library?.errors) ? library.errors : [])
    ];
    const mal = Array.isArray(library?.mal) ? library.mal : [];
    const serializd = Array.isArray(library?.serializd) ? library.serializd : [];
    const continueRows = homeContinueRows(library);
    const featuredIndex = continueRows.length ? Math.min(Number(state.home.featuredIndex || 0), continueRows.length - 1) : 0;
    state.home.featuredIndex = featuredIndex;

    const totalLibrary = mal.length + serializd.length;
    const watchingCount =
        mal.filter(item => {
            const status = String(item?.status || "").toLowerCase();
            return status === "watching" || status === "rewatching";
        }).length +
        serializd.filter(item => item?.currently_watching === true || String(item?.status || "").toLowerCase() === "watching").length;
    const completedCount =
        mal.filter(item => String(item?.status || "").toLowerCase() === "completed").length +
        serializd.filter(item => item?.completed === true || String(item?.status || "").toLowerCase() === "completed").length;
    const ratedCount = entries.filter(entry => entry?.rating != null).length;

    return `
        <div class="view-inner home-dashboard">
            <div class="home-hero home-hero-compact">
                <div>
                    <div class="eyebrow">YOUR MEDIA COMMAND CENTER</div>
                    <h1>Welcome back${state.profile.displayName ? `, ${esc(state.profile.displayName)}` : ""}.</h1>
                    <p>Track what you watch, pick up where you left off, and keep your media journey together.</p>
                </div>
                <div class="home-hero-actions">
                    <button class="btn btn-primary" data-action="home-watch">Log something <span>→</span></button>
                    <button class="btn" data-action="home-search">Find a title</button>
                </div>
            </div>

            ${homeFeaturedMarkup(continueRows)}

            <div class="home-stat-strip">
                <div><span>LIBRARY</span><strong>${totalLibrary || "—"}</strong><small>${mal.length} MAL · ${serializd.length} Serializd</small></div>
                <div><span>IN PROGRESS</span><strong>${watchingCount || "—"}</strong><small>${watchingCount ? "currently watching" : "nothing in progress"}</small></div>
                <div><span>COMPLETED</span><strong>${completedCount || "—"}</strong><small>${completedCount ? "completed across services" : "no completed titles loaded"}</small></div>
                <div><span>RECENT RATINGS</span><strong>${ratedCount || "—"}</strong><small>from your timeline</small></div>
            </div>

            <section class="home-media-section">
                <div class="home-section-head">
                    <div>
                        <div class="eyebrow">CONTINUE WATCHING</div>
                        <h2>Pick up where you left off</h2>
                    </div>
                    <button class="btn" data-action="home-library">Open library</button>
                </div>
                ${state.home.loading ? `
                    <div class="home-loading"><div class="loading-dot"></div><span>Loading your dashboard…</span></div>
                ` : continueRows.length ? `
                    <div class="home-media-grid">
                        ${continueRows.slice(0, 8).map(item => mediaCardMarkup(item, homeServiceKey(item), { action: "home-continue", subtitle: homeProgressMeta(item, homeServiceKey(item)).label })).join("")}
                    </div>
                ` : `
                    <div class="home-empty home-empty-short"><strong>No titles are currently in progress.</strong><span>Start something through Watch and it will appear here.</span></div>
                `}
            </section>

            <div class="home-lower-grid">
                <section class="home-panel home-recent-panel">
                    <div class="home-panel-head">
                        <div><div class="eyebrow">RECENT ACTIVITY</div><h2>Latest from your timeline</h2></div>
                        <button class="btn" data-action="home-history">View all</button>
                    </div>
                    ${entries.length ? `<div class="home-activity-list">${entries.slice(0, 5).map(homeActivityRow).join("")}</div>` : errors.length ? `<div class="home-inline-error"><span>${esc(errors[0])}</span><button class="btn" data-action="home-refresh">Retry</button></div>` : `<div class="home-empty"><strong>Your activity will appear here.</strong><span>Log something through Watch to start building your WAYMARK timeline.</span></div>`}
                </section>

                <section class="home-panel home-actions-panel">
                    <div class="eyebrow">QUICK ACTIONS</div>
                    <h2>Jump right in</h2>
                    <div class="home-action-grid">
                        <button class="home-action-tile" data-action="home-review"><span>✎</span><strong>Review</strong><small>Write something</small></button>
                        <button class="home-action-tile" data-action="home-rate"><span>★</span><strong>Rate</strong><small>Score a title</small></button>
                        <button class="home-action-tile" data-action="home-history"><span>◷</span><strong>History</strong><small>See your timeline</small></button>
                        <button class="home-action-tile" data-action="home-library"><span>▣</span><strong>Library</strong><small>Browse everything</small></button>
                    </div>
                </section>
            </div>

            <div class="home-footer-row">
                <div><div class="eyebrow">YOUR WAYMARK</div><h2>Everything you watch, in one place.</h2></div>
                <div class="home-service-list"><span class="home-service-pill"><i></i> MyAnimeList</span><span class="home-service-pill"><i></i> Serializd</span></div>
                <button class="btn" data-action="home-refresh">${state.home.loading ? "Refreshing…" : "Refresh"}</button>
            </div>
        </div>
    `;
}

async function loadHomeDashboard() {
    const requestId = ++state.home.requestId;
    state.home.loading = true;
    if (state.route === "home") view.innerHTML = homeDashboardShell();

    try {
        const [historyData, libraryData] = await Promise.all([
            call("history", { limit: 8 }),
            call("library")
        ]);

        if (requestId !== state.home.requestId || state.route !== "home") return;
        state.home.history = historyData;
        state.home.library = libraryData;
        state.home.featuredIndex = 0;
    } catch (error) {
        if (requestId !== state.home.requestId || state.route !== "home") return;
        state.home.history = state.home.history || { entries: [], errors: [] };
        state.home.library = state.home.library || { mal: [], serializd: [], errors: [] };

        const existingErrors = [
            ...(Array.isArray(state.home.history.errors) ? state.home.history.errors : []),
            ...(Array.isArray(state.home.library.errors) ? state.home.library.errors : [])
        ];
        const message = error?.message || "Dashboard data could not be loaded.";
        state.home.history.errors = existingErrors.length ? existingErrors : [message];
    } finally {
        if (requestId === state.home.requestId && state.route === "home") {
            state.home.loading = false;
            view.innerHTML = homeDashboardShell();
        }
    }
}

function home() {
    view.innerHTML = homeDashboardShell();

    if ((!state.home.history || !state.home.library) && !state.home.loading) {
        loadHomeDashboard();
    }
}

function searchEntry() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header">
                <div class="eyebrow">DISCOVER ACROSS YOUR SERVICES</div>
                <h1>Find something</h1>
                <p>Search once, then choose the exact service identity you want to explore.</p>
            </div>
            <div class="panel search-entry-panel">
                <div class="search-bar">
                    <input id="q" type="search" placeholder="Search a title..." value="${esc(state.search.query)}" autocomplete="off">
                    <button class="btn btn-primary" data-action="search-start">Search</button>
                </div>
                <div class="search-hint">WAYMARK will ask two quick questions before contacting the connected catalogs.</div>
            </div>
        </div>
    `;
}

function guidedAnimeQuestion() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header">
                <div class="eyebrow">GUIDED SEARCH · 1 OF 2</div>
                <h1>${esc(state.search.query)}</h1>
                <p>Tell WAYMARK how to route this title.</p>
            </div>
            <div class="panel question-panel">
                <div class="question-title">Is it an anime?</div>
                <div class="choice-row">
                    <button class="btn" data-action="search-back-entry">Back</button>
                    <button class="btn btn-choice" data-action="yes">Yes</button>
                    <button class="btn btn-choice" data-action="no">No</button>
                </div>
            </div>
        </div>
    `;
}

function guidedTypeQuestion() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header">
                <div class="eyebrow">GUIDED SEARCH · 2 OF 2</div>
                <h1>${esc(state.search.query)}</h1>
                <p>Choose the media type.</p>
            </div>
            <div class="panel question-panel">
                <div class="question-title">TV show or movie?</div>
                <div class="choice-row">
                    <button class="btn" data-action="search-back-anime">Back</button>
                    <button class="btn btn-choice" data-action="tv">TV show</button>
                    <button class="btn btn-choice" data-action="movie">Movie</button>
                </div>
            </div>
        </div>
    `;
}

function catalogPoster(item, service) {
    if (!item || typeof item !== "object") return "";

    const candidates = [];
    const add = value => {
        if (typeof value === "string" && value.trim()) candidates.push(value.trim());
    };
    const addPicture = picture => {
        if (!picture || typeof picture !== "object") return;
        add(picture.large);
        add(picture.medium);
        add(picture.small);
        add(picture.url);
    };
    const addImages = images => {
        if (!images || typeof images !== "object") return;
        for (const key of ["large", "medium", "small", "original", "default"]) {
            const value = images[key];
            if (typeof value === "string") add(value);
            else if (value && typeof value === "object") add(value.url);
        }
        add(images.url);
    };

    const sources = [
        item,
        item.node,
        item.media,
        item.data,
        item.title_data
    ].filter(value => value && typeof value === "object");

    for (const source of sources) {
        add(source.image_url);
        add(source.image);
        add(source.poster);
        add(source.posterUrl);
        add(source.poster_url);
        add(source.imageUrl);
        add(source.posterPath);
        add(source.poster_path);
        add(source.imagePath);
        add(source.image_path);
        add(source.cover);
        add(source.cover_url);
        add(source.coverUrl);
        add(source.thumbnail);
        add(source.thumb);
        add(source.showImage);
        add(source.show_image);
        add(source.showPoster);
        add(source.show_poster);
        add(source.bannerImage);
        add(source.banner_image);
        add(source.showBannerImage);
        add(source.show_banner_image);
        add(source.artwork);
        add(source.artworkUrl);
        add(source.artwork_url);
        addPicture(source.main_picture);
        addImages(source.images);
    }

    // Preserve the service distinction for future sources while accepting the
    // flattened and nested shapes returned by the current MAL/Serializd bridge.
    return candidates[0] || "";
}

function catalogPosterMarkup(item, service, alt) {
    const src = catalogPoster(item, service);
    if (!src) return `<span class="search-result-poster search-result-poster-fallback">No poster</span>`;
    return `<img class="search-result-poster" src="${esc(src)}" alt="${esc(alt)}" loading="lazy" onerror="this.style.display='none'">`;
}

function serviceColumn(service, title, results, selected, error) {
    const rows = results.map((item, index) => {
        const name = service === "mal"
            ? ((item.node || item).title || "Untitled")
            : (item.name || item.title || "Untitled");
        const id = service === "mal"
            ? ((item.node || item).id ?? "")
            : (item.id ?? "");
        const secondary = service === "mal"
            ? `MAL ID: ${id}`
            : `Serializd ID: ${id}${item.premiereDate ? ` · ${item.premiereDate}` : ""}`;
        return `
            <button class="result-row ${selected?.index === index + 1 ? "selected" : ""}" data-action="${service}" data-index="${index + 1}">
                ${catalogPosterMarkup(item, service, `${name} poster`)}
                <span class="result-copy">
                    <strong>${esc(name)}</strong>
                    <small>${esc(secondary)}</small>
                </span>
                <span class="result-arrow">→</span>
            </button>
        `;
    }).join("");
    return `
        <div class="panel service-panel">
            <div class="result-heading">
                <div>
                    <div class="eyebrow">${service === "mal" ? "MYANIMELIST" : "SERIALIZD"}</div>
                    <h2>${title}</h2>
                </div>
                <span class="service-pill">${service === "mal" ? "MAL" : "Serializd"}</span>
            </div>
            ${error ? `<div class="error-box">${esc(error)}</div>` : `<div class="result-list">${rows || `<div class="empty-state compact">No results found.</div>`}</div>`}
            ${selected?.details ? renderDetails(service, selected.details) : ""}
        </div>
    `;
}

function results() {
    const s = state.search;
    const catalog = s.catalog;
    const mal = catalog.mal?.results || [];
    const serializd = catalog.serializd?.results || [];

    view.innerHTML = `
        <div class="view-inner search-results-view">
            <div class="screen-header search-result-header">
                <div>
                    <div class="eyebrow">WAYMARK SEARCH</div>
                    <h1>${esc(s.query)}</h1>
                    <p>${s.isAnime ? "Anime" : "Non-anime"} · ${s.mediaType === "tv" ? "TV show" : "Movie"} · Read-only</p>
                </div>
                <div class="search-header-actions">
                    <button class="btn" data-action="search-back-type">Back</button>
                    <button class="btn" data-action="new-search">New search</button>
                </div>
            </div>

            ${catalog.routing.mal ? serviceColumn("mal", "Results", mal, s.mal, catalog.mal.error) : ""}
            ${catalog.routing.serializd ? serviceColumn("serializd", "Results", serializd, s.serializd, catalog.serializd.error) : ""}

            ${!catalog.routing.mal && !catalog.routing.serializd
                ? `<div class="panel"><div class="empty-state">WAYMARK does not currently have a connected service for non-anime movies.</div></div>`
                : ""}
        </div>
    `;
}

function detailValue(labelText, value) {
    if (value === undefined || value === null || value === "") return "";
    return `<span><em>${esc(labelText)}</em><b>${esc(value)}</b></span>`;
}

function listText(value) {
    if (!Array.isArray(value)) return value;
    return value.map(item => {
        if (typeof item === "object") {
            return item.name || item.title || item.genreName || item.studioName || "";
        }
        return item;
    }).filter(Boolean).join(", ");
}

function detailImage(service, d) {
    if (service === "mal") {
        return d.image_url
            || d.main_picture?.large
            || d.main_picture?.medium
            || "";
    }

    return d.image
        || d.poster
        || d.posterUrl
        || d.image_url
        || d.imageUrl
        || "";
}

function detailBackdrop(service, d) {
    if (service === "mal") return "";
    return d.backdrop
        || d.backdropUrl
        || d.backdrop_url
        || "";
}

function detailTitle(service, d) {
    return service === "mal"
        ? (d.title || "Untitled")
        : (d.name || d.title || "Untitled");
}

function renderDetails(service, d) {
    const title = detailTitle(service, d);
    const image = detailImage(service, d);
    const backdrop = detailBackdrop(service, d);
    const serviceName = service === "mal" ? "MyAnimeList" : "Serializd";

    const artwork = image
        ? `<img class="details-poster" src="${esc(image)}" alt="${esc(title)} poster" loading="lazy">`
        : `<div class="details-poster details-poster-fallback"><span>No artwork</span><small>Artwork unavailable</small></div>`;

    const backdropLayer = backdrop
        ? `<div class="details-backdrop" style="background-image:url('${esc(backdrop)}')"></div>`
        : "";

    if (service === "mal") {
        const genres = listText(d.genres);
        const studios = listText(d.studios);
        const aired = d.start_date
            ? `${d.start_date}${d.end_date ? ` → ${d.end_date}` : ""}`
            : null;

        return `
            <div class="details-card">
                ${backdropLayer}
                <div class="details-content">
                    <div class="details-hero">
                        ${artwork}
                        <div class="details-hero-copy">
                            <div class="eyebrow">SELECTED MYANIMELIST TITLE</div>
                            <h3>${esc(title)}</h3>
                            <div class="details-service-line">
                                <span class="service-pill">${esc(serviceName)}</span>
                                ${d.id != null ? `<span class="details-id">ID ${esc(d.id)}</span>` : ""}
                            </div>
                            <p class="details-lead">Canonical title details from MyAnimeList. Fields are shown only when the connected service provides them.</p>
                            <div class="details-actions">
                                <button class="btn btn-primary" data-action="watch-from-details"
                                        data-title="${esc(title)}" data-anime="true">
                                    Use in Watch
                                </button>
                            </div>
                        </div>
                    </div>

                    <div class="metadata-grid">
                        ${detailValue("Score", d.score)}
                        ${detailValue("Rank", d.rank)}
                        ${detailValue("Popularity", d.popularity)}
                        ${detailValue("Year", d.year)}
                        ${detailValue("Episodes", d.episodes)}
                        ${detailValue("Duration", d.duration)}
                        ${detailValue("Status", d.status)}
                        ${detailValue("Source", d.source)}
                        ${detailValue("Aired", aired)}
                    </div>

                    ${genres ? `<div class="detail-line"><strong>Genres</strong><span>${esc(genres)}</span></div>` : ""}
                    ${studios ? `<div class="detail-line"><strong>Studios</strong><span>${esc(studios)}</span></div>` : ""}
                    ${d.synopsis ? `<div class="synopsis"><strong>Synopsis</strong><p>${esc(d.synopsis)}</p></div>` : ""}
                    <div class="detail-note">Artwork is displayed from the connected service's remote image URL. WAYMARK does not host or store the image.</div>
                    <div class="details-actions">
                        <button class="btn" data-action="search-clear-selection">Back to results</button>
                    </div>
                </div>
            </div>
        `;
    }

    const rating = typeof d.averageRating === "number"
        ? (d.averageRating / 2).toFixed(2)
        : null;
    const genres = listText(d.genres);
    const seasons = Array.isArray(d.seasons) ? d.seasons : [];

    return `
        <div class="details-card">
            ${backdropLayer}
            <div class="details-content">
                <div class="details-hero">
                    ${artwork}
                    <div class="details-hero-copy">
                        <div class="eyebrow">SELECTED SERIALIZD TITLE</div>
                        <h3>${esc(title)}</h3>
                        <div class="details-service-line">
                            <span class="service-pill">${esc(serviceName)}</span>
                            ${d.id != null ? `<span class="details-id">ID ${esc(d.id)}</span>` : ""}
                        </div>
                        <p class="details-lead">Canonical title details from Serializd. Fields are shown only when the connected service provides them.</p>
                        <div class="details-actions">
                            <button class="btn btn-primary" data-action="watch-from-details"
                                    data-title="${esc(title)}" data-anime="false">
                                Use in Watch
                            </button>
                        </div>
                    </div>
                </div>

                <div class="metadata-grid">
                    ${rating !== null ? detailValue("Community rating", `${rating} / 5`) : ""}
                    ${detailValue("Seasons", d.numSeasons ?? (seasons.length || null))}
                    ${detailValue("Episodes", d.numEpisodes)}
                    ${detailValue("Status", d.status)}
                    ${detailValue("Premiere", d.premiereDate)}
                    ${detailValue("Last air date", d.lastAirDate)}
                </div>

                ${genres ? `<div class="detail-line"><strong>Genres</strong><span>${esc(genres)}</span></div>` : ""}

                ${seasons.length ? `
                    <div class="season-list">
                        <strong>Seasons</strong>
                        ${seasons.map((season, index) => {
                            const name = season.name || season.seasonName || `Season ${index + 1}`;
                            const count = season.episodeCount ?? season.numberOfEpisodes ?? season.numEpisodes;
                            return `
                                <div class="season-row">
                                    <span>${esc(name)}</span>
                                    <small>${count != null ? `${esc(count)} episodes` : "Episode count unavailable"}</small>
                                </div>
                            `;
                        }).join("")}
                    </div>
                ` : ""}

                ${d.summary ? `<div class="synopsis"><strong>Synopsis</strong><p>${esc(d.summary)}</p></div>` : ""}
                <div class="detail-note">Artwork is displayed from the connected service's remote image URL. WAYMARK does not host or store the image.</div>
            </div>
        </div>
    `;
}


function startSearch() {
    const input = document.getElementById("q");
    const query = input?.value.trim();
    if (!query) {
        msg("Enter a title first.");
        input?.focus();
        return;
    }

    state.search = {
        query,
        isAnime: null,
        mediaType: null,
        catalog: null,
        mal: null,
        serializd: null
    };
    guidedAnimeQuestion();
}

async function finishSearch() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="empty-state loading-state">
                <div class="loading-dot"></div>
                <strong>Searching through WAYMARK…</strong>
                <span>Checking the connected catalog(s).</span>
            </div>
        </div>
    `;

    try {
        state.search.catalog = await call("search_catalogs", {
            query: state.search.query,
            is_anime: state.search.isAnime,
            media_type: state.search.mediaType
        });
        results();
    } catch (error) {
        view.innerHTML = `
            <div class="view-inner">
                <div class="error-box">Search failed: ${esc(error.message)}</div>
                <button class="btn back-btn" data-action="new-search">Back to search</button>
            </div>
        `;
    }
}

async function selectResult(service, index) {
    const resultsList = service === "mal"
        ? state.search.catalog.mal.results
        : state.search.catalog.serializd.results;

    msg(`Loading ${service === "mal" ? "MAL" : "Serializd"} details…`);

    try {
        const result = await call("select_search_result", {
            service,
            results: resultsList,
            index
        });

        state.search[service] = {
            index,
            selected: result.selected,
            details: result.details
        };

        results();
    } catch (error) {
        msg(`Could not load details: ${error.message}`);
    }
}

async function library(forceRefresh = false) {
    // Home already loads the same read-only library payload. Reuse it when
    // available so navigating Home -> Library does not make a second remote
    // library request. A manual Refresh still goes through the backend.
    if (!forceRefresh && state.home.library && !state.home.loading) {
        renderLibrary(state.home.library);
        return;
    }

    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header">
                <div class="eyebrow">CONNECTED LIBRARIES</div>
                <h1>Your library</h1>
                <p>Read-only view of the media you've logged across your connected services.</p>
            </div>
            <div class="empty-state loading-state">
                <div class="loading-dot"></div>
                <strong>Loading your library…</strong>
                <span>Checking MyAnimeList and Serializd.</span>
            </div>
        </div>
    `;

    try {
        const data = await call("library");
        renderLibrary(data);
    } catch (error) {
        view.innerHTML = `
            <div class="view-inner">
                <div class="screen-header">
                    <div class="eyebrow">CONNECTED LIBRARIES</div>
                    <h1>Your library</h1>
                    <p>WAYMARK could not load the connected libraries.</p>
                </div>
                <div class="panel">
                    <div class="error-box">Library failed: ${esc(error.message)}</div>
                    <button class="btn back-btn" data-action="library-retry">Retry</button>
                </div>
            </div>
        `;
    }
}

function libraryCard(service, item) {
    const serviceKey = service === "serializd" ? "serializd" : "mal";
    const title = item?.title || "Untitled";
    const poster = catalogPoster(item, serviceKey);
    const status = String(item?.status || "").replace(/_/g, " ");
    const progressMeta = homeProgressMeta(item, serviceKey);
    const progress = progressMeta.progress;
    const meta = serviceKey === "mal"
        ? progressMeta.label
        : (status === "watching" || status === "completed"
            ? `${progressMeta.label} · ${status}`
            : ([item?.seasons != null ? `${item.seasons} seasons` : "", item?.episodes != null ? `${item.episodes} episodes` : ""].filter(Boolean).join(" · ") || "Serializd"));
    return `
        <article class="library-media-card">
            <div class="library-media-art${poster ? "" : " is-missing"}">
                ${poster ? `<img src="${esc(poster)}" alt="${esc(title)} poster" loading="lazy" decoding="async" onerror="this.closest('.library-media-art')?.classList.add('is-missing'); this.remove();">` : ""}
                <div class="library-media-fallback"><span>${esc(title.slice(0, 1).toUpperCase())}</span></div>
                ${status ? `<span class="library-media-badge">${esc(status)}</span>` : ""}
            </div>
            <div class="library-media-copy"><strong>${esc(title)}</strong><span>${esc(meta)}</span>${progress != null ? `<div class="library-media-progress"><i style="width:${progress}%"></i></div>` : ""}</div>
        </article>
    `;
}

function libraryPanel(service, items) {
    const isMal = service === "mal";
    const title = isMal ? "MyAnimeList" : "Serializd";
    const cards = (items || []).map(item => libraryCard(service, item)).join("");
    return `
        <section class="library-service-section">
            <div class="library-section-head">
                <div><div class="eyebrow">${isMal ? "MYANIMELIST" : "SERIALIZD"}</div><h2>${title}</h2></div>
                <span class="service-pill">${items?.length || 0} ${items?.length === 1 ? "title" : "titles"}</span>
            </div>
            ${cards ? `<div class="library-media-grid">${cards}</div>` : `<div class="empty-state compact">No titles found in this library.</div>`}
        </section>
    `;
}

function renderLibrary(data) {
    const mal = Array.isArray(data?.mal) ? data.mal : [];
    const serializd = Array.isArray(data?.serializd) ? data.serializd : [];
    const errors = Array.isArray(data?.errors) ? data.errors : [];
    const total = mal.length + serializd.length;
    view.innerHTML = `
        <div class="view-inner library-view">
            <div class="library-hero-header">
                <div><div class="eyebrow">YOUR MEDIA COLLECTION</div><h1>Library</h1><p>${total ? `${total} titles across your connected services.` : "Your connected media, gathered in one place."}</p></div>
                <div class="library-header-actions"><span class="library-total-badge">${total || "—"} titles</span><button class="btn" data-action="library-retry">Refresh</button></div>
            </div>
            ${errors.length ? `<div class="library-warnings">${errors.map(error => `<div class="library-warning">${esc(error)}</div>`).join("")}</div>` : ""}
            ${libraryPanel("mal", mal)}
            ${libraryPanel("serializd", serializd)}
        </div>
    `;
}

async function history() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header">
                <div class="eyebrow">WATCH HISTORY</div>
                <h1>Your history</h1>
                <p>Read-only recent activity from your connected services.</p>
            </div>
            <div class="empty-state loading-state">
                <div class="loading-dot"></div>
                <strong>Loading your history…</strong>
                <span>Checking MyAnimeList and Serializd activity.</span>
            </div>
        </div>
    `;

    try {
        const data = await call("history", { limit: 20 });
        renderHistory(data);
    } catch (error) {
        view.innerHTML = `
            <div class="view-inner">
                <div class="screen-header">
                    <div class="eyebrow">WATCH HISTORY</div>
                    <h1>Your history</h1>
                    <p>WAYMARK could not load your recent activity.</p>
                </div>
                <div class="panel">
                    <div class="error-box">History failed: ${esc(error.message)}</div>
                    <button class="btn back-btn" data-action="history-retry">Retry</button>
                </div>
            </div>
        `;
    }
}

function historyRow(entry) {
    const service = entry?.service || "Service";
    const show = entry?.show || "Unknown show";
    const item = entry?.item || "";
    const date = entry?.date || "";
    const rating = entry?.rating;

    return `
        <div class="history-row">
            <div class="history-copy">
                <div class="history-service">${esc(service)}</div>
                <strong>${esc(show)}</strong>
                ${item ? `<small>${esc(item)}</small>` : ""}
            </div>
            <div class="history-meta">
                ${date ? `<span>${esc(date)}</span>` : ""}
                ${rating != null ? `<span>Rating ${esc(rating)}</span>` : ""}
            </div>
        </div>
    `;
}

function renderHistory(data) {
    const entries = Array.isArray(data?.entries) ? data.entries : [];
    const errors = Array.isArray(data?.errors) ? data.errors : [];

    view.innerHTML = `
        <div class="view-inner history-view">
            <div class="screen-header history-header">
                <div>
                    <div class="eyebrow">WATCH HISTORY</div>
                    <h1>Your history</h1>
                    <p>Recent read-only activity from MyAnimeList and Serializd.</p>
                </div>
                <button class="btn" data-action="history-retry">Refresh</button>
            </div>

            ${errors.length ? `
                <div class="history-warnings">
                    ${errors.map(error => `<div class="history-warning">${esc(error)}</div>`).join("")}
                </div>
            ` : ""}

            <div class="panel history-panel">
                <div class="result-heading">
                    <div>
                        <div class="eyebrow">RECENT ACTIVITY</div>
                        <h2>${entries.length} ${entries.length === 1 ? "entry" : "entries"}</h2>
                    </div>
                    <span class="service-pill">Read-only</span>
                </div>
                ${entries.length
                    ? `<div class="history-list">${entries.map(historyRow).join("")}</div>`
                    : `<div class="empty-state compact">No recent history found.</div>`
                }
            </div>
        </div>
    `;
}




const WATCH_SAVED_KEY = "waymark.watch.saved.v1";

function getSavedWatches() {
    try {
        const raw = localStorage.getItem(WATCH_SAVED_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

function setSavedWatches(items) {
    try {
        localStorage.setItem(WATCH_SAVED_KEY, JSON.stringify(items.slice(0, 12)));
    } catch {
        // Local persistence is a convenience; watch writes do not depend on it.
    }
}

function saveWatchCheckpoint() {
    const w = state.watch;
    if (!w.serializd && !w.mal) return;

    const title = (w.serializd?.name || w.serializd?.title || w.mal?.node?.title || w.mal?.title || w.query || "Saved watch");
    const poster = w.serializd
        ? watchPoster(w.serializd, "serializd")
        : watchPoster(w.mal, "mal");
    const entry = {
        id: `${w.serviceMode || "watch"}:${w.serializd?.id || ""}:${w.mal?.node?.id || w.mal?.id || ""}:${w.season?.season_id || ""}`,
        title,
        poster,
        serviceMode: w.serviceMode,
        query: w.query,
        isAnime: w.isAnime,
        mediaType: w.mediaType,
        serializd: w.serializd ? {
            id: w.serializd.id,
            name: w.serializd.name || w.serializd.title,
            image_url: watchPoster(w.serializd, "serializd")
        } : null,
        mal: w.mal ? {
            id: w.mal.node?.id || w.mal.id,
            title: w.mal.node?.title || w.mal.title,
            node: w.mal.node,
            details: w.mal.details,
            list_status: w.mal.list_status
        } : null,
        season: w.season ? { ...w.season } : null,
        serializdCompleted: !!w.serializdCompleted,
        lastEpisodes: Array.from(new Set(w.selectedEpisodes || w.malEpisodes || [])).sort((a, b) => a - b),
        savedAt: new Date().toISOString()
    };

    const items = getSavedWatches().filter(item => item.id !== entry.id);
    items.unshift(entry);
    setSavedWatches(items);
}

function removeSavedWatch(id) {
    setSavedWatches(getSavedWatches().filter(item => item.id !== id));
    watchEntry();
}

function watchSavedMarkup() {
    const items = getSavedWatches();
    if (!items.length) return "";
    return `
        <div class="panel watch-saved-panel">
            <div class="result-heading">
                <div><div class="eyebrow">SAVED WATCH</div><h2>Continue where you left off</h2></div>
                <span class="service-pill">${items.length}</span>
            </div>
            <div class="watch-saved-list">
                ${items.map(item => `
                    <div class="watch-saved-row">
                        ${item.poster
                            ? `<img class="watch-saved-poster" src="${esc(item.poster)}" alt="${esc(item.title)} poster" loading="lazy" onerror="this.style.display='none'">`
                            : `<span class="watch-saved-poster watch-result-poster-fallback">No poster</span>`}
                        <div class="watch-saved-copy">
                            <strong>${esc(item.title)}</strong>
                            <small>${esc(item.serviceMode === "both" ? "MAL + Serializd" : item.serviceMode === "mal" ? "MyAnimeList" : "Serializd")}${item.season ? ` · S${String(item.season.season_number).padStart(2, "0")}` : ""}</small>
                            ${item.lastEpisodes?.length ? `<small>Last logged: ${item.lastEpisodes.map(n => `E${n}`).join(", ")}</small>` : ""}
                        </div>
                        <div class="watch-saved-actions">
                            <button class="btn" data-action="watch-continue-saved" data-saved-id="${esc(item.id)}">Continue</button>
                            <button class="btn" data-action="watch-remove-saved" data-saved-id="${esc(item.id)}" aria-label="Remove saved watch">×</button>
                        </div>
                    </div>
                `).join("")}
            </div>
        </div>
    `;
}

function watchNewButton() {
    return `<button class="btn watch-new-btn" data-action="watch-start-over">New Watch</button>`;
}

function resetWatch() {
    state.watch = {
        query: "",
        isAnime: null,
        mediaType: null,
        catalog: null,
        mal: null,
        serializd: null,
        serviceMode: null,
        seasons: null,
        season: null,
        episodes: null,
        selectedEpisodes: [],
        malStartEpisode: 1,
        malEpisodeCount: 1,
        malEpisodes: [],
        status: "watching",
        serializdCompleted: false,
        serializdCurrentlyWatching: null,
        serializdWatchingChoice: null,
        serializdRewatch: null,
        confirmation: false
    };
}

function watchEntry() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header">
                <div class="eyebrow">WATCH · STEP 1</div>
                <h1>What did you watch?</h1>
                <p>Choose the exact title, then select one or multiple episodes before WAYMARK writes anything.</p>
            </div>
            <div class="panel watch-entry-panel">
                <div class="search-bar">
                    <input id="watch-q" type="search" placeholder="Search a title..." value="${esc(state.watch.query)}" autocomplete="off">
                    <button class="btn btn-primary" data-action="watch-search">Continue</button>
                </div>
                <div class="watch-note">Nothing is written during search or selection. A final confirmation is required before saving.</div>
            </div>
            ${watchSavedMarkup()}
        </div>
    `;
}

function watchAnimeQuestion() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">WATCH · STEP 2</div>
                <h1>${esc(state.watch.query)}</h1>
                <p>Tell WAYMARK how to route this title.</p>
                ${watchNewButton()}
            </div>
            <div class="panel question-panel">
                <div class="question-title">Is it an anime?</div>
                <div class="choice-row">
                    <button class="btn" data-action="watch-back-entry">Back</button>
                    <button class="btn btn-choice" data-action="watch-anime-yes">Yes</button>
                    <button class="btn btn-choice" data-action="watch-anime-no">No</button>
                </div>
            </div>
        </div>
    `;
}

function watchMediaTypeQuestion() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">WATCH · STEP 3</div>
                <h1>${esc(state.watch.query)}</h1>
                <p>Choose whether this anime is a TV show or a movie.</p>
                ${watchNewButton()}
            </div>
            <div class="panel question-panel">
                <div class="question-title">TV show or movie?</div>
                <div class="choice-row">
                    <button class="btn" data-action="watch-back-anime">Back</button>
                    <button class="btn btn-choice" data-action="watch-media-tv">TV show</button>
                    <button class="btn btn-choice" data-action="watch-media-movie">Movie</button>
                </div>
            </div>
        </div>
    `;
}

async function finishWatchSearch() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="empty-state loading-state">
                <div class="loading-dot"></div>
                <strong>Finding your title…</strong>
                <span>Checking the connected catalog(s).</span>
            </div>
        </div>
    `;
    try {
        state.watch.catalog = await call("search_catalogs", {
            query: state.watch.query,
            is_anime: state.watch.isAnime,
            media_type: state.watch.mediaType || "tv"
        });
        renderWatchResults();
    } catch (error) {
        watchError(`Watch search failed: ${error.message}`);
    }
}

function watchError(message) {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header">
                <div class="eyebrow">WATCH</div>
                <h1>Watch setup</h1>
                <p>WAYMARK could not continue the watch workflow.</p>
            </div>
            <div class="panel">
                <div class="error-box">${esc(message)}</div>
                <button class="btn" data-action="watch-start-over">Start over</button>
            </div>
        </div>
    `;
}

function watchPoster(item, service) {
    if (!item) return "";
    if (service === "mal") {
        const node = item.node || item;
        return node.image_url
            || node.main_picture?.large
            || node.main_picture?.medium
            || item.image_url
            || "";
    }
    return item.image_url
        || item.image
        || item.poster
        || item.posterUrl
        || item.imageUrl
        || item.posterPath
        || item.poster_path
        || "";
}

function watchPosterMarkup(item, service, alt) {
    const src = watchPoster(item, service);
    if (!src) return `<span class="watch-result-poster watch-result-poster-fallback">No poster</span>`;
    return `<img class="watch-result-poster" src="${esc(src)}" alt="${esc(alt)}" loading="lazy" onerror="this.style.display='none'">`;
}

function renderWatchResults() {
    const c = state.watch.catalog || {};
    const mal = c.mal?.results || [];
    const serializd = c.serializd?.results || [];

    const selectedMal = state.watch.mal;
    const selectedSerializd = state.watch.serializd;
    const canUseSerializd = state.watch.mediaType === "tv";
    const canUseMal = state.watch.isAnime === true;

    view.innerHTML = `
        <div class="view-inner watch-view">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">WATCH · SELECT TITLE</div>
                <h1>${esc(state.watch.query)}</h1>
                <p>${state.watch.isAnime ? (canUseSerializd ? "Choose the service identity you want to update. For anime TV shows, you can use MAL, Serializd, or both." : "Choose the MyAnimeList title to update.") : "Choose the Serializd TV show you want to update."}</p>
                <div class="watch-header-actions">
                    <button class="btn" data-action="watch-back-type">Back</button>
                    ${watchNewButton()}
                </div>
            </div>

            ${canUseMal ? `
                <div class="panel watch-selection-panel">
                    <div class="result-heading">
                        <div><div class="eyebrow">MYANIMELIST</div><h2>Anime</h2></div>
                        <span class="service-pill">${selectedMal ? "Selected" : `${mal.length} matches`}</span>
                    </div>
                    <div class="result-list">
                        ${mal.length ? mal.map((item, i) => {
                            const node = item.node || item;
                            const chosen = selectedMal && (
                                (selectedMal.node?.id || selectedMal.id) === node.id
                            );
                            return `
                                <button class="result-row watch-result-select ${chosen ? "watch-result-selected" : ""}" data-action="watch-select-mal" data-index="${i + 1}">
                                    ${watchPosterMarkup(item, "mal", node.title || "MAL poster")}
                                    <span class="result-copy">
                                        <strong>${esc(node.title || "Untitled")}</strong>
                                        <small>MAL ID: ${esc(node.id ?? "—")}${item.list_status?.num_episodes_watched != null ? ` · Current: E${esc(item.list_status.num_episodes_watched)}` : ""}</small>
                                    </span>
                                    <span class="result-arrow">${chosen ? "✓" : "→"}</span>
                                </button>
                            `;
                        }).join("") : `<div class="empty-state compact">No MAL matches found.</div>`}
                    </div>
                </div>
            ` : ""}

            ${canUseSerializd ? `
                <div class="panel watch-selection-panel">
                    <div class="result-heading">
                        <div><div class="eyebrow">SERIALIZD</div><h2>TV show</h2></div>
                        <span class="service-pill">${selectedSerializd ? "Selected" : `${serializd.length} matches`}</span>
                    </div>
                    <div class="result-list">
                        ${serializd.length ? serializd.map((item, i) => {
                            const chosen = selectedSerializd && String(selectedSerializd.id) === String(item.id);
                            return `
                                <button class="result-row watch-result-select ${chosen ? "watch-result-selected" : ""}" data-action="watch-select-serializd" data-index="${i + 1}">
                                    ${watchPosterMarkup(item, "serializd", `${item.name || item.title || "Serializd"} poster`)}
                                    <span class="result-copy">
                                        <strong>${esc(item.name || item.title || "Untitled")}</strong>
                                        <small>Serializd ID: ${esc(item.id ?? "—")}</small>
                                        ${chosen && state.watch.serializdCompleted ? `<small class="watch-completed-badge">✓ Completed on Serializd</small>` : ""}
                                    </span>
                                    <span class="result-arrow">${chosen ? "✓" : "→"}</span>
                                </button>
                            `;
                        }).join("") : `<div class="empty-state compact">No Serializd matches found.</div>`}
                    </div>
                </div>
            ` : ""}

            <div class="watch-actions">
                ${selectedMal && canUseMal ? `<button class="btn btn-primary" data-action="watch-use-mal">Use MAL</button>` : ""}
                ${selectedSerializd && canUseSerializd ? `<button class="btn btn-primary" data-action="watch-use-serializd">Use Serializd</button>` : ""}
                ${canUseMal && canUseSerializd && selectedMal && selectedSerializd ? `<button class="btn btn-primary" data-action="watch-use-both">Use Both</button>` : ""}
            </div>
        </div>
    `;
}

function malTotalEpisodes() {
    const mal = state.watch.mal || {};
    const node = mal.node || mal;
    const details = mal.details || {};
    const total =
        details.episodes ??
        details.num_episodes ??
        node.episodes ??
        node.num_episodes ??
        node.waymark_num_episodes ??
        "";
    const n = Number(total);
    return Number.isFinite(n) && n > 0 ? n : null;
}

function malCurrentProgress() {
    const mal = state.watch.mal || {};
    const status = mal.list_status || {};
    const n = Number(status.num_episodes_watched);
    return Number.isFinite(n) && n >= 0 ? n : 0;
}

function updateMalBatch() {
    const start = Math.max(1, Number(document.getElementById("mal-start")?.value || state.watch.malStartEpisode || 1));
    const count = Math.max(1, Number(document.getElementById("mal-count")?.value || state.watch.malEpisodeCount || 1));
    const total = malTotalEpisodes();
    const max = total ? Math.min(total, start + count - 1) : start + count - 1;
    state.watch.malStartEpisode = start;
    state.watch.malEpisodeCount = Math.max(1, max - start + 1);
    state.watch.malEpisodes = Array.from({length: state.watch.malEpisodeCount}, (_, i) => start + i);
    renderMalPicker();
}

function renderMalPicker() {
    const total = malTotalEpisodes();
    const current = malCurrentProgress();
    const title = (state.watch.mal?.node || state.watch.mal || {}).title || state.watch.query;
    let startDefault = Number(state.watch.malStartEpisode || (current + 1));
    if (total) startDefault = Math.min(Math.max(1, startDefault), total);
    else startDefault = Math.max(1, startDefault);

    let countDefault = Math.max(1, Number(state.watch.malEpisodeCount || 1));
    if (total) countDefault = Math.min(countDefault, Math.max(1, total - startDefault + 1));

    const selectedStart = Number(state.watch.malStartEpisode || startDefault);
    const selectedCount = Number(state.watch.malEpisodeCount || countDefault);
    const end = selectedStart + selectedCount - 1;

    view.innerHTML = `
        <div class="view-inner watch-view">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">WATCH · MYANIMELIST</div>
                <h1>${esc(title)}</h1>
                <p>MAL does not provide episode titles here. Choose the starting episode and how many consecutive episodes you watched.</p>
                ${watchNewButton()}
            </div>
            <div class="panel">
                <div class="watch-mal-meta">
                    <div>
                        <span>Current MAL progress</span>
                        <strong>E${esc(current)}</strong>
                    </div>
                    <div>
                        <span>Total episodes on MAL</span>
                        <strong>${total ? esc(total) : "Unavailable"}</strong>
                    </div>
                </div>

                <div class="watch-range-grid">
                    <div class="watch-field">
                        <label for="mal-start">Starting episode</label>
                        <input id="mal-start" type="number" min="1" ${total ? `max="${total}"` : ""} value="${esc(selectedStart)}">
                        <small class="field-help">Example: start at E24.</small>
                    </div>
                    <div class="watch-field">
                        <label for="mal-count">Number of consecutive episodes</label>
                        <div class="watch-stepper">
                            <button class="btn" data-action="watch-mal-minus" aria-label="Decrease episode count">−</button>
                            <input id="mal-count" type="number" min="1" ${total ? `max="${Math.max(1, total - selectedStart + 1)}"` : ""} value="${esc(selectedCount)}">
                            <button class="btn" data-action="watch-mal-plus" aria-label="Increase episode count">+</button>
                        </div>
                        <small class="field-help">Example: 3 means E24, E25, E26.</small>
                    </div>
                </div>

                <div class="watch-batch-preview">
                    <span>Will update MAL progress to</span>
                    <strong>${selectedCount === 1 ? `E${selectedStart}` : `E${selectedStart}–E${end}`}</strong>
                    <small>${selectedCount} consecutive episode${selectedCount === 1 ? "" : "s"}${total ? ` · limit E${total}` : ""}</small>
                </div>

                <div class="watch-field">
                    <label for="watch-status">MAL status</label>
                    <select id="watch-status">
                        <option value="watching" ${state.watch.status === "watching" ? "selected" : ""}>Watching</option>
                        <option value="completed" ${state.watch.status === "completed" ? "selected" : ""}>Completed</option>
                        <option value="rewatching" ${state.watch.status === "rewatching" ? "selected" : ""}>Rewatching</option>
                        <option value="keep" ${state.watch.status === "keep" ? "selected" : ""}>Keep current status</option>
                    </select>
                </div>

                <div class="watch-actions">
                    <button class="btn" data-action="watch-back-title">Back</button>
                    <button class="btn btn-primary" data-action="watch-review-mal">${state.watch.serviceMode === "both" ? "Continue to Serializd" : "Review changes"}</button>
                </div>
            </div>
        </div>
    `;
}
function renderWatchSeasons() {
    const seasons = state.watch.seasons?.seasons || [];
    view.innerHTML = `
        <div class="view-inner watch-view">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">WATCH · SELECT SEASON</div>
                <h1>${esc(state.watch.serializd?.name || state.watch.query)}</h1>
                <p>Choose the season, then check every episode you watched.</p>
                <div class="watch-header-actions">
                    <button class="btn" data-action="watch-back-results">Back</button>
                    ${watchNewButton()}
                </div>
            </div>
            <div class="panel watch-selection-panel">
                <div class="result-heading">
                    <div><div class="eyebrow">SERIALIZD</div><h2>Seasons / arcs</h2></div>
                    <span class="service-pill">${seasons.length} ${seasons.length === 1 ? "season" : "seasons"}</span>
                </div>
                ${state.watch.serializdCompleted
                    ? `<div class="watch-completed-banner">✓ You have completed this show on Serializd. Selecting an already-watched episode can be logged as a rewatch.</div>`
                    : state.watch.seasons?.show_watched
                        ? `<div class="watch-progress-banner">You have already watched part of this show on Serializd.</div>`
                        : ""}
                <div class="watch-choice-list">
                    ${seasons.length ? seasons.map(season => `
                        <button class="watch-choice" data-action="watch-select-season" data-season-number="${season.season_number}" data-season-id="${season.season_id}">
                            ${season.image_url
                                ? `<img class="watch-season-poster" src="${esc(season.image_url)}" alt="${esc(season.name)} poster" loading="lazy" onerror="this.style.display='none'">`
                                : `<span class="watch-season-poster watch-season-poster-fallback">No poster</span>`}
                            <span class="watch-choice-copy">
                                <strong>S${String(season.season_number).padStart(2, "0")} · ${esc(season.name)}</strong>
                                <small>${esc(season.episode_count)} numbered episodes${season.watched_count ? ` · ${esc(season.watched_count)} watched` : ""}${season.season_completed ? " · Completed" : ""}</small>
                            </span>
                            <span>→</span>
                        </button>
                    `).join("") : `<div class="empty-state compact">No numbered seasons were found.</div>`}
                </div>
            </div>
        </div>
    `;
}

async function loadWatchSeasons() {
    const showId = state.watch.serializd?.id;
    if (!showId) return watchError("The selected Serializd title has no show ID.");
    view.innerHTML = `
        <div class="view-inner">
            <div class="empty-state loading-state">
                <div class="loading-dot"></div>
                <strong>Loading seasons…</strong>
                <span>Reading the selected Serializd show.</span>
            </div>
        </div>
    `;
    try {
        state.watch.seasons = await call("watch_seasons", { show_id: showId });
        state.watch.serializdCurrentlyWatching = state.watch.seasons?.currently_watching === true;
        state.watch.serializdWatchingChoice = null;
        renderWatchSeasons();
    } catch (error) {
        watchError(`Could not load seasons: ${error.message}`);
    }
}

async function loadWatchEpisodes() {
    const showId = state.watch.serializd?.id;
    const seasonNumber = state.watch.season?.season_number;
    if (!showId || !seasonNumber) return watchError("The selected Serializd season is incomplete.");
    view.innerHTML = `
        <div class="view-inner">
            <div class="empty-state loading-state">
                <div class="loading-dot"></div>
                <strong>Loading episodes…</strong>
                <span>Reading the selected Serializd season.</span>
            </div>
        </div>
    `;
    try {
        state.watch.episodes = await call("watch_episodes", {
            show_id: showId,
            season_number: seasonNumber
        });
        state.watch.selectedEpisodes = [];
        renderWatchEpisodes();
    } catch (error) {
        watchError(`Could not load episodes: ${error.message}`);
    }
}

function updateWatchEpisodeSelectionUI() {
    const eps = state.watch.episodes?.episodes || [];
    const selected = new Set(state.watch.selectedEpisodes);
    const allSelected = eps.length > 0 && selected.size === eps.length;

    view.querySelectorAll('button[data-action="watch-toggle-episode"]').forEach(button => {
        const number = Number(button.dataset.episodeNumber);
        const isSelected = selected.has(number);
        button.classList.toggle("watch-episode-selected", isSelected);
        button.setAttribute("aria-pressed", String(isSelected));
        const check = button.querySelector(".watch-episode-check");
        if (check) check.textContent = isSelected ? "✓" : "";
    });

    const toolbarCount = view.querySelector("[data-watch-selection-count]");
    if (toolbarCount) toolbarCount.textContent = `${selected.size} selected`;

    const toolbarMeta = view.querySelector("[data-watch-selection-meta]");
    if (toolbarMeta) {
        toolbarMeta.textContent = `${allSelected ? "Whole season selected" : `${eps.length} numbered episodes available`}${state.watch.episodes?.watched_episode_numbers?.length ? ` · ${state.watch.episodes.watched_episode_numbers.length} already watched` : ""}`;
    }

    const selectAllButton = view.querySelector('[data-action="watch-select-all"]');
    if (selectAllButton) selectAllButton.textContent = allSelected ? "All selected" : "Select all";

    const footerCount = view.querySelector("[data-watch-footer-count]");
    if (footerCount) footerCount.textContent = `${selected.size} episode${selected.size === 1 ? "" : "s"} selected`;

    const hint = view.querySelector("[data-watch-complete-hint]");
    if (hint) hint.remove();
    if (allSelected) {
        const footer = view.querySelector("[data-watch-footer-copy]");
        if (footer) {
            const node = document.createElement("span");
            node.className = "watch-complete-hint";
            node.dataset.watchCompleteHint = "true";
            node.textContent = "✓ Entire numbered season selected — season will be marked complete.";
            footer.appendChild(node);
        }
    }

    const saveButton = view.querySelector('[data-action="watch-review-serializd"]');
    if (saveButton) saveButton.disabled = selected.size === 0;
}

function toggleWatchEpisode(number) {
    const selected = new Set(state.watch.selectedEpisodes);
    if (selected.has(number)) selected.delete(number);
    else selected.add(number);
    state.watch.selectedEpisodes = Array.from(selected).sort((a, b) => a - b);
    // Episode selection is a purely local state change. Update only the
    // affected controls instead of rebuilding the entire Watch screen.
    updateWatchEpisodeSelectionUI();
}

function renderWatchEpisodes() {
    const season = state.watch.season;
    const eps = state.watch.episodes?.episodes || [];
    const selected = new Set(state.watch.selectedEpisodes);
    const allSelected = eps.length > 0 && selected.size === eps.length;

    view.innerHTML = `
        <div class="view-inner watch-view">
            <div class="screen-header watch-screen-header">
                <div class="watch-episode-header">
                    ${season.image_url
                        ? `<img class="watch-episode-poster" src="${esc(season.image_url)}" alt="${esc(season.name)} poster" onerror="this.style.display='none'">`
                        : ""}
                    <div>
                        <div class="eyebrow">WATCH · SELECT EPISODES</div>
                        <h1>${esc(state.watch.serializd?.name || state.watch.query)}</h1>
                        <p>S${String(season.season_number).padStart(2, "0")} · ${esc(season.name)} · Select every episode you watched.</p>
                    </div>
                </div>
                <div class="watch-header-actions">
                    <button class="btn" data-action="watch-back-seasons">Back</button>
                    ${watchNewButton()}
                </div>
            </div>
            <div class="panel watch-selection-panel">
                <div class="watch-episode-toolbar">
                    <div>
                        <strong data-watch-selection-count>${selected.size} selected</strong>
                        <small data-watch-selection-meta>${allSelected ? "Whole season selected" : `${eps.length} numbered episodes available`}${state.watch.episodes?.watched_episode_numbers?.length ? ` · ${state.watch.episodes.watched_episode_numbers.length} already watched` : ""}</small>
                    </div>
                    <div class="watch-actions">
                        <button class="btn" data-action="watch-select-all">${allSelected ? "All selected" : "Select all"}</button>
                        <button class="btn" data-action="watch-clear-all">Clear</button>
                    </div>
                </div>

                <div class="watch-episode-grid">
                    ${eps.map(ep => {
                        const isSelected = selected.has(ep.episode_number);
                        return `
                            <button class="watch-episode ${isSelected ? "watch-episode-selected" : ""}" data-action="watch-toggle-episode" data-episode-number="${ep.episode_number}" aria-pressed="${isSelected}">
                                <span class="watch-episode-check">${isSelected ? "✓" : ""}</span>
                                <strong>E${String(ep.episode_number).padStart(2, "0")}</strong>
                                <span>${esc(ep.title)}</span>
                            </button>
                        `;
                    }).join("")}
                </div>

                <div class="watch-selection-footer">
                    <div data-watch-footer-copy>
                        <strong data-watch-footer-count>${selected.size} episode${selected.size === 1 ? "" : "s"} selected</strong>
                        ${allSelected ? `<span class="watch-complete-hint" data-watch-complete-hint>✓ Entire numbered season selected — season will be marked complete.</span>` : ""}
                    </div>
                    <div class="watch-actions">
                        <button class="btn btn-primary" data-action="watch-review-serializd" ${selected.size ? "" : "disabled"}>Save changes</button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderWatchCombinedPicker() {
    // Serializd selection is primary; MAL mapping is optional and can be set
    // after the Serializd episode selection.
    renderWatchEpisodes();
}

function renderWatchRewatchQuestion() {
    const season = state.watch.season;
    const selected = state.watch.selectedEpisodes || [];
    view.innerHTML = `
        <div class="view-inner watch-view">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">WATCH · REWATCH</div>
                <h1>Are you rewatching this show?</h1>
                <p>Serializd already has this show marked as completed. Tell WAYMARK how to log the selected episode${selected.length === 1 ? "" : "s"}.</p>
                ${watchNewButton()}
            </div>
            <div class="panel watch-rewatch-panel">
                <div class="watch-rewatch-summary">
                    <strong>${esc(state.watch.serializd?.name || state.watch.query)}</strong>
                    ${season ? `<span>S${String(season.season_number).padStart(2, "0")} · ${esc(season.name)}</span>` : ""}
                    <span>${selected.map(n => `E${n}`).join(", ")}</span>
                </div>
                <div class="watch-warning">Choosing <strong>Yes</strong> sends these Serializd logs with its rewatch flag. Choosing <strong>No</strong> records them as normal watch logs.</div>
                <div class="watch-actions">
                    <button class="btn" data-action="watch-back-rewatch">Back</button>
                    <button class="btn" data-action="watch-rewatch-no">No, new watch</button>
                    <button class="btn btn-primary" data-action="watch-rewatch-yes">Yes, rewatching</button>
                </div>
            </div>
        </div>
    `;
}

function renderWatchCurrentlyWatchingQuestion() {
    const season = state.watch.season;
    const selected = state.watch.selectedEpisodes || [];
    view.innerHTML = `
        <div class="view-inner watch-view">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">WATCH · SERIALIZD STATUS</div>
                <h1>Are you watching this show?</h1>
                <p>You logged new episode${selected.length === 1 ? "" : "s"} for a show that is not currently in your Serializd watching list.</p>
                ${watchNewButton()}
            </div>
            <div class="panel watch-rewatch-panel">
                <div class="watch-rewatch-summary">
                    <strong>${esc(state.watch.serializd?.name || state.watch.query)}</strong>
                    ${season ? `<span>S${String(season.season_number).padStart(2, "0")} · ${esc(season.name)}</span>` : ""}
                    <span>${selected.map(n => `E${n}`).join(", ")}</span>
                </div>
                <div class="watch-warning">Choosing <strong>Yes</strong> also marks the show as <strong>Currently Watching</strong> on Serializd. Choosing <strong>No</strong> only logs the selected episode${selected.length === 1 ? "" : "s"}.</div>
                <div class="watch-actions">
                    <button class="btn" data-action="watch-currently-no">No, just log it</button>
                    <button class="btn btn-primary" data-action="watch-currently-yes">Yes, I'm watching</button>
                </div>
            </div>
        </div>
    `;
}

function renderWatchConfirmation() {
    const mode = state.watch.serviceMode;
    const selected = state.watch.selectedEpisodes || [];
    const malEpisodes = state.watch.malEpisodes || [];
    const season = state.watch.season;
    const seasonTotal = Number(state.watch.episodes?.final_episode || 0);
    const seasonCompleted = seasonTotal > 0
        && selected.length === seasonTotal
        && selected.every(n => n >= 1 && n <= seasonTotal);

    view.innerHTML = `
        <div class="view-inner watch-view">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">WATCH · CONFIRM</div>
                <h1>Ready to save?</h1>
                <p>Nothing has been written yet. Review the exact operations below.</p>
                ${watchNewButton()}
            </div>
            <div class="panel watch-confirm-panel">
                <div class="watch-summary">
                    ${mode !== "mal" ? `<div><span>Serializd show</span><strong>${esc(state.watch.serializd?.name || state.watch.query)}</strong></div>` : ""}
                    ${mode !== "mal" ? `<div><span>Serializd episodes</span><strong>${selected.length ? selected.map(n => `E${n}`).join(", ") : "None"}</strong></div>` : ""}
                    ${mode !== "mal" && season ? `<div><span>Season</span><strong>S${String(season.season_number).padStart(2, "0")} · ${esc(season.name)}</strong></div>` : ""}
                    ${mode !== "mal" ? `<div><span>Season completion</span><strong>${seasonCompleted ? "Yes — entire numbered season selected" : "No"}</strong></div>` : ""}
                    ${mode !== "serializd" ? `<div><span>MAL title</span><strong>${esc((state.watch.mal?.node || state.watch.mal)?.title || "Selected MAL title")}</strong></div>` : ""}
                    ${mode !== "serializd" ? `<div><span>MAL episodes</span><strong>${malEpisodes.length ? malEpisodes.map(n => `E${n}`).join(", ") : "None"}</strong></div>` : ""}
                    ${mode !== "serializd" ? `<div><span>MAL status</span><strong>${esc(state.watch.status === "keep" ? "Keep current status" : state.watch.status)}</strong></div>` : ""}
                    ${mode !== "mal" ? `<div><span>Serializd log type</span><strong>${state.watch.serializdRewatch ? "Rewatch" : "New watch log"}</strong></div>` : ""}
                    ${mode !== "mal" && !state.watch.serializdRewatch ? `<div><span>Serializd show status</span><strong>${state.watch.serializdCurrentlyWatching === true ? "Already currently watching" : state.watch.serializdWatchingChoice === true ? "Mark as currently watching" : "Leave current show status unchanged"}</strong></div>` : ""}
                    <div><span>Writes</span><strong>${mode === "both" ? "MAL + Serializd" : mode === "mal" ? "MAL" : "Serializd"}</strong></div>
                </div>
                <div class="watch-warning">This will perform a real write to the selected connected service(s). Continue only if the selections above are correct.</div>
                <div class="watch-actions">
                    <button class="btn" data-action="watch-back-confirm">Back</button>
                    <button class="btn btn-primary" data-action="watch-confirm">YES — Save changes</button>
                </div>
            </div>
        </div>
    `;
}

async function executeWatchBatch() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="empty-state loading-state">
                <div class="loading-dot"></div>
                <strong>Saving your watch…</strong>
                <span>Applying each selected episode through the connected service.</span>
            </div>
        </div>
    `;

    try {
        const seasonTotal = Number(state.watch.episodes?.final_episode || 0) || null;
        const result = await call("watch_execute_batch", {
            mode: state.watch.serviceMode,
            mal_id: state.watch.mal?.node?.id || state.watch.mal?.id || null,
            serializd_id: state.watch.serializd?.id || null,
            serializd_season_id: state.watch.season?.season_id || null,
            season_number: state.watch.season?.season_number || null,
            mal_episodes: state.watch.malEpisodes || [],
            serializd_episodes: state.watch.selectedEpisodes || [],
            mal_total_episodes: malTotalEpisodes(),
            season_total_episodes: seasonTotal,
            status: state.watch.status,
            serializd_rewatch: !!state.watch.serializdRewatch,
            serializd_watching_choice: state.watch.serializdWatchingChoice
        });
        if (result?.show_completed) state.watch.serializdCompleted = true;
        if (result?.ok || result?.partial) {
            saveWatchCheckpoint();
            state.home.library = null;
            state.home.history = null;
            state.home.featuredIndex = 0;
        }
        renderWatchResult(result);
    } catch (error) {
        watchError(`Watch save failed: ${error.message}`);
    }
}

function renderWatchResult(result) {
    const operations = Array.isArray(result?.operations) ? result.operations : [];
    const failed = operations.filter(op => !op.ok);
    const succeeded = operations.filter(op => op.ok);

    view.innerHTML = `
        <div class="view-inner watch-view">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">WATCH · RESULT</div>
                <h1>${result?.ok ? "Watch saved" : result?.partial ? "Partially saved" : "Watch not saved"}</h1>
                <p>${result?.ok ? "WAYMARK completed the requested service updates." : "Review the operation results before retrying."}</p>
                ${watchNewButton()}
            </div>
            <div class="panel">
                <div class="watch-result-list">
                    ${succeeded.map(op => `<div class="watch-result ok">✓ ${esc(op.name)}</div>`).join("")}
                    ${failed.map(op => `<div class="watch-result failed">✕ ${esc(op.name)} — ${esc(op.error)}</div>`).join("")}
                    ${result?.season_completed ? `<div class="watch-result ok">✓ Serializd season completed</div>` : ""}
                    ${result?.show_completed ? `<div class="watch-result ok">✓ Serializd show completed</div>` : ""}
                    ${Array.isArray(result?.skipped_existing) && result.skipped_existing.length ? `<div class="watch-result">Already logged / skipped: ${result.skipped_existing.length}</div>` : ""}
                </div>
                <div class="watch-actions">
                    <button class="btn" data-action="watch-history">View history</button>
                    <button class="btn btn-primary" data-action="watch-start-over">Log another</button>
                </div>
            </div>
        </div>
    `;
}


// M20.5.9 — Rating + Progress workflow. This is deliberately separate from
// Review and Watch so the existing verified workflows remain isolated.
function resetRate() {
    state.rate = {
        query: "", isAnime: null, mediaType: null, catalog: null, mal: null,
        serializd: null, service: null, malStatus: null, malRating: "",
        malProgress: 0, malTotal: 0, malOriginal: null, serializdTarget: null,
        seasons: null, season: null, episodes: null, serializdRating: "",
        serializdProgressTarget: "", serializdProgressSelected: [], serializdProgressRewatch: false, serializdExisting: null, serializdRatingTouched: false, confirmation: false,
        loading: false, loadingKey: "", requestSeq: 0, pending: null
    };
}

function rateEntry() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header"><div class="eyebrow">RATE + UPDATE</div><h1>Update something</h1><p>Choose a title, then update its rating, progress, and service-specific status.</p></div>
            <div class="panel search-entry-panel"><div class="search-bar"><input id="rate-q" type="search" placeholder="Search a title..." value="${esc(state.rate.query)}" autocomplete="off"><button class="btn btn-primary" data-action="rate-search">Search</button></div><div class="search-hint">For anime TV, MyAnimeList appears first and Serializd appears second. Their data stays independent.</div></div>
        </div>`;
}

function rateAnimeQuestion() {
    view.innerHTML = `<div class="view-inner"><div class="screen-header"><div class="eyebrow">RATE + UPDATE · 1 OF 2</div><h1>${esc(state.rate.query)}</h1><p>Tell WAYMARK how to route this title.</p></div><div class="panel question-panel"><div class="question-title">Is it an anime?</div><div class="choice-row"><button class="btn" data-action="rate-back-entry">Back</button><button class="btn btn-choice" data-action="rate-anime-yes">Yes</button><button class="btn btn-choice" data-action="rate-anime-no">No</button></div></div></div>`;
}

function rateTypeQuestion() {
    view.innerHTML = `<div class="view-inner"><div class="screen-header"><div class="eyebrow">RATE + UPDATE · 2 OF 2</div><h1>${esc(state.rate.query)}</h1><p>Choose the media type.</p></div><div class="panel question-panel"><div class="question-title">Is it a TV show or a movie?</div><div class="choice-row"><button class="btn" data-action="rate-back-anime">Back</button><button class="btn btn-choice" data-action="rate-type-tv">TV Show</button><button class="btn btn-choice" data-action="rate-type-movie">Movie</button></div></div></div>`;
}

async function finishRateSearch() {
    view.innerHTML = `<div class="view-inner"><div class="empty-state loading-state"><div class="loading-dot"></div><strong>Searching connected catalogs…</strong><span>Checking the services that support this media type.</span></div></div>`;
    try { state.rate.catalog = await call("search_catalogs", {query: state.rate.query, is_anime: state.rate.isAnime === true, media_type: state.rate.mediaType || "tv"}); renderRateResults(); }
    catch (error) { view.innerHTML = `<div class="view-inner"><div class="empty-state"><strong>Search failed</strong><span>${esc(error.message)}</span><button class="btn" data-action="rate-start-over">Start over</button></div></div>`; }
}

function rateResultCard(service, item, index) {
    const isMal = service === "mal";
    const node = isMal ? (item.node || item) : item;
    const title = node.title || node.name || "Untitled";
    const id = node.id || "";
    const image = isMal ? (node.image_url || node.main_picture?.large || node.main_picture?.medium) : (item.image_url || item.image || item.poster);
    return `<button class="watch-result-row" data-action="rate-select-title" data-service="${service}" data-index="${index}">${image ? `<img class="watch-result-poster" src="${esc(image)}" alt="" loading="lazy" onerror="this.style.display='none'">` : `<span class="watch-result-poster watch-result-poster-fallback">No poster</span>`}<span class="watch-result-copy"><span class="eyebrow">${isMal ? "MYANIMELIST" : "SERIALIZD"}</span><strong>${esc(title)}</strong><small>${isMal ? `MAL ID: ${esc(id)}` : `Serializd ID: ${esc(id)}`}</small></span><span class="service-pill">Select</span></button>`;
}

function renderRateResults() {
    const c=state.rate.catalog||{}; const mal=c.mal?.results||[]; const sz=c.serializd?.results||[];
    const malAllowed=state.rate.isAnime===true; const szAllowed=state.rate.mediaType==="tv";
    view.innerHTML=`<div class="view-inner watch-view"><div class="screen-header watch-screen-header"><div class="eyebrow">RATE + UPDATE · SELECT TITLE</div><h1>${esc(state.rate.query)}</h1><p>${malAllowed?"Anime TV results are ordered MyAnimeList first, then Serializd.":"Choose the Serializd TV identity to update."}</p><div class="watch-header-actions"><button class="btn" data-action="rate-start-over">Start over</button></div></div>${malAllowed?`<div class="panel"><div class="result-heading"><div><div class="eyebrow">MYANIMELIST</div><h2>${mal.length} matches</h2></div></div><div class="watch-result-list">${mal.length?mal.map((x,i)=>rateResultCard("mal",x,i+1)).join(""):`<div class="empty-state compact">No MyAnimeList results.</div>`}</div></div>`:""}${szAllowed?`<div class="panel"><div class="result-heading"><div><div class="eyebrow">SERIALIZD</div><h2>${sz.length} matches</h2></div></div><div class="watch-result-list">${sz.length?sz.map((x,i)=>rateResultCard("serializd",x,i+1)).join(""):`<div class="empty-state compact">No Serializd results.</div>`}</div></div>`:""}</div>`;
}

function malRateTitle() { return state.rate.mal?.node?.title || state.rate.mal?.title || state.rate.query; }
function malStatuses() { return ["watching","completed","on_hold","dropped","rewatching"]; }
function renderMalUpdate() {
    const r=state.rate, st=r.malStatus||{}, ls=st.my_list_status||{};
    const rawStatus=ls.status||""; const status=malStatuses().includes(rawStatus)?rawStatus:""; const current=Number(ls.num_episodes_watched||0); const total=Number(r.malTotal||r.mal?.details?.num_episodes||r.mal?.node?.num_episodes||0)||0; r.malProgress=Number.isFinite(Number(r.malProgress))?Number(r.malProgress):current; r.malTotal=total;
    view.innerHTML=`<div class="view-inner watch-view"><div class="screen-header watch-screen-header"><div class="eyebrow">MYANIMELIST · UPDATE</div><h1>${esc(malRateTitle())}</h1><p>Title-level rating and progress. MyAnimeList does not use episode-by-episode ratings here.</p><div class="watch-header-actions"><button class="btn" data-action="rate-back-results">Back</button></div></div><div class="panel review-editor-panel"><div class="review-field"><label for="mal-rating">Rating</label><select id="mal-rating"><option value="">No rating change</option>${Array.from({length:10},(_,i)=>i+1).map(n=>`<option value="${n}" ${String(r.malRating)===String(n)?"selected":""}>${n} / 10</option>`).join("")}</select><small>One whole-number title rating from 1–10.</small></div><div class="review-field"><label for="mal-progress">Progress</label><input id="mal-progress" type="number" min="0" ${total?`max="${total}"`:""} value="${esc(r.malProgress)}"><small>Current: ${current}${total?` / ${total}`:" episodes"}. If status is Completed, progress is set to the known total.</small></div><div class="review-field"><label for="mal-status">Status</label><select id="mal-status"><option value="" ${status===""?"selected":""}>No status change</option>${malStatuses().map(v=>`<option value="${v}" ${status===v?"selected":""}>${v=== "on_hold"?"On Hold":v.charAt(0).toUpperCase()+v.slice(1)}</option>`).join("")}</select></div><div class="watch-warning">MAL changes are independent from Serializd. No MAL review text or episode rating is offered.</div><div class="watch-actions"><button class="btn" data-action="rate-back-results">Back</button><button class="btn btn-primary" data-action="rate-preview-mal">Review changes</button></div></div></div>`;
}

function captureMalRate() { const r=state.rate; r.malRating=document.getElementById("mal-rating")?.value||""; const p=document.getElementById("mal-progress"); r.malProgress=p?.value===""?null:Number(p.value); r.malStatus=document.getElementById("mal-status")?.value||null; if(r.malStatus==="completed" && r.malTotal>0) r.malProgress=r.malTotal; }

function renderRateConfirmation() {
    const r=state.rate; const mal= r.pending?.service==="mal"; const sz= r.pending?.service==="serializd";
    view.innerHTML=`<div class="view-inner watch-view"><div class="screen-header watch-screen-header"><div class="eyebrow">RATE + UPDATE · CONFIRM</div><h1>Ready to update?</h1><p>Nothing has been written yet. Review the exact changes.</p></div><div class="panel watch-confirm-panel"><div class="watch-summary">${mal?`<div><span>Service</span><strong>MyAnimeList</strong></div><div><span>Title</span><strong>${esc(malRateTitle())}</strong></div><div><span>Rating</span><strong>${r.malRating?`${esc(r.malRating)} / 10`:"No change"}</strong></div><div><span>Progress</span><strong>${r.malProgress!=null?`${esc(r.malProgress)}${r.malTotal?` / ${r.malTotal}`:""}`:"No change"}</strong></div><div><span>Status</span><strong>${esc(r.malStatus||"No change")}</strong></div>`:""}${sz?`<div><span>Service</span><strong>Serializd</strong></div><div><span>Title</span><strong>${esc(r.serializd?.name||r.serializd?.title||r.query)}</strong></div><div><span>Target</span><strong>${esc(r.serializdTarget)}</strong></div><div><span>Rating</span><strong>${r.serializdRating?`${esc(r.serializdRating)} / 5`:"No rating change"}</strong></div>${r.serializdTarget==="progress"?`<div><span>Episodes</span><strong>${(r.serializdProgressSelected||[]).map(n=>`E${String(n).padStart(2,"0")}`).join(", ")}</strong></div><div><span>Log type</span><strong>${r.serializdProgressRewatch?"Rewatch":"Normal watch"}</strong></div>`:""}`:""}</div><div class="watch-warning">This performs a real write to ${mal?"MyAnimeList":"Serializd"}.</div><div class="watch-actions"><button class="btn" data-action="rate-back-confirm">Back</button><button class="btn btn-primary" data-action="rate-confirm">YES — Update</button></div></div></div>`;
}

async function selectRateTitle(service,index) {
    const results=service==="mal"?state.rate.catalog.mal.results:state.rate.catalog.serializd.results;
    const item=results[index-1]; if(!item) return;

    if(service === "serializd") {
        // The Rate workflow only needs the canonical Serializd show ID to
        // continue into seasons/episodes. Keep the selected catalog item
        // immediately so a detail-surface failure cannot erase the identity.
        const baseId = item.id ?? item.serializd_id ?? item.show_id;
        if(!baseId) { msg("Selected Serializd result has no show ID."); return; }
        state.rate.serializd = { ...item, id: Number(baseId) || baseId };
        state.rate.service = "serializd";
        // The catalog result already contains the canonical ID required by
        // Rating/Progress. Do not make a second select/details request here;
        // none of the Serializd Rating/Progress screens need it.
        renderSerializdUpdateChoice();
        return;
    }

    try {
        const picked=await call("select_search_result",{service,results,index});
        state.rate.mal={...item,...picked.selected,details:picked.details};
        state.rate.malTotal=Number(picked.details?.num_episodes||item.node?.num_episodes||0)||0;
        state.rate.service="mal";
        state.rate.malStatus=await call("mal_status",{mal_id:item.node?.id||item.id});
        state.rate.malOriginal=state.rate.malStatus;
        const ls=state.rate.malStatus?.my_list_status||{};
        state.rate.malProgress=Number(ls.num_episodes_watched||0);
        state.rate.malRating=ls.score?String(ls.score):"";
        renderMalUpdate();
    } catch(error){
        msg(`Could not load MyAnimeList details: ${error.message}`);
    }
}

function renderSerializdCatalogOnly() {
    const results = state.rate.catalog?.serializd?.results || [];
    view.innerHTML = `<div class="view-inner watch-view"><div class="screen-header watch-screen-header"><div class="eyebrow">SERIALIZD · SELECT TITLE</div><h1>${esc(state.rate.query)}</h1><p>Choose the Serializd identity to continue.</p><div class="watch-header-actions"><button class="btn" data-action="rate-start-over">Start over</button></div></div><div class="panel"><div class="watch-result-list">${results.length ? results.map((x,i)=>rateResultCard("serializd",x,i+1)).join("") : `<div class="empty-state compact">No Serializd result was found for this title.</div>`}</div></div></div>`;
}

function renderSerializdUpdateChoice() {
    const r=state.rate; view.innerHTML=`<div class="view-inner watch-view"><div class="screen-header watch-screen-header"><div class="eyebrow">SERIALIZD · UPDATE</div><h1>${esc(r.serializd?.name||r.serializd?.title||r.query)}</h1><p>Choose what you want to update on Serializd. This remains separate from MyAnimeList.</p><div class="watch-header-actions"><button class="btn" data-action="rate-back-results">Back</button></div></div><div class="panel"><div class="action-grid">${card("★","Rating","Rate the series, a season, or an episode.","rate-sz-rating")}${card("↗","Progress","Move Serializd progress to a target episode.","rate-sz-progress")}</div></div></div>`;
}

function renderSerializdRatingTargetChoice() {
    const r=state.rate; view.innerHTML=`<div class="view-inner watch-view"><div class="screen-header watch-screen-header"><div class="eyebrow">SERIALIZD · RATING TARGET</div><h1>${esc(r.serializd?.name||r.query)}</h1><p>Choose whether the rating belongs to the series, a season, or an episode.</p><div class="watch-header-actions"><button class="btn" data-action="rate-sz-back">Back</button></div></div><div class="panel"><div class="action-grid">${card("◎","Series","Rate the whole series.","rate-sz-series")}${card("◉","Season","Choose a season and rate it.","rate-sz-season")}${card("◌","Episode","Choose a season and episode, then rate it.","rate-sz-episode")}</div></div></div>`;
}

function beginRateLoad(key, message) {
    const token = ++state.rate.requestSeq;
    state.rate.loading = true;
    state.rate.loadingKey = key;
    view.innerHTML = `<div class="view-inner"><div class="empty-state loading-state"><div class="loading-dot"></div><strong>${esc(message)}</strong><span>Serializd is responding. Please wait — the controls are temporarily locked to prevent duplicate requests.</span></div></div>`;
    return token;
}

function rateLoadCurrent(token) {
    return token === state.rate.requestSeq;
}

function endRateLoad(token) {
    if (rateLoadCurrent(token)) {
        state.rate.loading = false;
        state.rate.loadingKey = "";
    }
}

async function loadRateSeasons() {
    const token = beginRateLoad("seasons", "Loading Serializd seasons…");
    try {
        const data = await call("serializd_seasons", {show_id:state.rate.serializd.id});
        if (!rateLoadCurrent(token)) return;
        state.rate.seasons = data;
        renderRateSeasons();
    } catch(e) {
        if (!rateLoadCurrent(token)) return;
        msg(`Could not load seasons: ${e.message}`);
        renderSerializdUpdateChoice();
    } finally {
        endRateLoad(token);
    }
}
function renderRateSeasons() { const seasons=state.rate.seasons?.seasons||[]; view.innerHTML=`<div class="view-inner watch-view"><div class="screen-header watch-screen-header"><div class="eyebrow">SERIALIZD · SELECT SEASON</div><h1>${esc(state.rate.serializd?.name||state.rate.query)}</h1><p>Choose a numbered season.</p></div><div class="panel"><div class="watch-choice-list">${seasons.map(s=>`<button class="watch-choice" data-action="rate-select-season" data-season-id="${s.season_id}" data-season-number="${s.season_number}"><span class="watch-choice-copy"><strong>S${String(s.season_number).padStart(2,"0")} · ${esc(s.name)}</strong><small>${s.episode_count||"?"} episodes</small></span><span>→</span></button>`).join("")}</div></div></div>`; }
async function loadRateEpisodes() {
    const token = beginRateLoad("episodes", `Loading S${String(state.rate.season?.season_number || 0).padStart(2,"0")} episodes…`);
    try {
        const data = await call("watch_episodes", {show_id:state.rate.serializd.id, season_number:state.rate.season.season_number});
        if (!rateLoadCurrent(token)) return;
        state.rate.episodes = data;
        renderRateEpisodes();
    } catch(e) {
        if (!rateLoadCurrent(token)) return;
        msg(`Could not load episodes: ${e.message}`);
        renderRateSeasons();
    } finally {
        endRateLoad(token);
    }
}
function renderRateEpisodes() { const eps=state.rate.episodes?.episodes||[]; view.innerHTML=`<div class="view-inner watch-view"><div class="screen-header watch-screen-header"><div class="eyebrow">SERIALIZD · SELECT EPISODE</div><h1>${esc(state.rate.serializd?.name||state.rate.query)}</h1><p>S${String(state.rate.season.season_number).padStart(2,"0")} · Choose an episode.</p></div><div class="panel"><div class="watch-episode-grid">${eps.map(ep=>`<button type="button" class="watch-episode" data-action="rate-select-episode" data-episode-number="${ep.episode_number}"><strong>E${String(ep.episode_number).padStart(2,"0")}</strong><span>${esc(ep.title)}</span></button>`).join("")}</div></div></div>`; }
function renderSerializdRatingEditor() {
    const r = state.rate;
    view.innerHTML = `<div class="view-inner review-view"><div class="screen-header"><div class="eyebrow">SERIALIZD · RATING</div><h1>${esc(r.serializd?.name||r.query)}</h1><p>${esc(r.serializdTarget)}</p><div class="watch-header-actions"><button class="btn" data-action="rate-sz-back">Back</button></div></div><div class="panel review-editor-panel"><div class="review-field"><label for="sz-rating">Rating</label><select id="sz-rating"><option value="">No rating</option>${Array.from({length:10},(_,i)=>i+1).map(n=>{const v=(n/2).toFixed(1);return `<option value="${v}" ${String(r.serializdRating)===v?"selected":""}>${v} / 5</option>`}).join("")}</select><small data-rate-existing-status>${r.serializdExisting ? "Existing rating loaded." : "Checking existing rating in the background…"}</small></div><div class="watch-warning">Rating-only mode writes no review text. Existing Review workflow remains unchanged.</div><div class="watch-actions"><button class="btn" data-action="rate-sz-back">Back</button><button class="btn btn-primary" data-action="rate-preview-sz">Review changes</button></div></div></div>`;
}

async function loadRateExisting() {
    const r = state.rate;
    const token = ++state.rate.requestSeq;
    state.rate.loading = true;
    state.rate.loadingKey = "existing-rating";
    const target = r.serializdTarget;
    const showId = r.serializd?.id;
    const seasonId = r.season?.season_id || null;
    const episodeNumber = r.episode?.episode_number || null;
    try {
        const data = await call("review_existing", {target, show_id:showId, season_id:seasonId, episode_number:episodeNumber});
        if (!rateLoadCurrent(token)) return;
        r.serializdExisting = data?.matches?.[0] || null;
        if (!r.serializdRatingTouched && r.serializdExisting?.stars != null) {
            r.serializdRating = String(r.serializdExisting.stars);
            const select = document.getElementById("sz-rating");
            if (select) select.value = r.serializdRating;
        }
        const status = document.querySelector("[data-rate-existing-status]");
        if (status) status.textContent = r.serializdExisting?.stars != null ? "Existing rating loaded." : "No existing rating found.";
    } catch(_) {
        if (!rateLoadCurrent(token)) return;
        r.serializdExisting = null;
        const status = document.querySelector("[data-rate-existing-status]");
        if (status) status.textContent = "Could not check existing rating; you can still enter a new one.";
    } finally {
        endRateLoad(token);
    }
}
function renderSerializdProgressEditor() {
    const r = state.rate;
    const eps = r.episodes?.episodes || [];
    const watched = new Set(r.episodes?.watched_episode_numbers || []);
    const selected = new Set(r.serializdProgressSelected || []);
    const allSelected = eps.length > 0 && selected.size === eps.length;
    const watchedCount = watched.size;
    view.innerHTML = `
        <div class="view-inner watch-view">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">SERIALIZD · SELECT EPISODES</div>
                <h1>${esc(r.serializd?.name || r.query)}</h1>
                <p>S${String(r.season.season_number).padStart(2,"0")} · ${watchedCount} of ${eps.length} numbered episodes are already logged.</p>
                <div class="watch-header-actions"><button class="btn" data-action="rate-sz-back">Back</button></div>
            </div>
            <div class="panel watch-selection-panel">
                <div class="watch-episode-toolbar">
                    <div>
                        <strong>${selected.size} selected</strong>
                        <small>${allSelected ? "Whole season selected" : "Select the episodes you want to update"} · ${watchedCount} already logged</small>
                    </div>
                    <div class="watch-actions">
                        <button class="btn" data-action="rate-progress-select-all">${allSelected ? "All selected" : "Select all"}</button>
                        <button class="btn" data-action="rate-progress-clear-all">Clear</button>
                    </div>
                </div>
                <div class="watch-episode-grid">
                    ${eps.map(ep => {
                        const n = Number(ep.episode_number);
                        const isSelected = selected.has(n);
                        const isWatched = watched.has(n);
                        return `<button type="button" class="watch-episode ${isSelected ? "watch-episode-selected" : ""}" data-action="rate-progress-toggle-episode" data-episode-number="${n}" aria-pressed="${isSelected}">
                            <span class="watch-episode-check">${isSelected ? "✓" : ""}</span>
                            <strong>E${String(n).padStart(2,"0")}</strong>
                            <span>${esc(ep.title)}</span>
                            <span>${isWatched ? "Already logged" : "Not logged"}</span>
                        </button>`;
                    }).join("")}
                </div>
                <div class="watch-selection-footer">
                    <div>
                        <strong>${selected.size} episode${selected.size === 1 ? "" : "s"} selected</strong>
                        <span>${selected.size ? "You will choose Normal watch or Rewatching next." : "Select at least one episode."}</span>
                    </div>
                    <div class="watch-actions">
                        <button class="btn btn-primary" data-action="rate-preview-sz-progress" ${selected.size ? "" : "disabled"}>Review changes</button>
                    </div>
                </div>
            </div>
        </div>`;
}

function renderSerializdProgressRewatchQuestion() {
    const r = state.rate;
    const selected = (r.serializdProgressSelected || []).slice().sort((a,b)=>a-b);
    const watched = new Set(r.episodes?.watched_episode_numbers || []);
    const already = selected.filter(n => watched.has(n));
    view.innerHTML = `
        <div class="view-inner watch-view">
            <div class="screen-header watch-screen-header">
                <div class="eyebrow">SERIALIZD · PROGRESS</div>
                <h1>Are you rewatching these episodes?</h1>
                <p>Choose how Serializd should log the ${selected.length} selected episode${selected.length === 1 ? "" : "s"}.</p>
            </div>
            <div class="panel watch-rewatch-panel">
                <div class="watch-rewatch-summary">
                    <strong>${esc(r.serializd?.name || r.query)}</strong>
                    <span>S${String(r.season.season_number).padStart(2,"0")} · ${selected.map(n=>`E${String(n).padStart(2,"0")}`).join(", ")}</span>
                    ${already.length ? `<span>${already.length} selected episode${already.length === 1 ? " is" : "s are"} already logged.</span>` : `<span>None of the selected episodes are currently logged.</span>`}
                </div>
                <div class="watch-warning">Choose <strong>Yes</strong> to log the selected episodes as a Serializd rewatch. Choose <strong>No</strong> to add only episodes that are not already logged.</div>
                <div class="watch-actions">
                    <button class="btn" data-action="rate-progress-rewatch-back">Back</button>
                    <button class="btn" data-action="rate-progress-rewatch-no">No — normal watch</button>
                    <button class="btn btn-primary" data-action="rate-progress-rewatch-yes">Yes — rewatching</button>
                </div>
            </div>
        </div>`;
}

async function executeRate() {
    if (state.rate.loading) return;
    const r=state.rate;
    const pending=r.pending||{};
    const token = ++state.rate.requestSeq;
    state.rate.loading = true;
    state.rate.loadingKey = "submit";
    view.innerHTML=`<div class="view-inner"><div class="empty-state loading-state"><div class="loading-dot"></div><strong>Updating ${pending.service==="mal"?"MyAnimeList":"Serializd"}…</strong><span>Writing once. Please wait — duplicate submissions are locked.</span></div></div>`;
    try {
        let result;
        if(pending.service==="mal"){
            result=await call("mal_update",{mal_id:r.mal.node?.id||r.mal.id,rating:r.malRating?Number(r.malRating):null,progress:r.malProgress,status:r.malStatus,total_episodes:r.malTotal});
            if (token === state.rate.requestSeq) { state.home.library = null; state.home.history = null; state.home.featuredIndex = 0; renderRateResult(result,"MyAnimeList"); }
        } else if(pending.kind==="rating"){
            result=await call("serializd_rate",{target:r.serializdTarget,show_id:r.serializd.id,season_id:r.season?.season_id||null,episode_number:r.episode?.episode_number||null,stars:r.serializdRating?Number(r.serializdRating):null,existing:r.serializdExisting});
            if (token === state.rate.requestSeq) { state.home.library = null; state.home.history = null; state.home.featuredIndex = 0; renderRateResult(result,"Serializd"); }
        } else {
            result=await call("serializd_progress",{show_id:r.serializd.id,season_id:r.season.season_id,season_number:r.season.season_number,selected_episode_numbers:r.serializdProgressSelected||[],watched_episode_numbers:r.episodes?.watched_episode_numbers||[],rewatch:!!r.serializdProgressRewatch,season_total_episodes:Number(r.episodes?.final_episode||0)||null});
            if (token === state.rate.requestSeq) { state.home.library = null; state.home.history = null; state.home.featuredIndex = 0; renderRateResult(result,"Serializd"); }
        }
    } catch(e){
        if (token === state.rate.requestSeq) renderRateResult({ok:false,error:e.message},pending.service==="mal"?"MyAnimeList":"Serializd");
    } finally {
        if (token === state.rate.requestSeq) { state.rate.loading=false; state.rate.loadingKey=""; }
    }
}
function renderRateResult(result,service){
    const ok=!!result?.ok;
    const pending=state.rate.pending||{};
    const r=state.rate;
    const progress=pending.kind==="progress" && service==="Serializd";
    const rating=pending.kind==="rating" && service==="Serializd";
    const targetLabel = r.serializdTarget === "episode" ? "episode" : r.serializdTarget === "season" ? "season" : "series";
    const details = progress && ok
        ? `<div class="watch-result-list"><div class="watch-result ok">✓ ${esc(service)}</div><div class="watch-result">Logged: ${Number(result.logged?.length||0)} episode${result.logged?.length===1?"":"s"}</div><div class="watch-result">Already logged / skipped: ${Number(result.skipped_existing?.length||0)}</div><div class="watch-result">Log type: ${result.rewatch?"Rewatch":"Normal watch"}</div>${result.season_completed?`<div class="watch-result ok">✓ Season marked complete</div>`:""}</div>`
        : rating && ok
            ? `<div class="watch-result-list"><div class="watch-result ok">✓ ${esc(service)} rating saved</div><div class="watch-result ok">✓ ${esc(targetLabel.charAt(0).toUpperCase()+targetLabel.slice(1))} marked as watched</div></div>`
            : `<div class="watch-result-list"><div class="watch-result ${ok?"ok":"failed"}">${ok?"✓":"✕"} ${esc(service)}</div></div>`;
    view.innerHTML=`<div class="view-inner watch-view"><div class="screen-header watch-screen-header"><div class="eyebrow">RATE + UPDATE · RESULT</div><h1>${ok?`${service} updated`: `${service} update failed`}</h1><p>${ok?"The requested change was accepted.":esc(result?.error||"Update failed.")}</p></div><div class="panel">${details}<div class="watch-actions">${ok&&service==="MyAnimeList"&&state.rate.mediaType==="tv"?`<button class="btn btn-primary" data-action="rate-continue-serializd">Continue to Serializd</button>`:`<button class="btn btn-primary" data-action="rate-start-over">Done</button>`}</div></div></div>`;
}

// M20.5.8 — Review workflow. This is intentionally separate from Watch so
// existing Watch/Search/Library/History behavior remains unchanged.
function resetReview() {
    state.review = {
        query: "",
        catalog: null,
        serializd: null,
        target: null,
        seasons: null,
        season: null,
        episodes: null,
        episode: null,
        stars: "",
        text: "",
        isRewatch: false,
        containsSpoiler: false,
        like: false,
        allowsComments: true,
        backdate: null,
        existing: null,
        editing: false,
        reviewId: null,
        focus: "review",
        confirmation: false
    };
}

function reviewEntry() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header">
                <div class="eyebrow">REVIEW · STEP 1</div>
                <h1>${state.review.focus === "rating" ? "Rate something" : "What do you want to review?"}</h1>
                <p>Search a Serializd TV show, then choose the series, season, or episode you want to review.</p>
            </div>
            <div class="panel review-entry-panel">
                <div class="search-bar">
                    <input id="review-q" type="search" placeholder="Search a TV show..." value="${esc(state.review.query)}" autocomplete="off">
                    <button class="btn btn-primary" data-action="review-search">Continue</button>
                </div>
                <div class="watch-note">Nothing is written during search or selection. A final confirmation is required before saving.</div>
            </div>
        </div>
    `;
}

async function finishReviewSearch() {
    view.innerHTML = `
        <div class="view-inner">
            <div class="empty-state loading-state"><div class="loading-dot"></div><strong>Finding your title…</strong><span>Checking Serializd.</span></div>
        </div>
    `;
    try {
        state.review.catalog = await call("search_catalogs", {
            query: state.review.query,
            is_anime: false,
            media_type: "tv"
        });
        renderReviewResults();
    } catch (error) {
        reviewError(`Review search failed: ${error.message}`);
    }
}

function reviewError(message) {
    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header"><div class="eyebrow">REVIEW</div><h1>Review setup</h1><p>WAYMARK could not continue the review workflow.</p></div>
            <div class="panel"><div class="error-box">${esc(message)}</div><button class="btn" data-action="review-start-over">Start over</button></div>
        </div>
    `;
}

function reviewTitle() {
    return state.review.serializd?.name || state.review.serializd?.title || state.review.query || "Selected title";
}

function renderReviewResults() {
    const results = state.review.catalog?.serializd?.results || [];
    view.innerHTML = `
        <div class="view-inner review-view">
            <div class="screen-header">
                <div><div class="eyebrow">REVIEW · SELECT TITLE</div><h1>${esc(state.review.query)}</h1><p>Select the Serializd identity you want to review.</p></div>
                <div class="watch-header-actions"><button class="btn" data-action="review-back-entry">Back</button><button class="btn" data-action="review-start-over">New Review</button></div>
            </div>
            <div class="panel review-selection-panel">
                <div class="result-heading"><div><div class="eyebrow">SERIALIZD</div><h2>TV shows</h2></div><span class="service-pill">${results.length} ${results.length === 1 ? "match" : "matches"}</span></div>
                <div class="result-list">
                    ${results.length ? results.map((item, i) => `
                        <button class="result-row review-result-select" data-action="review-select-title" data-index="${i + 1}">
                            ${watchPosterMarkup(item, "serializd", `${item.name || item.title || "Serializd"} poster`)}
                            <span class="result-copy"><strong>${esc(item.name || item.title || "Untitled")}</strong><small>Serializd ID: ${esc(item.id ?? "—")}</small></span><span class="result-arrow">→</span>
                        </button>
                    `).join("") : `<div class="empty-state compact">No Serializd matches found.</div>`}
                </div>
            </div>
        </div>
    `;
}

function renderReviewTargetChoice() {
    view.innerHTML = `
        <div class="view-inner review-view">
            <div class="screen-header"><div class="eyebrow">REVIEW · STEP 2</div><h1>${esc(reviewTitle())}</h1><p>What part of this show do you want to review?</p></div>
            <div class="panel question-panel review-target-panel">
                <div class="choice-row review-target-grid">
                    <button class="btn btn-choice" data-action="review-target-series">Series</button>
                    <button class="btn btn-choice" data-action="review-target-season">Season</button>
                    <button class="btn btn-choice" data-action="review-target-episode">Episode</button>
                </div>
                <div class="watch-actions"><button class="btn" data-action="review-back-results">Back</button><button class="btn" data-action="review-start-over">New Review</button></div>
            </div>
        </div>
    `;
}

async function loadReviewSeasons() {
    const id = state.review.serializd?.id;
    if (!id) return reviewError("The selected Serializd title has no show ID.");
    view.innerHTML = `<div class="view-inner"><div class="empty-state loading-state"><div class="loading-dot"></div><strong>Loading seasons…</strong><span>Reading the selected Serializd show.</span></div></div>`;
    try {
        state.review.seasons = await call("review_seasons", { show_id: id });
        renderReviewSeasons();
    } catch (error) { reviewError(`Could not load seasons: ${error.message}`); }
}

function renderReviewSeasons() {
    const seasons = state.review.seasons?.seasons || [];
    view.innerHTML = `
        <div class="view-inner review-view">
            <div class="screen-header"><div class="eyebrow">REVIEW · SELECT SEASON</div><h1>${esc(reviewTitle())}</h1><p>Choose the season you want to review.</p><div class="watch-header-actions"><button class="btn" data-action="review-back-target">Back</button><button class="btn" data-action="review-start-over">New Review</button></div></div>
            <div class="panel review-selection-panel"><div class="result-heading"><div><div class="eyebrow">SERIALIZD</div><h2>Seasons</h2></div><span class="service-pill">${seasons.length}</span></div>
                <div class="watch-choice-list">${seasons.length ? seasons.map(season => `
                    <button class="watch-choice" data-action="review-select-season" data-season-number="${season.season_number}" data-season-id="${season.season_id}">
                        ${season.image_url ? `<img class="watch-season-poster" src="${esc(season.image_url)}" alt="${esc(season.name)} poster" loading="lazy" onerror="this.style.display='none'">` : `<span class="watch-season-poster watch-season-poster-fallback">No poster</span>`}
                        <span class="watch-choice-copy"><strong>S${String(season.season_number).padStart(2,"0")} · ${esc(season.name)}</strong><small>${season.episode_count != null ? `${esc(season.episode_count)} episodes` : "Episode count unavailable"}</small></span><span>→</span>
                    </button>`).join("") : `<div class="empty-state compact">No numbered seasons were found.</div>`}</div>
            </div>
        </div>
    `;
}

async function loadReviewEpisodes() {
    const showId = state.review.serializd?.id;
    const seasonNumber = state.review.season?.season_number;
    if (!showId || !seasonNumber) return reviewError("The selected Review season is incomplete.");
    view.innerHTML = `<div class="view-inner"><div class="empty-state loading-state"><div class="loading-dot"></div><strong>Loading episodes…</strong><span>Reading the selected Serializd season.</span></div></div>`;
    try {
        state.review.episodes = await call("review_episodes", { show_id: showId, season_number: seasonNumber });
        renderReviewEpisodes();
    } catch (error) { reviewError(`Could not load episodes: ${error.message}`); }
}

function renderReviewEpisodes() {
    const eps = state.review.episodes?.episodes || [];
    view.innerHTML = `
        <div class="view-inner review-view">
            <div class="screen-header"><div class="eyebrow">REVIEW · SELECT EPISODE</div><h1>${esc(reviewTitle())}</h1><p>S${String(state.review.season.season_number).padStart(2,"0")} · ${esc(state.review.season.name)} · Choose one episode.</p><div class="watch-header-actions"><button class="btn" data-action="review-back-seasons">Back</button><button class="btn" data-action="review-start-over">New Review</button></div></div>
            <div class="panel review-selection-panel"><div class="watch-episode-grid review-episode-grid">${eps.length ? eps.map(ep => `
                <button class="watch-episode" data-action="review-select-episode" data-episode-number="${ep.episode_number}"><strong>E${String(ep.episode_number).padStart(2,"0")}</strong><span>${esc(ep.title)}</span><span>→</span></button>
            `).join("") : `<div class="empty-state compact">No numbered episodes were found.</div>`}</div></div>
        </div>
    `;
}

function reviewTargetLabel() {
    if (state.review.target === "series") return "Series";
    if (state.review.target === "season") return `S${String(state.review.season?.season_number || "").padStart(2,"0")} · ${state.review.season?.name || "Season"}`;
    return `S${String(state.review.season?.season_number || "").padStart(2,"0")}E${String(state.review.episode?.episode_number || "").padStart(2,"0")} · ${state.review.episode?.title || "Episode"}`;
}

function reviewStarsOptions() {
    const min = state.review.target === "season" ? 1 : 0.5;
    let out = `<option value="">No rating</option>`;
    for (let n = min; n <= 5; n += 0.5) out += `<option value="${n}" ${String(state.review.stars) === String(n) ? "selected" : ""}>${n.toFixed(1)} / 5</option>`;
    return out;
}

function renderReviewEditor() {
    const r = state.review;
    view.innerHTML = `
        <div class="view-inner review-view">
            <div class="screen-header"><div class="eyebrow">REVIEW · ${r.editing ? "EDIT" : "WRITE"}</div><h1>${esc(reviewTitle())}</h1><p>${esc(reviewTargetLabel())}</p><div class="watch-header-actions"><button class="btn" data-action="review-back-editor-target">Back</button><button class="btn" data-action="review-start-over">New Review</button></div></div>
            <div class="panel review-editor-panel">
                <div class="review-editor-target"><span>Reviewing</span><strong>${esc(reviewTargetLabel())}</strong></div>
                <div class="review-field"><label for="review-stars">Rating</label><select id="review-stars">${reviewStarsOptions()}</select><small>${r.target === "season" ? "Season ratings currently support 1.0–5.0 in 0.5 increments." : "Ratings support half-star increments."}</small></div>
                <div class="review-field"><label for="review-text">Review</label><textarea id="review-text" rows="8" maxlength="5000" placeholder="Write your review...">${esc(r.text)}</textarea><small><span id="review-count">${r.text.length}</span> / 5000</small></div>
                <div class="review-options">
                    <label><input id="review-rewatch" type="checkbox" ${r.isRewatch ? "checked" : ""}> Rewatch</label>
                    <label><input id="review-spoiler" type="checkbox" ${r.containsSpoiler ? "checked" : ""}> Contains spoilers</label>
                    <label><input id="review-like" type="checkbox" ${r.like ? "checked" : ""}> Like</label>
                </div>
                <div class="watch-actions">
                    <button class="btn" data-action="review-find-existing">${r.editing ? "Other existing reviews" : "Find existing review"}</button>
                    <button class="btn btn-primary" data-action="review-preview">${r.editing ? "Review changes" : (r.focus === "rating" ? "Review rating" : "Review changes")}</button>
                </div>
            </div>
        </div>
    `;
    const textarea = document.getElementById("review-text");
    textarea?.addEventListener("input", () => { const c = document.getElementById("review-count"); if (c) c.textContent = textarea.value.length; });
}

async function loadExistingReviews() {
    const payload = { target: state.review.target, show_id: state.review.serializd?.id, season_id: state.review.season?.season_id || null, episode_number: state.review.episode?.episode_number || null };
    view.innerHTML = `<div class="view-inner"><div class="empty-state loading-state"><div class="loading-dot"></div><strong>Finding existing reviews…</strong><span>Reading your Serializd diary.</span></div></div>`;
    try {
        const data = await call("review_existing", payload);
        state.review.existing = data?.matches || [];
        renderExistingReviews();
    } catch (error) { msg(`Could not load existing reviews: ${error.message}`); renderReviewEditor(); }
}

function renderExistingReviews() {
    const items = state.review.existing || [];
    view.innerHTML = `
        <div class="view-inner review-view">
            <div class="screen-header"><div class="eyebrow">REVIEW · EXISTING</div><h1>${esc(reviewTitle())}</h1><p>${esc(reviewTargetLabel())}</p><div class="watch-header-actions"><button class="btn" data-action="review-back-existing">Back</button></div></div>
            <div class="panel review-existing-panel">
                <div class="result-heading"><div><div class="eyebrow">SERIALIZD DIARY</div><h2>${items.length} ${items.length === 1 ? "entry" : "entries"}</h2></div><span class="service-pill">Live</span></div>
                ${items.length ? `<div class="review-existing-list">${items.map((item, i) => `
                    <div class="review-existing-row"><div><strong>${item.stars != null ? `${Number(item.stars).toFixed(1)} / 5` : "No rating"}</strong><small>${esc(item.backdate || item.dateAdded || "Date unavailable")}</small>${item.review_text ? `<p>${esc(item.review_text)}</p>` : `<p class="review-muted">No review text.</p>`}</div><div class="watch-actions"><button class="btn" data-action="review-edit-existing" data-existing-index="${i}">Edit</button>${item.review_id ? `<button class="btn" data-action="review-delete-existing" data-existing-index="${i}">Delete</button>` : ""}</div></div>
                `).join("")}</div>` : `<div class="empty-state compact">No existing diary entry was found for this target.</div>`}
                <div class="watch-actions"><button class="btn btn-primary" data-action="review-back-existing">Back to editor</button></div>
            </div>
        </div>
    `;
}

function captureReviewFields() {
    state.review.stars = document.getElementById("review-stars")?.value || "";
    state.review.text = document.getElementById("review-text")?.value || "";
    state.review.isRewatch = !!document.getElementById("review-rewatch")?.checked;
    state.review.containsSpoiler = !!document.getElementById("review-spoiler")?.checked;
    state.review.like = !!document.getElementById("review-like")?.checked;
}

function renderReviewConfirmation() {
    captureReviewFields();
    const r = state.review;
    view.innerHTML = `
        <div class="view-inner review-view"><div class="screen-header"><div class="eyebrow">REVIEW · CONFIRM</div><h1>${r.editing ? "Ready to update?" : "Ready to save?"}</h1><p>Nothing has been written yet. Review the exact changes below.</p></div>
        <div class="panel review-confirm-panel"><div class="watch-summary">
            <div><span>Show</span><strong>${esc(reviewTitle())}</strong></div><div><span>Target</span><strong>${esc(reviewTargetLabel())}</strong></div><div><span>Rating</span><strong>${r.stars ? `${esc(r.stars)} / 5` : "No rating"}</strong></div><div><span>Rewatch</span><strong>${r.isRewatch ? "Yes" : "No"}</strong></div><div><span>Review</span><strong class="review-confirm-text">${r.text ? esc(r.text) : "No review text"}</strong></div>
        </div><div class="watch-warning">This will perform a real ${r.editing ? "update" : "write"} to Serializd. Because you are reviewing this ${r.target === "episode" ? "episode" : r.target === "season" ? "season" : "series"}, WAYMARK will also mark it as watched.</div><div class="watch-actions"><button class="btn" data-action="review-back-confirm">Back</button><button class="btn btn-primary" data-action="review-confirm">${r.editing ? "YES — Update review" : "YES — Save review"}</button></div></div></div>
    `;
}

async function executeReview() {
    // The confirmation screen has no review form fields. The values were
    // captured when the user clicked Review changes / Review rating.
    // Do not call captureReviewFields() here or it would overwrite the
    // saved values with empty values from the confirmation DOM.
    const r = state.review;
    if (!r.stars && !r.text.trim()) { msg("Add a rating or review text first."); renderReviewEditor(); return; }
    view.innerHTML = `<div class="view-inner"><div class="empty-state loading-state"><div class="loading-dot"></div><strong>${r.editing ? "Updating your review…" : "Saving your review…"}</strong><span>Writing through Serializd.</span></div></div>`;
    try {
        let result;
        if (r.editing) {
            result = await call("review_update", { review_id: r.reviewId, target: r.target, show_id: r.serializd?.id || null, season_id: r.season?.season_id || null, stars: r.stars || null, review_text: r.text, is_rewatch: r.isRewatch, contains_spoiler: r.containsSpoiler, like: r.like, allows_comments: r.allowsComments, episode_number: r.episode?.episode_number || null, backdate: r.backdate || null });
        } else {
            result = await call("review_execute", { target: r.target, show_id: r.serializd?.id, season_id: r.season?.season_id || null, episode_number: r.episode?.episode_number || null, stars: r.stars || null, review_text: r.text, is_rewatch: r.isRewatch, contains_spoiler: r.containsSpoiler, like: r.like, allows_comments: r.allowsComments });
        }
        renderReviewResult(result);
    } catch (error) { reviewError(`Review save failed: ${error.message}`); }
}

function renderReviewResult(result) {
    const ok = !!result?.ok;
    const watched = ok && result?.watched === true;
    const partial = !ok && result?.review_saved === true;
    const targetWord = state.review.target === "episode" ? "episode" : state.review.target === "season" ? "season" : "series";
    const headline = ok
        ? (state.review.editing ? "Review updated" : "Review saved")
        : (partial ? "Review saved, watch state failed" : "Review not saved");
    const message = ok
        ? `Serializd accepted the review and WAYMARK marked the ${result?.watched_operation || targetWord} as watched.`
        : (partial
            ? `The review was saved, but WAYMARK could not mark the ${targetWord} as watched: ${result?.error || "unknown error"}`
            : (result?.error || "Review write failed."));
    view.innerHTML = `<div class="view-inner review-view"><div class="screen-header"><div class="eyebrow">REVIEW · RESULT</div><h1>${esc(headline)}</h1><p>${esc(message)}</p></div><div class="panel"><div class="watch-result-list"><div class="watch-result ${ok ? "ok" : "failed"}">${ok ? "✓" : "✕"} ${esc(reviewTargetLabel())}</div>${watched ? `<div class="watch-result ok">✓ Marked as watched</div>` : ""}</div><div class="watch-actions"><button class="btn" data-action="review-find-existing">View existing reviews</button><button class="btn btn-primary" data-action="review-start-over">Review another</button></div></div></div>`;
}

function reviewRenderCurrent() {
    const r = state.review;
    if (!r.query) return reviewEntry();
    if (!r.catalog) return finishReviewSearch();
    if (!r.serializd) return renderReviewResults();
    if (!r.target) return renderReviewTargetChoice();
    if (r.target === "season" && !r.season) return loadReviewSeasons();
    if (r.target === "episode" && !r.season) return loadReviewSeasons();
    if (r.target === "episode" && !r.episode) return loadReviewEpisodes();
    if (!r.confirmation) return renderReviewEditor();
    return renderReviewConfirmation();
}

function generic(route) {
    if (route === "settings") {
        renderProfileSettings();
        return;
    }
    const titles = {
        watch: "What did you watch?",
        review: "What do you want to review?",
        history: "Your history"
    };

    view.innerHTML = `
        <div class="view-inner">
            <div class="screen-header">
                <div class="eyebrow">${label.textContent}</div>
                <h1>${titles[route]}</h1>
                <p>This screen is connected to the WAYMARK application shell. Its live operation will be connected in its dedicated step.</p>
            </div>
            <div class="panel">
                <div class="empty-state">Live ${esc(route)} integration is next.</div>
            </div>
        </div>
    `;
}

function render() {
    if (state.route === "home") home();
    else if (state.route === "search") {
        if (!state.search.catalog && state.search.isAnime === null) searchEntry();
        else if (!state.search.catalog && state.search.mediaType === null) guidedTypeQuestion();
        else if (!state.search.catalog) guidedAnimeQuestion();
        else results();
    } else if (state.route === "library") {
        library();
    } else if (state.route === "history") {
        history();
    } else if (state.route === "review") {
        reviewRenderCurrent();
    } else if (state.route === "rate") {
        const r = state.rate;
        if (!r.query) rateEntry();
        else if (r.isAnime === null) rateAnimeQuestion();
        else if (r.isAnime === true && r.mediaType === null) rateTypeQuestion();
        else if (!r.catalog) finishRateSearch();
        else if (!r.service) renderRateResults();
        else if (r.service === "mal" && r.confirmation) renderRateConfirmation();
        else if (r.service === "mal") renderMalUpdate();
        else if (r.service === "serializd" && r.confirmation) renderRateConfirmation();
        else if (r.service === "serializd" && r.serializdTarget === "progress" && r.episodes) renderSerializdProgressEditor();
        else if (r.service === "serializd" && r.serializdTarget === "rating_choice") renderSerializdRatingTargetChoice();
        else if (r.service === "serializd" && r.serializdTarget) renderSerializdRatingEditor();
        else renderSerializdUpdateChoice();
    } else if (state.route === "watch") {
        if (!state.watch.query) watchEntry();
        else if (state.watch.isAnime === null) watchAnimeQuestion();
        else if (state.watch.isAnime === true && state.watch.mediaType === null) watchMediaTypeQuestion();
        else if (!state.watch.catalog) finishWatchSearch();
        else if (!state.watch.serviceMode) renderWatchResults();
        else if (state.watch.serviceMode === "mal" && !state.watch.malEpisodes.length) renderMalPicker();
        else if (state.watch.serviceMode === "both" && !state.watch.malEpisodes.length) renderMalPicker();
        else if ((state.watch.serviceMode === "serializd" || state.watch.serviceMode === "both") && !state.watch.seasons) loadWatchSeasons();
        else if ((state.watch.serviceMode === "serializd" || state.watch.serviceMode === "both") && !state.watch.season) renderWatchSeasons();
        else if ((state.watch.serviceMode === "serializd" || state.watch.serviceMode === "both") && !state.watch.episodes) loadWatchEpisodes();
        else if ((state.watch.serviceMode === "serializd" || state.watch.serviceMode === "both") && !state.watch.selectedEpisodes.length) renderWatchEpisodes();
        else renderWatchConfirmation();
    } else {
        generic(state.route);
    }
}

document.addEventListener("click", async event => {
    const profileButton = event.target.closest(".profile");
    if (profileButton && !state.setup.active) {
        openProfileEditor();
        return;
    }

    const routeButton = event.target.closest("[data-route]");
    if (routeButton) {
        setRoute(routeButton.dataset.route);
        return;
    }

    const button = event.target.closest("[data-action]");
    if (!button) return;

    const action = button.dataset.action;

    if (action === "setup-connect-mal") {
        await handleSetupMal();
        return;
    }
    if (action === "setup-connect-serializd") {
        await handleSetupSerializd();
        return;
    }
    if (action === "setup-finish") {
        await handleSetupFinish();
        return;
    }
    if (action === "profile-save") {
        await saveProfile();
        return;
    }
    if (action === "profile-pick-avatar") {
        document.getElementById("profile-avatar-input")?.click();
        return;
    }
    if (action === "profile-remove-avatar" || action === "profile-skip-avatar") {
        state.profile.personalization.avatar = null;
        applyPersonalization();
        const saved = await savePersonalization();
        if (state.profile.firstRun) renderProfileSetup();
        else renderProfileSettings();
        if (!saved) msg("Profile picture removed for this session, but could not be saved.");
        return;
    }
    if (action === "profile-pick-background") {
        document.getElementById("profile-background-input")?.click();
        return;
    }
    if (action === "profile-remove-background" || action === "profile-skip-background") {
        state.profile.personalization.background = null;
        applyPersonalization();
        const saved = await savePersonalization();
        if (state.profile.firstRun) renderProfileSetup();
        else renderProfileSettings();
        if (!saved) msg("Background removed for this session, but could not be saved.");
        return;
    }
    if (action === "profile-accent") {
        const accent = button.dataset.accent;
        if (PERSONALIZATION_ACCENTS[accent]) {
            state.profile.personalization.accent = accent;
            applyPersonalization();
            const saved = await savePersonalization();
            if (state.profile.firstRun) renderProfileSetup();
            else renderProfileSettings();
            if (!saved) msg("Accent changed for this session, but could not be saved.");
        }
        return;
    }

    // Serializd is remote and can take a few seconds. Once a Rating/Progress
    // navigation request starts, ignore additional remote navigation clicks
    // until that request finishes. Local episode selection remains unrestricted.
    const rateRemoteActions = new Set([
        "rate-select-season", "rate-select-episode", "rate-sz-series",
        "rate-sz-season", "rate-sz-episode", "rate-sz-progress",
        "rate-confirm"
    ]);
    if (state.rate.loading && rateRemoteActions.has(action)) return;

    if (action === "home-featured-prev" || action === "home-featured-next" || action === "home-featured-go") {
        const rows = homeContinueRows(state.home.library);
        if (rows.length <= 1) return;
        if (action === "home-featured-go") {
            state.home.featuredIndex = Math.max(0, Math.min(Number(button.dataset.index || 0), rows.length - 1));
        } else {
            const delta = action === "home-featured-next" ? 1 : -1;
            state.home.featuredIndex = (Number(state.home.featuredIndex || 0) + delta + rows.length) % rows.length;
        }
        view.innerHTML = homeDashboardShell();
        return;
    }

    if (action === "home-watch") {
        resetWatch();
        setRoute("watch");
        return;
    }

    if (action === "home-continue") {
        const title = event.currentTarget?.dataset?.title || "";
        resetWatch();
        state.watch.query = title;
        setRoute("watch");
        return;
    }

    if (action === "home-search") {
        setRoute("search");
        return;
    }

    if (action === "home-review") {
        resetReview();
        state.review.focus = "review";
        setRoute("review");
        return;
    }

    if (action === "home-rate") {
        resetRate();
        setRoute("rate");
        return;
    }

    if (action === "home-library") {
        setRoute("library");
        return;
    }

    if (action === "home-history") {
        setRoute("history");
        return;
    }

    if (action === "home-refresh") {
        state.home.history = null;
        state.home.library = null;
        state.home.featuredIndex = 0;
        state.home.loading = false;
        if (state.route !== "home") {
            setRoute("home");
        } else {
            await loadHomeDashboard();
        }
        return;
    }

    if (["watch", "library", "history", "settings", "search"].includes(action)) {
        setRoute(action);
        return;
    }

    if (action === "review") {
        resetReview();
        state.review.focus = "review";
        setRoute("review");
        return;
    }

    if (action === "rate") {
        resetRate();
        setRoute("rate");
        return;
    }

    if (action === "library-retry") {
        state.home.library = null;
        await library(true);
        return;
    }

    if (action === "history-retry") {
        await history();
        return;
    }


    if (action === "rate-search") {
        const input=document.getElementById("rate-q"); const q=input?.value.trim();
        if(!q){msg("Enter a title first.");input?.focus();return;}
        resetRate(); state.rate.query=q; rateAnimeQuestion(); return;
    }
    if (action === "rate-start-over") { resetRate(); setRoute("rate"); return; }
    if (action === "rate-back-entry") { resetRate(); setRoute("rate"); return; }
    if (action === "rate-anime-yes") { state.rate.isAnime=true; rateTypeQuestion(); return; }
    if (action === "rate-anime-no") { state.rate.isAnime=false; state.rate.mediaType="tv"; await finishRateSearch(); return; }
    if (action === "rate-back-anime") { state.rate.mediaType=null; rateAnimeQuestion(); return; }
    if (action === "rate-type-tv") { state.rate.mediaType="tv"; await finishRateSearch(); return; }
    if (action === "rate-type-movie") { state.rate.mediaType="movie"; await finishRateSearch(); return; }
    if (action === "rate-back-results") { state.rate.service=null; state.rate.mal=null; state.rate.serializd=null; renderRateResults(); return; }
    if (action === "rate-select-title") { await selectRateTitle(button.dataset.service,Number(button.dataset.index)); return; }
    if (action === "rate-preview-mal") { captureMalRate(); state.rate.pending={service:"mal"}; state.rate.confirmation=true; renderRateConfirmation(); return; }
    if (action === "rate-back-confirm") { state.rate.confirmation=false; if(state.rate.service==="mal") renderMalUpdate(); else if(state.rate.serializdTarget==="progress") renderSerializdProgressEditor(); else renderSerializdRatingEditor(); return; }
    if (action === "rate-confirm") { await executeRate(); return; }
    if (action === "rate-continue-serializd") { state.rate.service=null; state.rate.confirmation=false; state.rate.pending=null; state.rate.serializd=null; renderSerializdCatalogOnly(); return; }
    if (action === "rate-sz-rating") { state.rate.serializdTarget="rating_choice"; renderSerializdRatingTargetChoice(); return; }
    if (action === "rate-sz-series") { state.rate.serializdTarget="series"; state.rate.season=null; state.rate.episode=null; state.rate.episodes=null; state.rate.serializdRating=""; state.rate.serializdExisting=null; state.rate.serializdRatingTouched=false; renderSerializdRatingEditor(); loadRateExisting(); return; }
    if (action === "rate-sz-season" || action === "rate-sz-episode") { state.rate.serializdTarget=action === "rate-sz-season" ? "season" : "episode"; state.rate.seasons=null; state.rate.season=null; state.rate.episode=null; state.rate.episodes=null; await loadRateSeasons(); return; }
    if (action === "rate-sz-progress") { state.rate.serializdTarget="progress"; state.rate.seasons=null; state.rate.season=null; state.rate.episodes=null; await loadRateSeasons(); return; }
    if (action === "rate-select-season") { state.rate.season={season_id:Number(button.dataset.seasonId),season_number:Number(button.dataset.seasonNumber),name:button.querySelector(".watch-choice-copy strong")?.textContent||`Season ${button.dataset.seasonNumber}`}; if(state.rate.serializdTarget==="progress" || state.rate.serializdTarget==="episode") { if(state.rate.serializdTarget==="progress") { state.rate.serializdProgressSelected=[]; state.rate.serializdProgressRewatch=false; } await loadRateEpisodes(); } else { state.rate.serializdRating=""; state.rate.serializdExisting=null; state.rate.serializdRatingTouched=false; renderSerializdRatingEditor(); loadRateExisting(); } return; }
    if (action === "rate-select-episode") { const n=Number(button.dataset.episodeNumber); state.rate.episode=(state.rate.episodes?.episodes||[]).find(e=>Number(e.episode_number)===n)||null;
        if (!state.rate.episode) { msg("That Serializd episode could not be resolved."); return; } state.rate.serializdTarget="episode"; state.rate.serializdRating=""; state.rate.serializdExisting=null; state.rate.serializdRatingTouched=false; renderSerializdRatingEditor(); loadRateExisting(); return; }
    if (action === "rate-progress-toggle-episode") {
        event.preventDefault();
        event.stopPropagation();
        if (event.detail > 1) return;
        const n=Number(button.dataset.episodeNumber);
        if(!Number.isInteger(n)||n<=0)return;
        const selected=new Set(state.rate.serializdProgressSelected||[]);
        if(selected.has(n))selected.delete(n);else selected.add(n);
        state.rate.serializdProgressSelected=Array.from(selected).sort((a,b)=>a-b);
        renderSerializdProgressEditor();
        return;
    }
    if (action === "rate-progress-select-all") { state.rate.serializdProgressSelected=(state.rate.episodes?.episodes||[]).map(e=>Number(e.episode_number)).filter(n=>n>0); renderSerializdProgressEditor(); return; }
    if (action === "rate-progress-clear-all") { state.rate.serializdProgressSelected=[]; renderSerializdProgressEditor(); return; }
    if (action === "rate-sz-back") { state.rate.requestSeq++; if(state.rate.serializdTarget==="progress" && state.rate.episodes) { state.rate.serializdProgressSelected=[]; state.rate.serializdProgressRewatch=false; state.rate.episodes=null; state.rate.season=null; state.rate.seasons=null; loadRateSeasons(); } else if((state.rate.serializdTarget==="season"||state.rate.serializdTarget==="episode") && !state.rate.season) { state.rate.serializdTarget="rating_choice"; renderSerializdRatingTargetChoice(); } else if(state.rate.serializdTarget==="season"||state.rate.serializdTarget==="episode"){state.rate.season=null;state.rate.episode=null;state.rate.episodes=null;loadRateSeasons();} else if(state.rate.serializdTarget==="series"){state.rate.serializdTarget="rating_choice";renderSerializdRatingTargetChoice();} else if(state.rate.serializdTarget==="rating_choice"){state.rate.serializdTarget=null;renderSerializdUpdateChoice();} else {state.rate.serializdTarget=null;renderSerializdUpdateChoice();} return; }
    if (action === "rate-preview-sz") { state.rate.serializdRating=document.getElementById("sz-rating")?.value||""; if(!state.rate.serializdRating){msg("Choose a Serializd rating first.");return;} state.rate.pending={service:"serializd",kind:"rating"}; state.rate.confirmation=true; renderRateConfirmation(); return; }
    if (action === "rate-preview-sz-progress") { state.rate.serializdProgressSelected=(state.rate.serializdProgressSelected||[]).map(Number).filter(n=>Number.isInteger(n)&&n>0).sort((a,b)=>a-b); if(!state.rate.serializdProgressSelected.length){msg("Select at least one episode first.");return;} renderSerializdProgressRewatchQuestion(); return; }
    if (action === "rate-progress-rewatch-back") { renderSerializdProgressEditor(); return; }
    if (action === "rate-progress-rewatch-no" || action === "rate-progress-rewatch-yes") { state.rate.serializdProgressRewatch=action==="rate-progress-rewatch-yes"; state.rate.pending={service:"serializd",kind:"progress"}; state.rate.confirmation=true; renderRateConfirmation(); return; }

    if (action === "review-search") {
        const input = document.getElementById("review-q");
        const query = input?.value.trim();
        if (!query) { msg("Enter a title first."); input?.focus(); return; }
        resetReview();
        state.review.query = query;
        state.review.focus = "review";
        await finishReviewSearch();
        return;
    }

    if (action === "review-start-over") { resetReview(); setRoute("review"); return; }
    if (action === "review-back-entry") { resetReview(); setRoute("review"); return; }
    if (action === "review-back-results") { state.review.serializd = null; state.review.target = null; renderReviewResults(); return; }
    if (action === "review-back-target") { state.review.target = null; state.review.seasons = null; state.review.season = null; state.review.episodes = null; state.review.episode = null; renderReviewTargetChoice(); return; }
    if (action === "review-back-seasons") { state.review.episode = null; state.review.episodes = null; renderReviewSeasons(); return; }
    if (action === "review-back-editor-target") { state.review.target = null; state.review.season = null; state.review.episode = null; state.review.seasons = null; state.review.episodes = null; state.review.editing = false; state.review.reviewId = null; renderReviewTargetChoice(); return; }
    if (action === "review-back-confirm") { state.review.confirmation = false; renderReviewEditor(); return; }

    if (action === "review-select-title") {
        const item = state.review.catalog?.serializd?.results?.[Number(button.dataset.index) - 1];
        if (!item) return;
        try {
            const picked = await call("select_search_result", { service: "serializd", results: state.review.catalog.serializd.results, index: Number(button.dataset.index) });
            state.review.serializd = { ...item, ...picked?.selected, details: picked?.details };
            state.review.target = null;
            renderReviewTargetChoice();
        } catch (error) { msg(`Could not load Serializd details: ${error.message}`); }
        return;
    }

    if (action === "review-target-series") { state.review.target = "series"; state.review.season = null; state.review.episode = null; renderReviewEditor(); return; }
    if (action === "review-target-season" || action === "review-target-episode") {
        state.review.target = action === "review-target-season" ? "season" : "episode";
        state.review.seasons = null; state.review.season = null; state.review.episode = null;
        await loadReviewSeasons(); return;
    }
    if (action === "review-select-season") {
        state.review.season = { season_id: Number(button.dataset.seasonId), season_number: Number(button.dataset.seasonNumber), name: button.querySelector(".watch-choice-copy strong")?.textContent?.replace(/^S\d+ · /, "") || `Season ${button.dataset.seasonNumber}` };
        state.review.episode = null;
        if (state.review.target === "season") renderReviewEditor(); else await loadReviewEpisodes();
        return;
    }
    if (action === "review-select-episode") {
        const number = Number(button.dataset.episodeNumber);
        const ep = (state.review.episodes?.episodes || []).find(x => Number(x.episode_number) === number);
        if (!ep) return;
        state.review.episode = ep;
        renderReviewEditor();
        return;
    }
    if (action === "review-preview") {
        captureReviewFields();
        if (!state.review.stars && !state.review.text.trim()) {
            msg("Add a rating or review text first.");
            return;
        }
        state.review.confirmation = true;
        renderReviewConfirmation();
        return;
    }
    if (action === "review-confirm") { state.review.confirmation = true; await executeReview(); return; }
    if (action === "review-find-existing") { captureReviewFields(); await loadExistingReviews(); return; }
    if (action === "review-back-existing") { renderReviewEditor(); return; }
    if (action === "review-edit-existing") {
        const item = state.review.existing?.[Number(button.dataset.existingIndex)];
        if (!item?.review_id) { msg("This diary entry has no editable review ID."); return; }
        state.review.editing = true; state.review.reviewId = Number(item.review_id); state.review.stars = item.stars != null ? String(item.stars) : ""; state.review.text = item.review_text || ""; state.review.isRewatch = !!item.is_rewatch; state.review.containsSpoiler = !!item.contains_spoiler; state.review.like = !!item.like; state.review.allowsComments = item.allows_comments !== false; state.review.backdate = item.backdate || null; state.review.confirmation = false; renderReviewEditor(); return;
    }
    if (action === "review-delete-existing") {
        const item = state.review.existing?.[Number(button.dataset.existingIndex)];
        if (!item?.review_id) { msg("This diary entry has no deletable review ID."); return; }
        if (!window.confirm("Delete this Serializd review/log? This cannot be undone.")) return;
        try {
            const result = await call("review_delete", { review_id: Number(item.review_id) });
            if (result?.ok) { msg("Review deleted."); await loadExistingReviews(); } else msg(result?.error || "Review deletion failed.");
        } catch (error) { msg(`Review deletion failed: ${error.message}`); }
        return;
    }

    if (action === "watch-from-details") {
        const title = button.dataset.title?.trim();
        if (!title) {
            msg("Could not start Watch: title is missing.");
            return;
        }
        resetWatch();
        state.watch.query = title;
        state.watch.isAnime = button.dataset.anime === "true";
        state.watch.mediaType = state.watch.isAnime ? null : "tv";
        setRoute("watch");
        if (state.watch.isAnime) {
            watchMediaTypeQuestion();
        } else {
            await finishWatchSearch();
        }
        return;
    }

    if (action === "watch-back-entry") {
        resetWatch();
        watchEntry();
        return;
    }

    if (action === "watch-back-anime") {
        state.watch.mediaType = null;
        state.watch.catalog = null;
        state.watch.mal = null;
        state.watch.serializd = null;
        watchAnimeQuestion();
        return;
    }

    if (action === "watch-back-type") {
        state.watch.catalog = null;
        state.watch.mal = null;
        state.watch.serializd = null;
        watchMediaTypeQuestion();
        return;
    }

    if (action === "watch-back-results") {
        ++watchSerializdSelectionGeneration;
        state.watch.serviceMode = null;
        state.watch.seasons = null;
        state.watch.season = null;
        state.watch.episodes = null;
        state.watch.selectedEpisodes = [];
        renderWatchResults();
        return;
    }

    if (action === "watch-back-seasons") {
        state.watch.season = null;
        state.watch.episodes = null;
        state.watch.selectedEpisodes = [];
        renderWatchSeasons();
        return;
    }

    if (action === "watch-continue-saved") {
        const saved = getSavedWatches().find(item => item.id === button.dataset.savedId);
        if (!saved) return;
        resetWatch();
        state.watch.query = saved.query || saved.title || "";
        state.watch.isAnime = saved.isAnime ?? false;
        state.watch.mediaType = saved.mediaType || "tv";
        state.watch.serviceMode = saved.serviceMode || "serializd";
        state.watch.serializd = saved.serializd || null;
        state.watch.mal = saved.mal || null;
        state.watch.season = saved.season || null;
        state.watch.serializdCompleted = !!saved.serializdCompleted;
        state.watch.serializdRewatch = null;
        if (state.watch.serviceMode === "mal") {
            renderMalPicker();
        } else if (state.watch.serviceMode === "both") {
            renderMalPicker();
        } else if (state.watch.season) {
            await loadWatchEpisodes();
        } else {
            await loadWatchSeasons();
        }
        return;
    }

    if (action === "watch-remove-saved") {
        removeSavedWatch(button.dataset.savedId);
        return;
    }

    if (action === "watch-search") {
        const input = document.getElementById("watch-q");
        const query = input?.value.trim();
        if (!query) {
            msg("Enter a title first.");
            input?.focus();
            return;
        }
        resetWatch();
        state.watch.query = query;
        watchAnimeQuestion();
        return;
    }

    if (action === "watch-anime-yes") {
        state.watch.isAnime = true;
        state.watch.mediaType = null;
        watchMediaTypeQuestion();
        return;
    }

    if (action === "watch-anime-no") {
        state.watch.isAnime = false;
        state.watch.mediaType = "tv";
        await finishWatchSearch();
        return;
    }

    if (action === "watch-media-tv" || action === "watch-media-movie") {
        state.watch.mediaType = action === "watch-media-movie" ? "movie" : "tv";
        await finishWatchSearch();
        return;
    }

    if (action === "watch-select-mal") {
        const results = state.watch.catalog?.mal?.results || [];
        const index = Number(button.dataset.index);
        const item = results[index - 1];
        if (!item) return;

        try {
            const picked = await call("select_search_result", {
                service: "mal",
                results,
                index
            });
            const details = picked?.details || {};
            const selected = picked?.selected || {};
            state.watch.mal = {
                ...item,
                ...picked,
                details,
                node: {
                    ...(item.node || {}),
                    ...details
                },
                list_status: selected?.list_status || item?.list_status || null
            };

            // The selected-result detail request now includes MAL's
            // user-specific my_list_status field, so current progress is
            // available without a second network round-trip. If MAL has no
            // list entry for this anime, the missing status is treated as a
            // new entry with zero watched episodes.
            const listStatus = state.watch.mal.list_status;
            const current = Number(listStatus?.num_episodes_watched);
            state.watch.mal.currentProgress = Number.isFinite(current) && current >= 0 ? current : 0;
        } catch (error) {
            msg(`Could not load MAL details: ${error.message}`);
            return;
        }

        const current = Number(state.watch.mal.currentProgress || 0);
        const total = malTotalEpisodes();
        state.watch.malStartEpisode = total
            ? Math.min(Math.max(1, current + 1), total)
            : Math.max(1, current + 1);
        state.watch.malEpisodeCount = 1;
        state.watch.malEpisodes = [];
        renderWatchResults();
        return;
    }

    if (action === "watch-select-serializd") {
        const item = state.watch.catalog?.serializd?.results?.[Number(button.dataset.index) - 1];
        if (!item) return;

        // Selection itself is a local UI action and must not wait for the
        // remote Serializd show-state request. The old flow awaited
        // watch_seasons() here, so a 1–2 second Serializd response time was
        // directly visible as a delay before the checkmark appeared.
        // A monotonically increasing generation prevents a slower response
        // from an earlier title click from overwriting a newer selection.
        const selectionGeneration = ++watchSerializdSelectionGeneration;
        state.watch.serializd = item;
        state.watch.seasons = null;
        state.watch.serializdCompleted = false;
        state.watch.serializdCurrentlyWatching = null;
        state.watch.serializdWatchingChoice = null;
        state.watch.serializdRewatch = null;

        // Render immediately so the selected state/checkmark is synchronous
        // from the user's perspective. The authoritative account state is
        // loaded in the background and applied only if this is still the
        // active Serializd selection.
        renderWatchResults();

        try {
            const progress = await call("watch_seasons", { show_id: item.id });
            if (selectionGeneration !== watchSerializdSelectionGeneration) return;
            if (String(state.watch.serializd?.id) !== String(item.id)) return;
            state.watch.seasons = progress;
            state.watch.serializdCompleted = !!progress?.show_completed;
            state.watch.serializdCurrentlyWatching = progress?.currently_watching === true;
            // Do not re-render the results screen here. The selection was
            // already rendered synchronously above; re-rendering after the
            // background request completes causes the visible second flicker
            // reported in the Watch title picker. The fetched state is kept
            // in memory for Use Serializd / Use Both and later Watch steps.
        } catch (error) {
            if (selectionGeneration !== watchSerializdSelectionGeneration) return;
            if (String(state.watch.serializd?.id) !== String(item.id)) return;
            state.watch.seasons = null;
            msg(`Could not read Serializd watch status: ${error.message}`);
            // Keep the selected result on screen. The error message is enough
            // feedback; rebuilding the results view would create another
            // unnecessary visual transition.
        }
        return;
    }

    if (action === "watch-use-mal") {
        if (!state.watch.mal) return;
        state.watch.serviceMode = "mal";
        state.watch.malEpisodes = [];
        renderMalPicker();
        return;
    }

    if (action === "watch-use-serializd") {
        if (!state.watch.serializd) return;
        state.watch.serviceMode = "serializd";
        state.watch.season = null;
        state.watch.episodes = null;
        state.watch.selectedEpisodes = [];
        state.watch.serializdRewatch = null;
        state.watch.serializdWatchingChoice = null;
        if (!state.watch.seasons) await loadWatchSeasons();
        else {
            state.watch.serializdCurrentlyWatching = state.watch.seasons?.currently_watching === true;
            state.watch.serializdWatchingChoice = null;
            renderWatchSeasons();
        }
        return;
    }

    if (action === "watch-use-both") {
        if (!state.watch.mal || !state.watch.serializd) return;
        state.watch.serviceMode = "both";
        state.watch.malEpisodes = [];
        // Keep the Serializd season payload that was already loaded when the
        // user selected the Serializd title. Use Both is a local workflow
        // transition; throwing this data away forces the same show to be
        // fetched again after the MAL step.
        state.watch.confirmation = false;
        renderMalPicker();
        return;
    }

    if (action === "watch-mal-minus" || action === "watch-mal-plus") {
        const countInput = document.getElementById("mal-count");
        const startInput = document.getElementById("mal-start");
        const total = malTotalEpisodes();
        const start = Math.max(1, Number(startInput?.value || state.watch.malStartEpisode || 1));
        let count = Math.max(1, Number(countInput?.value || state.watch.malEpisodeCount || 1));
        count += action === "watch-mal-plus" ? 1 : -1;
        count = Math.max(1, count);
        if (total) count = Math.min(count, Math.max(1, total - start + 1));
        state.watch.malStartEpisode = total ? Math.min(start, total) : start;
        state.watch.malEpisodeCount = count;
        state.watch.malEpisodes = Array.from({length: count}, (_, i) => state.watch.malStartEpisode + i);
        renderMalPicker();
        return;
    }

    if (action === "watch-review-mal") {
        const start = Math.max(1, Number(document.getElementById("mal-start")?.value || 1));
        const count = Math.max(1, Number(document.getElementById("mal-count")?.value || 1));
        const total = malTotalEpisodes();
        if (total && start > total) {
            msg(`MAL has ${total} episodes.`);
            return;
        }
        const safeCount = total ? Math.min(count, total - start + 1) : count;
        state.watch.malStartEpisode = start;
        state.watch.malEpisodeCount = safeCount;
        state.watch.malEpisodes = Array.from({length: safeCount}, (_, i) => start + i);
        state.watch.status = document.getElementById("watch-status")?.value || "watching";
        state.watch.confirmation = false;

        if (state.watch.serviceMode === "both") {
            // The Serializd show/seasons were already loaded while selecting
            // the title. Reuse that payload instead of issuing another
            // watch_seasons request just because the MAL step completed.
            state.watch.season = null;
            state.watch.episodes = null;
            state.watch.selectedEpisodes = [];
            if (state.watch.seasons) {
                state.watch.serializdCurrentlyWatching = state.watch.seasons?.currently_watching === true;
                state.watch.serializdWatchingChoice = null;
                renderWatchSeasons();
            } else {
                await loadWatchSeasons();
            }
        } else {
            renderWatchConfirmation();
        }
        return;
    }

    if (action === "watch-back-title") {
        state.watch.serviceMode = null;
        state.watch.malEpisodes = [];
        state.watch.seasons = null;
        state.watch.season = null;
        state.watch.episodes = null;
        state.watch.selectedEpisodes = [];
        renderWatchResults();
        return;
    }

    if (action === "watch-select-season") {
        const seasonNumber = Number(button.dataset.seasonNumber);
        const seasons = state.watch.seasons?.seasons || [];
        const selected = seasons.find(item => Number(item.season_number) === seasonNumber);
        if (!selected) return;
        state.watch.season = { ...selected };
        state.watch.selectedEpisodes = [];
        state.watch.serializdRewatch = null;
        await loadWatchEpisodes();
        return;
    }

    if (action === "watch-toggle-episode") {
        toggleWatchEpisode(Number(button.dataset.episodeNumber));
        return;
    }

    if (action === "watch-select-all") {
        const eps = state.watch.episodes?.episodes || [];
        state.watch.selectedEpisodes = eps.map(ep => ep.episode_number);
        updateWatchEpisodeSelectionUI();
        return;
    }

    if (action === "watch-clear-all") {
        state.watch.selectedEpisodes = [];
        updateWatchEpisodeSelectionUI();
        return;
    }

    if (action === "watch-review-serializd") {
        if (!state.watch.selectedEpisodes.length) {
            msg("Select at least one episode.");
            return;
        }

        state.watch.confirmation = false;

        // Trigger rewatch when every selected episode is already watched.
        // Whole-show completion is not required for this decision.
        const watchedNumbers = new Set(
            (state.watch.episodes?.watched_episode_numbers || [])
                .map(Number)
                .filter(Number.isFinite)
        );
        const selectedNumbers = state.watch.selectedEpisodes.map(Number);
        const allSelectedAlreadyWatched =
            selectedNumbers.length > 0 &&
            selectedNumbers.every(number => watchedNumbers.has(number));

        if (allSelectedAlreadyWatched && state.watch.serializdRewatch === null) {
            renderWatchRewatchQuestion();
        } else if (
            state.watch.serializdWatchingChoice === null
            && state.watch.serializdRewatch !== true
            && state.watch.serializdCurrentlyWatching !== true
        ) {
            // A normal watch must explicitly decide the show-level status.
            // This also matters after the user answers "No, new watch" on
            // the rewatch question: a completed show is now being started
            // again, so it still needs the Currently Watching decision.
            // The backend performs a fresh live-state check before writing.
            renderWatchCurrentlyWatchingQuestion();
        } else {
            renderWatchConfirmation();
        }
        return;
    }

    if (action === "watch-rewatch-yes" || action === "watch-rewatch-no") {
        state.watch.serializdRewatch = action === "watch-rewatch-yes";
        if (!state.watch.serializdRewatch) {
            if (state.watch.serializdCurrentlyWatching === true) {
                state.watch.serializdWatchingChoice = null;
                renderWatchConfirmation();
            } else {
                state.watch.serializdWatchingChoice = null;
                renderWatchCurrentlyWatchingQuestion();
            }
        } else {
            renderWatchConfirmation();
        }
        return;
    }

    if (action === "watch-currently-yes" || action === "watch-currently-no") {
        state.watch.serializdWatchingChoice = action === "watch-currently-yes";
        renderWatchConfirmation();
        return;
    }

    if (action === "watch-back-rewatch") {
        state.watch.serializdRewatch = null;
        state.watch.serializdWatchingChoice = null;
        renderWatchEpisodes();
        return;
    }

    if (action === "watch-back-confirm") {
        state.watch.confirmation = false;
        if (state.watch.serviceMode === "mal") renderMalPicker();
        else renderWatchEpisodes();
        return;
    }

    if (action === "watch-confirm") {
        state.watch.confirmation = true;
        await executeWatchBatch();
        return;
    }

    if (action === "watch-history") {
        setRoute("history");
        return;
    }

    if (action === "watch-start-over") {
        resetWatch();
        setRoute("watch");
        return;
    }

    if (action === "search-back-entry") {
        state.search.isAnime = null;
        state.search.mediaType = null;
        state.search.catalog = null;
        state.search.mal = null;
        state.search.serializd = null;
        searchEntry();
        return;
    }

    if (action === "search-back-anime") {
        state.search.mediaType = null;
        state.search.catalog = null;
        state.search.mal = null;
        state.search.serializd = null;
        guidedAnimeQuestion();
        return;
    }

    if (action === "search-back-type") {
        state.search.catalog = null;
        state.search.mal = null;
        state.search.serializd = null;
        guidedTypeQuestion();
        return;
    }

    if (action === "search-clear-selection") {
        state.search.mal = null;
        state.search.serializd = null;
        results();
        return;
    }

    if (action === "search-start") {
        startSearch();
        return;
    }

    if (action === "new-search") {
        state.search = {
            query: "",
            isAnime: null,
            mediaType: null,
            catalog: null,
            mal: null,
            serializd: null
        };
        setRoute("search");
        return;
    }

    if (action === "yes" || action === "no") {
        state.search.isAnime = action === "yes";
        guidedTypeQuestion();
        return;
    }

    if (action === "tv" || action === "movie") {
        state.search.mediaType = action;
        await finishSearch();
        return;
    }

    if (action === "mal" || action === "serializd") {
        await selectResult(action, Number(button.dataset.index));
    }
});

document.addEventListener("change", event => {
    if (event.target.id === "sz-rating") {
        state.rate.serializdRatingTouched = true;
        state.rate.serializdRating = event.target.value || "";
    } else if (event.target.id === "profile-avatar-input") {
        readProfileImage(event.target.files?.[0], 5 * 1024 * 1024, "profile picture");
    } else if (event.target.id === "profile-background-input") {
        readProfileImage(event.target.files?.[0], 10 * 1024 * 1024, "background image");
    }
});

let homeFeaturedTouchStartX = null;
document.addEventListener("touchstart", event => {
    if (!event.target.closest(".home-featured")) return;
    homeFeaturedTouchStartX = event.changedTouches?.[0]?.clientX ?? null;
}, { passive: true });

document.addEventListener("touchend", event => {
    if (homeFeaturedTouchStartX == null) return;
    const hero = event.target.closest(".home-featured");
    const endX = event.changedTouches?.[0]?.clientX ?? null;
    const rows = homeContinueRows(state.home.library);
    const delta = endX == null ? 0 : endX - homeFeaturedTouchStartX;
    homeFeaturedTouchStartX = null;
    if (!hero || rows.length <= 1 || Math.abs(delta) < 45) return;
    state.home.featuredIndex = (Number(state.home.featuredIndex || 0) + (delta < 0 ? 1 : -1) + rows.length) % rows.length;
    view.innerHTML = homeDashboardShell();
}, { passive: true });

document.addEventListener("keydown", event => {
    if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && document.querySelector(".home-featured")) {
        const rows = homeContinueRows(state.home.library);
        if (rows.length > 1 && !["INPUT", "TEXTAREA", "SELECT"].includes(event.target?.tagName)) {
            const delta = event.key === "ArrowRight" ? 1 : -1;
            state.home.featuredIndex = (Number(state.home.featuredIndex || 0) + delta + rows.length) % rows.length;
            view.innerHTML = homeDashboardShell();
            event.preventDefault();
            return;
        }
    }
    if (event.key !== "Enter") return;
    if (event.target.id === "q") {
        startSearch();
    } else if (event.target.id === "watch-q") {
        document.querySelector('[data-action="watch-search"]')?.click();
    } else if (event.target.id === "review-q") {
        document.querySelector('[data-action="review-search"]')?.click();
    } else if (event.target.id === "profile-name-input") {
        document.querySelector('[data-action="profile-save"]')?.click();
    }
});

bootstrap();
