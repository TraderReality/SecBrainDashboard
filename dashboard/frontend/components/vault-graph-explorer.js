window.VaultGraphExplorer = class VaultGraphExplorer {

    constructor(root) {
        this.root = root;
        this.graph = null;
        this.sync = null;
        this.positions = new Map();
        this.nodeById = new Map();
        this.palette = ["#40a9ff", "#b779ff", "#00e7a0", "#ffbd3e", "#fa6f9f", "#38d9d9", "#93d652", "#ff866c"];
        this.threeD = null;
        this.root.addEventListener("vault-graph-3d-error", event => {
            console.warn("SecBrain 3D-Graph:", event.detail?.message || "WebGL-Fehler");
            this.threeD?.dispose();
            this.threeD = null;
            this.render();
            this.setStatus("2D-Fallback: WebGL nicht verfügbar", "error");
        });
    }

    async load() {
        this.setStatus("Indexer-Export wird geladen …", "loading");

        try {
            const response = await fetch("/api/vault/graph", { cache: "no-store" });
            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload.detail || "Graphdaten sind nicht verfügbar.");
            }

            this.graph = payload.graph;
            this.sync = payload.sync || null;
            this.nodeById = new Map((this.graph.nodes || []).map(node => [node.id, node]));
            this.renderMetadata(payload);
            try {
                if (!window.VaultGraph3DExplorer) {
                    throw new Error("Der 3D-Renderer konnte nicht geladen werden.");
                }
                this.threeD?.dispose();
                this.threeD = new VaultGraph3DExplorer(this.root, node => this.selectNode(node));
                await this.threeD.render(this.graph, this.sync);
                this.setGraphStatus("3D");
            } catch (threeError) {
                console.warn("SecBrain 3D-Graph: Fallback auf 2D-Ansicht.", threeError);
                this.threeD = null;
                this.render();
                this.setGraphStatus("2D-Fallback");
            }
        } catch (error) {
            this.root.replaceChildren();
            const message = document.createElement("p");
            message.className = "graph-error";
            message.textContent = "Graph konnte nicht geladen werden: " + error.message;
            this.root.append(message);
            this.setStatus("Indexer-Sicht nicht verfügbar", "error");
        }
    }

    renderMetadata(payload) {
        const nodes = this.graph.nodes || [];
        const edges = this.graph.edges || [];
        const clusters = new Set(nodes.map(node => node.cluster || "Ohne Cluster"));
        document.getElementById("graph-node-count").textContent = String(nodes.length);
        document.getElementById("graph-edge-count").textContent = String(edges.length);
        document.getElementById("graph-cluster-count").textContent = String(clusters.size);
        document.getElementById("graph-updated-at").textContent = new Date(payload.updated_at * 1000)
            .toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
    }

    render(filter = "") {
        if (!this.graph) return;

        this.root.replaceChildren();
        const nodes = this.graph.nodes || [];
        const edges = this.graph.edges || [];
        this.positions = this.createLayout(nodes);

        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 1000 640");
        svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", "SecBrain Wissensgraph aus dem Indexer-Export");
        svg.classList.add("vault-graph-svg");

        const filterTerm = filter.trim().toLocaleLowerCase("de-DE");
        const matches = node => !filterTerm || [node.id, node.titel, node.title, node.cluster, node.typ]
            .filter(Boolean)
            .join(" ")
            .toLocaleLowerCase("de-DE")
            .includes(filterTerm);
        const matchedIds = new Set(nodes.filter(matches).map(node => node.id));

        const edgeLayer = document.createElementNS(svg.namespaceURI, "g");
        edgeLayer.classList.add("graph-edge-layer");
        edges.forEach(edge => {
            const source = this.positions.get(edge.from || edge.source);
            const target = this.positions.get(edge.to || edge.target);
            if (!source || !target) return;
            const line = document.createElementNS(svg.namespaceURI, "line");
            line.setAttribute("x1", source.x);
            line.setAttribute("y1", source.y);
            line.setAttribute("x2", target.x);
            line.setAttribute("y2", target.y);
            if (filterTerm && !matchedIds.has(source.id) && !matchedIds.has(target.id)) {
                line.classList.add("is-muted");
            }
            edgeLayer.append(line);
        });
        svg.append(edgeLayer);

        const nodeLayer = document.createElementNS(svg.namespaceURI, "g");
        nodeLayer.classList.add("graph-node-layer");
        nodes.forEach(node => {
            const point = this.positions.get(node.id);
            const group = document.createElementNS(svg.namespaceURI, "g");
            const nodeMatch = matches(node);
            const color = this.colorFor(node.cluster || "Ohne Cluster");
            group.classList.add("vault-graph-node");
            if (filterTerm && !nodeMatch) group.classList.add("is-muted");
            group.setAttribute("transform", `translate(${point.x} ${point.y})`);
            group.setAttribute("tabindex", "0");
            group.setAttribute("role", "button");
            group.setAttribute("aria-label", `${node.titel || node.title || node.id} öffnen`);

            const halo = document.createElementNS(svg.namespaceURI, "circle");
            halo.setAttribute("r", "14");
            halo.setAttribute("fill", color);
            halo.setAttribute("opacity", "0.14");
            const circle = document.createElementNS(svg.namespaceURI, "circle");
            circle.setAttribute("r", String(Math.max(4.5, Math.min(9, 4 + Number(node.grad || 0) * 0.7))));
            circle.setAttribute("fill", color);
            circle.setAttribute("stroke", "#d9ecff");
            circle.setAttribute("stroke-width", "1");
            const label = document.createElementNS(svg.namespaceURI, "text");
            label.setAttribute("x", "10");
            label.setAttribute("y", "4");
            label.textContent = this.shorten(node.titel || node.title || node.id, 26);
            const title = document.createElementNS(svg.namespaceURI, "title");
            title.textContent = `${node.titel || node.title || node.id} · ${node.cluster || "Ohne Cluster"}`;

            group.append(halo, circle, label, title);
            const select = () => this.selectNode(node);
            group.addEventListener("click", select);
            group.addEventListener("keydown", event => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    select();
                }
            });
            nodeLayer.append(group);
        });
        svg.append(nodeLayer);
        this.root.append(svg);
    }

    applyFilter(filter = "") {
        if (this.threeD) {
            this.threeD.applyFilter(filter);
            return;
        }
        this.render(filter);
    }

    resetView() {
        this.threeD?.resetView();
    }

    createLayout(nodes) {
        const groups = new Map();
        nodes.forEach(node => {
            const cluster = node.cluster || "Ohne Cluster";
            if (!groups.has(cluster)) groups.set(cluster, []);
            groups.get(cluster).push(node);
        });

        const clusters = [...groups.keys()].sort((a, b) => a.localeCompare(b, "de"));
        const positions = new Map();
        clusters.forEach((cluster, clusterIndex) => {
            const angle = (Math.PI * 2 * clusterIndex / clusters.length) - Math.PI / 2;
            const center = {
                x: 500 + Math.cos(angle) * (clusters.length === 1 ? 0 : 205),
                y: 320 + Math.sin(angle) * (clusters.length === 1 ? 0 : 175)
            };
            const members = groups.get(cluster);
            members.forEach((node, index) => {
                const nodeAngle = Math.PI * 2 * index / Math.max(members.length, 1);
                const distance = 22 + Math.floor(index / 7) * 30;
                positions.set(node.id, {
                    id: node.id,
                    x: center.x + Math.cos(nodeAngle) * distance,
                    y: center.y + Math.sin(nodeAngle) * distance
                });
            });
        });
        return positions;
    }

    selectNode(node) {
        document.getElementById("graph-node-title").textContent = node.titel || node.title || node.id;
        const details = document.getElementById("graph-node-details");
        details.replaceChildren();
        const entries = [
            ["Kennung", node.id],
            ["Typ", node.typ || "–"],
            ["Cluster", node.cluster || "–"],
            ["Pfad", node.pfad || node.path || "–"],
            ["Ausgehende Links", String((node.outgoing_links || []).length)],
            ["Verbindungen", String(node.grad || 0)]
        ];
        entries.forEach(([label, value]) => {
            const row = document.createElement("div");
            const term = document.createElement("dt");
            const definition = document.createElement("dd");
            term.textContent = label;
            definition.textContent = value;
            row.append(term, definition);
            details.append(row);
        });
    }

    setStatus(text, state) {
        const element = document.getElementById("graph-source-status");
        element.textContent = text;
        element.dataset.state = state;
    }

    setGraphStatus(view) {
        const current = this.sync?.current === true;
        const label = current ? "aktuell" : "veraltet";
        this.setStatus(`${view} · Index ${label}`, current ? "ready" : "error");
    }

    colorFor(cluster) {
        let hash = 0;
        for (let index = 0; index < cluster.length; index += 1) hash = (hash * 31 + cluster.charCodeAt(index)) >>> 0;
        return this.palette[hash % this.palette.length];
    }

    shorten(value, limit) {
        return value.length > limit ? value.slice(0, limit - 1) + "…" : value;
    }
};
