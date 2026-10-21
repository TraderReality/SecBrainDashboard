window.VaultUpload = {
    modal: null,
    mode: "markdown",
    file: null,

    open() {
        if (!this.modal) this.create();
        this.showMode("markdown");
        this.modal.style.display = "flex";
    },

    close() {
        if (this.modal) this.modal.style.display = "none";
    },

    create() {
        const modal = document.createElement("div");
        modal.id = "vault-upload-modal";
        modal.setAttribute("role", "dialog");
        modal.setAttribute("aria-modal", "true");
        modal.setAttribute("aria-labelledby", "vault-upload-title");
        modal.innerHTML = `
            <section class="vault-upload-panel dokulader-panel">
                <header class="vault-upload-header">
                    <div>
                        <h2 id="vault-upload-title">📚 DokuLader</h2>
                        <p>Quellen sicher für den nächsten Watcher-Lauf bereitstellen.</p>
                    </div>
                    <button id="vault-upload-close" type="button" aria-label="DokuLader schließen">✕</button>
                </header>
                <nav class="dokulader-tabs" aria-label="Importart">
                    <button type="button" data-mode="markdown">Markdown</button>
                    <button type="button" data-mode="urls">Web-URLs</button>
                    <button type="button" data-mode="pdf">PDF-Handbuch</button>
                    <button type="button" data-mode="package">Doku-Paket</button>
                </nav>
                <div id="dokulader-content"></div>
                <div id="vault-upload-status" class="vault-upload-status" aria-live="polite"></div>
                <footer class="vault-upload-actions">
                    <button id="vault-upload-cancel" class="secondary" type="button">Schließen</button>
                    <button id="vault-upload-submit" type="button" disabled>Importieren</button>
                </footer>
            </section>`;
        document.body.appendChild(modal);
        this.modal = modal;
        modal.querySelector("#vault-upload-close").onclick = () => this.close();
        modal.querySelector("#vault-upload-cancel").onclick = () => this.close();
        modal.querySelector("#vault-upload-submit").onclick = () => this.submit();
        modal.querySelectorAll("[data-mode]").forEach(button => {
            button.onclick = () => this.showMode(button.dataset.mode);
        });
        modal.onclick = event => { if (event.target === modal) this.close(); };
        document.addEventListener("keydown", event => {
            if (event.key === "Escape" && modal.style.display !== "none") this.close();
        });
    },

    showMode(mode) {
        this.mode = mode;
        this.file = null;
        this.setStatus("");
        this.modal.querySelectorAll("[data-mode]").forEach(button => {
            button.classList.toggle("active", button.dataset.mode === mode);
        });
        const content = document.getElementById("dokulader-content");
        const submit = document.getElementById("vault-upload-submit");
        submit.disabled = true;

        if (mode === "markdown") {
            content.innerHTML = `
                <label class="vault-upload-drop" for="vault-upload-file">
                    <strong>Markdown-Datei auswählen</strong>
                    <span>Nur .md · UTF-8 · maximal 512 KiB</span>
                    <input id="vault-upload-file" type="file" accept=".md,text/markdown,text/plain">
                </label>
                <div id="vault-upload-selection" class="vault-upload-selection">Keine Datei ausgewählt.</div>`;
            document.getElementById("vault-upload-file").onchange = event => this.selectFile(event.target.files[0]);
            submit.textContent = "In Inbox hochladen";
        } else if (mode === "urls") {
            content.innerHTML = `
                <label class="dokulader-field" for="dokulader-urls">
                    <strong>Dokumentations-URLs</strong>
                    <span>Eine HTTP(S)-URL pro Zeile · maximal 20 Seiten</span>
                    <textarea id="dokulader-urls" rows="8" placeholder="https://docs.example.org/start\nhttps://docs.example.org/kapitel"></textarea>
                </label>`;
            document.getElementById("dokulader-urls").oninput = event => {
                submit.disabled = !event.target.value.trim();
            };
            submit.textContent = "URLs laden und importieren";
        } else if (mode === "pdf") {
            content.innerHTML = `
                <label class="vault-upload-drop" for="vault-upload-file">
                    <strong>PDF-Handbuch auswählen</strong>
                    <span>PDF · lokal konvertiert · maximal 64 MiB</span>
                    <input id="vault-upload-file" type="file" accept=".pdf,application/pdf">
                </label>
                <div id="vault-upload-selection" class="vault-upload-selection">Kein PDF ausgewählt.</div>
                <p class="dokulader-hint">Das Original bleibt in <code>07 Anhänge/Dokumentationspakete</code>. DokuLader erzeugt lokal seitengebundene Markdown-Teile; nur ihr Manifest gelangt in die Inbox.</p>`;
            document.getElementById("vault-upload-file").onchange = event => this.selectFile(event.target.files[0]);
            submit.textContent = "PDF konvertieren und übernehmen";
        } else {
            content.innerHTML = `
                <label class="vault-upload-drop" for="vault-upload-file">
                    <strong>Dokumentationspaket auswählen</strong>
                    <span>ZIP · mindestens 100 Markdown-Dateien · maximal 64 MiB</span>
                    <input id="vault-upload-file" type="file" accept=".zip,application/zip">
                </label>
                <div id="vault-upload-selection" class="vault-upload-selection">Kein Paket ausgewählt.</div>
                <p class="dokulader-hint">Das Originalarchiv wird in <code>07 Anhänge/Dokumentationspakete</code> gespeichert. Die Inbox erhält nur das Manifest.</p>`;
            document.getElementById("vault-upload-file").onchange = event => this.selectFile(event.target.files[0]);
            submit.textContent = "Paket prüfen und übernehmen";
        }
    },

    selectFile(file) {
        const submit = document.getElementById("vault-upload-submit");
        const selection = document.getElementById("vault-upload-selection");
        this.file = null;
        if (!file) {
            submit.disabled = true;
            return;
        }
        const packageMode = this.mode === "package";
        const pdfMode = this.mode === "pdf";
        const extension = packageMode ? ".zip" : (pdfMode ? ".pdf" : ".md");
        const validExtension = file.name.toLowerCase().endsWith(extension);
        const limit = packageMode || pdfMode ? 64 * 1024 * 1024 : 512 * 1024;
        if (!validExtension) {
            submit.disabled = true;
            const expected = packageMode ? "ZIP-Paket" : (pdfMode ? "PDF-Handbuch" : "Markdown-Datei");
            return this.setStatus(`Bitte ein ${expected} auswählen.`, "error");
        }
        if (!file.size || file.size > limit) {
            submit.disabled = true;
            return this.setStatus(`Die Datei muss zwischen 1 Byte und ${packageMode || pdfMode ? "64 MiB" : "512 KiB"} groß sein.`, "error");
        }
        this.file = file;
        selection.textContent = `${file.name} · ${this.formatBytes(file.size)}`;
        this.setStatus("Bereit zum Import.");
        submit.disabled = false;
    },

    async submit() {
        if (this.mode === "urls") return this.importUrls();
        if (!this.file) return;
        const endpoint = this.mode === "package" ? "/api/dokulader/package" :
            (this.mode === "pdf" ? "/api/dokulader/pdf" : "/api/vault/inbox/upload");
        await this.withBusy(async () => {
            const result = await this.post(endpoint, {
                filename: this.file.name,
                content_base64: await this.fileToBase64(this.file),
            });
            if (this.mode === "package") {
                this.setStatus(`✓ ${result.filename}: ${result.markdown_files} Markdown-Dateien, Version ${result.version}.`, "success");
            } else if (this.mode === "pdf") {
                this.setStatus(`✓ ${result.filename}: ${result.pages} Seiten in ${result.chunks} Markdown-Teilen, Version ${result.version}.`, "success");
            } else {
                this.setStatus(`✓ ${result.filename} wurde in die Inbox hochgeladen.`, "success");
            }
            this.file = null;
            window.dispatchEvent(new CustomEvent("secbrain:inbox-uploaded", {detail: result}));
        });
    },

    async importUrls() {
        const urls = document.getElementById("dokulader-urls").value.split(/\r?\n/).map(url => url.trim()).filter(Boolean);
        await this.withBusy(async () => {
            const result = await this.post("/api/dokulader/urls", {urls});
            const parts = [`${result.imported.length} importiert`, `${result.skipped.length} übersprungen`, `${result.errors.length} Fehler`];
            const failures = result.errors.map(item => `${item.url}: ${item.reason}`).join("\n");
            this.setStatus(`✓ ${parts.join(" · ")}${failures ? `\n${failures}` : ""}`, result.errors.length ? "error" : "success");
            if (result.imported.length) {
                window.dispatchEvent(new CustomEvent("secbrain:inbox-uploaded", {detail: result}));
            }
        });
    },

    async withBusy(action) {
        const submit = document.getElementById("vault-upload-submit");
        submit.disabled = true;
        this.setStatus("DokuLader verarbeitet die Quelle …");
        try {
            await action();
        } catch (error) {
            this.setStatus(error.message || "Import fehlgeschlagen.", "error");
            submit.disabled = false;
        }
    },

    async post(url, payload) {
        const response = await fetch(url, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Import fehlgeschlagen.");
        return result;
    },

    fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = () => reject(new Error("Datei konnte nicht gelesen werden."));
            reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
            reader.readAsDataURL(file);
        });
    },

    formatBytes(bytes) {
        return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MiB` : `${Math.ceil(bytes / 1024)} KiB`;
    },

    setStatus(message, state = "") {
        const status = document.getElementById("vault-upload-status");
        if (!status) return;
        status.textContent = message;
        status.dataset.state = state;
    },
};

document.getElementById("vault-upload-open")?.addEventListener("click", () => window.VaultUpload.open());
