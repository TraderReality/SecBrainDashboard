let loopRenderer = null;
let selectedStation = null;
let vaultGraphExplorer = null;
let knowledgeRadar = null;
window.SecBrainCurrentStation = 1;
let setStationDetailsOpen = function(){};
let isMarkdownEditorDirty = function(){ return false; };


const stationDescriptions = {
    1: "Neue Informationen werden erfasst.",
    2: "Erfasste Inhalte werden analysiert.",
    3: "Ergebnisse und Quellen werden verglichen.",
    4: "Informationen werden strukturiert eingeordnet.",
    5: "Ein umsetzbarer Vorschlag wird erstellt.",
    6: "Der Vorschlag wartet auf eine Freigabe.",
    7: "Freigegebene Ergebnisse werden übernommen.",
    8: "Wissen wird für die Suche indexiert.",
    9: "Zusammenhänge werden verlinkt.",
    10: "Qualität und Regeln werden geprüft.",
    11: "Der Ablauf wird protokolliert.",
    12: "Ergebnisse werden berichtet."
};


const stationRuleReferences = {
    1: {
        section: "§ 1.1 · Phase 1 – Dokument analysieren",
        rule: "Vollständigen Inhalt lesen, Dokumenttyp bestimmen und Haupt- sowie Unterthemen erkennen."
    },
    2: {
        section: "§ 1.1 · Phase 1 – Dokument analysieren",
        rule: "Den Informationswert bewerten und die für die Aufgabe relevanten Inhalte herausarbeiten."
    },
    3: {
        section: "§ 1.1 · Phase 2 – Vault-Abgleich",
        rule: "Bestehende Themen, ähnliche Dokumente, Dubletten und mögliche Widersprüche im Vault prüfen."
    },
    4: {
        section: "§ 1.1 · Phase 3 – Einordnung",
        rule: "Das Dokument als bestehendes Wissen, Ergänzung, neues Wissen, Konflikt oder nicht zuordenbar einordnen."
    },
    5: {
        section: "§ 1.1 · Phase 4 – Vorschlag",
        rule: "Keine Vault-Änderung vornehmen; stattdessen einen vollständigen Integrationsvorschlag unter _Vorschlaege anlegen."
    },
    6: {
        section: "§ 1.1 · Phase 5 – Freigabe",
        rule: "Dauerhafte Änderungen erst nach ausdrücklicher Freigabe übernehmen; bis dahin bleibt ausschließlich der Vorschlag bestehen."
    },
    7: {
        section: "§ 2 · Station 03 – Freigaben umsetzen",
        rule: "Nur Aufgaben mit dem Feld freigegeben ausführen, den Vorschlag am Zielort übernehmen und die Aufgabe abschließen."
    },
    8: {
        section: "§ 2 · Station 09 – Index aktualisieren",
        rule: "Indexer ausführen; bei einem Fehler die Station überspringen, den Fund protokollieren und den Lauf fortsetzen."
    },
    9: {
        section: "§ 2 · Station 07 – Verlinken",
        rule: "Jede Wissensseite benötigt mindestens einen ausgehenden und einen eingehenden Wikilink."
    },
    10: {
        section: "§ 2 · Station 10 – Qualitätsprüfung",
        rule: "Die Prüfliste aus Abschnitt 8 vollständig abarbeiten."
    },
    11: {
        section: "§ 2 · Station 11 – Protokollieren und fortschreiben",
        rule: "Lauf, Quellen, geänderte Seiten und Funde in _Log.md festhalten; anschließend den Arbeitsvorrat fortschreiben."
    },
    12: {
        section: "§ 2 · Station 12 – Bericht und Commit",
        rule: "Für den Menschen berichten, was getan wurde, was auf Freigabe wartet und was entschieden werden muss."
    }
};


function updateStationDetails(station){

    selectedStation = station;

    const stationId = Number(station.id);
    window.SecBrainCurrentStation = stationId;
    const status = station.status || "READY";
    const ruleReference = stationRuleReferences[stationId];

    document.getElementById("station-number").innerText =
        stationId.toString().padStart(2,"0");
    document.getElementById("station-title").innerText = station.name;
    document.getElementById("station-status").innerText =
        station.active ? "AKTIV" : status;
    document.getElementById("station-description").innerText =
        stationDescriptions[stationId] || "Station im KI-Pflege-Loop.";
    document.getElementById("station-rule-file").innerText = "AGENTS.md";
    document.getElementById("station-rule-section").innerText =
        ruleReference?.section || "§ 2 · Der Pflege-Loop";
    document.getElementById("station-rule-text").innerText =
        ruleReference?.rule ||
        "Die Stationen geben den Takt vor. Jeder Schritt ist einzeln abbrechbar.";
    document.getElementById("station-next-step").innerText =
        stationId === 12
            ? "01 Erfassen"
            : (stationId + 1).toString().padStart(2,"0") + " " +
                (loopRenderer?.data.find(item => Number(item.id) === stationId + 1)?.name || "");

    loadGuardianRule(stationId);

}


async function loadGuardianRule(stationId){

    const section = document.getElementById("guardian-rule-section");
    const text = document.getElementById("guardian-rule-text");

    section.innerText = "Station " + stationId.toString().padStart(2,"0") + " · Wird geladen …";
    text.innerText = "Die zusätzliche Regel wird für diese Station geladen.";

    try {
        const response = await fetch(
            "/api/stations/" + stationId + "/guardian-rule",
            { cache: "no-store" }
        );
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Wächterregel nicht verfügbar.");
        }

        document.getElementById("guardian-rule-file").innerText = data.file;
        section.innerText = "Globale KI-Regeln + Station " + stationId.toString().padStart(2,"0");
        text.innerText = data.station;

    } catch (error) {
        section.innerText = "Nicht verfügbar";
        text.innerText = "Wächterregel konnte nicht geladen werden: " + error.message;
    }

}


function escapeHtml(value){
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}


const stationMdAnchors = {
    1: { type: "heading", heading: "Phase 1 – Dokument analysieren" },
    2: { type: "heading", heading: "Phase 1 – Dokument analysieren" },
    3: { type: "heading", heading: "Phase 2 – Vault-Abgleich" },
    4: { type: "heading", heading: "Phase 3 – Einordnung" },
    5: { type: "heading", heading: "Phase 4 – Vorschlag" },
    6: { type: "heading", heading: "Phase 5 – Freigabe" },
    7: { type: "table-row", number: "03" },
    8: { type: "table-row", number: "09" },
    9: { type: "table-row", number: "07" },
    10: { type: "table-row", number: "10" },
    11: { type: "table-row", number: "11" },
    12: { type: "table-row", number: "12" }
};


function extractMarkdownHeadingSection(content, headingText){

    const lines = content.replace(/\r\n/g, "\n").split("\n");
    let capturing = false;
    const collected = [];

    for (let i = 0; i < lines.length; i++){
        const match = lines[i].match(/^#{2,6}\s+(.*)$/);
        if (match) {
            if (capturing) break;
            if (match[1].trim() === headingText) capturing = true;
            continue;
        }
        if (capturing) collected.push(lines[i]);
    }

    return collected.join("\n").trim();

}


function extractMarkdownTableRow(content, rowNumber){

    const lines = content.replace(/\r\n/g, "\n").split("\n");

    for (const line of lines){
        if (!line.trim().startsWith("|")) continue;
        const cells = line.split("|").map(cell => cell.trim());
        if (cells[1] === rowNumber) return cells[3] || "";
    }

    return "";

}


function stripMarkdownInline(text){

    return text
        .replace(/`+([^`]+?)`+/g, "$1")
        .replace(/\*\*([^*]+)\*\*/g, "$1")
        .replace(/\*([^*]+)\*/g, "$1")
        .replace(/^\s*-\s+/gm, "• ")
        .replace(/\n{3,}/g, "\n\n")
        .trim();

}


function extractStationRuleText(stationId, agentsContent){

    const anchor = stationMdAnchors[stationId];
    if (!agentsContent || !anchor) return "";

    const raw = anchor.type === "heading"
        ? extractMarkdownHeadingSection(agentsContent, anchor.heading)
        : extractMarkdownTableRow(agentsContent, anchor.number);

    return raw ? stripMarkdownInline(raw) : "";

}


let regelwerkOverviewLoaded = false;

async function loadRegelwerkOverview(){

    if (regelwerkOverviewLoaded) return;

    const container = document.getElementById("regelwerk-explorer-view");
    if (!container) return;

    try {
        const [statusResponse, agentsResponse] = await Promise.all([
            fetch("/api/status"),
            fetch("/api/vault/agents-md", { cache: "no-store" })
        ]);
        const data = await statusResponse.json();

        if (!statusResponse.ok) {
            throw new Error("Regelwerk-Übersicht nicht verfügbar.");
        }

        let agentsContent = "";
        if (agentsResponse.ok) {
            const agentsData = await agentsResponse.json();
            agentsContent = agentsData.content || "";
        }

        renderRegelwerkOverview(data.loop.stations || [], agentsContent);
        regelwerkOverviewLoaded = true;

    } catch (error) {
        console.error("SECBrain Regelwerk Explorer Error:", error);
        container.innerHTML =
            '<p class="regelwerk-overview-error">Regelwerk-Übersicht konnte nicht geladen werden.</p>';
    }

}


function renderRegelwerkOverview(stations, agentsContent){

    const container = document.getElementById("regelwerk-explorer-view");
    if (!container) return;

    const rows = stations
        .slice()
        .sort((a, b) => Number(a.id) - Number(b.id))
        .map(function(station){
            const stationId = Number(station.id);
            const ref = stationRuleReferences[stationId];
            const section = ref?.section || "—";
            const ruleText =
                extractStationRuleText(stationId, agentsContent) ||
                ref?.rule ||
                "Für diese Station liegt keine Regel-Referenz vor.";

            return (
                '<div class="regelwerk-row" data-station="' + stationId + '" tabindex="0" role="button" ' +
                'aria-expanded="false" aria-controls="regelwerk-detail-' + stationId + '">' +
                '<span class="regelwerk-row-number">' + stationId.toString().padStart(2,"0") + '</span>' +
                '<span class="regelwerk-row-name">' + escapeHtml(station.name) + '</span>' +
                '<span class="regelwerk-row-source">AGENTS.md</span>' +
                '<span class="regelwerk-row-rule">' +
                escapeHtml(section) +
                '<span class="regelwerk-row-toggle" aria-hidden="true">▾</span>' +
                '</span>' +
                '</div>' +
                '<div class="regelwerk-row-detail" id="regelwerk-detail-' + stationId + '" hidden>' +
                '<p>' + escapeHtml(ruleText) + '</p>' +
                '</div>'
            );
        })
        .join("");

    container.innerHTML =
        '<div class="regelwerk-overview">' +
        '<div class="panel regelwerk-list">' +
        '<div class="regelwerk-row regelwerk-list-header">' +
        '<span></span>' +
        '<span>Station</span>' +
        '<span>Quelle</span>' +
        '<span>Regel-Referenz</span>' +
        '</div>' +
        rows +
        '</div>' +
        '</div>';

    container.querySelectorAll(".regelwerk-row[data-station]").forEach(function(row){
        row.addEventListener("click", function(){ toggleRegelwerkRow(row); });
        row.addEventListener("keydown", function(event){
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                toggleRegelwerkRow(row);
            }
        });
    });

}


function toggleRegelwerkRow(row){

    if (!row) return;

    const stationId = row.dataset.station;
    const detail = document.getElementById("regelwerk-detail-" + stationId);
    if (!detail) return;

    const expanded = row.classList.toggle("expanded");
    row.setAttribute("aria-expanded", String(expanded));
    detail.hidden = !expanded;

}


function updateRuntimeActivity(loop){

    const orchestration = loop.orchestration || {};
    const workflowRunning = Boolean(orchestration.active);
    scannerApprovalPending = typeof orchestration.state === "string"
        ? Boolean(orchestration.approval_required) || orchestration.state === "applying" : null;
    if (scannerLastStatus) renderScannerStatus({...scannerLastStatus, app_write_pending: loop.app_write_pending});

    loopRenderer?.setAutonomousRunning(workflowRunning);

    const workflowState = document.getElementById("workflow-state");
    const workflowStart = document.getElementById("workflow-start");
    const workflowStop = document.getElementById("workflow-stop");
    const workflowApprove = document.getElementById("workflow-approve");
    const workflowReject = document.getElementById("workflow-reject");
    const workflowStatus = document.getElementById("workflow-status");

    if (workflowState) {
        const workflowLabel = {
            running: "LÄUFT",
            stopping: "STOPPT",
            completed: "FERTIG",
            applying: "ÜBERNIMMT",
            awaiting_approval: "FREIGABE",
            rejected: "ABGELEHNT",
            failed: "FEHLER",
            stopped: "ANGEHALTEN",
            idle: "RUHT"
        }[orchestration.state] || "RUHT";

        workflowState.innerText = workflowLabel;
        workflowState.dataset.state = workflowRunning
            ? "working"
            : (orchestration.state === "completed" ? "ready" : "offline");
        const approvalRequired = Boolean(orchestration.approval_required);
        workflowStart.disabled = workflowRunning || approvalRequired;
        workflowStop.disabled = !workflowRunning;
        workflowApprove.hidden = !approvalRequired;
        workflowReject.hidden = !approvalRequired;
        workflowStatus.innerText = orchestration.error
            ? "Angehalten: " + orchestration.error
            : approvalRequired
                ? "Station 06 wartet. Prüfe den Vorschlag in der Ausgabe und gib ihn ausdrücklich frei oder lehne ihn ab."
            : workflowRunning
                ? "Watcher verarbeitet den fixierten Inbox-Snapshot. Ein Stopp greift nach der aktuellen Station."
                : orchestration.state === "completed"
                    ? "Der freigegebene 12-Stationen-Lauf wurde kontrolliert abgeschlossen."
                    : "Station 01–05 analysieren die echte Inbox; Station 06 wartet auf deine Freigabe.";
    }

    const output = document.getElementById("runtime-output");
    if (output) {
        const results = (orchestration.results || []).slice().reverse();
        const signature = results.map(result => result.station_id + ":" + result.output.length).join("|");

        if (output.dataset.signature !== signature) {
            output.dataset.signature = signature;
            output.textContent = results.length
                ? results.map(function(result){
                    return "Station " + String(result.station_id).padStart(2, "0") +
                        " · " + result.station + "\n" + result.output;
                }).join("\n\n────────────────────\n\n")
                : "Noch keine Stationsausgabe vorhanden.";
            output.scrollTop = 0;
        }
    }

}



async function loadShell(){


    try {


        const response = await fetch(
            "/api/status"
        );


        const data = await response.json();



        document.getElementById(
            "vault-path"
        ).innerText =
            data.vault.path;



        if(!loopRenderer){


            loopRenderer =
                new LoopRenderer(
                    document.getElementById(
                        "loop-svg-container"
                    )
                );


        }



        const stations = data.loop.stations;

        loopRenderer.setData(stations);
        updateRuntimeActivity(data.loop);

        if(!selectedStation){
            updateStationDetails(
                stations.find(station => station.active) || stations[0]
            );
        }



    }


    catch(error){


        scannerWorkflowUnavailable();
        console.error(
            "SECBrain Dashboard Error:",
            error
        );


    }


}


async function refreshRuntimeActivity(){

    try {
        const response = await fetch(
            "/api/watcher-loop/status",
            { cache: "no-store" }
        );
        const loop = await response.json();

        if (!response.ok) {
            throw new Error("Watcher-Lauf nicht verfügbar.");
        }

        updateRuntimeActivity(loop);

    } catch(error) {
        scannerWorkflowUnavailable();
        console.error("SECBrain Watcher Runtime Error:", error);
    }

}




function bindWorkflowControls(){

    const start = document.getElementById("workflow-start");
    const stop = document.getElementById("workflow-stop");
    const approve = document.getElementById("workflow-approve");
    const reject = document.getElementById("workflow-reject");
    const goal = document.getElementById("workflow-goal");
    const author = document.getElementById("workflow-author");
    const copyOutput = document.getElementById("runtime-output-copy");

    copyOutput.onclick = async function(){
        const output = document.getElementById("runtime-output");
        try {
            await navigator.clipboard.writeText(output.textContent);
            copyOutput.innerText = "Kopiert";
            setTimeout(function(){ copyOutput.innerText = "Kopieren"; }, 1400);
        } catch (error) {
            output.focus();
            window.getSelection().selectAllChildren(output);
        }
    };

    start.onclick = async function(){
        const original = start.innerText;
        start.disabled = true;
        start.innerText = "Lauf wird gestartet …";

        try {
            const response = await fetch("/api/watcher-loop/autonomous/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ goal: goal.value, author: author.value })
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.detail || "Autonomer Lauf konnte nicht gestartet werden.");
            }
            await loadShell();
            await refreshRuntimeActivity();
        } catch (error) {
            alert("Autonomer Lauf: " + error.message);
        } finally {
            start.innerText = original;
        }
    };

    stop.onclick = async function(){
        stop.disabled = true;
        try {
            await fetch("/api/watcher-loop/autonomous/stop", { method: "POST" });
            await refreshRuntimeActivity();
        } finally {
            stop.disabled = false;
        }
    };

    async function decide(action){
        approve.disabled = true;
        reject.disabled = true;
        try {
            const response = await fetch("/api/watcher-loop/autonomous/" + action, { method: "POST" });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "Entscheidung fehlgeschlagen.");
            await refreshRuntimeActivity();
        } catch (error) {
            alert("Watcher-Loop: " + error.message);
        } finally {
            approve.disabled = false;
            reject.disabled = false;
        }
    }

    approve.onclick = function(){ decide("approve"); };
    reject.onclick = function(){ decide("reject"); };

}


function validationLine(label, value){
    const row = document.createElement("div");
    row.className = "validation-line";
    const name = document.createElement("strong");
    name.textContent = label;
    const content = document.createElement("span");
    content.textContent = value;
    row.append(name, content);
    return row;
}

function renderValidationEvidence(data){
    const container = document.getElementById("validation-evidence");
    container.replaceChildren();
    if (!data.available || !data.evidence) {
        container.textContent = data.reason || "Kein prüfbarer Lauf vorhanden.";
        return;
    }
    const evidence = data.evidence;
    const kind = evidence.kind === "knowledge_radar" ? "Wissensradar" : "Inbox";
    const date = new Date(evidence.completed_at);
    container.append(
        validationLine("Lauf", String(evidence.run_id || "–")),
        validationLine("Art", kind),
        validationLine("Abschluss", Number.isNaN(date.getTime()) ? "Unbekannt" : date.toLocaleString("de-DE")),
        validationLine("Indexer beim Lauf", evidence.indexer?.ok ? "Erfolgreich" : "Nicht bestätigt"),
        validationLine("Vault-Commit", evidence.commit?.ok
            ? String(evidence.commit.revision || "Kennung fehlt")
            : String(evidence.commit?.reason || "Kein Commit dokumentiert"))
    );
    const heading = document.createElement("h3");
    heading.textContent = "Geprüfte Dateien";
    const files = document.createElement("ul");
    files.className = "validation-files";
    Object.keys(evidence.files || {}).forEach(path => {
        const item = document.createElement("li");
        item.textContent = path;
        files.append(item);
    });
    container.append(heading, files);
}

function renderValidationCurrent(data){
    const container = document.getElementById("validation-current");
    container.replaceChildren();
    if (!data.available || data.pending) {
        container.textContent = data.pending
            ? "Ein neuerer Lauf ist noch ungeklärt. Der frühere Nachweis gilt nicht als aktueller Erfolg."
            : (data.reason || "Kein prüfbarer Lauf vorhanden.");
        return;
    }
    const summary = document.createElement("p");
    summary.className = "validation-summary";
    summary.dataset.status = String(data.overall || "nicht prüfbar");
    const date = new Date(data.checked_at);
    summary.textContent = `Gesamtstatus: ${data.overall || "nicht prüfbar"} · ${Number.isNaN(date.getTime()) ? "Zeit unbekannt" : date.toLocaleString("de-DE")}`;
    const list = document.createElement("ul");
    list.className = "validation-checks";
    (data.checks || []).forEach(check => {
        const item = document.createElement("li");
        item.dataset.status = String(check.status || "nicht prüfbar");
        const title = document.createElement("strong");
        title.textContent = `${check.path || check.id}: ${check.status || "nicht prüfbar"}`;
        const detail = document.createElement("span");
        detail.textContent = String(check.detail || "");
        item.append(title, detail);
        list.append(item);
    });
    container.append(summary, list);
}

async function loadValidation(){
    const status = document.getElementById("validation-status");
    const button = document.getElementById("validation-recheck");
    document.getElementById("validation-current").textContent = "Noch keine erneute Prüfung gestartet.";
    status.textContent = "Nachweis wird geladen …";
    button.disabled = true;
    try {
        const response = await fetch("/api/validation/last");
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Nachweis konnte nicht geladen werden.");
        renderValidationEvidence(data);
        status.textContent = data.pending
            ? "Ein neuerer Lauf ist ungeklärt. Frühere Ergebnisse gelten nicht als aktuell."
            : (data.available ? "Letzter abgeschlossener Lauf" : (data.reason || "Kein prüfbarer Lauf vorhanden."));
        button.disabled = !data.available || data.pending;
    } catch (error) {
        status.textContent = error.message;
        document.getElementById("validation-evidence").textContent = "Nachweis nicht verfügbar.";
    }
}

// Scanner: bounded polling, and the latest attempt always takes precedence.
let scannerApprovalPending = null;
let scannerLastStatus = null;
let scannerTimer = null;
let scannerGeneration = 0;
const SCANNER_POLL_LIMIT = 120;

function stopScannerPolling(){
    scannerGeneration += 1;
    clearTimeout(scannerTimer);
    scannerTimer = null;
}

function scannerWorkflowUnavailable(){
    scannerApprovalPending = null;
    if (scannerLastStatus) renderScannerStatus(scannerLastStatus);
}

function scannerMessage(text, tone = "warning"){
    const status = document.getElementById("scanner-status");
    status.textContent = text;
    status.dataset.tone = tone;
    if (tone !== "success") scannerLastStatus = null;
}

function scannerTime(value){
    if (!value) return "Noch nicht vorhanden";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Zeitpunkt nicht verfügbar" : date.toLocaleString("de-DE");
}

function renderScannerStatus(data){
    const attempt = data.last_attempt;
    const baseline = data.last_complete;
    document.getElementById("scanner-baseline").textContent = baseline
        ? scannerTime(baseline.finished_at) + " · " + baseline.scan_id
        : "Noch keine vollständige Vergleichsbasis. Der erste vollständige Scan inventarisiert den Bestand.";
    const attemptState = attempt?.state === "complete" ? "vollständig geprüft"
        : attempt?.state === "running" ? "Scan läuft" : "nicht vollständig geprüft";
    document.getElementById("scanner-attempt").textContent = attempt
        ? scannerTime(attempt.started_at) + " · " + attemptState + (attempt.message && attempt.message !== attemptState ? " · " + attempt.message : "")
        : "Noch kein Versuch gestartet.";
    const phases = {idle: "Bereit", inventory: "Dateien erfassen", rules: "Regeln bewerten",
        verify: "Dateistand erneut prüfen", publish: "Bericht veröffentlichen", done: "Beendet"};
    const progress = data.progress || {};
    document.getElementById("scanner-progress").textContent =
        (phases[progress.phase] || "Status nicht verfügbar") + " · " +
        (progress.completed || 0) + " / " + (progress.total || 0) + " Dateien";
    document.getElementById("scanner-start").disabled = data.state === "running";
    if (data.state === "running") {
        scannerMessage("Scan läuft · noch nicht vollständig geprüft.");
    } else if (data.state === "incomplete") {
        scannerMessage("nicht vollständig geprüft · App-Übernahmen bleiben gesperrt." + ((data.message || attempt?.message) && (data.message || attempt?.message) !== "nicht vollständig geprüft" ? " " + (data.message || attempt.message) : ""));
    } else if (data.state === "complete" && data.overall === "verletzt") {
        scannerMessage("Vollständig geprüft · Regeln verletzt. App-Übernahmen bleiben gesperrt.", "danger");
    } else if (data.state === "complete" && (data.app_write_pending === true || scannerApprovalPending === true)) {
        scannerMessage("Scan abgeschlossen · App-Übernahme ausstehend. Der Änderungssatz wird vor der Übernahme erneut geprüft.");
    } else if (data.state === "complete" && (data.app_write_pending !== false || scannerApprovalPending === null)) {
        scannerMessage("Scan abgeschlossen · Übernahmestatus nicht verfügbar. Aktuelle App-Freigabe noch ungeklärt.");
    } else if (data.state === "complete" && data.overall === "erfüllt"
               && (!attempt || attempt.state === "complete")) {
        scannerMessage("Vollständig geprüft · Regeln erfüllt zum angezeigten Prüfzeitpunkt.", "success");
    } else if (data.state === "complete") {
        scannerMessage("Prüfung beendet · Regelstatus unklar. App-Übernahmen bleiben gesperrt.");
    } else {
        scannerMessage("Noch nicht geprüft · einen Scan starten, um die Vergleichsbasis anzulegen.");
    }
    scannerLastStatus = data;
}

function scannerRows(id, rows, findings = false){
    const list = document.getElementById(id);
    list.replaceChildren();
    if (!rows.length) {
        const empty = document.createElement("li");
        empty.textContent = "Keine Einträge im angezeigten Bericht.";
        list.append(empty);
    }
    rows.forEach(row => {
        const item = document.createElement("li");
        const path = document.createElement("strong");
        path.textContent = row.path || ".";
        item.append(path);
        if (findings) {
            const reference = document.createElement("span");
            reference.textContent = row.rule_id
                ? row.rule_id + " · " + (row.source?.path || "AGENTS.md") + ":" + (row.source?.line || "?")
                : "Technische Prüfung · " + (row.status || "unklar");
            const reason = document.createElement("p");
            reason.textContent = row.reason || "Kein Grund verfügbar.";
            item.append(reference, reason);
        }
        list.append(item);
    });
}

function clearScannerReport(){
    const link = document.getElementById("scanner-report");
    link.hidden = true;
    link.removeAttribute("href");
    document.getElementById("scanner-report-summary").textContent = "Noch kein Bericht für den aktuellen Versuch geladen.";
    ["new", "changed", "removed", "technical", "violations", "unclear"].forEach(name => {
        document.getElementById("scanner-" + name).textContent = "Noch kein Bericht geladen.";
    });
}

function renderScannerReport(report){
    const link = document.getElementById("scanner-report");
    link.href = "/api/scanner/reports/" + encodeURIComponent(report.scan_id);
    link.hidden = false;
    link.textContent = "JSON-Bericht öffnen · " + report.scan_id;
    document.getElementById("scanner-report-summary").textContent =
        "Bericht vom " + scannerTime(report.finished_at) + " · " +
        (report.complete ? "vollständiger Scan" : "nicht vollständig geprüft") + " · " +
        (report.files || []).length + " Dateien · Modell: " + (report.model || "nicht verfügbar") +
        (report.complete && !(report.changes || []).length ? " · Keine Dateiänderungen im Bericht." : "");
    const changes = report.changes || [];
    scannerRows("scanner-new", changes.filter(row => row.status === "neu"));
    scannerRows("scanner-changed", changes.filter(row => row.status === "geändert"));
    scannerRows("scanner-removed", changes.filter(row => row.status === "entfernt"));
    scannerRows("scanner-technical", report.technical_findings || [], true);
    scannerRows("scanner-violations", (report.findings || []).filter(row => row.status === "verletzt"), true);
    scannerRows("scanner-unclear", (report.findings || []).filter(row => row.status === "unklar"), true);
}

async function scannerRequest(url, method = "GET"){
    const response = await fetch(url, {method, cache: "no-store", signal: AbortSignal.timeout(15000)});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Scanner-Anfrage fehlgeschlagen.");
    return data;
}

async function pollScanner(generation, remaining){
    if (generation !== scannerGeneration || document.getElementById("scanner-view").hidden) return;
    try {
        const data = await scannerRequest("/api/scanner/status");
        if (generation !== scannerGeneration || document.getElementById("scanner-view").hidden) return;
        renderScannerStatus(data);
        if (data.state === "running") {
            clearScannerReport();
            if (remaining > 1) scannerTimer = setTimeout(() => pollScanner(generation, remaining - 1), 2000);
            else scannerMessage("Scan läuft · automatische Aktualisierung pausiert. Status über „Aktualisieren“ erneut laden.");
            return;
        }
        clearScannerReport();
        const reportId = data.last_attempt?.scan_id || data.last_complete?.scan_id;
        if (reportId) {
            try {
                const report = await scannerRequest("/api/scanner/reports/" + encodeURIComponent(reportId));
                if (generation === scannerGeneration && !document.getElementById("scanner-view").hidden) renderScannerReport(report);
            } catch (error) {
                if (generation === scannerGeneration) {
                    scannerMessage("Bericht nicht verfügbar · nicht vollständig geprüft. " + error.message);
                    document.getElementById("scanner-report-summary").textContent = "Bericht konnte nicht geladen werden.";
                }
            }
        }
    } catch (error) {
        if (generation !== scannerGeneration) return;
        scannerMessage("Scanner nicht verfügbar · nicht vollständig geprüft. " + error.message);
        clearScannerReport();
        document.getElementById("scanner-start").disabled = false;
    }
}

async function loadScanner(){
    stopScannerPolling();
    scannerMessage("Scannerstatus wird geladen · noch nicht vollständig geprüft.");
    clearScannerReport();
    await pollScanner(scannerGeneration, SCANNER_POLL_LIMIT);
}

async function startScanner(){
    stopScannerPolling();
    const generation = scannerGeneration;
    document.getElementById("scanner-start").disabled = true;
    scannerMessage("Scan wird gestartet · noch nicht vollständig geprüft.");
    clearScannerReport();
    try {
        await scannerRequest("/api/scanner/scan", "POST");
        if (generation === scannerGeneration) await pollScanner(generation, SCANNER_POLL_LIMIT);
    } catch (error) {
        if (generation !== scannerGeneration) return;
        scannerMessage("Scan konnte nicht gestartet werden · nicht vollständig geprüft. " + error.message);
        document.getElementById("scanner-start").disabled = false;
    }
}


function bindViewNavigation(){

    const dashboardView = document.getElementById("dashboard-view");
    const explorerView = document.getElementById("vault-explorer-view");
    const regelwerkView = document.getElementById("regelwerk-explorer-view");
    const knowledgeRadarView = document.getElementById("knowledge-radar-view");
    const validationView = document.getElementById("validation-view");
    const scannerView = document.getElementById("scanner-view");
    const menus = document.querySelectorAll(".menu[data-view]");
    const search = document.getElementById("graph-search");
    const refresh = document.getElementById("graph-refresh");
    const reset = document.getElementById("graph-reset");

    const showView = async function(view){
        const explorerActive = view === "vault-explorer";
        dashboardView.hidden = view !== "dashboard";
        explorerView.hidden = !explorerActive;
        if (regelwerkView) regelwerkView.hidden = view !== "regelwerk-explorer";
        if (knowledgeRadarView) knowledgeRadarView.hidden = view !== "knowledge-radar";
        if (validationView) validationView.hidden = view !== "validation";
        if (scannerView) scannerView.hidden = view !== "scanner";
        if (view !== "scanner") stopScannerPolling();
        menus.forEach(menu => menu.classList.toggle("active", menu.dataset.view === view));

        if (explorerActive) {
            if (!vaultGraphExplorer) {
                vaultGraphExplorer = new VaultGraphExplorer(
                    document.getElementById("vault-graph-canvas")
                );
            }
            await vaultGraphExplorer.load();
        }

        if (view === "regelwerk-explorer") {
            await loadRegelwerkOverview();
        }
        if (view === "knowledge-radar") {
            if (!knowledgeRadar) knowledgeRadar = new KnowledgeRadar(knowledgeRadarView);
            await knowledgeRadar.load();
        }
        if (view === "validation") await loadValidation();
        if (view === "scanner") await loadScanner();
    };

    menus.forEach(menu => {
        menu.tabIndex = 0;
        menu.addEventListener("click", () => showView(menu.dataset.view));
        menu.addEventListener("keydown", event => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                showView(menu.dataset.view);
            }
        });
    });

    search.addEventListener("input", function(){
        vaultGraphExplorer?.applyFilter(search.value);
    });
    refresh.addEventListener("click", async function(){
        await vaultGraphExplorer?.load();
        if (search.value) vaultGraphExplorer?.applyFilter(search.value);
    });
    reset.addEventListener("click", function(){
        vaultGraphExplorer?.resetView();
    });

    const validationButton = document.getElementById("validation-recheck");
    validationButton.addEventListener("click", async function(){
        validationButton.disabled = true;
        const status = document.getElementById("validation-status");
        status.textContent = "Aktueller Zustand wird lesend geprüft …";
        try {
            const response = await fetch("/api/validation/last/recheck", { method: "POST" });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "Erneute Prüfung fehlgeschlagen.");
            renderValidationEvidence(data);
            renderValidationCurrent(data);
            status.textContent = data.pending ? "Ein neuerer Lauf ist ungeklärt." : "Erneute Prüfung abgeschlossen.";
        } catch (error) {
            status.textContent = error.message;
        } finally {
            validationButton.disabled = false;
        }
    });

}


document.addEventListener(
    "station-selected",
    function(event){


        const station =
            event.detail;



        updateStationDetails(station);
        setStationDetailsOpen(true);


    }
);


function bindSidebarToggle(){

    const toggle = document.getElementById("sidebar-toggle");
    const toggleIcon = document.getElementById("sidebar-toggle-icon");
    const sidebar = document.getElementById("app-sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");

    if (!toggle || !sidebar || !backdrop) return;

    const setOpen = function(open){

        sidebar.classList.toggle("open", open);
        backdrop.classList.toggle("visible", open);
        toggle.setAttribute("aria-expanded", String(open));
        if (toggleIcon) toggleIcon.textContent = open ? "◂" : "▸";

    };

    const isOpen = function(){
        return sidebar.classList.contains("open");
    };

    toggle.addEventListener("click", function(){
        setOpen(!isOpen());
    });

    backdrop.addEventListener("click", function(){
        setOpen(false);
    });

    document.addEventListener("keydown", function(event){

        if (event.key === "Escape" && isOpen()) {
            setOpen(false);
            toggle.focus();
        }

    });

    sidebar.querySelectorAll(".menu[data-view]").forEach(function(menu){
        menu.addEventListener("click", function(){
            setOpen(false);
        });
    });

}


function bindDetailsPanelToggle(){

    const toggle = document.getElementById("details-toggle");
    const toggleIcon = document.getElementById("details-toggle-icon");
    const panel = document.getElementById("station-details-panel");
    const backdrop = document.getElementById("details-backdrop");

    if (!toggle || !panel || !backdrop) return;

    const setOpen = function(open){

        panel.classList.toggle("open", open);
        backdrop.classList.toggle("visible", open);
        toggle.setAttribute("aria-expanded", String(open));
        if (toggleIcon) toggleIcon.textContent = open ? "▸" : "◂";

    };

    const isOpen = function(){
        return panel.classList.contains("open");
    };

    toggle.addEventListener("click", function(){
        setOpen(!isOpen());
    });

    backdrop.addEventListener("click", function(){
        setOpen(false);
    });

    document.addEventListener("keydown", function(event){

        if (event.key === "Escape" && isOpen()) {
            setOpen(false);
            toggle.focus();
        }

    });

    setStationDetailsOpen = setOpen;

}


function bindGraphDetailsPanelToggle(){

    const toggle = document.getElementById("graph-details-toggle");
    const toggleIcon = document.getElementById("graph-details-toggle-icon");
    const panel = document.getElementById("graph-details-panel");
    const backdrop = document.getElementById("graph-details-backdrop");
    const title = document.getElementById("graph-node-title");

    if (!toggle || !panel || !backdrop) return;

    const setOpen = function(open){

        panel.classList.toggle("open", open);
        backdrop.classList.toggle("visible", open);
        toggle.setAttribute("aria-expanded", String(open));
        if (toggleIcon) toggleIcon.textContent = open ? "▸" : "◂";

    };

    const isOpen = function(){
        return panel.classList.contains("open");
    };

    toggle.addEventListener("click", function(){
        setOpen(!isOpen());
    });

    backdrop.addEventListener("click", function(){
        setOpen(false);
    });

    document.addEventListener("keydown", function(event){

        if (event.key === "Escape" && isOpen()) {
            setOpen(false);
            toggle.focus();
        }

    });

    // vault-graph-explorer.js schreibt bei Knotenauswahl direkt in #graph-node-title —
    // das Popup öffnet sich automatisch, sobald sich der Titel ändert (wie beim
    // station-selected-Ereignis auf dem Dashboard), ohne diese Datei anzufassen.
    if (title) {
        const observer = new MutationObserver(function(){
            setOpen(true);
        });
        observer.observe(title, { childList: true, characterData: true, subtree: true });
    }

}


function renderMarkdownPreview(source){

    const escapeHtml = function(text){
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    };

    const inline = function(text){
        text = escapeHtml(text);
        text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
        text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
        text = text.replace(/\*([^*]+)\*/g, "<em>$1</em>");
        text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, "<a href=\"$2\" target=\"_blank\" rel=\"noopener\">$1</a>");
        return text;
    };

    const lines = source.replace(/\r\n/g, "\n").split("\n");
    let html = "";
    let inCodeBlock = false;
    let listOpen = false;

    const closeList = function(){
        if (listOpen) { html += "</ul>"; listOpen = false; }
    };

    lines.forEach(function(line){

        if (/^```/.test(line)) {
            if (inCodeBlock) { html += "</pre>"; inCodeBlock = false; }
            else { closeList(); html += "<pre>"; inCodeBlock = true; }
            return;
        }

        if (inCodeBlock) { html += escapeHtml(line) + "\n"; return; }

        const heading = line.match(/^(#{1,6})\s+(.*)$/);
        if (heading) {
            closeList();
            const level = heading[1].length;
            html += "<h" + level + ">" + inline(heading[2]) + "</h" + level + ">";
            return;
        }

        if (/^\s*[-*]\s+/.test(line)) {
            if (!listOpen) { html += "<ul>"; listOpen = true; }
            html += "<li>" + inline(line.replace(/^\s*[-*]\s+/, "")) + "</li>";
            return;
        }

        closeList();
        if (line.trim() === "") { return; }
        html += "<p>" + inline(line) + "</p>";

    });

    closeList();
    if (inCodeBlock) html += "</pre>";

    return html;

}


function bindMarkdownEditorModal(){

    const badge = document.getElementById("markdown-rule-badge");
    const modal = document.getElementById("markdown-editor-modal");
    const backdrop = document.getElementById("markdown-editor-backdrop");
    const closeBtn = document.getElementById("markdown-editor-close");
    const cancelBtn = document.getElementById("markdown-editor-cancel");
    const saveBtn = document.getElementById("markdown-editor-save");
    const textarea = document.getElementById("markdown-editor-textarea");
    const preview = document.getElementById("markdown-editor-preview");
    const status = document.getElementById("markdown-editor-status");
    const subtitle = document.getElementById("markdown-editor-subtitle");
    const confirmBar = document.getElementById("markdown-editor-confirm");
    const confirmCancel = document.getElementById("markdown-editor-confirm-cancel");
    const confirmDiscard = document.getElementById("markdown-editor-confirm-discard");
    const confirmSave = document.getElementById("markdown-editor-confirm-save");
    const body = document.getElementById("markdown-editor-body");
    const paneLeft = document.getElementById("markdown-editor-pane-left");
    const resizer = document.getElementById("markdown-editor-resizer");

    if (!badge || !modal) return;

    let lastFocused = null;
    let dirty = false;

    if (body && paneLeft && resizer) {

        const SPLIT_STORAGE_KEY = "secbrain-md-editor-split";
        let dragging = false;

        const applySplit = function(percent){
            percent = Math.min(80, Math.max(20, percent));
            paneLeft.style.flexBasis = percent + "%";
        };

        const saveSplit = function(percent){
            try {
                localStorage.setItem(SPLIT_STORAGE_KEY, String(percent));
            } catch (error) { /* Speicher nicht verfügbar, kein Problem */ }
        };

        const loadSplit = function(){
            try {
                const stored = localStorage.getItem(SPLIT_STORAGE_KEY);
                if (stored) applySplit(parseFloat(stored));
            } catch (error) { /* Speicher nicht verfügbar, kein Problem */ }
        };

        const currentPercent = function(){
            const rect = body.getBoundingClientRect();
            return (paneLeft.getBoundingClientRect().width / rect.width) * 100;
        };

        loadSplit();

        resizer.addEventListener("pointerdown", function(event){
            dragging = true;
            resizer.classList.add("dragging");
            resizer.setPointerCapture(event.pointerId);
            document.body.style.userSelect = "none";
        });

        resizer.addEventListener("pointermove", function(event){
            if (!dragging) return;
            const rect = body.getBoundingClientRect();
            applySplit(((event.clientX - rect.left) / rect.width) * 100);
        });

        const endDrag = function(event){
            if (!dragging) return;
            dragging = false;
            resizer.classList.remove("dragging");
            try { resizer.releasePointerCapture(event.pointerId); } catch (error) { /* bereits freigegeben */ }
            document.body.style.userSelect = "";
            saveSplit(currentPercent());
        };

        resizer.addEventListener("pointerup", endDrag);
        resizer.addEventListener("pointercancel", endDrag);

        resizer.addEventListener("keydown", function(event){
            if (event.key === "ArrowLeft") {
                event.preventDefault();
                const next = currentPercent() - 2;
                applySplit(next);
                saveSplit(next);
            } else if (event.key === "ArrowRight") {
                event.preventDefault();
                const next = currentPercent() + 2;
                applySplit(next);
                saveSplit(next);
            }
        });

    }

    const setStatus = function(text){
        status.innerText = text;
    };

    const updatePreview = function(){
        preview.innerHTML = renderMarkdownPreview(textarea.value);
    };

    const setDirty = function(value){
        dirty = value;
        if (value) setStatus("Nicht gespeicherte Änderungen.");
    };

    isMarkdownEditorDirty = function(){
        return dirty;
    };

    const showConfirm = function(show){
        confirmBar.classList.toggle("visible", show);
    };

    const setOpen = function(open){
        modal.classList.toggle("open", open);
        modal.setAttribute("aria-hidden", String(!open));
        if (!open) showConfirm(false);
        if (open) {
            lastFocused = document.activeElement;
            textarea.focus();
        } else if (lastFocused) {
            lastFocused.focus();
        }
    };

    const load = async function(){

        textarea.value = "";
        textarea.disabled = true;
        saveBtn.disabled = true;
        setStatus("Wird geladen …");
        preview.innerHTML = "";
        showConfirm(false);

        try {
            const response = await fetch("/api/vault/agents-md", { cache: "no-store" });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "AGENTS.md konnte nicht geladen werden.");
            }

            textarea.value = data.content;
            subtitle.innerText = "Regelquelle · " + data.path;
            updatePreview();
            setStatus("Geladen.");
            setDirty(false);

        } catch (error) {
            setStatus("Fehler: " + error.message);
        } finally {
            textarea.disabled = false;
            saveBtn.disabled = false;
        }

    };

    const openModal = function(){
        setOpen(true);
        load();
    };

    badge.addEventListener("click", openModal);
    badge.addEventListener("keydown", function(event){
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openModal();
        }
    });

    textarea.addEventListener("input", function(){
        updatePreview();
        setDirty(true);
    });

    const save = async function(){

        const original = saveBtn.innerText;
        saveBtn.disabled = true;
        saveBtn.innerText = "Speichert …";
        setStatus("Speichert …");

        try {
            const response = await fetch("/api/vault/agents-md", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content: textarea.value })
            });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "AGENTS.md konnte nicht gespeichert werden.");
            }

            setStatus("Gespeichert.");
            setDirty(false);
            return true;

        } catch (error) {
            setStatus("Fehler beim Speichern: " + error.message);
            return false;

        } finally {
            saveBtn.disabled = false;
            saveBtn.innerText = original;
        }

    };

    const requestClose = function(){
        if (dirty) {
            showConfirm(true);
            return;
        }
        setOpen(false);
    };

    closeBtn.addEventListener("click", requestClose);
    cancelBtn.addEventListener("click", requestClose);
    backdrop.addEventListener("click", requestClose);

    document.addEventListener("keydown", function(event){
        if (event.key === "Escape" && modal.classList.contains("open")) {
            if (confirmBar.classList.contains("visible")) {
                showConfirm(false);
            } else {
                requestClose();
            }
        }
    });

    confirmCancel.addEventListener("click", function(){
        showConfirm(false);
    });

    confirmDiscard.addEventListener("click", function(){
        setDirty(false);
        showConfirm(false);
        setOpen(false);
    });

    confirmSave.addEventListener("click", async function(){
        const original = confirmSave.innerText;
        confirmSave.disabled = true;
        confirmSave.innerText = "Speichert …";

        const success = await save();

        confirmSave.disabled = false;
        confirmSave.innerText = original;

        if (success) {
            showConfirm(false);
            setOpen(false);
        }
    });

    saveBtn.addEventListener("click", save);

}


bindWorkflowControls();
document.getElementById("scanner-start").addEventListener("click", startScanner);
document.getElementById("scanner-refresh").addEventListener("click", loadScanner);
bindViewNavigation();
bindSidebarToggle();
bindDetailsPanelToggle();
bindGraphDetailsPanelToggle();
bindMarkdownEditorModal();
loadShell();


window.addEventListener("beforeunload", function(event){

    if (isMarkdownEditorDirty()) {
        event.preventDefault();
        event.returnValue = "";
    }

});



setInterval(
    loadShell,
    5000
);


setInterval(
    refreshRuntimeActivity,
    1000
);
