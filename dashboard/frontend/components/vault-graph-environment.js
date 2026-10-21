import * as THREE from "three";

export class VaultGraphEnvironmentMethods {
    addLabel(node, position, color) {
        const label = document.createElement("canvas");
        label.width = 512;
        label.height = 64;
        const context = label.getContext("2d");
        context.font = "600 28px Arial";
        context.textAlign = "center";
        context.lineJoin = "round";
        context.lineWidth = 7;
        context.strokeStyle = "rgba(4, 10, 22, .9)";
        context.fillStyle = "#e4f6ff";
        const text = this.shorten(node.titel || node.title || node.id, 31);
        context.strokeText(text, 256, 39);
        context.fillText(text, 256, 39);
        const texture = new THREE.CanvasTexture(label);
        texture.colorSpace = THREE.SRGBColorSpace;
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false }));
        /* Beschriftungen liegen als lesbare Ebene oberhalb ihres Knotens –
         * unabhängig davon, in welche Cortexrichtung die Oberfläche zeigt. */
        sprite.position.copy(position).add(new THREE.Vector3(0, 1.18, 0));
        sprite.scale.set(3.8, 0.48, 1);
        sprite.userData = { node, basePosition: position.clone() };
        sprite.visible = false;
        this.scene.add(sprite);
        this.labelSprites.push(sprite);
    }

    buildNeuralBackdrop() {
        /*
         * Hintergrund als wenige GPU-Objekte, nicht als hunderte Meshes:
         * Sternenfeld, Knoten, Linien, bewegte Signale, Ringe und Wellen.
         * Die Mitte bleibt bewusst frei – dort hat das Gehirn Priorität.
         */
        const group = new THREE.Group();
        group.name = "SecBrain-Neuraler-Hintergrund";
        /* Kamerarelativ: Das dekorative, animierte Umfeld bleibt hinter der
         * aktuellen Ansicht. Gehirn, Bühne und Vault-Graph bleiben dagegen
         * echte Weltobjekte und behalten ihre räumliche Orientierung. */
        this.scene.add(group);
        this.neuralBackdropRoot = group;

        const stars = [];
        const starColors = [];
        const cyan = new THREE.Color(0x21d8ff);
        const violet = new THREE.Color(0xb65cff);
        const rose = new THREE.Color(0xff5bc9);
        for (let index = 0; index < 1280; index += 1) {
            const angle = Math.random() * Math.PI * 2;
            const radius = 16 + Math.pow(Math.random(), 0.52) * 43;
            const x = Math.cos(angle) * radius;
            const y = (Math.random() - 0.5) * 34;
            const z = -13 - Math.random() * 24;
            stars.push(x, y, z);
            const color = Math.random() < 0.13 ? rose : (Math.random() < 0.28 ? violet : cyan);
            starColors.push(color.r, color.g, color.b);
        }
        const starGeometry = new THREE.BufferGeometry();
        starGeometry.setAttribute("position", new THREE.Float32BufferAttribute(stars, 3));
        starGeometry.setAttribute("color", new THREE.Float32BufferAttribute(starColors, 3));
        this.neuralField = new THREE.Points(starGeometry, new THREE.PointsMaterial({
            map: this.makeGlowTexture(),
            size: 0.24,
            vertexColors: true,
            transparent: true,
            opacity: 0.76,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }));
        this.neuralField.renderOrder = -14;
        group.add(this.neuralField);

        const hubs = [];
        const hubColors = [];
        const hubPoints = [];
        for (let index = 0; index < 108; index += 1) {
            const side = index % 2 === 0 ? -1 : 1;
            const x = side * (10 + Math.random() * 36);
            const y = (Math.random() - 0.5) * 32;
            const z = -10 - Math.random() * 16;
            const point = new THREE.Vector3(x, y, z);
            hubPoints.push(point);
            hubs.push(x, y, z);
            const color = Math.random() < 0.22 ? rose : cyan;
            hubColors.push(color.r, color.g, color.b);
        }
        const hubGeometry = new THREE.BufferGeometry();
        hubGeometry.setAttribute("position", new THREE.Float32BufferAttribute(hubs, 3));
        hubGeometry.setAttribute("color", new THREE.Float32BufferAttribute(hubColors, 3));
        this.neuralHubs = new THREE.Points(hubGeometry, new THREE.PointsMaterial({
            map: this.makeGlowTexture(),
            size: 0.78,
            vertexColors: true,
            transparent: true,
            opacity: 0.96,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }));
        this.neuralHubs.renderOrder = -13;
        group.add(this.neuralHubs);

        const linkPositions = [];
        for (let index = 0; index < hubPoints.length; index += 1) {
            const source = hubPoints[index];
            const nearest = hubPoints
                .map((point, target) => ({ point, target, distance: point.distanceTo(source) }))
                .filter(item => item.target !== index && item.distance < 15)
                .sort((a, b) => a.distance - b.distance)
                .slice(0, 3);
            nearest.forEach(item => {
                if (item.target < index) return;
                linkPositions.push(source.x, source.y, source.z, item.point.x, item.point.y, item.point.z);
                if (this.signalPaths.length < 160) {
                    this.signalPaths.push({ from: source.clone(), to: item.point.clone(), progress: Math.random(), speed: 0.1 + Math.random() * 0.22 });
                }
            });
        }
        const linkGeometry = new THREE.BufferGeometry();
        linkGeometry.setAttribute("position", new THREE.Float32BufferAttribute(linkPositions, 3));
        this.neuralLinks = new THREE.LineSegments(linkGeometry, new THREE.LineBasicMaterial({
            color: 0x168ec8,
            transparent: true,
            opacity: 0.36,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }));
        this.neuralLinks.renderOrder = -12;
        group.add(this.neuralLinks);

        const signalGeometry = new THREE.BufferGeometry();
        signalGeometry.setAttribute("position", new THREE.Float32BufferAttribute(this.signalPaths.length * 3, 3));
        this.neuralSignals = new THREE.Points(signalGeometry, new THREE.PointsMaterial({
            map: this.makeGlowTexture(),
            color: 0xdffbff,
            size: 0.44,
            transparent: true,
            opacity: 0.95,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }));
        this.neuralSignals.renderOrder = -11;
        group.add(this.neuralSignals);

        const ringPositions = [];
        for (let ring = 0; ring < 14; ring += 1) {
            const radius = 6.4 + ring * 1.16;
            for (let segment = 0; segment < 100; segment += 1) {
                if ((segment + ring * 3) % 9 === 0) continue;
                const a = segment / 100 * Math.PI * 2;
                const b = (segment + 1) / 100 * Math.PI * 2;
                ringPositions.push(Math.cos(a) * radius, Math.sin(a) * radius, -13.5, Math.cos(b) * radius, Math.sin(b) * radius, -13.5);
            }
        }
        const ringGeometry = new THREE.BufferGeometry();
        ringGeometry.setAttribute("position", new THREE.Float32BufferAttribute(ringPositions, 3));
        this.neuralRings = new THREE.LineSegments(ringGeometry, new THREE.LineBasicMaterial({
            color: 0x185bbd,
            transparent: true,
            opacity: 0.22,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }));
        this.neuralRings.renderOrder = -12;
        group.add(this.neuralRings);

        const wavePositions = [];
        const waveColors = [];
        for (let xIndex = 0; xIndex < 96; xIndex += 1) {
            for (let zIndex = 0; zIndex < 38; zIndex += 1) {
                const x = (xIndex / 95 - 0.5) * 58;
                const z = (zIndex / 37 - 0.5) * 27;
                if (Math.abs(x) < 10 && Math.abs(z) < 8) continue;
                const edge = Math.min(1, Math.abs(x) / 29);
                wavePositions.push(x, -8.5, z - 8);
                waveColors.push(0.02 + edge * 0.7, 0.25 + edge * 0.05, 0.58 + edge * 0.28);
            }
        }
        this.waveBase = new Float32Array(wavePositions);
        const waveGeometry = new THREE.BufferGeometry();
        waveGeometry.setAttribute("position", new THREE.BufferAttribute(this.waveBase.slice(), 3));
        waveGeometry.setAttribute("color", new THREE.Float32BufferAttribute(waveColors, 3));
        this.waveField = new THREE.Points(waveGeometry, new THREE.PointsMaterial({
            size: 0.09,
            vertexColors: true,
            transparent: true,
            opacity: 0.52,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }));
        this.waveField.renderOrder = -10;
        group.add(this.waveField);

        /* Wenige starke Lichtknoten bilden die visuellen Anker der Referenz. */
        hubPoints
            .filter((_, index) => index % 6 === 0)
            .slice(0, 18)
            .forEach((point, index) => {
                const burst = new THREE.Sprite(new THREE.SpriteMaterial({
                    map: this.makeGlowTexture(),
                    color: index % 4 === 0 ? 0xff63d1 : 0x28d9ff,
                    transparent: true,
                    opacity: 0.92,
                    blending: THREE.AdditiveBlending,
                    depthWrite: false
                }));
                burst.position.copy(point);
                burst.scale.setScalar(index % 5 === 0 ? 2.15 : 1.36);
                burst.renderOrder = -11;
                group.add(burst);
                this.neuralBursts.push(burst);
            });

        /* Datenströme am Boden: ein kombiniertes Linienobjekt für alle Bahnen. */
        const flowPositions = [];
        for (let stream = 0; stream < 88; stream += 1) {
            const side = stream % 2 === 0 ? -1 : 1;
            const startX = side * (7.5 + Math.random() * 24);
            const startZ = -13 + Math.random() * 15;
            const length = 16 + Math.random() * 28;
            let previous = new THREE.Vector3(startX, -8.25, startZ);
            for (let segment = 1; segment <= 28; segment += 1) {
                const progress = segment / 28;
                const x = startX + side * progress * length;
                const z = startZ + Math.sin(progress * 7 + stream) * 1.5 + progress * 9;
                const y = -8.28 + Math.sin(progress * 9 + stream * 0.5) * 0.15;
                const next = new THREE.Vector3(x, y, z);
                flowPositions.push(previous.x, previous.y, previous.z, next.x, next.y, next.z);
                previous = next;
            }
        }
        const flowGeometry = new THREE.BufferGeometry();
        flowGeometry.setAttribute("position", new THREE.Float32BufferAttribute(flowPositions, 3));
        this.flowLines = new THREE.LineSegments(flowGeometry, new THREE.LineBasicMaterial({
            color: 0x1aaeff,
            transparent: true,
            opacity: 0.27,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }));
        this.flowLines.renderOrder = -9;
        group.add(this.flowLines);
    }

    makeGlowTexture() {
        const canvas = document.createElement("canvas");
        canvas.width = 96;
        canvas.height = 96;
        const context = canvas.getContext("2d");
        /* Neutral-weißer Verlauf, 1:1 aus der Neural-Graph-Demo — die
         * Tönung entsteht ausschließlich über die Sprite-`color`, nicht
         * bereits in der Textur selbst. */
        const gradient = context.createRadialGradient(48, 48, 0, 48, 48, 48);
        gradient.addColorStop(0.00, "rgba(255,255,255,1)");
        gradient.addColorStop(0.14, "rgba(255,255,255,0.72)");
        gradient.addColorStop(0.35, "rgba(255,255,255,0.20)");
        gradient.addColorStop(0.65, "rgba(255,255,255,0.045)");
        gradient.addColorStop(1.00, "rgba(255,255,255,0)");
        context.fillStyle = gradient;
        context.fillRect(0, 0, 96, 96);
        const texture = new THREE.CanvasTexture(canvas);
        texture.colorSpace = THREE.SRGBColorSpace;
        return texture;
    }

    updateNeuralBackdrop(delta) {
        this.backdropTime += delta;
        if (this.neuralField) this.neuralField.material.opacity = 0.66 + Math.sin(this.backdropTime * 0.42) * 0.12;
        if (this.neuralHubs) this.neuralHubs.material.size = 0.5 + Math.sin(this.backdropTime * 1.3) * 0.08;
        if (this.neuralLinks) this.neuralLinks.material.opacity = 0.23 + Math.sin(this.backdropTime * 0.34) * 0.08;
        if (this.neuralRings) {
            this.neuralRings.rotation.z += delta * 0.018;
            this.neuralRings.material.opacity = 0.17 + Math.sin(this.backdropTime * 0.48) * 0.07;
        }
        this.neuralBursts.forEach((burst, index) => {
            const scale = (index % 5 === 0 ? 2.15 : 1.36) * (0.86 + Math.sin(this.backdropTime * 1.25 + index) * 0.14);
            burst.scale.setScalar(scale);
            burst.material.opacity = 0.66 + Math.sin(this.backdropTime * 1.4 + index) * 0.2;
        });
        if (this.flowLines) this.flowLines.material.opacity = 0.2 + Math.sin(this.backdropTime * 0.55) * 0.09;
        if (this.neuralSignals) {
            const positions = this.neuralSignals.geometry.getAttribute("position").array;
            this.signalPaths.forEach((path, index) => {
                path.progress = (path.progress + path.speed * delta) % 1;
                positions[index * 3] = THREE.MathUtils.lerp(path.from.x, path.to.x, path.progress);
                positions[index * 3 + 1] = THREE.MathUtils.lerp(path.from.y, path.to.y, path.progress);
                positions[index * 3 + 2] = THREE.MathUtils.lerp(path.from.z, path.to.z, path.progress);
            });
            this.neuralSignals.geometry.getAttribute("position").needsUpdate = true;
            this.neuralSignals.material.size = 0.28 + Math.sin(this.backdropTime * 2.1) * 0.07;
        }
        if (this.waveField && this.waveBase) {
            const positions = this.waveField.geometry.getAttribute("position").array;
            for (let index = 0; index < positions.length; index += 3) {
                positions[index + 1] = this.waveBase[index + 1]
                    + Math.sin(this.waveBase[index] * 0.16 + this.backdropTime * 1.15) * 0.25
                    + Math.cos(this.waveBase[index + 2] * 0.25 - this.backdropTime * 0.75) * 0.13;
            }
            this.waveField.geometry.getAttribute("position").needsUpdate = true;
        }
        this.stageRings.forEach((ring, index) => {
            ring.rotation.z += delta * (index % 2 === 0 ? 0.045 : -0.026);
            ring.material.opacity = 0.3 + Math.sin(this.backdropTime * 1.1 + index) * 0.14;
        });
        if (this.stageCore) {
            const scale = 0.95 + Math.sin(this.backdropTime * 1.4) * 0.06;
            this.stageCore.scale.setScalar(scale);
            this.stageCore.material.opacity = 0.76 + Math.sin(this.backdropTime * 1.6) * 0.15;
        }
        if (this.stageBeam) this.stageBeam.material.opacity = 0.22 + Math.sin(this.backdropTime * 0.95) * 0.09;
        /* Vereinheitlichte, durchgehende Knoten-Optik (Angleichen): Atmen/Glühen
         * läuft jetzt IMMER, auch während eine Auswahl aktiv ist – nur gedimmt
         * statt komplett auszusetzen. selectNode()/clearSelection()/
         * setActiveVaultRegion() setzen dafür nur noch this.activeNode,
         * this.selectedRelatedIds und this.activeVaultRegion; die eigentlichen
         * Zieltier-Werte (unverändert aus den bisherigen Funktionen
         * übernommen) werden hier jeden Frame neu berechnet. */
        this.nodeMeshes.forEach(mesh => {
            mesh.userData.neuralCharge = Math.max(0, (mesh.userData.neuralCharge || 0) - delta * 1.25);
            const wave = 0.5 + Math.sin(this.backdropTime * 1.55 + mesh.userData.neuralPhase) * 0.5;
            const charge = mesh.userData.neuralCharge;
            const [glow, shell, , halo] = mesh.userData.visuals || [];
            const nodeId = mesh.userData.node?.id;

            let scaleBase, emissiveBase, opacityBase, transparentBase;
            let glowScaleMult, glowOpacityBase, shellScaleMult, shellOpacityBase, haloOpacityBase;
            let dendriteLineBase, dendriteTipBase, breatheScale;

            if (this.activeNode) {
                const isActive = nodeId === this.activeNode.id;
                const isRelated = this.selectedRelatedIds ? this.selectedRelatedIds.has(nodeId) : isActive;
                /* Wunsch: Knoten ohne Verbindung zum angeklickten Knoten werden
                 * komplett ausgeblendet statt nur gedimmt – dieselbe .visible-
                 * Klemme wie bei den Dendriten/Kanten, unabhängig von den
                 * Wave-/Charge-Zuschlägen weiter unten. */
                mesh.visible = isRelated;
                if (glow) glow.visible = isRelated;
                if (shell) shell.visible = isRelated;
                if (halo) halo.visible = isRelated;
                if (mesh.userData.dendrites) mesh.userData.dendrites.visible = isRelated;
                scaleBase = isActive ? 1.7 : 1.18;
                emissiveBase = isActive ? 3.2 : 1.7;
                opacityBase = 1;
                transparentBase = false;
                glowScaleMult = isActive ? 1.45 : 1.08;
                glowOpacityBase = isActive ? 1 : 0.72;
                shellScaleMult = isActive ? 1.3 : 1;
                shellOpacityBase = isActive ? 0.42 : 0.12;
                haloOpacityBase = isActive ? 0.18 : 0.06;
                dendriteLineBase = isActive ? 0.92 : 0.58;
                dendriteTipBase = isActive ? 1 : 0.72;
                breatheScale = 0.22;
            } else if (this.activeVaultRegion) {
                /* Aus einer Knotenauswahl zurückkehrend müssen zuvor
                 * ausgeblendete Knoten wieder sichtbar werden. */
                mesh.visible = true;
                if (glow) glow.visible = true;
                if (shell) shell.visible = true;
                if (halo) halo.visible = true;
                if (mesh.userData.dendrites) mesh.userData.dendrites.visible = true;
                const regionSelected = mesh.userData.vaultRegion === this.activeVaultRegion;
                /* emissiveIntensity ist der eigentliche Bloom-Auslöser: Der
                 * Soma selbst (nicht nur der Glow-Sprite) liegt bei 2.35 weit
                 * über der Bloom-Schwelle und verschmilzt dadurch mit eng
                 * benachbarten Knoten zu einem Klumpen – unabhängig von der
                 * Glow-Sprite-Größe. Reduziert auf einen Wert, der noch klar
                 * heller als der Ruhezustand ist, aber nicht mehr blüht. */
                scaleBase = regionSelected ? 1.12 : 1;
                emissiveBase = regionSelected ? 1.5 : 0.22;
                opacityBase = regionSelected ? 1 : 0.1;
                transparentBase = !regionSelected;
                /* Glow-Werte der Regionsauswahl bewusst unter den ursprüng-
                 * lichen 1.3/0.95 gehalten: mit dem neuen, größeren Glow-
                 * Sprite und dem neuen Bloom-Pass verschmelzen sonst eng
                 * beieinanderliegende Knoten einer Blase zu einem Klumpen. */
                glowScaleMult = regionSelected ? 1.05 : 1;
                glowOpacityBase = regionSelected ? 0.5 : 0.035;
                shellScaleMult = regionSelected ? 1.18 : 1;
                shellOpacityBase = regionSelected ? 0.28 : 0.025;
                haloOpacityBase = regionSelected ? 0.045 : 0.006;
                dendriteLineBase = regionSelected ? 0.62 : 0.025;
                dendriteTipBase = regionSelected ? 0.82 : 0.035;
                breatheScale = 0.3;
            } else {
                mesh.visible = true;
                if (glow) glow.visible = true;
                if (shell) shell.visible = true;
                if (halo) halo.visible = true;
                if (mesh.userData.dendrites) mesh.userData.dendrites.visible = true;
                scaleBase = 1;
                emissiveBase = 1.05;
                opacityBase = 1;
                transparentBase = false;
                glowScaleMult = 1;
                glowOpacityBase = 0.48;
                shellScaleMult = 1;
                shellOpacityBase = 0.25;
                haloOpacityBase = 0.03;
                dendriteLineBase = 0.48;
                dendriteTipBase = 0.68;
                breatheScale = 1;
            }

            mesh.scale.setScalar(scaleBase);
            mesh.material.emissiveIntensity = emissiveBase + wave * 0.38 * breatheScale + charge * 1.8;
            mesh.material.opacity = opacityBase;
            mesh.material.transparent = transparentBase;
            if (glow) {
                glow.scale.setScalar(glow.userData.baseScale * glowScaleMult * (1 + wave * 0.05 * breatheScale + charge * 0.22));
                glow.material.opacity = glowOpacityBase + wave * 0.12 * breatheScale + charge * 0.3;
            }
            if (shell) {
                shell.scale.setScalar(shell.userData.baseScale * shellScaleMult);
                shell.material.opacity = shellOpacityBase + wave * 0.12 * breatheScale + charge * 0.28;
            }
            if (halo) halo.material.opacity = haloOpacityBase + wave * 0.025 * breatheScale + charge * 0.1;
            const dendrites = mesh.userData.dendrites;
            if (dendrites?.userData?.lines) {
                dendrites.userData.lines.material.opacity = dendriteLineBase + wave * 0.16 * breatheScale + charge * 0.2;
            }
            if (dendrites?.userData?.tips) {
                dendrites.userData.tips.material.opacity = dendriteTipBase + wave * 0.16 * breatheScale + charge * 0.12;
            }

            /* Phase 2: Nur der Zellkörper (Soma/Cage/Halo/Glow) wackelt leicht
             * innerhalb seiner Atlasblase; die bereits gewachsenen Dendriten,
             * die Hit-Area und das Label bleiben unverändert an Ort und
             * Stelle. Die Kandidatenposition wird jeden Frame über die
             * bestehende clampToAtlasBubble() zurück in die Blase geklemmt,
             * damit der Knoten sie nie verlassen kann. */
            if (mesh.userData.wanderBase) {
                const base = mesh.userData.wanderBase;
                const t = this.backdropTime;
                const room = mesh.userData.wanderRoom;
                /* Die Wander-Amplitude ist proportional zur Blasengröße statt
                 * eines winzigen Fixwerts – sonst ist die Bewegung bei den
                 * deutlich größeren Atlasblasen praktisch unsichtbar. Der
                 * Knoten nutzt so spürbar mehr vom freien Raum der Blase,
                 * bleibt über clampToAtlasBubble() aber weiterhin sicher
                 * darin eingeschlossen. */
                const amplitude = room?.radii
                    ? Math.min(room.radii.x, room.radii.y, room.radii.z) * 0.16
                    : 0.14;
                const candidate = this._wanderCandidate || (this._wanderCandidate = new THREE.Vector3());
                candidate.set(
                    base.x + Math.sin(t * 0.62 + mesh.userData.wanderSeedX * 6.28318) * amplitude,
                    base.y + Math.sin(t * 0.51 + mesh.userData.wanderSeedY * 6.28318 + 2.1) * amplitude,
                    base.z + Math.sin(t * 0.57 + mesh.userData.wanderSeedZ * 6.28318 + 4.2) * amplitude
                );
                if (room) {
                    /* Gleicher Grenzwert (0.8) wie bei der Erstplatzierung in
                     * createInteriorPositions() – sonst würde dieser Clamp die
                     * jetzt weiter außen platzierten Knoten jeden Frame wieder
                     * nach innen ziehen. */
                    this.clampToAtlasBubble(candidate, room, 0.8);
                }
                mesh.position.copy(candidate);
                if (shell) shell.position.copy(candidate);
                if (halo) halo.position.copy(candidate);
                if (glow) {
                    glow.position.copy(candidate);
                    if (mesh.userData.wanderDirection) {
                        glow.position.addScaledVector(mesh.userData.wanderDirection, 0.025);
                    }
                }
            }
        });
        /* Diskrete Signal-Pakete je Axon – 1:1 aus der Demo: eigener
         * Feuer-Countdown pro Kante, kein Deckel auf eine Kantenzahl. Die
         * Kanten-Grundopazität (baseOpacity) bleibt unangetastet, damit die
         * bestehende Klick-Hervorhebung in selectNode()/clearSelection()/
         * setActiveVaultRegion() nicht überschrieben wird. */
        const pulseScratch = this._pulseScratch || (this._pulseScratch = new THREE.Vector3());
        this.edgePaths.forEach(axon => {
            /* Ausgeblendete Kanten (Knotenauswahl: keine Verbindung zum
             * angeklickten Knoten) feuern keine neuen Signal-Pakete und
             * bereits unterwegs befindliche werden mitversteckt. */
            const edgeActive = axon.tube.visible;
            if (edgeActive) {
                axon.nextFire -= delta;
                if (axon.nextFire <= 0) {
                    this.spawnAxonPulse(axon, Math.random() > 0.5);
                    axon.nextFire = 2.5 + Math.random() * 6.5;
                }
            }
            for (let index = axon.pulses.length - 1; index >= 0; index -= 1) {
                const pulse = axon.pulses[index];
                pulse.group.visible = edgeActive;
                pulse.t += delta * pulse.speed;
                if (pulse.t >= 1) {
                    if (pulse.target) {
                        pulse.target.userData.neuralCharge = Math.min(
                            1.3,
                            (pulse.target.userData.neuralCharge || 0) + 0.9
                        );
                    }
                    this.graphPathGroup?.remove(pulse.group);
                    pulse.group.children.forEach(child => child.material?.dispose?.());
                    axon.pulses.splice(index, 1);
                    continue;
                }
                axon.curve.getPointAt(pulse.forward ? pulse.t : 1 - pulse.t, pulseScratch);
                pulse.group.position.copy(pulseScratch);
                pulse.group.scale.setScalar(0.7 + Math.sin(pulse.t * Math.PI) * 0.6);
                pulse.halo.material.opacity = 0.9;
            }
        });
    }

    addStage() {
        const base = new THREE.Mesh(
            new THREE.CylinderGeometry(9.3, 10.4, 1.15, 96),
            new THREE.MeshStandardMaterial({ color: 0x03070e, metalness: 0.92, roughness: 0.2 })
        );
        base.position.y = -8.9;
        this.scene.add(base);

        const upper = new THREE.Mesh(
            new THREE.CylinderGeometry(8.65, 9.35, 0.42, 96),
            new THREE.MeshStandardMaterial({ color: 0x07192b, metalness: 0.86, roughness: 0.23 })
        );
        upper.position.y = -8.15;
        this.scene.add(upper);

        for (let index = 0; index < 7; index += 1) {
            const ring = new THREE.Mesh(
                new THREE.TorusGeometry(3.1 + index * 0.83, index === 0 ? 0.07 : 0.025, 8, 96),
                new THREE.MeshBasicMaterial({ color: index % 3 === 0 ? 0x9a54ff : 0x23c8ff, transparent: true, opacity: index === 0 ? 0.88 : 0.48, blending: THREE.AdditiveBlending, depthWrite: false })
            );
            ring.rotation.x = Math.PI / 2;
            ring.position.y = -7.9 + index * 0.018;
            this.scene.add(ring);
            this.stageRings.push(ring);
        }

        const core = new THREE.Mesh(
            new THREE.CircleGeometry(3.2, 96),
            new THREE.MeshBasicMaterial({ map: this.makeHologramTexture(), transparent: true, opacity: 0.92, blending: THREE.AdditiveBlending, depthWrite: false })
        );
        core.rotation.x = -Math.PI / 2;
        core.position.y = -7.88;
        this.scene.add(core);
        this.stageCore = core;

        const beam = new THREE.Mesh(
            new THREE.CylinderGeometry(3.15, 1.05, 6.8, 48, 1, true),
            new THREE.MeshBasicMaterial({ map: this.makeBeamTexture(), color: 0x3acaff, transparent: true, opacity: 0.31, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false })
        );
        beam.position.y = -5.35;
        this.scene.add(beam);
        this.stageBeam = beam;
    }

    makeHologramTexture() {
        const canvas = document.createElement("canvas");
        canvas.width = 256;
        canvas.height = 256;
        const context = canvas.getContext("2d");
        const gradient = context.createRadialGradient(128, 128, 0, 128, 128, 128);
        gradient.addColorStop(0, "rgba(238,255,255,1)");
        gradient.addColorStop(0.08, "rgba(81,225,255,.95)");
        gradient.addColorStop(0.32, "rgba(24,150,255,.42)");
        gradient.addColorStop(0.67, "rgba(43,80,255,.1)");
        gradient.addColorStop(1, "rgba(0,30,110,0)");
        context.fillStyle = gradient;
        context.fillRect(0, 0, 256, 256);
        return new THREE.CanvasTexture(canvas);
    }

    makeBeamTexture() {
        const canvas = document.createElement("canvas");
        canvas.width = 4;
        canvas.height = 256;
        const context = canvas.getContext("2d");
        const gradient = context.createLinearGradient(0, 0, 0, 256);
        gradient.addColorStop(0, "rgba(255,255,255,0)");
        gradient.addColorStop(0.4, "rgba(130,231,255,.08)");
        gradient.addColorStop(0.82, "rgba(98,220,255,.48)");
        gradient.addColorStop(1, "rgba(0,120,255,0)");
        context.fillStyle = gradient;
        context.fillRect(0, 0, 4, 256);
        return new THREE.CanvasTexture(canvas);
    }

}
