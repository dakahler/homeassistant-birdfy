/**
 * Birdfy Moments Card (`custom:birdfy-moments-card`)
 * A Home Assistant Lovelace card with an expandable pop-out modal dialog
 * for viewing the Birdfy camera snapshot, species filter pills, and playable MP4 Moments feed.
 */

class BirdfyMomentsCard extends HTMLElement {
  #hass = null;
  #config = {};
  #selectedIndex = 0;
  #selectedSpecies = "all";
  #rendered = false;
  #lastFeedSignature = "";

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this.#config = config || {};
    this.#render();
  }

  set hass(hass) {
    this.#hass = hass;
    if (!this.#rendered) {
      this.#render();
      return;
    }
    this.#updateContent();
  }

  get hass() {
    return this.#hass;
  }

  connectedCallback() {
    if (!this.#rendered) {
      this.#render();
    }
  }

  disconnectedCallback() {
    const dialog = this.shadowRoot?.querySelector("dialog");
    if (dialog?.open) {
      dialog.close();
    }
  }

  getCardSize() {
    return 4;
  }

  getGridOptions() {
    return {
      columns: 12,
      rows: 5,
      min_columns: 6,
      min_rows: 3,
    };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        {
          name: "feed_entity",
          selector: { entity: { domain: "sensor" } },
        },
        {
          name: "image_entity",
          selector: { entity: { domain: "image" } },
        },
      ],
    };
  }

  static getStubConfig(hass) {
    const feedEntity = Object.keys(hass?.states || {}).find((id) =>
      id.endsWith("_moments_feed")
    );
    const imageEntity = Object.keys(hass?.states || {}).find(
      (id) => id.startsWith("image.") && id.endsWith("_last_moment")
    );
    return {
      title: "Birdfy Moments",
      feed_entity: feedEntity || "",
      image_entity: imageEntity || "",
    };
  }

  #resolveEntities() {
    const states = this.#hass?.states || {};
    let feedEntityId = this.#config.feed_entity || this.#config.entity;
    if (!feedEntityId || !states[feedEntityId]) {
      feedEntityId = Object.keys(states).find((id) =>
        id.endsWith("_moments_feed")
      );
    }

    let imageEntityId = this.#config.image_entity;
    if (!imageEntityId || !states[imageEntityId]) {
      if (feedEntityId) {
        const prefix = feedEntityId
          .replace(/^sensor\./, "image.")
          .replace(/_moments_feed$/, "_last_moment");
        if (states[prefix]) {
          imageEntityId = prefix;
        }
      }
      if (!imageEntityId) {
        imageEntityId = Object.keys(states).find(
          (id) => id.startsWith("image.") && id.endsWith("_last_moment")
        );
      }
    }

    return {
      feedState: feedEntityId ? states[feedEntityId] : null,
      imageState: imageEntityId ? states[imageEntityId] : null,
      feedEntityId,
      imageEntityId,
    };
  }

  #formatTime(epochMs) {
    if (!epochMs) return "";
    const dt = new Date(Number(epochMs));
    if (Number.isNaN(dt.getTime())) return "";
    const now = new Date();
    const isToday = dt.toDateString() === now.toDateString();
    const timeStr = dt.toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
    if (isToday) {
      return `Today, ${timeStr}`;
    }
    const dateStr = dt.toLocaleDateString([], {
      month: "short",
      day: "numeric",
    });
    return `${dateStr}, ${timeStr}`;
  }

  #getFilteredMoments(moments) {
    if (this.#selectedSpecies === "all") {
      return moments;
    }
    const target = this.#selectedSpecies.toLowerCase();
    return moments.filter((m) => {
      const primary = String(m.species || "").toLowerCase();
      const labels = Array.isArray(m.ai_labels)
        ? m.ai_labels.map((l) => String(l).toLowerCase())
        : [];
      return (
        primary.includes(target) || labels.some((l) => l.includes(target))
      );
    });
  }

  #openModal(initialIndex = 0) {
    this.#selectedIndex = initialIndex;
    const dialog = this.shadowRoot?.querySelector("#moments-dialog");
    if (!dialog) return;
    this.#renderModalBody();
    if (!dialog.open) {
      dialog.showModal();
    }
  }

  #stopVideoPlayback() {
    const video = this.shadowRoot?.querySelector("#modal-video-player");
    if (video) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    }
  }

  #render() {
    if (!this.shadowRoot) return;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          --birdfy-accent: var(--primary-color, #00b894);
          --birdfy-bg: var(--ha-card-background, var(--card-background-color, #1c1c1e));
          --birdfy-text: var(--primary-text-color, #f5f5f7);
          --birdfy-muted: var(--secondary-text-color, #9a9aa6);
          --birdfy-surface: rgba(255, 255, 255, 0.06);
          --birdfy-border: rgba(255, 255, 255, 0.12);
        }

        ha-card {
          overflow: hidden;
          position: relative;
          background: var(--birdfy-bg);
          color: var(--birdfy-text);
          border-radius: var(--ha-card-border-radius, 12px);
        }

        .hero-button {
          appearance: none;
          border: none;
          padding: 0;
          margin: 0;
          width: 100%;
          display: block;
          position: relative;
          background: #0d0d10;
          cursor: pointer;
          text-align: left;
          color: inherit;
          aspect-ratio: 16 / 9;
          overflow: hidden;
        }

        .hero-button:focus-visible {
          outline: 2px solid var(--birdfy-accent);
          outline-offset: -2px;
        }

        .hero-img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
          transition: transform 0.25s ease, opacity 0.2s ease;
        }

        .hero-img:not([src]),
        .hero-img[src=""] {
          opacity: 0;
        }

        .hero-button:hover .hero-img {
          transform: scale(1.02);
        }

        .hero-overlay {
          position: absolute;
          inset: 0;
          background: linear-gradient(
            180deg,
            rgba(0, 0, 0, 0.45) 0%,
            rgba(0, 0, 0, 0) 35%,
            rgba(0, 0, 0, 0.78) 100%
          );
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          padding: 14px 16px;
        }

        .hero-top {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
        }

        .card-title {
          font-size: 0.95rem;
          font-weight: 600;
          color: #fff;
          text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
        }

        .expand-pill {
          background: rgba(0, 0, 0, 0.55);
          backdrop-filter: blur(8px);
          color: #fff;
          padding: 5px 10px;
          border-radius: 999px;
          font-size: 0.78rem;
          font-weight: 600;
          display: inline-flex;
          align-items: center;
          gap: 5px;
          border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .hero-bottom {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          gap: 12px;
        }

        .latest-species {
          font-size: 1.15rem;
          font-weight: 700;
          color: #fff;
          text-shadow: 0 1px 4px rgba(0, 0, 0, 0.75);
        }

        .latest-time {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.82);
          margin-top: 2px;
        }

        .stats-bar {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          padding: 12px 16px;
          border-top: 1px solid var(--birdfy-border);
        }

        .stat-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: 6px 8px;
          background: var(--birdfy-surface);
          border-radius: 8px;
        }

        .stat-value {
          font-size: 1.05rem;
          font-weight: 700;
          color: var(--birdfy-text);
        }

        .stat-label {
          font-size: 0.72rem;
          color: var(--birdfy-muted);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        /* Native <dialog> Pop-Out Modal */
        dialog#moments-dialog {
          width: min(1040px, 94vw);
          max-height: 90vh;
          padding: 0;
          border: 1px solid rgba(255, 255, 255, 0.16);
          border-radius: 16px;
          background: #141417;
          color: #f5f5f7;
          box-shadow: 0 24px 64px rgba(0, 0, 0, 0.65);
          overflow: hidden;
        }

        dialog#moments-dialog[open] {
          display: flex;
          flex-direction: column;
        }

        dialog#moments-dialog::backdrop {
          background-color: rgba(0, 0, 0, 0.72);
          backdrop-filter: blur(4px);
        }

        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 14px 20px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          background: #1c1c21;
        }

        .modal-header h2 {
          margin: 0;
          font-size: 1.1rem;
          font-weight: 700;
        }

        .close-btn {
          appearance: none;
          border: 1px solid rgba(255, 255, 255, 0.18);
          background: rgba(255, 255, 255, 0.08);
          color: #fff;
          border-radius: 8px;
          padding: 6px 12px;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
        }

        .close-btn:hover {
          background: rgba(255, 255, 255, 0.16);
        }

        .species-nav {
          display: flex;
          gap: 8px;
          padding: 10px 20px;
          overflow-x: auto;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          background: #18181c;
          scrollbar-width: thin;
        }

        .filter-pill {
          appearance: none;
          border: 1px solid rgba(255, 255, 255, 0.14);
          background: rgba(255, 255, 255, 0.06);
          color: #e5e5ea;
          border-radius: 999px;
          padding: 5px 12px;
          font-size: 0.8rem;
          font-weight: 600;
          white-space: nowrap;
          cursor: pointer;
        }

        .filter-pill[aria-pressed="true"] {
          background: var(--birdfy-accent);
          border-color: var(--birdfy-accent);
          color: #fff;
        }

        .modal-body {
          display: grid;
          grid-template-columns: 1.45fr 1fr;
          min-height: 0;
          flex: 1;
          overflow: hidden;
        }

        @media (max-width: 780px) {
          .modal-body {
            grid-template-columns: 1fr;
            overflow-y: auto;
          }
        }

        .stage-pane {
          padding: 18px 20px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          border-right: 1px solid rgba(255, 255, 255, 0.08);
          background: #0f0f12;
        }

        .stage-media-wrap {
          width: 100%;
          aspect-ratio: 16 / 9;
          background: #000;
          border-radius: 12px;
          overflow: hidden;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .stage-media-wrap video,
        .stage-media-wrap img {
          width: 100%;
          height: 100%;
          object-fit: contain;
          display: block;
        }

        .stage-meta {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 12px;
          flex-wrap: wrap;
        }

        .stage-species {
          font-size: 1.2rem;
          font-weight: 700;
        }

        .stage-time {
          font-size: 0.85rem;
          color: #9a9aa6;
          margin-top: 2px;
        }

        .stage-links {
          display: flex;
          gap: 8px;
        }

        .stage-link {
          text-decoration: none;
          background: rgba(255, 255, 255, 0.1);
          color: #fff;
          padding: 6px 12px;
          border-radius: 8px;
          font-size: 0.8rem;
          font-weight: 600;
        }

        .feed-list {
          list-style: none;
          margin: 0;
          padding: 12px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-height: 68vh;
        }

        .feed-item-btn {
          appearance: none;
          width: 100%;
          border: 1px solid rgba(255, 255, 255, 0.08);
          background: rgba(255, 255, 255, 0.04);
          color: inherit;
          border-radius: 10px;
          padding: 8px;
          display: grid;
          grid-template-columns: 112px 1fr;
          gap: 12px;
          align-items: center;
          text-align: left;
          cursor: pointer;
          transition: background 0.15s ease, border-color 0.15s ease;
        }

        .feed-item-btn:hover {
          background: rgba(255, 255, 255, 0.09);
        }

        .feed-item-btn[aria-current="true"] {
          border-color: var(--birdfy-accent);
          background: rgba(0, 184, 148, 0.14);
        }

        .feed-thumb-wrap {
          position: relative;
          width: 112px;
          aspect-ratio: 16 / 9;
          border-radius: 7px;
          overflow: hidden;
          background: #000;
        }

        .feed-thumb-wrap img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
        }

        .play-badge {
          position: absolute;
          bottom: 4px;
          right: 4px;
          background: rgba(0, 0, 0, 0.72);
          color: #fff;
          font-size: 0.68rem;
          padding: 2px 6px;
          border-radius: 4px;
          font-weight: 600;
        }

        .feed-item-species {
          font-size: 0.92rem;
          font-weight: 600;
          color: #fff;
        }

        .feed-item-time {
          font-size: 0.78rem;
          color: #9a9aa6;
          margin-top: 3px;
        }
      </style>

      <ha-card>
        <button type="button" class="hero-button" id="open-modal-btn" aria-haspopup="dialog">
          <img class="hero-img" id="hero-img" alt="Latest Birdfy Moment" />
          <div class="hero-overlay">
            <div class="hero-top">
              <span class="card-title" id="card-title"></span>
              <span class="expand-pill">⤢ Moments Feed</span>
            </div>
            <div class="hero-bottom">
              <div>
                <div class="latest-species" id="latest-species">Loading...</div>
                <div class="latest-time" id="latest-time"></div>
              </div>
            </div>
          </div>
        </button>

        <div class="stats-bar">
          <div class="stat-item">
            <span class="stat-value" id="stat-moments">0</span>
            <span class="stat-label">Moments</span>
          </div>
          <div class="stat-item">
            <span class="stat-value" id="stat-visits">0</span>
            <span class="stat-label">Bird Visits</span>
          </div>
          <div class="stat-item">
            <span class="stat-value" id="stat-species">0</span>
            <span class="stat-label">Species</span>
          </div>
        </div>
      </ha-card>

      <dialog id="moments-dialog" closedby="any" aria-labelledby="birdfy-modal-title">
        <div class="modal-header">
          <h2 id="birdfy-modal-title">Birdfy Moments Feed</h2>
          <button type="button" class="close-btn" id="close-modal-btn">✕ Close</button>
        </div>
        <nav class="species-nav" id="species-nav" aria-label="Filter moments by species"></nav>
        <div class="modal-body">
          <div class="stage-pane" id="stage-pane"></div>
          <ul class="feed-list" id="feed-list"></ul>
        </div>
      </dialog>
    `;

    const openBtn = this.shadowRoot.querySelector("#open-modal-btn");
    const closeBtn = this.shadowRoot.querySelector("#close-modal-btn");
    const dialog = this.shadowRoot.querySelector("#moments-dialog");

    openBtn?.addEventListener("click", () => this.#openModal(0));
    closeBtn?.addEventListener("click", () => dialog?.close());
    dialog?.addEventListener("close", () => this.#stopVideoPlayback());

    // Fallback for browsers without declarative <dialog closedby="any"> support (e.g. Safari)
    if (dialog && !("closedBy" in HTMLDialogElement.prototype)) {
      dialog.addEventListener("click", (event) => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        const isDialogContent =
          rect.top <= event.clientY &&
          event.clientY <= rect.top + rect.height &&
          rect.left <= event.clientX &&
          event.clientX <= rect.left + rect.width;
        if (isDialogContent) return;
        dialog.close();
      });
    }

    this.#rendered = true;
    this.#updateContent();
  }

  #updateContent() {
    if (!this.#rendered || !this.shadowRoot) return;
    const { feedState, imageState } = this.#resolveEntities();

    const titleEl = this.shadowRoot.querySelector("#card-title");
    const speciesEl = this.shadowRoot.querySelector("#latest-species");
    const timeEl = this.shadowRoot.querySelector("#latest-time");
    const heroImg = this.shadowRoot.querySelector("#hero-img");
    const statMoments = this.shadowRoot.querySelector("#stat-moments");
    const statVisits = this.shadowRoot.querySelector("#stat-visits");
    const statSpecies = this.shadowRoot.querySelector("#stat-species");

    const title =
      this.#config.title ||
      feedState?.attributes?.friendly_name?.replace(/ Moments Feed$/i, "") ||
      "Birdfy Moments";
    if (titleEl) titleEl.textContent = title;

    if (!feedState) {
      if (speciesEl) speciesEl.textContent = "No Birdfy Moments entity found";
      return;
    }

    const attrs = feedState.attributes || {};
    const moments = Array.isArray(attrs.moments) ? attrs.moments : [];
    const latest = moments[0] || null;

    if (speciesEl) {
      speciesEl.textContent = latest?.species || feedState.state || "No moments yet";
    }
    if (timeEl) {
      timeEl.textContent = latest?.time ? this.#formatTime(latest.time) : "";
    }

    const imgUrl =
      imageState?.attributes?.entity_picture ||
      latest?.image_url ||
      imageState?.attributes?.image_url ||
      "";
    if (heroImg && imgUrl && heroImg.getAttribute("src") !== imgUrl) {
      heroImg.setAttribute("src", imgUrl);
    }

    if (statMoments) statMoments.textContent = String(attrs.total_moments ?? moments.length);
    if (statVisits) statVisits.textContent = String(attrs.bird_visits ?? 0);
    if (statSpecies) statSpecies.textContent = String(attrs.species_count ?? 0);

    const dialog = this.shadowRoot.querySelector("#moments-dialog");
    const sig = `${latest?.alarm_id || ""}:${moments.length}`;
    if (dialog?.open && sig !== this.#lastFeedSignature) {
      this.#lastFeedSignature = sig;
      this.#renderModalBody();
    }
  }

  #renderModalBody() {
    if (!this.shadowRoot) return;
    const { feedState } = this.#resolveEntities();
    const attrs = feedState?.attributes || {};
    const allMoments = Array.isArray(attrs.moments) ? attrs.moments : [];
    const speciesCounts = attrs.species_counts || {};

    // 1. Render Species Filter Pills
    const navEl = this.shadowRoot.querySelector("#species-nav");
    if (navEl) {
      navEl.innerHTML = "";
      const pills = [
        { key: "all", label: `All Moments (${allMoments.length})` },
        ...Object.entries(speciesCounts).map(([sp, cnt]) => ({
          key: sp,
          label: `${sp} (${cnt})`,
        })),
      ];
      for (const pill of pills) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "filter-pill";
        btn.setAttribute(
          "aria-pressed",
          String(this.#selectedSpecies === pill.key)
        );
        btn.textContent = pill.label;
        btn.addEventListener("click", () => {
          this.#selectedSpecies = pill.key;
          this.#selectedIndex = 0;
          this.#renderModalBody();
        });
        navEl.appendChild(btn);
      }
    }

    const filtered = this.#getFilteredMoments(allMoments);
    if (this.#selectedIndex >= filtered.length) {
      this.#selectedIndex = 0;
    }
    const activeMoment = filtered[this.#selectedIndex] || null;

    // 2. Render Main Video / Snapshot Stage
    const stageEl = this.shadowRoot.querySelector("#stage-pane");
    if (stageEl) {
      stageEl.innerHTML = "";
      if (!activeMoment) {
        const empty = document.createElement("div");
        empty.textContent = "No moments in this filter.";
        stageEl.appendChild(empty);
      } else {
        const mediaWrap = document.createElement("div");
        mediaWrap.className = "stage-media-wrap";

        if (activeMoment.video_url) {
          const video = document.createElement("video");
          video.id = "modal-video-player";
          video.controls = true;
          video.autoplay = true;
          video.playsInline = true;
          if (activeMoment.image_url) {
            video.poster = activeMoment.image_url;
          }
          video.src = activeMoment.video_url;
          mediaWrap.appendChild(video);
        } else if (activeMoment.image_url) {
          const img = document.createElement("img");
          img.src = activeMoment.image_url;
          img.alt = activeMoment.species || "Moment snapshot";
          mediaWrap.appendChild(img);
        }

        const meta = document.createElement("div");
        meta.className = "stage-meta";

        const info = document.createElement("div");
        const spTitle = document.createElement("div");
        spTitle.className = "stage-species";
        spTitle.textContent = activeMoment.species || "Motion";

        const tmSub = document.createElement("div");
        tmSub.className = "stage-time";
        tmSub.textContent = this.#formatTime(activeMoment.time);
        info.append(spTitle, tmSub);

        const links = document.createElement("div");
        links.className = "stage-links";
        if (activeMoment.video_url) {
          const aVid = document.createElement("a");
          aVid.className = "stage-link";
          aVid.href = activeMoment.video_url;
          aVid.target = "_blank";
          aVid.rel = "noopener noreferrer";
          aVid.textContent = "⬇ MP4 Video";
          links.appendChild(aVid);
        }
        if (activeMoment.image_url) {
          const aImg = document.createElement("a");
          aImg.className = "stage-link";
          aImg.href = activeMoment.image_url;
          aImg.target = "_blank";
          aImg.rel = "noopener noreferrer";
          aImg.textContent = "🖼 Full Photo";
          links.appendChild(aImg);
        }

        meta.append(info, links);
        stageEl.append(mediaWrap, meta);
      }
    }

    // 3. Render Scrollable Moments Feed List
    const listEl = this.shadowRoot.querySelector("#feed-list");
    if (listEl) {
      listEl.innerHTML = "";
      filtered.forEach((moment, idx) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "feed-item-btn";
        btn.setAttribute("aria-current", String(idx === this.#selectedIndex));

        const thumbWrap = document.createElement("div");
        thumbWrap.className = "feed-thumb-wrap";
        if (moment.image_url) {
          const img = document.createElement("img");
          img.src = moment.image_url;
          img.loading = "lazy";
          img.alt = moment.species || "Moment thumbnail";
          thumbWrap.appendChild(img);
        }
        if (moment.video_url) {
          const badge = document.createElement("span");
          badge.className = "play-badge";
          badge.textContent = "▶ Video";
          thumbWrap.appendChild(badge);
        }

        const textWrap = document.createElement("div");
        const sp = document.createElement("div");
        sp.className = "feed-item-species";
        sp.textContent = moment.species || "Motion";

        const tm = document.createElement("div");
        tm.className = "feed-item-time";
        tm.textContent = this.#formatTime(moment.time);

        textWrap.append(sp, tm);
        btn.append(thumbWrap, textWrap);
        btn.addEventListener("click", () => {
          this.#selectedIndex = idx;
          this.#renderModalBody();
        });

        li.appendChild(btn);
        listEl.appendChild(li);
      });
    }
  }
}

if (!customElements.get("birdfy-moments-card")) {
  customElements.define("birdfy-moments-card", BirdfyMomentsCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "birdfy-moments-card")) {
  window.customCards.push({
    type: "birdfy-moments-card",
    name: "Birdfy Moments Card",
    description:
      "Camera snapshot card with a pop-out modal for browsing and playing Birdfy Moments.",
    preview: true,
  });
}
