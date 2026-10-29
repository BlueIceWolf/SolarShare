/* SolarShare: full-width Home Assistant dashboard card. */
class SolarShareCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this.period = "month";
    this.entities = null;
    this.devices = new Map();
    this.loading = false;
  }
  setConfig(config) {
    this.config = config || {};
    this.period = this.config.period || "month";
    this.lastHistoryPeriod = this.period !== "live" ? this.period : "month";
    this.render();
  }
  set hass(hass) {
    this._hass = hass;
    if (!this.entities && !this.loading) this.load();
    this.render();
  }
  static getStubConfig() { return {period: "month"}; }
  static getConfigElement() { return document.createElement("solarshare-card-editor"); }
  selected(key, defaults) {
    return Array.isArray(this.config[key]) ? this.config[key] : defaults;
  }
  visibleSection(name) {
    return this.selected("sections", ["overview","apartments","wallboxes","live_site","live_units"]).includes(name);
  }
  getCardSize() { return 8; }
  async load() {
    if (!this._hass || this.loading) return;
    this.loading = true;
    try {
      const [entities, devices] = await Promise.all([
        this._hass.callWS({type: "config/entity_registry/list"}),
        this._hass.callWS({type: "config/device_registry/list"})
      ]);
      this.entities = entities.filter(e => e.platform === "solarshare" && e.unique_id);
      this.devices = new Map(devices.map(d => [d.id, d]));
    } catch (err) {
      this.error = "Geräteliste nicht verfügbar: " + err.message;
    } finally {
      this.loading = false;
      this.render();
    }
  }
  esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }
  find(deviceId, metric) {
    if (!this.entities) return null;
    const suffix = "_" + metric + "_" + this.period;
    return this.entities.find(e => e.device_id === deviceId && e.unique_id.endsWith(suffix));
  }
  site(metric) {
    return this.entities && this.entities.find(e => e.unique_id.endsWith("_site_" + metric + "_" + this.period));
  }
  live() {
    if (!this.entities) return null;
    const entity = this.entities.find(e => e.unique_id.endsWith("_site_live_autarky"));
    return this.state(entity);
  }
  state(entity) {
    if (!entity || !this._hass) return null;
    const value = this._hass.states[entity.entity_id];
    return value && !["unknown", "unavailable"].includes(value.state) ? value : null;
  }
  value(entity, euros) {
    const state = this.state(entity);
    const n = state ? Number(state.state) : NaN;
    if (!Number.isFinite(n)) return "—";
    return euros
      ? new Intl.NumberFormat("de-DE", {style:"currency",currency:"EUR"}).format(n)
      : new Intl.NumberFormat("de-DE", {minimumFractionDigits:2,maximumFractionDigits:2}).format(n) + " kWh";
  }
  section(items, label) {
    if (!items.length) return "";
    const available = [
      ["observed", "Verbrauch", "Vom Zähler erfasste kWh. Kann von zugeordneten Mengen abweichen, wenn Messintervalle fehlen."],
      ["solar", "Solarstrom", "Rechnerisch zugeordneter PV-Strom aus gültigen Bilanzintervallen."],
      ["grid", "Netzstrom", "Rechnerisch zugeordnete Netzenergie einschließlich Speicherherkunft."],
      ["unknown", "Ungeklärt", "Noch keiner Stromherkunft eindeutig zugeordnete Energie."],
      ["priced_energy_cost", "Kosten", "Nur bereits sicher bepreiste Energie; Teilbeträge sind keine vollständige Rechnung."]
    ];
    const enabled = this.selected("columns", available.map(([key]) => key));
    const columns = available.filter(([key]) => enabled.includes(key));
    if (!columns.length) return "";
    const number = (entity, cost) => this.esc(this.value(entity, cost));
    const headers = columns.map(([metric, title, help]) =>
      '<th scope="col" class="col-' + metric + '" title="' + this.esc(help) +
      '">' + this.esc(title) + '<span class="help-marker" aria-hidden="true">ⓘ</span></th>'
    ).join("");
    const rows = items.map(device => {
      const cells = columns.map(([metric]) => {
        const entity = this.find(device.id, metric);
        const state = this.state(entity);
        const isCost = metric === "priced_energy_cost";
        const partial = isCost && state && state.attributes.partial_amount === true;
        const hint = "Kosten nur aus eindeutig bepreisten Intervallen. Ungeklärte oder fehlende Anteile sind nicht enthalten.";
        const indicator = partial
          ? '<span class="cost-partial" title="' + this.esc(hint) +
            '" aria-label="Nur Teilbetrag">Teil</span>'
          : "";
        return '<td class="col-' + metric + '" data-entity="' +
          this.esc(entity?.entity_id || "") + '">' +
          '<span class="cell-value">' + number(entity, isCost) + '</span>' +
          indicator + '</td>';
      }).join("");
      return '<tr><th scope="row" class="unit-label">' +
        this.esc(device.name_by_user || device.name || "Einheit") +
        '</th>' + cells + '</tr>';
    }).join("");
    return '<section class="data-section"><div class="section-head"><div><h3>' +
      this.esc(label) + '</h3><p>Gemessene und zugeordnete Energiemengen</p></div>' +
      '<span class="section-count">' + items.length +
      (items.length === 1 ? ' Einheit' : ' Einheiten') + '</span></div>' +
      '<div class="scroll"><table><thead><tr><th scope="col" class="unit-label">Einheit</th>' +
      headers + '</tr></thead><tbody>' + rows + '</tbody></table></div></section>';
  }
  liveUnitSection(devices, label) {
    if (!devices.length) return "";
    const findLive = device => this.entities.find(e =>
      e.device_id === device.id && e.unique_id.endsWith("_live_autarky"));
    const watt = n => {
      const value = Number(n);
      if (n === undefined || n === null || !Number.isFinite(value)) return "—";
      return new Intl.NumberFormat("de-DE", {
        minimumFractionDigits: Math.abs(value) < 10 ? 1 : 0,
        maximumFractionDigits: Math.abs(value) < 10 ? 1 : 0
      }).format(value) + " W";
    };
    const cards = devices.map(device => {
      const state = this.state(findLive(device));
      const number = state ? Number(state.state) : NaN;
      const power = state ? Number(state.attributes.power_w) : NaN;
      const valid = Number.isFinite(number) && Number.isFinite(power) &&
        state.attributes.status === "live";
      const hasLoad = valid && power > 0;
      const percent = hasLoad ? Math.max(0, Math.min(100, number)) : 0;
      return '<article class="unit-card"><div class="unit-name">' +
        this.esc(device.name_by_user || device.name || "Einheit") +
        '</div><div class="unit-primary"><strong>' +
        (hasLoad ? this.esc(percent.toLocaleString("de-DE") + " %") : "—") +
        '</strong><span>Autarkie anteilig</span></div>' +
        '<div class="unit-progress" aria-hidden="true"><div style="width:' +
        percent + '%"></div></div>' +
        '<div class="unit-detail"><span>Verbrauch</span><strong>' +
        this.esc(watt(state?.attributes?.power_w)) + '</strong></div>' +
        '<div class="unit-detail"><span>Eigenversorgung</span><strong>' +
        this.esc(watt(state?.attributes?.local_w)) + '</strong></div>' +
        '<div class="unit-detail"><span>Netz</span><strong>' +
        this.esc(watt(state?.attributes?.grid_w)) + '</strong></div>' +
        (!valid ? '<p class="unit-warning">Leistungswert fehlt oder ist nicht aktuell</p>' :
          !hasLoad ? '<p class="unit-hint">Keine messbare Last – Quote nicht aussagekräftig</p>' : '') +
        '</article>';
    }).join("");
    return '<section class="data-section"><div class="section-head"><div><h3>' +
      this.esc(label) + '</h3><p>Verbrauchsproportionale Live-Verteilung</p></div>' +
      '<span class="section-count">' + devices.length + ' Einheiten</span></div>' +
      '<div class="unit-grid">' + cards + '</div></section>';
  }
  render() {
    if (!this.shadowRoot || !this.config) return;
    const css = [
      ":host{display:block;min-width:0;color:var(--primary-text-color)}",
      "ha-card{box-sizing:border-box;width:100%;min-width:0;padding:clamp(14px,2vw,24px);border-radius:18px}",
      ".top{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}",
      ".brand{min-width:0}.brand h2{margin:0;font-size:clamp(20px,2vw,26px);letter-spacing:-.03em;font-weight:650}",
      ".brand p{margin:5px 0 0;color:var(--secondary-text-color);font-size:12px}",
      ".mode-switch{display:inline-flex;gap:4px;padding:4px;border:1px solid var(--divider-color);border-radius:12px;background:var(--secondary-background-color)}",
      "button{font:inherit;cursor:pointer;color:var(--primary-text-color);border:0}",
      "button:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}",
      ".mode-button{padding:9px 18px;background:transparent;border-radius:9px;font-weight:600;font-size:13px}",
      ".mode-button.on{background:var(--card-background-color);box-shadow:0 1px 5px rgba(0,0,0,.09);color:var(--primary-text-color)}",
      ".period-bar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:16px}",
      ".period-button{background:var(--secondary-background-color);border:1px solid transparent;padding:8px 12px;border-radius:9px;font-size:12px}",
      ".period-button.on{background:var(--primary-color);color:var(--text-primary-color,#fff);font-weight:650}",
      ".section-caption{margin:18px 0 10px;display:flex;gap:8px;justify-content:space-between;align-items:center;flex-wrap:wrap}",
      ".section-caption strong{font-size:14px}.section-caption span{color:var(--secondary-text-color);font-size:12px}",
      ".stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}",
      ".stat{min-width:0;box-sizing:border-box;border:1px solid var(--divider-color);border-radius:13px;padding:14px 16px;background:var(--card-background-color)}",
      ".stat-name{color:var(--secondary-text-color);font-size:12px;display:block;line-height:1.35}",
      ".stat-value{font-size:clamp(19px,2vw,24px);font-weight:690;letter-spacing:-.02em;display:block;margin-top:7px;font-variant-numeric:tabular-nums;white-space:nowrap}",
      ".stat-note{font-size:11px;color:var(--secondary-text-color);margin-top:5px}",
      ".stat[data-metric=pv] .stat-value{color:var(--success-color,var(--primary-text-color))}",
      ".data-section{margin-top:14px;border:1px solid var(--divider-color);border-radius:14px;overflow:hidden;background:var(--card-background-color)}",
      ".section-head{padding:16px 17px;display:flex;justify-content:space-between;align-items:center;gap:10px}",
      ".section-head h3{margin:0;font-size:16px;font-weight:680;letter-spacing:-.01em}",
      ".section-head p{margin:4px 0 0;font-size:12px;color:var(--secondary-text-color)}",
      ".section-count{font-size:11px;color:var(--secondary-text-color);white-space:nowrap;background:var(--secondary-background-color);border-radius:7px;padding:5px 8px}",
      ".scroll{max-width:100%;overflow:auto;overscroll-behavior-x:contain}",
      "table{width:100%;border-collapse:separate;border-spacing:0;min-width:710px;text-align:right}",
      "thead th{font-size:11px;font-weight:630;color:var(--secondary-text-color);background:var(--secondary-background-color);white-space:nowrap}",
      "table th,table td{padding:13px 16px;border-bottom:1px solid var(--divider-color);font-variant-numeric:tabular-nums}",
      "tbody tr:last-child>*{border-bottom:none}tbody tr:hover{background:var(--secondary-background-color)}",
      "table .unit-label{text-align:left;min-width:125px;font-weight:600;white-space:nowrap}",
      "table td{text-align:right;white-space:nowrap;font-size:13px}",
      ".cell-value{font-weight:550}.col-solar .cell-value{color:var(--success-color,var(--primary-text-color))}",
      ".col-unknown .cell-value{color:var(--secondary-text-color)}",
      ".col-priced_energy_cost{min-width:90px}",
      ".help-marker{display:inline-block;margin-left:5px;font-size:10px;opacity:.45;cursor:help}",
      ".cost-partial{display:inline-block;margin-left:6px;border:1px solid var(--divider-color);border-radius:5px;padding:2px 4px;font-size:10px;line-height:1;color:var(--secondary-text-color);font-weight:500;cursor:help}",
      "td[data-entity]:not([data-entity='']){cursor:pointer}",
      ".footnote{font-size:11px;color:var(--secondary-text-color);line-height:1.55;margin:13px 2px 0}",
      ".footnote strong{color:var(--primary-text-color);font-weight:600}",
      ".live-layout{display:flex;flex-wrap:wrap;align-items:center;gap:22px;padding:2px 17px 18px}",
      ".live-gauge{width:140px;height:140px;border-radius:50%;display:grid;place-items:center;flex-shrink:0}",
      ".live-inner{width:114px;height:114px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;background:var(--card-background-color)}",
      ".live-inner strong{font-size:29px;letter-spacing:-.02em}.live-inner span{font-size:11px;color:var(--secondary-text-color)}",
      ".live-details{display:grid;grid-template-columns:repeat(2,minmax(130px,1fr));gap:10px;flex:1;min-width:220px}",
      ".live-stat{padding:11px 14px;border:1px solid var(--divider-color);border-radius:11px}",
      ".live-stat span{display:block;color:var(--secondary-text-color);font-size:11px}",
      ".live-stat strong{display:block;font-size:19px;margin-top:4px;font-variant-numeric:tabular-nums}",
      ".unit-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(195px,1fr));gap:10px;padding:0 16px 16px}",
      ".unit-card{padding:14px;border:1px solid var(--divider-color);border-radius:12px;background:var(--card-background-color);min-width:0}",
      ".unit-name{font-size:13px;font-weight:650;overflow-wrap:anywhere}",
      ".unit-primary{display:flex;align-items:baseline;justify-content:space-between;gap:6px;margin:12px 0 8px}",
      ".unit-primary strong{font-size:23px;font-variant-numeric:tabular-nums}.unit-primary span{font-size:10px;color:var(--secondary-text-color)}",
      ".unit-progress{height:5px;background:var(--divider-color);border-radius:8px;overflow:hidden;margin-bottom:12px}",
      ".unit-progress>div{height:100%;background:var(--success-color,#349b51)}",
      ".unit-detail{display:flex;justify-content:space-between;gap:10px;padding:4px 0;font-size:12px}",
      ".unit-detail span{color:var(--secondary-text-color)}.unit-detail strong{font-variant-numeric:tabular-nums}",
      ".unit-warning,.unit-hint{font-size:11px;color:var(--secondary-text-color);margin:10px 0 0}",
      "@media(max-width:980px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}",
      "@media(max-width:520px){.top{align-items:flex-start}.stats{gap:8px}.stat{padding:11px 12px}",
      ".stat-value{font-size:19px}.section-head{padding:13px}.section-count{display:none}",
      ".live-layout{padding:0 12px 14px}.unit-grid{padding:0 12px 12px}.mode-button{padding:8px 13px}}"
    ].join("");
    if (!this.entities) {
      this.shadowRoot.innerHTML = "<style>" + css + "</style><ha-card>" +
        this.esc(this.error || "SolarShare wird geladen …") + "</ha-card>";
      return;
    }
    const names = {live:"Live",day:"Heute",week:"Diese Woche",last_week:"Letzte Woche",
      month:"Dieser Monat",last_month:"Letzter Monat",year:"Jahr",lifetime:"Gesamt"};
    const selected = this.selected("periods", Object.keys(names));
    const visible = Object.keys(names).filter(key => selected.includes(key));
    const showLive = visible.includes("live");
    const history = visible.filter(key => key !== "live");
    if (!visible.length) visible.push("month");
    if (!visible.includes(this.period)) this.period = visible[0];
    const isLive = this.period === "live";
    if (!isLive) this.lastHistoryPeriod = this.period;
    const mode = '<div class="mode-switch" role="group" aria-label="Ansicht">' +
      (showLive ? '<button class="mode-button' + (isLive ? ' on' : '') +
        '" data-mode="live" aria-pressed="' + isLive + '">Live</button>' : '') +
      (history.length ? '<button class="mode-button' + (!isLive ? ' on' : '') +
        '" data-mode="history" aria-pressed="' + !isLive + '">Historie</button>' : '') +
      '</div>';
    const historyTabs = !isLive && history.length
      ? '<nav class="period-bar" aria-label="Zeitraum">' + history.map(id =>
          '<button class="period-button' + (id === this.period ? ' on' : '') +
          '" data-period="' + id + '" aria-pressed="' + (id === this.period) + '">' +
          this.esc(names[id]) + '</button>').join("") + '</nav>'
      : "";
    const devices = Array.from(this.devices.values()).filter(d =>
      ["Wohnung","Wallbox"].includes(d.model) && d.manufacturer === "SolarShare" &&
      this.entities.some(e => e.device_id === d.id) &&
      this.selected("units", Array.from(this.devices.values()).map(x => x.id)).includes(d.id));
    const apartments = devices.filter(d => d.model === "Wohnung");
    const wallboxes = devices.filter(d => d.model === "Wallbox");
    let body = "";
    if (isLive) {
      if (this.visibleSection("live_site")) {
        const live = this.live();
        const num = live ? Number(live.state) : NaN;
        const fmtW = value => typeof value === "number" && Number.isFinite(value)
          ? new Intl.NumberFormat("de-DE", {maximumFractionDigits:0}).format(value) + " W" : "—";
        let content = '<p class="footnote">Keine aktuellen Leistungswerte verfügbar. Prüfe die unter SolarShare → Konfigurieren → Live-Leistung hinterlegten Sensoren.</p>';
        if (Number.isFinite(num)) {
          const pct = Math.max(0, Math.min(100, num));
          content = '<div class="live-layout"><div class="live-gauge" style="background:conic-gradient(var(--success-color,#349b51) ' +
            pct + '%,var(--divider-color) 0)"><div class="live-inner"><strong>' +
            this.esc(pct.toLocaleString("de-DE")) +
            ' %</strong><span>Netzunabhängigkeit</span></div></div>' +
            '<div class="live-details"><div class="live-stat"><span>Gebäudeverbrauch</span><strong>' +
            this.esc(fmtW(Number(live.attributes.load_w))) + '</strong></div>' +
            '<div class="live-stat"><span>Netzbezug</span><strong>' +
            this.esc(fmtW(Number(live.attributes.import_w))) + '</strong></div></div></div>';
        }
        body += '<section class="data-section"><div class="section-head"><div><h3>Autarkie gerade</h3>' +
          '<p>Live-Leistung · keine Abrechnungsgröße</p></div></div>' + content + '</section>';
      }
      if (this.visibleSection("live_units")) {
        if (this.visibleSection("apartments")) body += this.liveUnitSection(apartments, "Wohnungen – Live");
        if (this.visibleSection("wallboxes")) body += this.liveUnitSection(wallboxes, "Wallboxen – Live");
      }
      body += '<p class="footnote">Die <strong>Live-Verteilung bleibt proportional</strong>: ' +
        'Alle teilnehmenden Einheiten haben bei gleicher Zuteilungsregel denselben prozentualen Deckungsgrad. ' +
        'Die zugeordneten Wattwerte unterscheiden sich nach Verbrauch.</p>';
    } else {
      const overview = [
        ["pv","PV-Erzeugung"], ["consumption","Gebäudeverbrauch"],
        ["import","Netzbezug"], ["residual","Allgemeinverbrauch / Messdifferenz"]
      ];
      const chosen = this.selected("overview", ["pv","import","consumption","residual"]);
      const cards = overview.filter(([metric]) => chosen.includes(metric)).map(([metric,name]) =>
        '<div class="stat" data-metric="' + metric + '"><span class="stat-name">' +
        this.esc(name) + '</span><strong class="stat-value">' +
        this.esc(this.value(this.site(metric), false)) + '</strong>' +
        '<div class="stat-note">' + this.esc(names[this.period] || "Zeitraum") +
        '</div></div>').join("");
      if (cards && this.visibleSection("overview")) body += '<div class="section-caption">' +
        '<strong>Gebäudeübersicht</strong><span>Zeitraum: ' +
        this.esc(names[this.period]) + '</span></div><div class="stats">' + cards + '</div>';
      if (this.visibleSection("apartments")) body += this.section(apartments, "Wohnungen");
      if (this.visibleSection("wallboxes")) body += this.section(wallboxes, "Wallboxen");
      body += '<p class="footnote"><strong>Hinweis zur Datenbasis:</strong> Verbrauch ist unabhängig vom Bilanzfenster gemessen; ' +
        'Solar-, Netz- und ungeklärte Anteile stammen aus erfolgreich zugeordneten Intervallen und können deshalb abweichen. ' +
        'Als „Teil“ markierte Kosten sind keine vollständigen Rechnungsbeträge. ' +
        'Im Restverbrauch stecken auch nicht einzeln gemessene Verbraucher wie der Keller.</p>';
    }
    const header = '<header class="top"><div class="brand"><h2>SolarShare</h2>' +
      '<p>Stromverteilung und Verbrauchsübersicht</p></div>' + mode + '</header>';
    this.shadowRoot.innerHTML = "<style>" + css + "</style><ha-card>" +
      header + historyTabs + body + "</ha-card>";
    this.shadowRoot.querySelectorAll("button[data-mode]").forEach(el => el.onclick = () => {
      if (el.dataset.mode === "live") {
        this.period = "live";
      } else {
        this.period = history.includes(this.lastHistoryPeriod)
          ? this.lastHistoryPeriod : (history[0] || "live");
      }
      this.render();
    });
    this.shadowRoot.querySelectorAll("button[data-period]").forEach(el => el.onclick = () => {
      this.period = el.dataset.period;
      this.lastHistoryPeriod = this.period;
      this.render();
    });
    this.shadowRoot.querySelectorAll("td[data-entity]").forEach(el => el.onclick = () => {
      if (el.dataset.entity) this.dispatchEvent(new CustomEvent("hass-more-info", {
        bubbles:true, composed:true, detail:{entityId:el.dataset.entity}
      }));
    });
  }

}
class SolarShareCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this.devices = [];
    this.loading = false;
    this.loaded = false;
  }
  setConfig(config) {
    this._config = {...config};
    this.render();
  }
  set hass(hass) {
    this._hass = hass;
    if (!this.loaded && !this.loading) this.loadDevices();
    this.render();
  }
  async loadDevices() {
    if (!this._hass || this.loaded || this.loading) return;
    this.loading = true;
    try {
      const devices = await this._hass.callWS({type:"config/device_registry/list"});
      this.devices = devices.filter(d =>
        d.manufacturer === "SolarShare" && ["Wohnung","Wallbox"].includes(d.model));
      this.loaded = true;
    } catch (error) {
      this.error = "Geräte konnten nicht geladen werden: " + error.message;
    } finally {
      this.loading = false;
      this.render();
    }
  }
  escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, ch => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
    })[ch]);
  }
  options(name, items) {
    const enabled = Array.isArray(this._config[name]) ?
      this._config[name] : items.map(item => item[0]);
    return items.map(([value,label]) =>
      '<label><input type="checkbox" data-set="' + name +
      '" value="' + this.escape(value) + '"' +
      (enabled.includes(value) ? ' checked' : '') + '>' +
      '<span>' + this.escape(label) + '</span></label>'
    ).join("");
  }
  render() {
    if (!this.shadowRoot || !this._config) return;
    const periods = [
      ["live","Live"],["day","Heute"],["week","Diese Woche"],["last_week","Letzte Woche"],
      ["month","Dieser Monat"],["last_month","Letzter Monat"],["year","Jahr"],["lifetime","Gesamt"]
    ];
    const sections = [
      ["overview","Gesamtübersicht"],["apartments","Wohnungen"],
      ["wallboxes","Wallboxen"],["live_site","Gebäude-Autarkie live"],
      ["live_units","Autarkie je Einheit live"]
    ];
    const cols = [
      ["observed","Gemessener Verbrauch"],["solar","Solarstrom"],
      ["grid","Netzstrom"],["unknown","Ungeklärte Herkunft"],
      ["priced_energy_cost","Kosten"]
    ];
    const summary = [
      ["pv","PV-Erzeugung"],["import","Netzbezug"],
      ["consumption","Gebäudeverbrauch"],["residual","Allgemeinverbrauch"]
    ];
    const defaultPeriod = this._config.period || "month";
    const periodOptions = periods.filter(([key]) =>
      (this._config.periods || periods.map(p => p[0])).includes(key));
    const unitEntries = this.devices.map(d => [d.id,d.name || d.name_by_user || "Einheit"]);
    this.shadowRoot.innerHTML =
      '<style>:host{display:block}h3{margin:16px 0 8px;font-size:15px}' +
      'fieldset{border:1px solid var(--divider-color);border-radius:12px;padding:12px;margin:10px 0}' +
      'legend{padding:0 5px;font-weight:600}label{display:flex;align-items:center;gap:8px;padding:5px 0;cursor:pointer}' +
      'input{accent-color:var(--primary-color)}select{width:100%;padding:9px;border-radius:10px;' +
      'background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color)}' +
      '.choices{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1px 12px}' +
      '.note{color:var(--secondary-text-color);font-size:12px}</style>' +
      '<h3>Standardansicht</h3><select data-default-period>' +
      periodOptions.map(([id,label]) => '<option value="' + id + '"' +
        (defaultPeriod === id ? ' selected' : '') + '>' + label + '</option>').join("") +
      '</select>' +
      '<fieldset><legend>Sichtbare Zeiträume</legend><div class="choices">' +
      this.options("periods",periods) + '</div></fieldset>' +
      '<fieldset><legend>Bereiche anzeigen</legend><div class="choices">' +
      this.options("sections",sections) + '</div></fieldset>' +
      '<fieldset><legend>Kennzahlen oben</legend><div class="choices">' +
      this.options("overview",summary) + '</div></fieldset>' +
      '<fieldset><legend>Spalten je Wohnung / Wallbox</legend><div class="choices">' +
      this.options("columns",cols) + '</div></fieldset>' +
      '<fieldset><legend>Sichtbare Wohnungen & Wallboxen</legend><div class="choices">' +
      (this.loaded ? this.options("units",unitEntries) :
        '<div class="note">' + this.escape(this.error || "SolarShare-Geräte werden geladen …") + '</div>') +
      '</div></fieldset>' +
      '<p class="note">Einstellungen betreffen nur die Darstellung. Die kWh-Erfassung und Abrechnung bleiben unverändert.</p>';
    this.shadowRoot.querySelectorAll('input[data-set]').forEach(input => {
      input.addEventListener("change", () => {
        const name = input.dataset.set;
        const group = name === "periods" ? periods : name === "sections" ? sections :
          name === "overview" ? summary : name === "columns" ? cols : unitEntries;
        const checked = this.shadowRoot.querySelectorAll('input[data-set="' + name + '"]:checked');
        const next = Array.from(checked, item => item.value);
        if (name === "periods" && !next.length) { this.render(); return; }
        this._config = {...this._config,[name]:next};
        if (name === "periods" && !next.includes(this._config.period || "month")) {
          this._config.period = next[0];
        }
        this.dispatchEvent(new CustomEvent("config-changed",{
          bubbles:true,composed:true,detail:{config:{...this._config}}
        }));
        this.render();
      });
    });
    const selector = this.shadowRoot.querySelector("select[data-default-period]");
    if (selector) selector.addEventListener("change", () => {
      this._config = {...this._config,period:selector.value};
      this.dispatchEvent(new CustomEvent("config-changed",{
        bubbles:true,composed:true,detail:{config:{...this._config}}
      }));
    });
  }
}
if (!customElements.get("solarshare-card-editor")) {
  customElements.define("solarshare-card-editor",SolarShareCardEditor);
}

if (!customElements.get("solarshare-card")) customElements.define("solarshare-card", SolarShareCard);
window.customCards = window.customCards || [];
window.customCards.push({type:"solarshare-card",name:"SolarShare",description:"Kosten und Verbrauch aller Wohnungen und Wallboxen"});
