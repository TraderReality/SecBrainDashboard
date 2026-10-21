import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { BLOOM_LAYER } from "./vault-graph-constants.js";
import { VaultGraphGraphMethods } from "./vault-graph-graph.js";
import { VaultGraphAtlasMethods } from "./vault-graph-atlas.js";
import { VaultGraphEnvironmentMethods } from "./vault-graph-environment.js";

/* Selektives Bloom: eigene Layer-Ebene, auf der ausschließlich Nodes
 * (Soma/Glow/Cage/Halo/Dendriten) und Kanten (Leiterbahnen + Signal-
 * Pakete) liegen. Gehirn-Mesh und Atlasblasen-Mesh bleiben auf der
 * Standard-Ebene 0 und werden dadurch von der Bloom-Passage ausgenommen. */

let brainTemplatePromise = null;

function loadBrainTemplate() {
    if (!brainTemplatePromise) {
        brainTemplatePromise = new GLTFLoader()
            .loadAsync("assets/graph/brain.glb")
            .then(gltf => gltf.scene)
            .catch(error => {
                brainTemplatePromise = null;
                throw error;
            });
    }
    return brainTemplatePromise;
}

function cloneBrainTemplate(template) {
    const clone = template.clone(true);
    clone.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return;
        object.geometry = object.geometry.clone();
        object.material = Array.isArray(object.material)
            ? object.material.map(material => material.clone())
            : object.material.clone();
    });
    return clone;
}

/*
 * Eigenständiger 3D-Renderer für den Vault Explorer.
 *
 * Daten kommen ausschließlich aus /api/vault/graph.  Diese Schicht besitzt
 * weder Schreibzugriff auf den Vault noch eine zweite Graphdatenbank.
 */
class VaultGraph3DExplorer {
    constructor(root, onSelect) {
        this.root = root;
        this.onSelect = onSelect;
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.canvas = null;
        this.frame = null;
        this.resizeObserver = null;
        this.nodeMeshes = [];
        this.interactionMeshes = [];
        this.nodeByMesh = new Map();
        this.nodeVisuals = new Map();
        this.edgeVisuals = [];
        this.edgePaths = [];
        this.edgeSignals = null;
        this.labelSprites = [];
        this.raycaster = new THREE.Raycaster();
        this.pointer = new THREE.Vector2();
        this.activeNode = null;
        this.filter = "";
        this.graph = null;
        this.brain = null;
        this.brainCenter = new THREE.Vector3();
        this.brainLift = 2.6;
        this.baseBrainOpacity = 0.84;
        this.atlasBrainOpacity = 0.42;
        this.medullaAnchor = null;
        this.surfaceMeshes = [];
        /* Unsichtbare Double-Side-Kopien nur für die begrenzten
         * Punkt-im-Gehirn-Prüfungen des Regelwerk-Hirnstamms. */
        this.brainContainmentMeshes = [];
        this.brainContainmentRaycaster = new THREE.Raycaster();
        this.stopped = false;
        this.homeCamera = new THREE.Vector3(0, 3.1, 40.5);
        this.neuralField = null;
        this.neuralBackdropRoot = null;
        this.neuralHubs = null;
        this.neuralLinks = null;
        this.neuralSignals = null;
        this.neuralRings = null;
        this.neuralBursts = [];
        this.flowLines = null;
        this.waveField = null;
        this.vaultRegionVolumes = [];
        this.vaultRegionRooms = new Map();
        this.corticalAtlasGroup = null;
        this.corticalAtlasMaterial = null;
        this.corticalAtlasMaterials = [];
        this.corticalVolumeGroup = null;
        this.activeVaultRegion = null;
        this.hasVaultRegionSelection = false;
        this.regionMenu = null;
        this.waveBase = null;
        this.signalPaths = [];
        this.backdropTime = 0;
        this.lastFrameTime = 0;
        this.stageRings = [];
        this.stageCore = null;
        this.stageBeam = null;
        this.cameraTransition = null;
        this.hoveredNode = null;
        this.hoverLogo = null;
        this.hoverLabel = null;
        this.graphNodeGroup = null;
        this.graphPathGroup = null;
        this.atlasOverrideStorageKey = "secbrain-watcher.vault-atlas-overrides.v2";
        this.atlasDevModeStorageKey = "secbrain-watcher.atlas-dev-mode.v1";
        this.atlasOverrides = this.loadAtlasOverrides();
        this.atlasDevMode = this.loadAtlasDevMode();
        this.atlasEditorMode = "position";
        this.fastDevMode = new URLSearchParams(window.location.search)
            .get("graph-dev") === "1" || this.atlasDevMode;
        this.atlasEditorGizmo = null;
        this.atlasEditorHandles = [];
        this.atlasHoveredHandle = null;
    this.atlasEditorRaycaster = new THREE.Raycaster();
    this.atlasEditorDrag = null;
    this.atlasDevNotice = "";
    this.atlasSurfacePreviewAt = 0;
    this.webglVersion = null;
    this.bloomComposer = null;
    this.finalComposer = null;
    this.bloomPass = null;
    this.bloomLayer = new THREE.Layers();
    this.bloomLayer.set(BLOOM_LAYER);
    this.bloomMaterialCache = new Map();
    this.darkMaterial = null;
    this.darkSpriteMaterial = null;
    this.darkLineMaterial = null;
    this.darkPointsMaterial = null;
    this.selectedRelatedIds = null;
    }

    async render(graph, sync = null) {
        this.dispose();
        this.graph = graph;
        this.sync = sync;
        this.root.replaceChildren();

        try {
            /* Den 29-MB-GLB-Abruf sofort beginnen. Szenenaufbau und Download
             * laufen dadurch parallel; weitere Render-Durchläufe verwenden
             * die bereits geparste Vorlage derselben Browser-Sitzung. */
            let brainReady = this.fastDevMode ? this.loadBrain() : null;
            this.createScene();
            brainReady ||= this.loadBrain();
            await brainReady;
            this.buildCorticalAtlas();
            /* Im Atlas-Editor zählt ausschließlich die Hülle. Graph-Nodes,
             * Kanten und ihre Hit-Flächen werden dort weder erzeugt noch
             * positioniert oder gerendert. */
            if (!this.atlasDevMode) this.buildGraph();
            if (this.atlasDevMode) this.setAtlasDevMode(true);
            /* Start ohne Auswahl: Erst ein bewusster Menüklick hebt eine oder
             * alle Atlasblasen hervor. */
            this.setActiveVaultRegion(null, false);
            this.start();
            return true;
        } catch (error) {
            this.dispose();
            throw error;
        }
    }

    createScene() {
        this.canvas = document.createElement("canvas");
        this.canvas.className = "vault-graph-three-canvas";
        this.canvas.setAttribute("aria-label", "Dreidimensionaler SecBrain Wissensgraph");
        this.root.append(this.canvas);
        this.addInterfaceOverlay();
        this.addRegionMenu();

        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color("#020712");
        this.scene.fog = new THREE.FogExp2("#020712", 0.018);
        this.camera = new THREE.PerspectiveCamera(39, 1, 0.1, 180);
        this.camera.position.copy(this.homeCamera);
        /* WebGL wird auf genau dem Canvas geprüft, das anschließend gerendert
         * wird. Dadurch bleibt der vorhandene 2D-Fallback eindeutig, falls
         * der Browser oder die Hardwarebeschleunigung keinen Kontext liefert. */
        const contextOptions = {
            alpha: false,
            antialias: true,
            depth: true,
            stencil: false,
            powerPreference: "high-performance"
        };
        const webgl2 = this.canvas.getContext("webgl2", contextOptions);
        const context = webgl2
            || this.canvas.getContext("webgl", contextOptions)
            || this.canvas.getContext("experimental-webgl", contextOptions);
        if (!context) {
            throw new Error("WebGL ist nicht verfügbar. Bitte Hardwarebeschleunigung im Browser aktivieren.");
        }
        this.webglVersion = webgl2 ? "WebGL 2" : "WebGL 1";
        this.canvas.dataset.webglVersion = this.webglVersion;
        this.renderer = new THREE.WebGLRenderer({
            canvas: this.canvas,
            context,
            antialias: true,
            alpha: false,
            powerPreference: "high-performance"
        });
        this.renderer.setPixelRatio(this.fastDevMode
            ? 1
            : Math.min(window.devicePixelRatio || 1, 1.75));
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.35;
        /* Der Explorer verwendet eine eigene Lichtkomposition statt
         * Hardware-Schatten. Das vermeidet nicht portable Depth-Texture-
         * Vergleiche auf einigen WebGL-Treibern. */
        this.renderer.shadowMap.enabled = false;

        /* Bloom-Postprocessing, an die Neural-Graph-Demo angelehnt
         * (secbrain-neural-graph.html). Die Demo-Werte (0.72/0.6/0.34) gehen
         * von frei verteilten Knoten aus; in der dicht gepackten Atlasblase
         * lässt der niedrige Threshold + die hohe Stärke benachbarte, additiv
         * geblendete Knoten-Glows zu einem einzigen Klumpen verschmelzen.
         * Reduzierte Stärke und höherer Threshold behalten den Bloom-Look,
         * ohne dicht stehende Knoten optisch zu einem Klumpen zu verschmelzen.
         * Im Atlas-Editor (fastDevMode) bleibt es wie schon der Neural-
         * Hintergrund und die Bühne bewusst aus, um die Editier-Performance
         * nicht zu belasten. */
        if (!this.fastDevMode) {
            const bloomWidth = Math.max(this.root.clientWidth, 1);
            const bloomHeight = Math.max(this.root.clientHeight, 1);

            /* Selektives Bloom (Standardtechnik aus dem three.js-Beispiel
             * "webgl_postprocessing_unreal_bloom_selective"): Nur Objekte auf
             * BLOOM_LAYER sollen leuchten – Gehirn-Mesh und Atlasblasen-Mesh
             * bleiben auf Layer 0 und damit unbeleuchtet vom Bloom.
             * Ablauf pro Frame: Szene mit auf Schwarz getauschten Materialien
             * aller Nicht-Bloom-Objekte rendern (liefert nur den Leucht-
             * beitrag von Nodes/Kanten, Tiefentest bleibt für korrekte
             * Verdeckung erhalten), dann die normale Szene rendern und beide
             * additiv mischen. */
            this.darkMaterial = new THREE.MeshBasicMaterial({ color: 0x000000 });
            this.darkSpriteMaterial = new THREE.SpriteMaterial({ color: 0x000000 });
            this.darkLineMaterial = new THREE.LineBasicMaterial({ color: 0x000000 });
            this.darkPointsMaterial = new THREE.PointsMaterial({ color: 0x000000, size: 0.0001 });
            this.bloomMaterialCache.clear();

            this.bloomComposer = new EffectComposer(this.renderer);
            this.bloomComposer.renderToScreen = false;
            this.bloomComposer.addPass(new RenderPass(this.scene, this.camera));
            this.bloomPass = new UnrealBloomPass(
                new THREE.Vector2(bloomWidth, bloomHeight),
                0.42,
                0.55,
                0.56
            );
            this.bloomComposer.addPass(this.bloomPass);

            const mixMaterial = new THREE.ShaderMaterial({
                uniforms: {
                    baseTexture: { value: null },
                    bloomTexture: { value: this.bloomComposer.renderTarget2.texture }
                },
                vertexShader: `
                    varying vec2 vUv;
                    void main() {
                        vUv = uv;
                        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
                    }
                `,
                fragmentShader: `
                    uniform sampler2D baseTexture;
                    uniform sampler2D bloomTexture;
                    varying vec2 vUv;
                    void main() {
                        gl_FragColor = texture2D(baseTexture, vUv) + texture2D(bloomTexture, vUv);
                    }
                `
            });
            const mixPass = new ShaderPass(mixMaterial, "baseTexture");
            mixPass.needsSwap = true;

            this.finalComposer = new EffectComposer(this.renderer);
            this.finalComposer.addPass(new RenderPass(this.scene, this.camera));
            this.finalComposer.addPass(mixPass);
            this.finalComposer.addPass(new OutputPass());
        }

        this.controls = new OrbitControls(this.camera, this.canvas);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.055;
        this.controls.minDistance = 6;
        this.controls.maxDistance = 72;
        /* Die Bühne ist eine feste Bodenebene: Kein Blick von unten auf die
         * Unterseite und kein Durchfahren des Podiums. */
        this.controls.minPolarAngle = 0.18;
        this.controls.maxPolarAngle = Math.PI / 2 - 0.08;
        this.controls.target.set(0, 0, 0);

        const ambient = new THREE.HemisphereLight(0xb7e9ff, 0x07101d, 3.2);
        this.scene.add(ambient);
        const key = new THREE.DirectionalLight(0xffd8c2, 7.5);
        key.position.set(9, 12, 11);
        this.scene.add(key);
        const rim = new THREE.PointLight(0x39cfff, 54, 52, 2);
        rim.position.set(-11, 7, 6);
        this.scene.add(rim);
        const glow = new THREE.PointLight(0xff5bc9, 28, 38, 2);
        glow.position.set(9, 1, 9);
        this.scene.add(glow);
        const underlight = new THREE.PointLight(0x1acbff, 46, 32, 2);
        underlight.position.set(0, -7.2, 4);
        this.scene.add(underlight);

        if (!this.fastDevMode) {
            this.buildNeuralBackdrop();
            this.addStage();
        }
        this.canvas.addEventListener("pointerdown", this.onPointerDown);
        this.canvas.addEventListener("pointermove", this.onPointerMove);
        this.canvas.addEventListener("pointerup", this.onPointerUp);
        this.canvas.addEventListener("pointercancel", this.onPointerUp);
        this.canvas.addEventListener("pointerleave", this.onPointerLeave);
        this.canvas.addEventListener("dblclick", this.onNodeDoubleClick);
        this.canvas.addEventListener("webglcontextlost", this.onContextLost, false);
        window.addEventListener("keydown", this.onKeyDown);
        this.resizeObserver = new ResizeObserver(() => this.resize());
        this.resizeObserver.observe(this.root);
        this.resize();
    }

    addInterfaceOverlay() {
        const nodes = this.graph?.nodes?.length || 0;
        const edges = this.graph?.edges?.length || 0;
        const current = this.sync?.current === true;
        const indexStatus = current ? "AKTUELL" : "VERALTET";
        const syncStatus = current ? "SYNCHRON" : "NEU INDEXIEREN";
        const overlay = document.createElement("div");
        overlay.className = "graph-neural-hud";
        overlay.setAttribute("aria-hidden", "true");
        overlay.innerHTML = `
            <div class="graph-neural-frame"></div>
            <div class="graph-neural-hud-top">
                <div><strong>SECBRAIN // NEURAL GRAPH</strong><span>INDEX: <b>${indexStatus}</b></span><span>NODES: ${nodes} · LINKS: ${edges}</span></div>
                <div class="graph-neural-sync">SYNC: <b>${syncStatus}</b><i></i><i></i><i></i><i></i></div>
            </div>
            <div class="graph-neural-hud-bottom"><span>READ-ONLY DATA STREAM</span><em></em><span>GRAPH ENGINE · WATCHER</span></div>`;
        this.root.append(overlay);
    }

    addRegionMenu() {
        const regions = this.vaultRegions();
        const menu = document.createElement("section");
        menu.className = "graph-region-menu";
        menu.setAttribute("aria-label", "Vault-Bereiche im Cortexraum hervorheben");
        menu.innerHTML = `
            <div class="graph-region-menu__title">BEREICHE</div>
            <div class="graph-region-menu__hint">Atlasblase hervorheben</div>
            <div class="graph-region-menu__items"></div>
            <div class="graph-region-menu__dev">
                <button type="button" class="graph-region-menu__dev-toggle" aria-pressed="false">ATLAS-EDITOR: AUS</button>
          <div class="graph-region-menu__dev-panel" hidden>
            <p>1. Positionieren · 2. Volumen formen. Dot ziehen: frei · Shift+ziehen: Tiefe.</p>
            <div class="graph-region-menu__dev-modes" role="group" aria-label="Atlas-Bearbeitung">
              <button type="button" data-atlas-mode="position" aria-pressed="true">1 · Position</button>
              <button type="button" data-atlas-mode="volume" aria-pressed="false">2 · Volumen</button>
            </div>
            <div class="graph-region-menu__dev-actions">
                        <button type="button" data-atlas-action="auto-fit">Alle automatisch einpassen</button>
                        <button type="button" data-atlas-action="reset-active">Aktive zurücksetzen</button>
                        <button type="button" data-atlas-action="reset-all">Alles zurücksetzen</button>
                        <button type="button" data-atlas-action="copy">JSON kopieren</button>
                    </div>
                    <div class="graph-region-menu__dev-status" aria-live="polite"></div>
                </div>
            </div>`;
        const items = menu.querySelector(".graph-region-menu__items");
        const addButton = (name, region, all = false) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "graph-region-menu__button";
            button.dataset.region = all ? "" : name;
            button.setAttribute("aria-pressed", "false");
            button.innerHTML = all
                ? "<span class=\"graph-region-menu__all\">◌</span><span>Alle Bereiche</span>"
                : `<span class="graph-region-menu__swatch" style="--region-color:#${region.color.toString(16).padStart(6, "0")}"></span><span>${name}</span>`;
            /* Toggle: ein zweiter Klick auf denselben, bereits aktiven Button
             * hebt die Hervorhebung wieder auf (zurück in den neutralen
             * Ausgangszustand), statt sie nur erneut zu setzen. */
            button.addEventListener("click", () => {
                const alreadyActive = button.classList.contains("is-active");
                if (alreadyActive) this.setActiveVaultRegion(null, false);
                else this.setActiveVaultRegion(all ? null : name);
            });
            items.append(button);
        };
        addButton("Alle Bereiche", null, true);
        Object.entries(regions).forEach(([name, region]) => addButton(name, region));
        /* Das Menü steuert nie die Orbit-Steuerung des Canvas darunter. */
        ["pointerdown", "pointermove", "pointerup"].forEach(type => {
            menu.addEventListener(type, event => event.stopPropagation());
        });
        this.root.append(menu);
        this.regionMenu = menu;
    menu.querySelector(".graph-region-menu__dev-toggle")?.addEventListener("click", () => {
      this.setAtlasDevMode(!this.atlasDevMode);
    });
    menu.querySelectorAll("[data-atlas-mode]").forEach((button) => {
      button.addEventListener("click", () => this.setAtlasEditorMode(button.dataset.atlasMode));
    });
        menu.querySelector('[data-atlas-action="auto-fit"]')?.addEventListener("click", () => {
            this.autoFitActiveAtlasRoom();
        });
        menu.querySelector('[data-atlas-action="reset-active"]')?.addEventListener("click", () => {
            this.resetAtlasOverride(this.activeVaultRegion);
        });
        menu.querySelector('[data-atlas-action="reset-all"]')?.addEventListener("click", () => {
            this.resetAllAtlasOverrides();
        });
        menu.querySelector('[data-atlas-action="copy"]')?.addEventListener("click", () => {
            this.copyAtlasOverrides();
        });
    }

    setActiveVaultRegion(folder, hasSelection = true) {
        this.activeVaultRegion = folder || null;
        this.hasVaultRegionSelection = hasSelection;
        const region = folder ? this.vaultRegions()[folder] : null;
        this.corticalAtlasMaterials.forEach(material => {
            material.uniforms.uActiveRegion.value = region?.atlasIndex ?? -1;
        });
        this.vaultRegionVolumes.forEach(room => {
            const selected = room.userData.folder === this.activeVaultRegion;
            const hasSpecificSelection = hasSelection && Boolean(this.activeVaultRegion);
            const showAll = hasSelection && !this.activeVaultRegion;
            const { fill, boundary, glow } = room.userData;
            if (fill) fill.material.opacity = hasSpecificSelection ? (selected ? 0.085 : 0.008) : (showAll ? 0.035 : 0.008);
            if (boundary) boundary.material.opacity = hasSpecificSelection ? (selected ? 0.42 : 0.035) : (showAll ? 0.18 : 0.035);
            if (glow) {
                glow.material.uniforms.uOpacity.value = hasSpecificSelection ? (selected ? 0.26 : 0.018) : (showAll ? 0.12 : 0.018);
                glow.scale.setScalar(hasSpecificSelection && selected ? 1.035 : 1.012);
            }
        });
        if (!this.activeNode) {
            /* Knoten-Optik für die Regionsauswahl kommt ebenfalls aus der
             * kontinuierlichen Formel in updateNeuralBackdrop() (liest
             * this.activeVaultRegion direkt) – hier nur noch die
             * Kanten-Hervorhebung, unverändert gegenüber vorher. */
            this.edgeVisuals.forEach(path => {
                const touchesRegion = !this.activeVaultRegion
                    || path.userData.sourceRegion === this.activeVaultRegion
                    || path.userData.targetRegion === this.activeVaultRegion;
                path.material.opacity = touchesRegion ? path.userData.baseOpacity : 0.018;
            });
        }
        this.setBrainTransparency(this.activeVaultRegion ? 0.25 : (hasSelection ? this.atlasBrainOpacity : this.baseBrainOpacity));
        this.regionMenu?.querySelectorAll(".graph-region-menu__button").forEach(button => {
            const isActive = hasSelection && (button.dataset.region || null) === this.activeVaultRegion;
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-pressed", String(isActive));
        });
        if (this.atlasDevMode) this.setAtlasEditorSelection(this.activeVaultRegion);
        this.updateAtlasDevStatus();
    }

    async loadBrain() {
        if (this.fastDevMode) {
            this.brain = cloneBrainTemplate(await loadBrainTemplate());
        } else {
            const gltf = await new GLTFLoader().loadAsync("assets/graph/brain.glb");
            this.brain = gltf.scene;
        }
        this.brain.name = "SecBrain-Wissensgraph-Gehirn";
        this.brain.traverse(object => {
            if (!(object instanceof THREE.Mesh)) return;
            this.surfaceMeshes.push(object);
            if (object.material instanceof THREE.MeshStandardMaterial) {
                object.material.color.set(0xe8cce3);
                object.material.emissive.set(0x171d55);
                object.material.emissiveIntensity = 0.12;
                object.material.roughness = 0.38;
                object.material.metalness = 0.14;
            }
        });
        this.scene.add(this.brain);

        const rawBounds = new THREE.Box3().setFromObject(this.brain);
        const rawSize = rawBounds.getSize(new THREE.Vector3());
        /* Weitere 1,5× größere Cortexfläche; die weiter gesetzte Reset-Kamera
         * hält dabei Gehirn und Podium gemeinsam im Bild. */
        const scale = 22.05 / Math.max(rawSize.x, rawSize.y, rawSize.z, 0.1);
        this.brain.scale.setScalar(scale);
        this.brain.updateMatrixWorld(true);
        const scaledBounds = new THREE.Box3().setFromObject(this.brain);
        scaledBounds.getCenter(this.brainCenter);
        this.brain.position.sub(this.brainCenter);
        /* Der Hirnstamm berührt die Bühne nicht: Das gesamte Modell inklusive
         * seiner Oberflächen-Projektion schwebt klar über dem Hologrammkern. */
        this.brain.position.y += this.brainLift;
        this.brain.updateMatrixWorld(true);
        this.brainCenter.set(0, this.brainLift, 0);
        this.brainBounds = new THREE.Box3().setFromObject(this.brain);
        const brainSize = this.brainBounds.getSize(new THREE.Vector3());
        /* Ein konservatives, vollständig im anatomischen Modell liegendes
         * Innenprofil. Dieses wird einmal bestimmt und vermeidet tausende
         * teure Triangle-Raycasts beim Aufbau der Raumkarte. */
        this.innerRegionAxes = new THREE.Vector3(
            brainSize.x * 0.38,
            brainSize.y * 0.34,
            brainSize.z * 0.38
        );
        this.corticalAtlasAxes = new THREE.Vector3(
            brainSize.x * 0.5,
            brainSize.y * 0.5,
            brainSize.z * 0.5
        );
        this.setBrainTransparency(this.baseBrainOpacity);
    }

    findNodeHit(event) {
        if (this.atlasDevMode || !this.renderer || !this.camera || !this.updatePointerFromEvent(event)) return null;
        this.raycaster.setFromCamera(this.pointer, this.camera);
        return this.raycaster.intersectObjects(this.interactionMeshes, false)[0] || null;
    }

    onPointerDown = event => {
        const atlasHandle = this.findAtlasEditorHandle(event);
        if (atlasHandle && this.beginAtlasEditorDrag(event, atlasHandle)) return;
        const hit = this.findNodeHit(event);
        if (hit) this.selectNode(hit.object.userData.node);
        else this.clearSelection();
    };

    /* Das Detail-Menü rechts (Titel/Kennung/Typ/Cluster/Pfad/…) öffnet sich
     * gezielt erst per Doppelklick – ein einfacher Klick fokussiert nur
     * (Kamera + Ausblenden), siehe selectNode(). */
    onNodeDoubleClick = event => {
        const hit = this.findNodeHit(event);
        if (hit) this.onSelect?.(hit.object.userData.node);
    };

    onPointerMove = event => {
        if (this.atlasEditorDrag) {
            this.updateAtlasEditorDrag(event);
            return;
        }
        const atlasHandle = this.findAtlasEditorHandle(event);
        this.setAtlasHandleHover(atlasHandle?.object || null);
        this.canvas?.classList.toggle("is-atlas-editor-hover", Boolean(atlasHandle));
        if (atlasHandle) {
            this.setNodeHover(null);
            return;
        }
        const hit = this.findNodeHit(event);
        this.setNodeHover(hit?.object.userData.node || null);
    };

    onPointerLeave = () => {
        if (this.atlasEditorDrag) return;
        this.setAtlasHandleHover(null);
        this.canvas?.classList.remove("is-atlas-editor-hover");
        this.setNodeHover(null);
    };

    onPointerUp = event => this.finishAtlasEditorDrag(event);

    setNodeHover(node) {
        const previous = this.hoveredNode;
        this.hoveredNode = node;
        this.canvas?.classList.toggle("is-node-hover", Boolean(node));
        if (previous && previous.id !== node?.id && previous.id !== this.activeNode?.id) {
            const previousLabel = this.labelSprites.find(sprite => sprite.userData.node.id === previous.id);
            if (previousLabel) previousLabel.visible = false;
        }
        if (!node) {
            this.hoverLogo?.classList.remove("is-visible");
            this.hoverLabel?.classList.remove("is-visible");
            return;
        }
        if (!this.hoverLogo) {
            this.hoverLogo = document.createElement("img");
            this.hoverLogo.className = "graph-node-hover-logo";
            this.hoverLogo.src = "assets/graph/world-brain-node-hover.svg";
            this.hoverLogo.alt = "";
            this.hoverLogo.setAttribute("aria-hidden", "true");
            this.root.append(this.hoverLogo);
        }
        if (!this.hoverLabel) {
            this.hoverLabel = document.createElement("div");
            this.hoverLabel.className = "graph-node-hover-label";
            this.hoverLabel.setAttribute("aria-hidden", "true");
            this.root.append(this.hoverLabel);
        }
        this.hoverLabel.textContent = node.titel || node.title || node.id;
        const label = this.labelSprites.find(sprite => sprite.userData.node.id === node.id);
        if (label) label.visible = true;
        this.updateHoverLogoPosition();
        this.hoverLogo.classList.add("is-visible");
        this.hoverLabel.classList.add("is-visible");
    }

    updateHoverLogoPosition() {
        if (!this.hoveredNode || !this.hoverLogo || !this.camera || !this.canvas) return;
        const mesh = this.nodeMeshes.find(item => item.userData.node.id === this.hoveredNode.id);
        if (!mesh) return;
        /* Der Marker ist bewusst am Mittelpunkt des sichtbaren Knotens
         * verankert – nicht an der größeren unsichtbaren Trefferfläche. */
        const worldCenter = mesh.getWorldPosition(new THREE.Vector3());
        const point = worldCenter.clone().project(this.camera);
        const canvasBounds = this.canvas.getBoundingClientRect();
        const rootBounds = this.root.getBoundingClientRect();
        const offset = new THREE.Vector3(
            mesh.geometry.boundingSphere?.radius || 0.1,
            0,
            0
        ).applyQuaternion(mesh.getWorldQuaternion(new THREE.Quaternion()));
        const projectedEdge = worldCenter.clone().add(offset).project(this.camera);
        const nodeDiameter = Math.max(
            12,
            Math.min(34, Math.abs(projectedEdge.x - point.x) * canvasBounds.width * 2)
        );
        const left = canvasBounds.left - rootBounds.left + (point.x * .5 + .5) * canvasBounds.width;
        const top = canvasBounds.top - rootBounds.top + (-point.y * .5 + .5) * canvasBounds.height;
        this.hoverLogo.style.left = `${left}px`;
        this.hoverLogo.style.top = `${top}px`;
        this.hoverLogo.style.setProperty("--graph-node-marker-size", `${nodeDiameter}px`);
        if (this.hoverLabel) {
            this.hoverLabel.style.left = `${left}px`;
            this.hoverLabel.style.top = `${top - nodeDiameter / 2 - 8}px`;
        }
    }

    onContextLost = event => {
        event.preventDefault();
        this.root.dispatchEvent(new CustomEvent("vault-graph-3d-error", {
            bubbles: true,
            detail: { message: "WebGL-Kontext wurde verloren." }
        }));
    };

    onKeyDown = event => {
        if (event.key === "Home") {
            event.preventDefault();
            this.resetView();
        }
    };

    selectNode(node) {
        if (!node) return;
        this.activeNode = node;
        const related = new Set([node.id]);
        this.edgeVisuals.forEach(path => {
            if (path.userData.sourceId === node.id) related.add(path.userData.targetId);
            if (path.userData.targetId === node.id) related.add(path.userData.sourceId);
        });
        /* Knoten-Optik (Scale/Emissive/Glow/Shell/Halo/Dendriten) wird nicht
         * mehr hier einmalig gesetzt, sondern jeden Frame in
         * updateNeuralBackdrop() aus this.activeNode/this.selectedRelatedIds
         * berechnet ("Angleichen" – das Atmen läuft dabei gedimmt weiter). */
        this.selectedRelatedIds = related;
        this.edgeVisuals.forEach(path => {
            const isConnected = path.userData.sourceId === node.id || path.userData.targetId === node.id;
            path.material.color.set(isConnected ? 0xffc680 : 0x42caff);
            path.material.opacity = isConnected ? 0.92 : 0.08;
            /* Kamera-Fokus (Wunsch): Verbindungen des angeklickten Knotens
             * bleiben sichtbar, der Rest wird ausgeblendet statt nur gedimmt. */
            path.visible = isConnected;
        });
        /* Atlasblasen (Füllung/Grenze/Leuchtrand) auf Wunsch komplett
         * ausgeblendet, solange ein Knoten fokussiert ist – unabhängig von
         * einer eventuell gleichzeitig aktiven Regionsauswahl. clearSelection()
         * stellt die passende Opazität über setActiveVaultRegion() wieder her. */
        this.vaultRegionVolumes.forEach(room => {
            const { fill, boundary, glow } = room.userData;
            if (fill) fill.material.opacity = 0;
            if (boundary) boundary.material.opacity = 0;
            if (glow) glow.material.uniforms.uOpacity.value = 0;
        });
        this.setBrainTransparency(0.2);
        this.focusCameraOnNode(node);
        this.labelSprites.forEach(sprite => {
            sprite.visible = sprite.userData.node.id === node.id;
        });
        /* this.onSelect() (öffnet das Detail-Menü rechts) wird bewusst NICHT
         * mehr hier aufgerufen – ein einfacher Klick soll nur noch
         * fokussieren/hervorheben. Das Menü öffnet erst per Doppelklick,
         * siehe onNodeDoubleClick(). */
    }

    clearSelection() {
        if (!this.activeNode) return;
        this.activeNode = null;
        /* Siehe selectNode(): die Knoten-Optik entspannt sich von selbst über
         * die kontinuierliche Formel in updateNeuralBackdrop(), sobald
         * this.activeNode/this.selectedRelatedIds zurückgesetzt sind. */
        this.selectedRelatedIds = null;
        this.edgeVisuals.forEach(path => {
            path.material.color.set(
                path.userData.intraRegion
                    ? (this.vaultRegions()[path.userData.sourceRegion]?.color ?? 0x42caff)
                    : 0x42caff
            );
            path.material.opacity = path.userData.baseOpacity;
            path.visible = true;
        });
        this.labelSprites.forEach(sprite => { sprite.visible = false; });
        this.setActiveVaultRegion(this.activeVaultRegion, this.hasVaultRegionSelection);
    }

    focusCameraOnNode(node) {
        if (!this.camera || !this.controls) return;
        /* Statt eines Fixabstands zu nur einem Punkt: eine Begrenzungskugel
         * über den aktiven Knoten UND alle direkt verbundenen Nachbarn
         * (this.selectedRelatedIds, in selectNode() bereits gesetzt) – die
         * Kamera fährt so weit heraus, dass wirklich jede angezeigte
         * Verbindung im Bild bleibt, unabhängig davon wie weit die Nachbarn
         * im Raum verteilt sind. */
        const relatedIds = this.selectedRelatedIds || new Set([node.id]);
        const points = [];
        relatedIds.forEach(id => {
            const relatedMesh = this.nodeMeshes.find(mesh => mesh.userData.node.id === id);
            if (relatedMesh) points.push(relatedMesh.position);
        });
        if (!points.length) {
            const position = this.nodeMeshes.find(mesh => mesh.userData.node.id === node.id)?.position;
            if (position) points.push(position);
        }
        if (!points.length) return;

        const sphere = new THREE.Sphere();
        sphere.setFromPoints(points);
        const target = sphere.center;
        /* Untergrenze hält die Framing-Distanz für einen einzelnen bzw. eng
         * beieinanderliegende Knoten nahe am bisherigen Fixwert (7.6). */
        const radius = Math.max(sphere.radius, 1.8);

        const outward = target.clone().sub(this.brainCenter);
        if (outward.lengthSq() < 0.001) outward.copy(this.camera.position).sub(this.brainCenter);
        outward.normalize();

        const verticalFov = THREE.MathUtils.degToRad(this.camera.fov);
        const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * this.camera.aspect);
        const padding = 1.35;
        const distanceForHeight = radius / Math.sin(verticalFov / 2);
        const distanceForWidth = radius / Math.sin(horizontalFov / 2);
        const distance = THREE.MathUtils.clamp(
            Math.max(distanceForHeight, distanceForWidth) * padding,
            this.controls.minDistance + 1,
            this.controls.maxDistance - 1
        );

        const camera = target.clone().addScaledVector(outward, distance);
        /* Bei einem Knoten am Hirnstamm zeigt dessen Oberflächennormale nach
         * unten. Die Fokusfahrt wird trotzdem oberhalb des Podiums gehalten. */
        camera.y = Math.max(camera.y, target.y + Math.min(2.6, radius * 0.6), -1.2);
        this.cameraTransition = {
            startedAt: performance.now(),
            duration: 720,
            fromCamera: this.camera.position.clone(),
            fromTarget: this.controls.target.clone(),
            toCamera: camera,
            toTarget: target
        };
    }

    updateCameraTransition(now) {
        if (!this.cameraTransition || !this.camera || !this.controls) return;
        const transition = this.cameraTransition;
        const raw = Math.min(1, (now - transition.startedAt) / transition.duration);
        const eased = 1 - Math.pow(1 - raw, 3);
        this.camera.position.lerpVectors(transition.fromCamera, transition.toCamera, eased);
        this.controls.target.lerpVectors(transition.fromTarget, transition.toTarget, eased);
        if (raw >= 1) this.cameraTransition = null;
    }

    updateCameraRelativeBackground() {
        if (!this.neuralBackdropRoot || !this.camera) return;
        this.neuralBackdropRoot.position.copy(this.camera.position);
        this.neuralBackdropRoot.quaternion.copy(this.camera.quaternion);
    }

    setBrainTransparency(opacity) {
        this.surfaceMeshes.forEach(mesh => {
            const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
            materials.forEach(material => {
                if (!(material instanceof THREE.MeshStandardMaterial)) return;
                material.transparent = opacity < 1;
                material.opacity = opacity;
                material.depthWrite = opacity >= 1;
                material.needsUpdate = true;
            });
        });
    }

    applyFilter(value) {
        this.filter = value.trim().toLocaleLowerCase("de-DE");
        const matches = node => !this.filter || [node.id, node.titel, node.title, node.cluster, node.typ]
            .filter(Boolean).join(" ").toLocaleLowerCase("de-DE").includes(this.filter);
        this.nodeMeshes.forEach(mesh => {
            const visible = matches(mesh.userData.node);
            (mesh.userData.visuals || [mesh]).forEach(visual => {
                visual.visible = visible;
            });
        });
        this.labelSprites.forEach(sprite => {
            sprite.visible = matches(sprite.userData.node) && this.activeNode?.id === sprite.userData.node.id;
        });
        this.edgeVisuals.forEach(path => {
            const sourceNode = this.nodeVisuals.get(path.userData.sourceId)?.[2]?.userData.node;
            const targetNode = this.nodeVisuals.get(path.userData.targetId)?.[2]?.userData.node;
            const visible = !this.filter || (sourceNode && matches(sourceNode)) || (targetNode && matches(targetNode));
            path.visible = visible;
        });
    }

    resetView() {
        if (!this.camera || !this.controls) return;
        this.cameraTransition = null;
        this.camera.position.copy(this.homeCamera);
        this.controls.target.set(0, 0, 0);
        this.controls.update();
    }

    resize() {
        if (!this.renderer || !this.camera) return;
        const width = Math.max(this.root.clientWidth, 1);
        const height = Math.max(this.root.clientHeight, 1);
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height, false);
        if (this.bloomComposer) this.bloomComposer.setSize(width, height);
        if (this.finalComposer) this.finalComposer.setSize(width, height);
        if (this.bloomPass) this.bloomPass.resolution.set(width, height);
    }

    /* Selektives Bloom, Hilfsfunktionen für die Bloom-Passage: Material
     * jedes Objekts, das NICHT auf BLOOM_LAYER liegt, kurzzeitig gegen ein
     * schwarzes Material desselben Objekttyps tauschen (Sprite/Points/Line/
     * Mesh je eigenes Dark-Material, da der Renderer je nach Objekttyp
     * bestimmte Material-Eigenschaften erwartet). Die Tiefeninformation
     * bleibt dadurch erhalten – Nodes hinter dem Gehirn-Mesh werden vom
     * Bloom-Pass weiterhin korrekt verdeckt. */
    darkenNonBloomed(object) {
        if (!object.material || this.bloomLayer.test(object.layers)) return;
        this.bloomMaterialCache.set(object, object.material);
        if (object.isSprite) object.material = this.darkSpriteMaterial;
        else if (object.isPoints) object.material = this.darkPointsMaterial;
        else if (object.isLine) object.material = this.darkLineMaterial;
        else object.material = this.darkMaterial;
    }

    restoreBloomMaterial(object) {
        const original = this.bloomMaterialCache.get(object);
        if (!original) return;
        object.material = original;
        this.bloomMaterialCache.delete(object);
    }

    start() {
        this.stopped = false;
        const animate = () => {
            if (this.stopped) return;
            this.frame = requestAnimationFrame(animate);
            const now = performance.now();
            const delta = Math.min((now - this.lastFrameTime) / 1000 || 0, 0.05);
            this.lastFrameTime = now;
            this.updateNeuralBackdrop(delta);
            this.updateCameraTransition(now);
            this.controls?.update();
            this.updateCameraRelativeBackground();
            this.updateHoverLogoPosition();
            if (this.bloomComposer && this.finalComposer) {
                this.scene.traverse(object => this.darkenNonBloomed(object));
                this.bloomComposer.render();
                this.scene.traverse(object => this.restoreBloomMaterial(object));
                this.finalComposer.render();
            } else {
                this.renderer?.render(this.scene, this.camera);
            }
        };
        animate();
    }

    dispose() {
        this.stopped = true;
        if (this.frame) cancelAnimationFrame(this.frame);
        this.resizeObserver?.disconnect();
        this.canvas?.removeEventListener("pointerdown", this.onPointerDown);
        this.canvas?.removeEventListener("pointermove", this.onPointerMove);
        this.canvas?.removeEventListener("pointerleave", this.onPointerLeave);
        this.canvas?.removeEventListener("pointerup", this.onPointerUp);
        this.canvas?.removeEventListener("pointercancel", this.onPointerUp);
        this.canvas?.removeEventListener("dblclick", this.onNodeDoubleClick);
        this.canvas?.removeEventListener("webglcontextlost", this.onContextLost);
        this.disposeAtlasEditorGizmo();
        this.hoverLogo?.remove();
        this.hoverLogo = null;
        this.hoverLabel?.remove();
        this.hoverLabel = null;
        window.removeEventListener("keydown", this.onKeyDown);
        this.controls?.dispose();
        this.brainContainmentMeshes.forEach(mesh => mesh.material?.dispose?.());
        this.brainContainmentMeshes = [];
        if (this.neuralBackdropRoot) {
            this.neuralBackdropRoot.traverse(object => {
                object.geometry?.dispose?.();
                const material = object.material;
                if (Array.isArray(material)) material.forEach(item => item.dispose?.());
                else material?.dispose?.();
            });
            this.scene?.remove(this.neuralBackdropRoot);
        }
        this.scene?.traverse(object => {
            if (object.geometry) object.geometry.dispose?.();
            const material = object.material;
            if (Array.isArray(material)) material.forEach(item => item.dispose?.());
            else material?.dispose?.();
        });
        this.bloomComposer?.dispose?.();
        this.bloomComposer = null;
        this.finalComposer?.dispose?.();
        this.finalComposer = null;
        this.bloomPass = null;
        this.darkMaterial?.dispose?.();
        this.darkMaterial = null;
        this.darkSpriteMaterial?.dispose?.();
        this.darkSpriteMaterial = null;
        this.darkLineMaterial?.dispose?.();
        this.darkLineMaterial = null;
        this.darkPointsMaterial?.dispose?.();
        this.darkPointsMaterial = null;
        this.bloomMaterialCache.clear();
        this.selectedRelatedIds = null;
        this.renderer?.dispose();
        this.nodeMeshes = [];
        this.nodeByMesh.clear();
        this.nodeVisuals.clear();
        this.edgeVisuals = [];
        this.edgePaths = [];
        this.edgeSignals = null;
        this.pulseGeometry = null;
        this.cameraTransition = null;
        this.neuralBackdropRoot = null;
        this.vaultRegionVolumes = [];
        this.vaultRegionRooms.clear();
        this.vaultRegionVolumeGroup = null;
        this.corticalAtlasGroup = null;
        this.corticalAtlasMaterial = null;
        this.corticalAtlasMaterials = [];
        this.corticalVolumeGroup = null;
        this.activeVaultRegion = null;
        this.hasVaultRegionSelection = false;
        this.regionMenu = null;
        this.labelSprites = [];
        this.webglVersion = null;
        this.canvas = null;
        this.frame = null;
    }

    colorFor(cluster) {
        const palette = [0x36d5ff, 0xbb76ff, 0x00e5a0, 0xffbd3d, 0xff6e9d, 0x49d8d2, 0xa6e35b, 0xff876e];
        let hash = 0;
        for (let index = 0; index < cluster.length; index += 1) hash = (hash * 31 + cluster.charCodeAt(index)) >>> 0;
        return palette[hash % palette.length];
    }

    shorten(value, limit) {
        return value.length > limit ? value.slice(0, limit - 1) + "…" : value;
    }
}

function installMethodGroups(target, ...groups) {
    for (const group of groups) {
        for (const name of Object.getOwnPropertyNames(group.prototype)) {
            if (name === "constructor") continue;
            Object.defineProperty(
                target.prototype,
                name,
                Object.getOwnPropertyDescriptor(group.prototype, name)
            );
        }
    }
}

installMethodGroups(
    VaultGraph3DExplorer,
    VaultGraphGraphMethods,
    VaultGraphAtlasMethods,
    VaultGraphEnvironmentMethods
);

window.VaultGraph3DExplorer = VaultGraph3DExplorer;
