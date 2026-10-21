class KnowledgeRadar {
    constructor(root) {
        this.root = root;
        this.data = null;
        this.selected = null;
        this.mode = "open";
        this.researched = [];
        this.loaded = false;
        this.phase = 1;
        this.list = document.getElementById("knowledge-radar-list");
        this.status = document.getElementById("knowledge-radar-status");
        document.getElementById("knowledge-radar-refresh")?.addEventListener("click", () => this.load(true));
        document.getElementById("knowledge-radar-filter")?.addEventListener("input", event => this.render(event.target.value));
        document.getElementById("knowledge-radar-research")?.addEventListener("click", () => this.startResearch());
        document.getElementById("knowledge-radar-ai-evaluate")?.addEventListener("click", () => this.evaluateAI(false));
        document.getElementById("knowledge-radar-ai-enabled")?.addEventListener("change", () => this.updateAIControls());
        document.getElementById("knowledge-growth-save")?.addEventListener("click", () => this.saveGrowthConfig());
        document.getElementById("knowledge-growth-run")?.addEventListener("click", () => this.runGrowthRadar());
        document.getElementById("knowledge-radar-tab-open")?.addEventListener("click", () => this.setMode("open"));
        document.getElementById("knowledge-radar-tab-researched")?.addEventListener("click", () => this.setMode("researched"));
        document.getElementById("knowledge-radar-candidate-select")?.addEventListener("change", event => this.selectFromMenu(event.target.value));
        this.bindDetailDrawer();
    }

    escape(value) {
        return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    bindDetailDrawer() {
        const toggle = document.getElementById("knowledge-radar-detail-toggle");
        const icon = document.getElementById("knowledge-radar-detail-toggle-icon");
        const panel = document.getElementById("knowledge-radar-detail-panel");
        const backdrop = document.getElementById("knowledge-radar-detail-backdrop");
        if (!toggle || !panel || !backdrop) return;
        this.setDetailOpen = open => {
            panel.classList.toggle("open", open);
            backdrop.classList.toggle("visible", open);
            toggle.setAttribute("aria-expanded", String(open));
            if (icon) icon.textContent = open ? "▸" : "◂";
        };
        toggle.addEventListener("click", () => this.setDetailOpen(!panel.classList.contains("open")));
        backdrop.addEventListener("click", () => this.setDetailOpen(false));
        document.addEventListener("keydown", event => {
            if (event.key === "Escape" && panel.classList.contains("open")) {
                this.setDetailOpen(false);
                toggle.focus();
            }
        });
    }

    updatePhase(phase, message, aiActive = false) {
        this.phase = phase;
        document.querySelectorAll("[data-radar-phase]").forEach(node => {
            const number = Number(node.dataset.radarPhase);
            node.classList.toggle("done", number < phase);
            node.classList.toggle("active", number === phase);
            node.classList.toggle("ai-active", number === phase && aiActive);
            if (number === phase) node.setAttribute("aria-current", "step");
            else node.removeAttribute("aria-current");
        });
        const status = document.getElementById("knowledge-radar-phase-status");
        if (status) status.textContent = message;
    }

    async load(force = false) {
        if (this.loaded && !force) {
            await Promise.all([this.loadGrowth(), this.loadResearched()]);
            return;
        }
        this.status.textContent = "Vault-Themen und offene Fragen werden lokal analysiert …";
        this.updatePhase(1, "Stufe 1 · Vault wird regelbasiert analysiert");
        this.list.innerHTML = "";
        try {
            const response = await fetch("/api/knowledge-radar", {cache: "no-store"});
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "Wissensradar nicht verfügbar.");
            this.data = data;
            this.loaded = true;
            document.getElementById("radar-document-count").textContent = data.documents_scanned;
            document.getElementById("radar-topic-count").textContent = data.topics.length;
            document.getElementById("radar-candidate-count").textContent = data.candidate_count;
            document.getElementById("knowledge-radar-open-count").textContent = data.candidate_count;
            this.status.textContent = data.method;
            this.updatePhase(1, "Stufe 1 · Wissenslücken erkannt · Radar bereit");
            this.render(document.getElementById("knowledge-radar-filter")?.value || "");
            await Promise.all([this.loadGrowth(), this.loadResearched()]);
        } catch (error) {
            this.status.textContent = `Analyse fehlgeschlagen: ${error.message}`;
            this.status.dataset.state = "error";
        }
    }

    async loadResearched() {
        const response = await fetch("/api/knowledge-radar/researched", {cache: "no-store"});
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Pflegeliste nicht verfügbar.");
        this.researched = data.topics || [];
        document.getElementById("knowledge-radar-researched-count").textContent = this.researched.length;
        this.render(document.getElementById("knowledge-radar-filter")?.value || "");
    }

    setMode(mode) {
        this.mode = mode;
        this.selected = null;
        ["open", "researched"].forEach(name => {
            const button = document.getElementById(`knowledge-radar-tab-${name}`);
            const active = name === mode;
            button.classList.toggle("active", active);
            button.setAttribute("aria-selected", String(active));
        });
        document.getElementById("knowledge-radar-list").hidden = mode !== "open";
        document.getElementById("knowledge-radar-researched-list").hidden = mode !== "researched";
        document.getElementById("knowledge-radar-title").textContent = mode === "open" ? "Kandidat auswählen" : "Pflegethema auswählen";
        document.getElementById("knowledge-radar-detail-body").innerHTML = `<p>${mode === "open" ? "Wähle links eine Wissenslücke aus." : "Wähle ein bereits recherchiertes Thema zur kontrollierten Weiterpflege aus."}</p>`;
        const researchButton = document.getElementById("knowledge-radar-research");
        researchButton.disabled = true;
        researchButton.textContent = mode === "open" ? "Kontrollierte Recherche starten" : "Pflegethema auswählen";
        document.getElementById("knowledge-radar-selection-status").textContent = mode === "open"
            ? "Maximal fünf Quellen; Ergebnisse bleiben außerhalb der Vault."
            : "Nach der Auswahl kann der vorhandene Wissensstand kontrolliert aktualisiert werden.";
        document.getElementById("knowledge-radar-result").hidden = true;
        document.getElementById("knowledge-radar-ai-result").hidden = true;
        this.updateAIControls();
        this.render(document.getElementById("knowledge-radar-filter")?.value || "");
    }

    updateAIControls() {
        const enabled = document.getElementById("knowledge-radar-ai-enabled").checked;
        const button = document.getElementById("knowledge-radar-ai-evaluate");
        button.disabled = !enabled || !this.selected || (this.mode === "researched" && !this.selected.candidate_available);
    }

    updateCandidateMenu(items) {
        const menu = document.getElementById("knowledge-radar-candidate-select");
        const label = document.getElementById("knowledge-radar-candidate-menu-label");
        if (!menu) return;
        const researched = this.mode === "researched";
        label.textContent = researched ? "Pflegethema auswählen" : "Kandidaten auswählen";
        const selectedValue = researched ? this.selected?.key : this.selected?.id;
        menu.innerHTML = `<option value="">${researched ? "Bitte Pflegethema wählen …" : "Bitte Kandidaten wählen …"}</option>` + items.map(item => {
            const value = researched ? item.key : item.id;
            const prefix = researched ? `${item.source_count} Quellen` : `${item.score}/100`;
            return `<option value="${this.escape(value)}"${selectedValue === value ? " selected" : ""}>${this.escape(prefix)} · ${this.escape(item.title)}</option>`;
        }).join("");
        menu.disabled = items.length === 0;
    }

    selectFromMenu(value) {
        if (!value) return;
        if (this.mode === "researched") this.selectResearched(this.researched.find(item => item.key === value));
        else this.select(this.data?.candidates.find(item => item.id === value));
        const attribute = this.mode === "researched" ? "data-researched-key" : "data-radar-id";
        const button = document.querySelector(`[${attribute}="${CSS.escape(value)}"]`);
        button?.scrollIntoView({block: "nearest", behavior: "smooth"});
    }

    async loadGrowth() {
        const status = document.getElementById("knowledge-growth-status");
        try {
            const response = await fetch("/api/knowledge-radar/growth", {cache: "no-store"});
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "Wachstumsstatus nicht verfügbar.");
            document.getElementById("knowledge-growth-schedule").value = data.config.schedule;
            document.getElementById("knowledge-growth-budget").value = data.config.topic_budget;
            const next = data.config.next_run ? new Date(data.config.next_run).toLocaleString("de-DE") : "nur manuell";
            const last = data.config.last_run ? new Date(data.config.last_run).toLocaleString("de-DE") : "noch keiner";
            status.textContent = `Letzter Lauf: ${last} · Nächster Lauf: ${next} · ${data.history_count} protokolliert`;
            this.renderGrowthHistory(data.history);
        } catch (error) {
            status.textContent = `Statusfehler: ${error.message}`;
            status.dataset.state = "error";
        }
    }

    renderGrowthHistory(history = []) {
        const list = document.getElementById("knowledge-growth-history-list");
        if (!history.length) {
            list.innerHTML = "<p>Noch keine Radar-Läufe protokolliert.</p>";
            return;
        }
        list.innerHTML = history.map(run => `
            <article>
                <strong>${this.escape(new Date(run.started_at).toLocaleString("de-DE"))} · ${run.trigger === "scheduled" ? "Automatisch" : "Manuell"}</strong>
                <small>${run.processed_topics}/${run.eligible_topics} Themen · ${run.skipped_unchanged} unverändert übersprungen · ${run.changed_sources} Quellenänderungen</small>
                <ul>${run.entries.map(entry => `<li data-state="${entry.status}">${this.escape(entry.title)} – ${entry.status === "completed" ? entry.sources.length + " Quellen" : this.escape(entry.error || "Fehler")}</li>`).join("")}</ul>
            </article>`).join("");
    }

    async saveGrowthConfig() {
        const button = document.getElementById("knowledge-growth-save");
        const status = document.getElementById("knowledge-growth-status");
        button.disabled = true;
        try {
            const response = await fetch("/api/knowledge-radar/growth/config", {
                method: "PUT", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    schedule: document.getElementById("knowledge-growth-schedule").value,
                    topic_budget: Number(document.getElementById("knowledge-growth-budget").value),
                }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "Einstellungen konnten nicht gespeichert werden.");
            status.textContent = "✓ Zeitplan und Themenbudget wurden lokal gespeichert.";
            await this.loadGrowth();
        } catch (error) {
            status.textContent = `Speichern fehlgeschlagen: ${error.message}`;
        } finally {
            button.disabled = false;
        }
    }

    async runGrowthRadar() {
        const button = document.getElementById("knowledge-growth-run");
        const status = document.getElementById("knowledge-growth-status");
        button.disabled = true;
        this.updatePhase(4, "Stufe 4 · Fällige Pflegethemen werden geprüft");
        status.textContent = "Fällige oder geänderte Themen werden innerhalb des Budgets geprüft …";
        try {
            const response = await fetch("/api/knowledge-radar/growth/run", {method: "POST"});
            const run = await response.json();
            if (!response.ok) throw new Error(run.detail || "Radar-Lauf fehlgeschlagen.");
            status.textContent = `✓ ${run.processed_topics} Themen geprüft, ${run.skipped_unchanged} unveränderte übersprungen, ${run.changed_sources} Quellenänderungen erkannt.`;
            this.updatePhase(4, `Stufe 4 · Pflege abgeschlossen · ${run.processed_topics} Thema/Themen geprüft`);
            await this.loadGrowth();
        } catch (error) {
            status.textContent = `Radar-Lauf fehlgeschlagen: ${error.message}`;
            this.updatePhase(4, "Stufe 4 · Pflegelauf fehlgeschlagen");
        } finally {
            button.disabled = false;
        }
    }

    render(query = "") {
        if (!this.data) return;
        const needle = query.trim().toLocaleLowerCase("de");
        if (this.mode === "researched") {
            const records = this.researched.filter(item => !needle || [item.title, item.topic, item.source, item.last_query].join(" ").toLocaleLowerCase("de").includes(needle));
            this.updateCandidateMenu(records);
            const target = document.getElementById("knowledge-radar-researched-list");
            target.innerHTML = records.length ? records.map(item => `
                <button class="knowledge-radar-item${this.selected?.key === item.key ? " active" : ""}" type="button" data-researched-key="${this.escape(item.key)}">
                    <span class="knowledge-radar-score">${item.source_count}</span>
                    <span><strong>${this.escape(item.title)}</strong><small>${this.escape(item.topic)} · zuletzt ${this.escape(new Date(item.last_researched_at).toLocaleString("de-DE"))}</small>
                    <span class="knowledge-radar-maintenance-meta"><em data-due="${item.due}">${item.due ? "Prüfung fällig" : "Aktuell"}</em><em>${item.research_count} Recherche(n)</em>${item.proposal?.target ? `<em>${this.escape(item.proposal.target)}</em>` : ""}</span></span>
                </button>`).join("") : '<p class="knowledge-radar-empty">Noch keine Themen recherchiert.</p>';
            target.querySelectorAll("[data-researched-key]").forEach(button => {
                button.onclick = () => this.selectResearched(this.researched.find(item => item.key === button.dataset.researchedKey));
            });
            return;
        }
        const candidates = this.data.candidates.filter(item =>
            !needle || [item.title, item.topic, item.source_title, item.reason].join(" ").toLocaleLowerCase("de").includes(needle)
        );
        this.updateCandidateMenu(candidates);
        if (!candidates.length) {
            this.list.innerHTML = '<p class="knowledge-radar-empty">Keine passenden Kandidaten gefunden.</p>';
            return;
        }
        this.list.innerHTML = candidates.map(item => `
            <button class="knowledge-radar-item${this.selected?.id === item.id ? " active" : ""}" type="button" data-radar-id="${this.escape(item.id)}">
                <span class="knowledge-radar-score">${item.score}</span>
                <span><strong>${this.escape(item.title)}</strong><small>${this.escape(item.topic)} · ${item.type === "offene_frage" ? "Offene Frage" : "Ausbaufähiges Thema"}</small></span>
            </button>`).join("");
        this.list.querySelectorAll("[data-radar-id]").forEach(button => {
            button.onclick = () => this.select(this.data.candidates.find(item => item.id === button.dataset.radarId));
        });
    }

    selectResearched(item) {
        if (!item) return;
        this.selected = item;
        this.setDetailOpen?.(true);
        document.getElementById("knowledge-radar-title").textContent = item.title;
        const next = item.next_check_at ? new Date(item.next_check_at).toLocaleString("de-DE") : "nicht geplant";
        document.getElementById("knowledge-radar-detail-body").innerHTML = `<dl>
            <div><dt>Status</dt><dd>${item.due ? "Erneute Prüfung fällig" : "Aktuell gepflegt"}</dd></div>
            <div><dt>Letzte Recherche</dt><dd>${this.escape(new Date(item.last_researched_at).toLocaleString("de-DE"))}</dd></div>
            <div><dt>Nächste Prüfung</dt><dd>${this.escape(next)}</dd></div>
            <div><dt>Rechercheläufe</dt><dd>${item.research_count}</dd></div>
            <div><dt>Quellen</dt><dd>${item.source_count}</dd></div>
            <div><dt>Vault-Ausgangsseite</dt><dd><code>${this.escape(item.source)}</code></dd></div>
            <div><dt>Einpflegeziel</dt><dd><code>${this.escape(item.proposal?.target || "noch keines")}</code></dd></div>
        </dl>`;
        const button = document.getElementById("knowledge-radar-research");
        button.disabled = !item.candidate_available;
        button.textContent = "Thema weiterrecherchieren";
        document.getElementById("knowledge-radar-selection-status").textContent = item.candidate_available ? "Bestehenden Wissensstand kontrolliert aktualisieren." : "Die ursprüngliche Wissenslücke ist derzeit nicht mehr im Radar offen.";
        document.getElementById("knowledge-radar-result").hidden = true;
        document.getElementById("knowledge-radar-ai-result").hidden = true;
        this.updateAIControls();
        this.render(document.getElementById("knowledge-radar-filter")?.value || "");
    }

    select(item) {
        if (!item) return;
        this.selected = item;
        this.setDetailOpen?.(true);
        document.getElementById("knowledge-radar-title").textContent = item.title;
        document.getElementById("knowledge-radar-detail-body").innerHTML = `
            <dl>
                <div><dt>Relevanz</dt><dd>${item.score} / 100</dd></div>
                <div><dt>Bereich</dt><dd>${this.escape(item.topic)}</dd></div>
                <div><dt>Quellseite</dt><dd><code>${this.escape(item.source)}</code></dd></div>
                <div><dt>Erkennung</dt><dd>${this.escape(item.reason)}</dd></div>
            </dl>`;
        document.getElementById("knowledge-radar-research").disabled = false;
        document.getElementById("knowledge-radar-research").textContent = "Kontrollierte Recherche starten";
        document.getElementById("knowledge-radar-selection-status").textContent = "Bereit: maximal fünf Quellen, keine Vault-Änderung.";
        document.getElementById("knowledge-radar-result").hidden = true;
        document.getElementById("knowledge-radar-ai-result").hidden = true;
        this.updateAIControls();
        this.render(document.getElementById("knowledge-radar-filter")?.value || "");
    }

    async startResearch() {
        if (!this.selected) return;
        const button = document.getElementById("knowledge-radar-research");
        const status = document.getElementById("knowledge-radar-selection-status");
        const resultBox = document.getElementById("knowledge-radar-result");
        button.disabled = true;
        this.updatePhase(2, "Stufe 2 · Kontrollierte Webrecherche läuft");
        status.textContent = "Suche, Quellenprüfung und lokaler Vault-Vergleich laufen …";
        resultBox.hidden = true;
        try {
            const response = await fetch("/api/knowledge-radar/research", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({candidate_id: this.selected.candidate_id || this.selected.id}),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "Recherche fehlgeschlagen.");
            const labels = {bereits_vorhanden: "Bereits vorhanden", verwandt: "Verwandt", neu: "Neu"};
            resultBox.innerHTML = `
                <div class="knowledge-radar-result-heading"><h3>Recherchebericht</h3><span>${this.escape(data.sources.length)} Quellen</span></div>
                <p class="knowledge-radar-workspace-path">Temporär: <code>${this.escape(data.workspace)}</code></p>
                <div class="knowledge-radar-sources">${data.sources.map(source => `
                    <article>
                        <a href="${this.escape(source.url)}" target="_blank" rel="noopener noreferrer">${this.escape(source.title)}</a>
                        <small>${this.escape(source.source_type)} · ${this.escape(source.date)}</small>
                        <p>${this.escape(source.statement)}</p>
                        <span data-classification="${source.vault_comparison.classification}">${labels[source.vault_comparison.classification] || source.vault_comparison.classification}</span>
                        <small>Ähnlichste Vault-Seite: ${this.escape(source.vault_comparison.vault_match || "keine")}</small>
                    </article>`).join("")}</div>
                <details><summary>Vollständigen temporären Bericht anzeigen</summary><pre>${this.escape(data.report)}</pre></details>
                <button id="knowledge-radar-create-proposal" type="button">Einpflegevorschlag erzeugen</button>
                <section id="knowledge-radar-proposal" class="knowledge-radar-proposal" hidden></section>`;
            resultBox.hidden = false;
            this.research = data;
            document.getElementById("knowledge-radar-create-proposal").onclick = () => this.createProposal();
            status.textContent = `✓ Recherche ${data.run_id} abgeschlossen. Nichts wurde in die Vault geschrieben.`;
            this.updatePhase(2, `Stufe 2 · ${data.sources.length} Quellen geprüft`);
            await this.loadResearched();
            if (document.getElementById("knowledge-radar-ai-enabled").checked) await this.evaluateAI(true);
        } catch (error) {
            status.textContent = `Recherche fehlgeschlagen: ${error.message}`;
            this.updatePhase(2, "Stufe 2 · Recherche fehlgeschlagen");
        } finally {
            button.disabled = false;
        }
    }

    async evaluateAI(useResearch = false) {
        if (!this.selected) return;
        const button = document.getElementById("knowledge-radar-ai-evaluate");
        const box = document.getElementById("knowledge-radar-ai-result");
        button.disabled = true;
        const evaluationPhase = useResearch ? 2 : 1;
        this.updatePhase(evaluationPhase, `Stufe ${evaluationPhase} · Lokale KI bewertet ${useResearch ? "Quellen und Vault-Abgleich" : "Kandidat und Dubletten"}`, true);
        box.hidden = false;
        box.innerHTML = "<p>Lokale KI bewertet den regelbasierten Befund in einer getrennten Sitzung …</p>";
        try {
            const candidateId = this.selected.candidate_id || this.selected.id;
            const payload = useResearch && this.research ? {run_id: this.research.run_id} : {candidate_id: candidateId};
            const response = await fetch("/api/knowledge-radar/ai-evaluate", {
                method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "KI-Bewertung fehlgeschlagen.");
            const list = items => items.length ? `<ul>${items.map(item => `<li>${this.escape(item)}</li>`).join("")}</ul>` : "<p>Keine erkannt.</p>";
            const vaultHits = data.vault_retrieval?.hits || [];
            const vaultSources = vaultHits.length
                ? `<h4>Gelesene Vault-Quellen via QMD</h4><ul>${vaultHits.map(hit =>
                    `<li><code>${this.escape(hit.path)}</code> · ${Math.round(Number(hit.score || 0) * 100)} %</li>`
                ).join("")}</ul>`
                : `<h4>Vault-Retrieval</h4><p>${this.escape(data.vault_retrieval?.error || "Keine passenden Vault-Quellen gefunden.")}</p>`;
            box.innerHTML = `<h3>KI-gestützte Radarbewertung</h3>
                <dl><div><dt>Modell</dt><dd>${this.escape(data.model)}</dd></div><div><dt>Phase</dt><dd>${this.escape(data.phase)}</dd></div>
                <div><dt>Regelbasiert</dt><dd>${data.rule_score} / 100</dd></div><div><dt>KI-Vertrauen</dt><dd>${data.confidence} / 100</dd></div>
                <div><dt>Empfehlung</dt><dd>${this.escape(data.recommendation)}</dd></div><div><dt>Zielvorschlag</dt><dd>${this.escape(data.proposed_target || "keiner")}</dd></div></dl>
                <h4>Bewertung</h4><p>${this.escape(data.summary)}</p><p>${this.escape(data.reasoning)}</p>
                <h4>Ähnliche Wissenslücken / Dubletten</h4>${list(data.duplicates)}
                <h4>Mögliche Konflikte</h4>${list(data.conflicts)}
                <h4>Vorgeschlagene Wikilinks</h4>${list(data.wikilinks)}
                ${vaultSources}
                <p class="advisory">Nur KI-Vorschlag – keine Vault-Änderung und keine Loop-Fortschaltung.</p>`;
            this.updatePhase(evaluationPhase, `Stufe ${evaluationPhase} · KI-Bewertung abgeschlossen · ${data.confidence} % Vertrauen`);
        } catch (error) {
            box.innerHTML = `<p>KI-Bewertung fehlgeschlagen: ${this.escape(error.message)}</p>`;
            this.updatePhase(evaluationPhase, `Stufe ${evaluationPhase} · KI-Bewertung fehlgeschlagen`);
        } finally {
            this.updateAIControls();
        }
    }

    async createProposal() {
        if (!this.research) return;
        const button = document.getElementById("knowledge-radar-create-proposal");
        const box = document.getElementById("knowledge-radar-proposal");
        const status = document.getElementById("knowledge-radar-selection-status");
        button.disabled = true;
        this.updatePhase(3, "Stufe 3 · Deterministischer Einpflegevorschlag wird erstellt");
        status.textContent = "Ziel, Markdown-Diff, Wikilinks und Konflikte werden vorbereitet …";
        try {
            const response = await fetch("/api/knowledge-radar/proposal", {
                method: "POST", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({run_id: this.research.run_id}),
            });
            const proposal = await response.json();
            if (!response.ok) throw new Error(proposal.detail || "Vorschlag konnte nicht erstellt werden.");
            this.proposal = proposal;
            const operation = proposal.operation === "neue_seite" ? "Neue Seite" : "Bestehende Seite ergänzen";
            box.innerHTML = `
                <div class="knowledge-radar-proposal-summary">
                    <div><span>Aktion</span><strong>${operation}</strong></div>
                    <div><span>Ziel</span><strong><code>${this.escape(proposal.target)}</code></strong></div>
                    <div><span>Vertrauen</span><strong>${proposal.confidence} %</strong></div>
                    <div><span>Konflikte</span><strong>${proposal.conflicts.length}</strong></div>
                </div>
                <h4>Vorgeschlagene Wikilinks</h4>
                <p>${proposal.wikilinks.length ? proposal.wikilinks.map(link => `<code>[[${this.escape(link)}]]</code>`).join(" ") : "Keine zusätzlichen Links."}</p>
                <h4>Mögliche Konflikte</h4>
                ${proposal.conflicts.length ? `<ul>${proposal.conflicts.map(item => `<li>${this.escape(item.message)}</li>`).join("")}</ul>` : "<p>Keine regelbasierten Konflikthinweise erkannt.</p>"}
                <details open><summary>Konkreter Markdown-Diff</summary><pre class="knowledge-radar-diff">${this.escape(proposal.markdown_diff)}</pre></details>
                <button id="knowledge-radar-handoff" type="button">An Station 06 übergeben</button>`;
            box.hidden = false;
            document.getElementById("knowledge-radar-handoff").onclick = () => this.handoff();
            status.textContent = "✓ Temporärer Einpflegevorschlag erstellt. Die Vault ist unverändert.";
            this.updatePhase(3, `Stufe 3 · Vorschlag bereit · ${proposal.confidence} % regelbasiertes Vertrauen`);
        } catch (error) {
            status.textContent = `Vorschlag fehlgeschlagen: ${error.message}`;
            this.updatePhase(3, "Stufe 3 · Vorschlag fehlgeschlagen");
            button.disabled = false;
        }
    }

    async handoff() {
        if (!this.proposal || !this.research) return;
        const button = document.getElementById("knowledge-radar-handoff");
        const status = document.getElementById("knowledge-radar-selection-status");
        button.disabled = true;
        this.updatePhase(5, "Übergabe · Station 06 wird vorbereitet");
        status.textContent = "Vorschlag wird kontrolliert an Station 06 übergeben …";
        try {
            const response = await fetch("/api/knowledge-radar/handoff", {
                method: "POST", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({run_id: this.research.run_id, proposal_id: this.proposal.proposal_id}),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || "Übergabe fehlgeschlagen.");
            status.textContent = "✓ Station 06 wartet jetzt ausdrücklich auf Freigabe. Noch keine Vault-Änderung.";
            this.updatePhase(5, "Station 06 · Wartet auf menschliche Freigabe");
            setTimeout(() => document.querySelector('.menu[data-view="dashboard"]')?.click(), 700);
        } catch (error) {
            status.textContent = `Übergabe fehlgeschlagen: ${error.message}`;
            this.updatePhase(3, "Stufe 3 · Übergabe an Station 06 fehlgeschlagen");
            button.disabled = false;
        }
    }
}

window.KnowledgeRadar = KnowledgeRadar;
