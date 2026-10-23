window.OllamaSettings = {

    modal: null,

    status: null,

    models: [],

    config: {},

    monitorTimer: null,

    activeTab: "connection",

    chatMessages: [],


    async open() {

        let existing =
            document.getElementById(
                "ollama-settings-modal"
            );


        if (existing) {

            existing.style.display = "flex";

            await this.refresh();

            return;

        }


        const modal =
            document.createElement("div");


        modal.id =
            "ollama-settings-modal";


        modal.innerHTML = `

        <div class="ollama-panel">

            <div class="ollama-header">

                <h2>
                    🧠 Ollama Control Center
                </h2>

                <button
                    id="ollama-close"
                    type="button"
                >
                    ✕
                </button>

            </div>


            <div class="ollama-tabs">

                <button
                    type="button"
                    data-tab="connection"
                >
                    🔌 Verbindung
                </button>

                <button
                    type="button"
                    data-tab="models"
                >
                    🤖 Modelle
                </button>

                <button
                    type="button"
                    data-tab="runtime"
                >
                    ⚙ Runtime
                </button>

                <button
                    type="button"
                    data-tab="sync"
                >
                    🧠 SECBrain Sync
                </button>

            </div>


            <div id="ollama-content">

                Lade Ollama Status...

            </div>

        </div>

        `;


        document.body.appendChild(
            modal
        );


        this.modal = modal;


        document
            .getElementById("ollama-close")
            .onclick = () => {

                modal.style.display =
                    "none";

            };


        modal
            .querySelectorAll(
                ".ollama-tabs button"
            )
            .forEach(button => {

                button.onclick = () => {

                    this.showTab(
                        button.dataset.tab
                    );

                };

            });


        await this.refresh();

        this.renderChatDock();

        this.showTab(
            "connection"
        );


        this.startMonitor();

    },


    async refresh() {

        try {

            const response =
                await fetch(
                    "/api/ollama/status",
                    {
                        cache: "no-store"
                    }
                );


            if (!response.ok) {

                throw new Error(
                    "Backend HTTP " +
                    response.status
                );

            }


            const data =
                await response.json();


            this.status =
                data;


            this.models =
                data.models || [];


            this.config =
                data.config || {};


            console.log(
                "SECBrain Ollama Sync",
                data
            );


            return data;


        } catch (error) {

            console.error(
                "Ollama Sync Fehler",
                error
            );


            this.status = {

                online: false,

                status: "offline",

                models: [],

                model_count: 0,

                error:
                    error.message

            };


            this.models = [];

        }

    },


    async saveConfig() {

        const url =
            document
                .getElementById(
                    "ollama-url"
                )
                .value
                .trim();


        const model =
            document
                .getElementById(
                    "ollama-model"
                )
                .value;


        const interval =
            Number(
                document
                    .getElementById(
                        "ollama-interval"
                    )
                    .value
            );


        const temperature =
            Number(
                document
                    .getElementById(
                        "ollama-temperature"
                    )
                    .value
            );


        const context =
            Number(
                document
                    .getElementById(
                        "ollama-context"
                    )
                    .value
            );


        const numPredict =
            Number(
                document
                    .getElementById(
                        "ollama-num-predict"
                    )
                    .value
            );


        const keepAlive =
            document
                .getElementById(
                    "ollama-keep-alive"
                )
                .value;


        const payload = {

            url,

            model,

            health_interval:
                interval,

            temperature,

            context,

            num_predict:
                numPredict,

            keep_alive:
                keepAlive,

            auto_sync: true

        };


        try {

            const response =
                await fetch(
                    "/api/ollama/config",
                    {

                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json"
                        },

                        body:
                            JSON.stringify(
                                payload
                            )

                    }
                );


            const result =
                await response.json();


            if (!response.ok) {

                throw new Error(
                    result.error ||
                    "Konfiguration fehlgeschlagen"
                );

            }


            await this.refresh();


            alert(
                "Ollama Konfiguration gespeichert."
            );


        } catch (error) {

            alert(
                "Fehler: " +
                error.message
            );

        }

    },


    async testConnection() {

        const result =
            await this.refresh();


        if (
            result &&
            result.online
        ) {

            alert(
                "Ollama ist ONLINE.\n\n" +
                "Modelle: " +
                result.model_count +
                "\n" +
                "Version: " +
                (
                    result.version ||
                    "unbekannt"
                )
            );

        } else {

            alert(
                "Ollama ist OFFLINE.\n\n" +
                (
                    result?.error ||
                    "Keine Verbindung."
                )
            );

        }

    },


    escapeHtml(value) {

        const node = document.createElement("div");
        node.textContent = String(value || "");
        return node.innerHTML;

    },


    async selectModel(model) {

        const response = await fetch(
            "/api/ollama/config",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ model })
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.error || "Modell konnte nicht ausgewählt werden."
            );
        }

        await this.refresh();

    },


    async setModelRole(role, model) {

        const response = await fetch(
            "/api/ollama/config",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ [role]: model })
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.detail || result.error || "Modellrolle konnte nicht gespeichert werden."
            );
        }

        await this.refresh();

    },


    async sendChat() {

        const input = document.getElementById("ollama-chat-input");
        const send = document.getElementById("ollama-chat-send");
        const content = input?.value.trim();

        if (!content || !this.config.model || !send) {
            return;
        }

        const diagramCommand = /^\/excalidraw(?:\s|$)/.test(content);
        const diagramPrompt = diagramCommand ? content.slice("/excalidraw".length).trim() : "";
        if (diagramCommand && !diagramPrompt) {
            this.chatMessages.push({ role: "assistant", content: "Bitte beschreibe das Diagramm nach /excalidraw.", diagram: true });
            this.renderChatDock();
            return;
        }

        this.chatMessages.push({
            role: "user",
            content,
            diagram: diagramCommand
        });

        input.value = "";
        send.disabled = true;
        send.textContent = diagramCommand ? "Diagramm wird im Work-Ordner gespeichert …" : "Antwort wird erstellt …";

        try {
            if (diagramCommand) {
                const response = await fetch("/api/excalidraw/generate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt: diagramPrompt, model: this.config.model })
                });
                if (!response.ok) {
                    throw new Error("Das Diagramm konnte nicht erstellt werden. Bitte prüfe Modell und Work-Freigabe.");
                }
                const result = await response.json();
                this.chatMessages.push({
                    role: "assistant",
                    content: `Diagramm gespeichert: ${result.relative_path} (${result.element_count} Elemente, Modell: ${result.model}).`,
                    diagram: true
                });
                return;
            }
            const response = await fetch(
                "/api/ollama/chat",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        model: this.config.model,
                        messages: this.chatMessages.filter(message => !message.diagram)
                    })
                }
            );

            const result = await response.json();

            if (!response.ok) {
                throw new Error(
                    result.detail || "Ollama hat nicht geantwortet."
                );
            }

            this.chatMessages.push({
                ...result.message,
                vault_retrieval: result.vault_retrieval || null
            });

        } catch (error) {
            this.chatMessages.push({
                role: "assistant",
                content: "⚠️ " + error.message,
                diagram: diagramCommand
            });
        } finally {
            this.renderChatDock();
        }

    },


    showTab(tab) {

        const box =
            document.getElementById(
                "ollama-content"
            );


        if (!box)
            return;


        this.activeTab = tab;


        if (tab === "connection") {

            box.innerHTML = `

                <h3>
                    🔌 Ollama Verbindung
                </h3>

                <label>
                    Ollama URL
                </label>

                <input
                    id="ollama-url"
                    value="${
                        this.config.url ||
                        "http://127.0.0.1:11434"
                    }"
                >

                <p>
                    Status:
                    <strong>
                        ${
                            this.status?.online
                            ? "ONLINE"
                            : "OFFLINE"
                        }
                    </strong>
                </p>

                <p>
                    Modelle:
                    ${
                        this.status?.model_count ??
                        0
                    }
                </p>

                <p>
                    Version:
                    ${
                        this.status?.version ||
                        "unbekannt"
                    }
                </p>

                <button
                    id="ollama-test"
                    type="button"
                >
                    Verbindung testen
                </button>

                <button
                    id="ollama-save-connection"
                    type="button"
                >
                    URL speichern
                </button>

            `;


            document
                .getElementById(
                    "ollama-test"
                )
                .onclick = () => {

                    this.testConnection();

                };


            document
                .getElementById(
                    "ollama-save-connection"
                )
                .onclick = async () => {

                    const url =
                        document
                            .getElementById(
                                "ollama-url"
                            )
                            .value;


                    await fetch(
                        "/api/ollama/config",
                        {

                            method: "POST",

                            headers: {
                                "Content-Type":
                                    "application/json"
                            },

                            body:
                                JSON.stringify({
                                    url
                                })

                        }
                    );


                    await this.refresh();

                    this.showTab(
                        "connection"
                    );

                };

        }


        if (tab === "models") {

            const models =
                this.models || [];


            let html = "";


            if (!models.length) {

                html = `

                    <div class="ollama-empty">

                        ⚠️ Keine Ollama Modelle installiert.

                        <br><br>

                        Ollama antwortet korrekt,
                        aber /api/tags liefert derzeit
                        0 Modelle.

                    </div>

                `;

            } else {

                html =
                    models
                        .map(model => `

                            <div class="ollama-model">

                                <div class="ollama-model-info">
                                    <strong>${this.escapeHtml(model.name)}</strong>
                                    <small>
                                    ${
                                        model.details?.parameter_size ||
                                        ""
                                    }

                                    ${
                                        model.details?.quantization_level
                                        ? " · " +
                                          model.details.quantization_level
                                        : ""
                                    }
                                    </small>
                                </div>

                                <label class="ollama-model-role" title="Standardmodell für die SecBrain-Watcher-App">
                                    <input
                                        class="ollama-default-model-input"
                                        type="checkbox"
                                        data-model="${this.escapeHtml(model.name)}"
                                        ${this.config.default_model === model.name ? "checked" : ""}
                                    >
                                    <span class="sr-only">Als Standardmodell für SecBrain Watcher verwenden</span>
                                </label>

                                <button
                                    class="ollama-select-model"
                                    type="button"
                                    data-model="${this.escapeHtml(model.name)}"
                                    ${this.config.model === model.name ? "disabled" : ""}
                                >
                                    ${this.config.model === model.name ? "Aktiv" : "Auswählen"}
                                </button>

                            </div>

                        `)
                        .join("");

            }


            box.innerHTML = `

                <h3>
                    🤖 Ollama Modelle
                </h3>

                <p>
                    Gefundene Modelle:
                    <strong>
                        ${models.length}
                    </strong>
                </p>

                <p class="ollama-model-help">
                    Das Watcher-Standardmodell wird dauerhaft gespeichert. „Aktiv“ gilt nur für die aktuelle Sitzung.
                </p>

                <div class="ollama-model-list">
                    <div class="ollama-model-columns" aria-hidden="true">
                        <span>Modell</span>
                        <span>Watcher-Standard</span>
                        <span>Sitzung</span>
                    </div>
                    ${html}
                </div>

                <button
                    id="ollama-refresh-models"
                    type="button"
                >
                    Modelle aktualisieren
                </button>

            `;


            document
                .getElementById(
                    "ollama-refresh-models"
                )
                .onclick = async () => {

                    await this.refresh();

                    this.showTab(
                        "models"
                    );

                };


            box.querySelectorAll(".ollama-select-model").forEach(button => {

                button.onclick = async () => {

                    try {
                        await this.selectModel(button.dataset.model);
                        this.showTab("models");
                    } catch (error) {
                        alert("Fehler: " + error.message);
                    }

                };

            });


            box.querySelectorAll(".ollama-default-model-input").forEach(checkbox => {

                checkbox.onchange = async () => {

                    try {
                        await this.setModelRole(
                            "default_model",
                            checkbox.checked ? checkbox.dataset.model : ""
                        );
                        this.renderChatDock();
                        this.showTab("models");
                    } catch (error) {
                        checkbox.checked = !checkbox.checked;
                        alert("Fehler: " + error.message);
                    }

                };

            });


        }


        if (tab === "runtime") {

            box.innerHTML = `

                <h3>
                    ⚙ Ollama Runtime
                </h3>

                <label>
                    Aktives Modell
                </label>

                <select
                    id="ollama-model"
                >

                    <option value="">
                        Kein Modell ausgewählt
                    </option>

                    ${
                        this.models
                            .map(model => `
                                <option
                                    value="${model.name}"
                                    ${
                                        this.config.model ===
                                        model.name
                                        ? "selected"
                                        : ""
                                    }
                                >
                                    ${model.name}
                                </option>
                            `)
                            .join("")
                    }

                </select>


                <label>
                    Health Check Intervall
                </label>

                <input
                    id="ollama-interval"
                    type="number"
                    min="1"
                    value="${
                        this.config.health_interval ||
                        5
                    }"
                >


                <label>
                    Temperature
                </label>

                <input
                    id="ollama-temperature"
                    type="number"
                    min="0"
                    max="2"
                    step="0.1"
                    value="${
                        this.config.temperature ??
                        0.2
                    }"
                >


                <label>
                    Context Size
                </label>

                <input
                    id="ollama-context"
                    type="number"
                    min="512"
                    value="${
                        this.config.context ||
                        8192
                    }"
                >


                <label>
                    Max Output Tokens
                </label>

                <input
                    id="ollama-num-predict"
                    type="number"
                    min="128"
                    value="${
                        this.config.num_predict ||
                        2048
                    }"
                >


                <label>
                    Keep Alive
                </label>

                <input
                    id="ollama-keep-alive"
                    value="${
                        this.config.keep_alive ||
                        "5m"
                    }"
                >


                <button
                    id="ollama-save-runtime"
                    type="button"
                >
                    Runtime speichern
                </button>

            `;


            document
                .getElementById(
                    "ollama-save-runtime"
                )
                .onclick = () => {

                    this.saveConfig();

                };

        }


        if (tab === "sync") {

            const online =
                this.status?.online;


            box.innerHTML = `

                <h3>
                    🧠 SECBrain ↔ Ollama Sync
                </h3>


                <div class="ollama-sync-status">

                    <p>
                        SECBrain Backend:
                        <strong>
                            ONLINE
                        </strong>
                    </p>


                    <p>
                        Ollama:
                        <strong>
                            ${
                                online
                                ? "ONLINE"
                                : "OFFLINE"
                            }
                        </strong>
                    </p>


                    <p>
                        Ollama URL:
                        <strong>
                            ${
                                this.status?.url ||
                                "unbekannt"
                            }
                        </strong>
                    </p>


                    <p>
                        Modelle:
                        <strong>
                            ${
                                this.status?.model_count ??
                                0
                            }
                        </strong>
                    </p>


                    <p>
                        Aktives Modell:
                        <strong>
                            ${
                                this.config?.model ||
                                "nicht ausgewählt"
                            }
                        </strong>
                    </p>


                    <p>
                        Ollama Version:
                        <strong>
                            ${
                                this.status?.version ||
                                "unbekannt"
                            }
                        </strong>
                    </p>

                </div>


                <button
                    id="ollama-full-sync"
                    type="button"
                >
                    🔄 Jetzt synchronisieren
                </button>

            `;


            document
                .getElementById(
                    "ollama-full-sync"
                )
                .onclick = async () => {

                    await this.refresh();

                    this.showTab(
                        "sync"
                    );

                };

        }

    },


    renderChatDock() {

        const box = document.getElementById("ollama-chat-dock");
        if (!box) return;

        const activeModel = this.config.model || "";
        this.renderFooterModelSelector();
        const history = this.chatMessages.length
            ? this.chatMessages.map(message => {
                const hits = message.vault_retrieval?.hits || [];
                const sources = hits.length ? `
                    <details class="ollama-chat-sources">
                        <summary>Vault-Quellen via QMD (${hits.length})</summary>
                        <ul>${hits.map(hit => `
                            <li><code>${this.escapeHtml(hit.path)}</code><span>${Math.round(Number(hit.score || 0) * 100)} %</span></li>
                        `).join("")}</ul>
                    </details>` : "";
                return `
                <article class="ollama-chat-message ollama-chat-${message.role}">
                    <strong>${message.role === "user" ? "Du" : "SECBrain"}</strong>
                    <p>${this.escapeHtml(message.content).replace(/\n/g, "<br>")}</p>
                    ${sources}
                </article>
            `}).join("")
            : `<p class="ollama-chat-empty">Stelle eine Frage zum Modell oder zu deiner Arbeit. Der Chat schreibt nichts in die Vault.</p>`;

        box.innerHTML = `
            <section class="ollama-chat">
                <div class="ollama-chat-toolbar">
                    <div>
                        <h3>💬 SECBrain Chat</h3>
                        <p>Lokale Sitzung – keine Änderung an der Vault.</p>
                    </div>
                </div>
                <div id="ollama-chat-history" class="ollama-chat-history">${history}</div>
                <label for="ollama-chat-input">Nachricht</label>
                <p class="ollama-chat-write-notice">Nur /excalidraw &lt;Beschreibung&gt; schreibt eine Diagrammdatei auf Local/Work.</p>
                <textarea id="ollama-chat-input" rows="3" placeholder="Frage an ${this.escapeHtml(activeModel || "ein Ollama-Modell")}" ${activeModel ? "" : "disabled"}></textarea>
                <button id="ollama-chat-send" type="button" ${activeModel ? "" : "disabled"}>Nachricht senden</button>
            </section>
        `;

        const historyElement = document.getElementById("ollama-chat-history");
        historyElement.scrollTop = historyElement.scrollHeight;

        document.getElementById("ollama-chat-send").onclick = () => this.sendChat();
        document.getElementById("ollama-chat-input").onkeydown = event => {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                this.sendChat();
            }
        };

    },


    renderFooterModelSelector() {

        const box = document.getElementById("ollama-footer-model");
        if (!box) return;

        const activeModel = this.config.model || "";
        const models = this.models || [];

        box.innerHTML = `
            <label for="ollama-footer-model-select">Modell:</label>
            <select id="ollama-footer-model-select" aria-label="Aktives Ollama-Sitzungsmodell" ${models.length ? "" : "disabled"}>
                <option value="">Modell auswählen</option>
                ${models.map(model => `
                    <option value="${this.escapeHtml(model.name)}" ${model.name === activeModel ? "selected" : ""}>
                        ${this.escapeHtml(model.name)}
                    </option>
                `).join("")}
            </select>
        `;

        const select = document.getElementById("ollama-footer-model-select");
        select.onchange = async event => {
            if (!event.target.value) return;
            select.disabled = true;
            try {
                await this.selectModel(event.target.value);
                this.renderChatDock();
            } catch (error) {
                select.disabled = false;
                alert("Fehler: " + error.message);
            }
        };

    },


    async initializeChatDock() {

        await this.refresh();
        this.renderChatDock();

    },


    startMonitor() {

        if (this.monitorTimer)
            return;


        this.monitorTimer =
            setInterval(
                async () => {

                    await this.refresh();

                },
                5000
            );

    }

};


console.log(
    "SECBrain Ollama Control Center geladen"
);


window.OllamaSettings.initializeChatDock();
