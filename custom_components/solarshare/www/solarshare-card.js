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
      ["observed","Gemessen"], ["solar","Solar"], ["grid","Netz"],
      ["unknown","Ungeklärt"], ["priced_energy_cost","Kosten"]
    ];
    const metrics = available.filter(([key]) => this.selected("columns", available.map(c => c[0])).includes(key));
    if (!metrics.length) return "";
    const rows = items.map(device => {
      const cells = metrics.map(([metric]) => {
        const entity = this.find(device.id, metric);
        const cost = metric === "priced_energy_cost";
        const state = this.state(entity);
        const partial = cost && state && Boolean(state.attributes.partial_amount);
        return '<td data-entity="' + this.esc(entity ? entity.entity_id : "") + '">' +
          this.esc(this.value(entity, cost)) + (partial ? "<small>Teilbetrag</small>" : "") + "</td>";
      }).join("");
      return "<tr><th>" + this.esc(device.name || "Unbenannt") + "</th>" + cells + "</tr>";
    }).join("");
    const headers = metrics.map(([,label]) => "<th>" + this.esc(label) + "</th>").join("");
    return '<section><h3>' + this.esc(label) + '</h3><div class="scroll"><table>' +
      "<thead><tr><th>Einheit</th>" + headers + "</tr></thead>" +
      "<tbody>" + rows + "</tbody></table></div></section>";
  }
  liveUnitSection(devices, label) {
    if (!devices.length) return "";
    const findLive = device => this.entities.find(e =>
      e.device_id === device.id && e.unique_id.endsWith("_live_autarky"));
    const cards = devices.map(device => {
      const entity = findLive(device);
      const state = this.state(entity);
      const number = state ? Number(state.state) : NaN;
      const valid = Number.isFinite(number) && state.attributes.status === "live";
      const percent = valid ? Math.max(0, Math.min(100, number)) : 0;
      const watt = n => typeof n === "number" && Number.isFinite(n)
        ? new Intl.NumberFormat("de-DE", {maximumFractionDigits:0}).format(n) + " W"
        : "—";
      return '<div class="unit-card"><div class="unit-name">' + this.esc(device.name || "Einheit") +
        '</div><div class="unit-pct">' + (valid ? this.esc(percent.toLocaleString("de-DE") + " %") : "—") +
        '</div><div class="unit-progress"><div style="width:' + percent + '%"></div></div>' +
        '<div class="unit-detail">Verbrauch <strong>' + this.esc(watt(state?.attributes?.power_w)) + '</strong></div>' +
        '<div class="unit-detail">Eigenversorgung <strong>' + this.esc(watt(state?.attributes?.local_w)) + '</strong></div>' +
        '<div class="unit-detail">Netz <strong>' + this.esc(watt(state?.attributes?.grid_w)) + '</strong></div>' +
        (!valid ? '<div class="note">Leistungssensor fehlt oder ist nicht aktuell</div>' : '') +
        '</div>';
    }).join("");
    return '<section><h3>' + this.esc(label) + '</h3><div class="unit-grid">' + cards +
      '</div><p class="note">Anteilige Live-Zuordnung aus dem gemeinsamen Gebäude. ' +
      'Alle Einheiten haben bei proportionaler Verteilung denselben Autarkie-Prozentsatz.</p></section>';
  }
  render() {
    if (!this.shadowRoot || !this.config) return;
    const css = [
      ":host{display:block;width:100%}ha-card{box-sizing:border-box;padding:20px;border-radius:20px;width:100%}",
      ".top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:16px}",
      "h2{margin:0;font-size:23px}h3{margin:0 0 12px;font-size:17px}",
      ".sub,.note{color:var(--secondary-text-color);font-size:12px}",
      ".periods{display:flex;gap:5px;flex-wrap:wrap}",
      "button{border:0;border-radius:9px;padding:8px 12px;cursor:pointer;color:var(--primary-text-color);background:var(--secondary-background-color)}",
      "button.on{color:#fff;background:var(--primary-color)}",
      ".stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}",
      ".stat,section{background:var(--secondary-background-color);padding:14px;border-radius:14px}",
      ".stat span{display:block;color:var(--secondary-text-color);font-size:12px;margin-bottom:8px}",
      ".stat strong{font-size:21px;font-variant-numeric:tabular-nums}",
      ".live{display:flex;align-items:center;flex-wrap:wrap;gap:24px;min-height:200px}",
      ".live-gauge{width:150px;height:150px;border-radius:50%;display:grid;place-items:center;flex-shrink:0}",
      ".live-inner{width:120px;height:120px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;background:var(--card-background-color)}",
      ".live-inner strong{font-size:30px}.live-details{display:flex;flex-direction:column;gap:8px}",
      ".live-details span{color:var(--secondary-text-color);font-size:13px}",
      ".unit-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}",
      ".unit-card{padding:14px;border-radius:12px;background:var(--card-background-color)}",
      ".unit-name{font-size:14px;font-weight:600}.unit-pct{font-size:24px;font-weight:700;margin:8px 0}",
      ".unit-progress{height:7px;border-radius:8px;background:var(--divider-color);overflow:hidden;margin-bottom:12px}",
      ".unit-progress>div{height:100%;background:var(--success-color,#16a34a)}",
      ".unit-detail{display:flex;justify-content:space-between;gap:6px;font-size:12px;padding:4px 0}",
      "section{margin-top:12px}.scroll{overflow:auto}",
      "table{width:100%;border-collapse:collapse;text-align:right;min-width:690px}",
      "td,th{padding:11px 8px;border-bottom:1px solid var(--divider-color);font-variant-numeric:tabular-nums}",
      "td:first-child,th:first-child{text-align:left}thead th{color:var(--secondary-text-color);font-size:12px}",
      "tbody tr:last-child>*{border-bottom:0}small{display:block;color:var(--warning-color);font-size:10px}",
      "td[data-entity]:not([data-entity='']){cursor:pointer}",
      "@media(max-width:900px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}",
      "@media(max-width:460px){ha-card{padding:12px}.stat strong{font-size:17px}}"
    ].join("");
    if (!this.entities) {
      this.shadowRoot.innerHTML = "<style>" + css + "</style><ha-card>" +
        this.esc(this.error || "SolarShare wird geladen …") + "</ha-card>";
      return;
    }
    const names = {live:"Live",day:"Heute",week:"Diese Woche",last_week:"Letzte Woche",month:"Dieser Monat",last_month:"Letzter Monat",year:"Jahr",lifetime:"Gesamt"};
    const visiblePeriods = this.selected("periods", Object.keys(names));
    if (visiblePeriods.length && !visiblePeriods.includes(this.period)) this.period = visiblePeriods[0];
    const periods = Object.entries(names).filter(([id]) => visiblePeriods.includes(id)).map(([id,label]) =>
      '<button data-period="' + id + '" class="' + (id === this.period ? "on" : "") + '">' + label + "</button>"
    ).join("");
    const devices = Array.from(this.devices.values()).filter(d =>
      ["Wohnung","Wallbox"].includes(d.model) && d.manufacturer === "SolarShare" &&
      this.entities.some(e => e.device_id === d.id) &&
      this.selected("units", Array.from(this.devices.values()).map(x => x.id)).includes(d.id));
    const apartments = devices.filter(d => d.model === "Wohnung");
    const wallboxes = devices.filter(d => d.model === "Wallbox");
    let body = "";
    if (this.period === "live") {
      const live = this.live();
      const autarky = live ? Number(live.state) : NaN;
      if (this.visibleSection("live_site")) {
        if (Number.isFinite(autarky)) {
          const pct = Math.max(0, Math.min(100, autarky));
          const load = Number(live.attributes.load_w);
          const imported = Number(live.attributes.import_w);
          const formatPower = n => Number.isFinite(n)
            ? new Intl.NumberFormat("de-DE", {maximumFractionDigits:0}).format(n) + " W" : "—";
          body += '<section><h3>Autarkie gerade</h3><div class="live">' +
            '<div class="live-gauge" style="background:conic-gradient(var(--success-color,#16a34a) ' + pct + '%,var(--divider-color) 0)">' +
            '<div class="live-inner"><strong>' + this.esc(pct.toLocaleString("de-DE")) + ' %</strong><span class="sub">Autarkie</span></div></div>' +
            '<div class="live-details"><div>Gebäudeverbrauch <strong>' + this.esc(formatPower(load)) + '</strong></div>' +
            '<div>Netzbezug <strong>' + this.esc(formatPower(imported)) + '</strong></div>' +
            '<span>Aktuelle Netzunabhängigkeit · Keine Abrechnungsgröße</span></div></div></section>';
        } else {
          body += '<section><h3>Autarkie gerade</h3><p>Keine aktuellen Leistungswerte verfügbar.</p>' +
            '<p class="note">Unter SolarShare → Konfigurieren → Live-Leistung den Gebäudeverbrauch und Netzbezug in Watt zuordnen.</p></section>';
        }
      }
      if (this.visibleSection("live_units")) {
        if (this.visibleSection("apartments")) body += this.liveUnitSection(apartments,"Wohnungen – Live");
        if (this.visibleSection("wallboxes")) body += this.liveUnitSection(wallboxes,"Wallboxen – Live");
      }
    } else {
      const stats = [["PV-Erzeugung","pv"],["Netzbezug","import"],
        ["Gebäudeverbrauch","consumption"],["Allgemeinverbrauch / Messdifferenz","residual"]]
        .filter(([,metric]) => this.selected("overview",["pv","import","consumption","residual"]).includes(metric))
        .map(([name,metric]) => '<div class="stat"><span>' + name + '</span><strong>' +
          this.esc(this.value(this.site(metric), false)) + "</strong></div>").join("");
      if (stats && this.visibleSection("overview")) body += '<div class="stats">' + stats + "</div>";
      if (this.visibleSection("apartments")) body += this.section(apartments,"Wohnungen");
      if (this.visibleSection("wallboxes")) body += this.section(wallboxes,"Wallboxen");
      body += '<p class="note">Kosten nur für eindeutig zugeordnete Energie. ' +
        'Allgemeinverbrauch enthält auch nicht gemessene Bereiche wie den Keller. ' +
        'Vorperioden enthalten nur seit ihrer Einführung erfasste Werte.</p>';
    }
    this.shadowRoot.innerHTML = "<style>" + css + "</style><ha-card>" +
      '<div class="top"><div><h2>☀ SolarShare</h2><div class="sub">Strom & Kosten je Einheit</div></div>' +
      '<div class="periods">' + periods + "</div></div>" + body + "</ha-card>";
    this.shadowRoot.querySelectorAll("button[data-period]").forEach(el => el.onclick = () => {
      this.period = el.dataset.period; this.render();
    });
    this.shadowRoot.querySelectorAll("td[data-entity]").forEach(el => el.onclick = () => {
      if (el.dataset.entity) this.dispatchEvent(new CustomEvent("hass-more-info", {
        bubbles:true, composed:true, detail:{entityId:el.dataset.entity}
      }));
    });
  }
}
if (!customElements.get("solarshare-card")) customElements.define("solarshare-card", SolarShareCard);
window.customCards = window.customCards || [];
window.customCards.push({type:"solarshare-card",name:"SolarShare",description:"Kosten und Verbrauch aller Wohnungen und Wallboxen"});
