import * as THREE from "three";
import { BLOOM_LAYER } from "./vault-graph-constants.js";

export class VaultGraphGraphMethods {
    buildGraph() {
        const nodes = this.graph.nodes || [];
        const edges = this.graph.edges || [];
        const nodeDataById = new Map(nodes.map(node => [node.id, node]));
        const positions = this.createInteriorPositions(nodes);
        const meshByNodeId = new Map();
        const nodeGroup = new THREE.Group();
        nodeGroup.name = "SecBrain-Graphknoten";
        this.scene.add(nodeGroup);
        this.graphNodeGroup = nodeGroup;

        for (const node of nodes) {
            const position = positions.get(node.id);
            if (!position) continue;
            const folder = this.vaultFolderFor(node);
            const color = this.vaultRegions()[folder]?.color ?? this.colorFor(folder);
            const radius = Math.max(0.105, Math.min(0.19, 0.105 + Number(node.grad || 0) * 0.009));
            const direction = position.clone().sub(this.brainCenter).normalize();
            const room = this.vaultRegionRooms.get(folder);
            /* Optik der Soma-/Glow-/Cage-/Halo-Schicht ist 1:1 aus der
             * Neural-Graph-Demo übernommen (secbrain-neural-graph.html). Die
             * Positions-Offsets (glow entlang `direction`, alle Schichten an
             * `position`) bleiben eine Besonderheit dieses Raums und sind
             * keine Optik-Parameter. */
            const glow = new THREE.Sprite(new THREE.SpriteMaterial({
                map: this.makeGlowTexture(),
                color,
                transparent: true,
                opacity: 0.4,
                blending: THREE.AdditiveBlending,
                depthWrite: false,
                depthTest: false
            }));
            glow.position.copy(position).addScaledVector(direction, 0.025);
            /* Der Demo-Faktor (radius * 5.2) geht von einer frei im Raum
             * verteilten Knotenwolke aus. In der Atlasblase sitzen die Knoten
             * viel dichter beieinander (mehrere Knoten auf engem Raum) – bei
             * unverändertem Faktor verschmelzen die additiv geblendeten Glow-
             * Sprites benachbarter Knoten zu einem einzigen großen Klumpen.
             * Reduzierter Faktor hält die Knoten optisch getrennt. */
            glow.userData.baseScale = radius * 2.2;
            glow.scale.setScalar(radius * 2.2);
            glow.renderOrder = 2;
            glow.layers.enable(BLOOM_LAYER);
            nodeGroup.add(glow);

            const shell = new THREE.Mesh(
                new THREE.IcosahedronGeometry(radius * 1.04, 1),
                new THREE.MeshBasicMaterial({
                    color: new THREE.Color(color).multiplyScalar(2.2),
                    wireframe: true,
                    transparent: true,
                    opacity: 0.3,
                    blending: THREE.AdditiveBlending,
                    depthWrite: false
                })
            );
            shell.position.copy(position);
            shell.userData.baseScale = 1;
            shell.renderOrder = 3;
            shell.layers.enable(BLOOM_LAYER);
            nodeGroup.add(shell);
            const material = new THREE.MeshStandardMaterial({
                color,
                emissive: color,
                emissiveIntensity: 0.45,
                metalness: 0.08,
                roughness: 0.22,
                transparent: true,
                opacity: 1
            });
            const mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(radius, 3), material);
            mesh.position.copy(position);
            mesh.userData.node = node;
            mesh.userData.vaultRegion = folder;
            mesh.userData.baseScale = 1;
            mesh.userData.visuals = [glow, shell, mesh];
            mesh.renderOrder = 4;
            mesh.layers.enable(BLOOM_LAYER);
            nodeGroup.add(mesh);
            this.nodeMeshes.push(mesh);
            meshByNodeId.set(node.id, mesh);
            this.nodeByMesh.set(mesh, node);
            this.nodeVisuals.set(node.id, [glow, shell, mesh]);
            const halo = new THREE.Mesh(
                new THREE.SphereGeometry(radius * 1.55, 20, 16),
                new THREE.MeshBasicMaterial({
                    color,
                    transparent: true,
                    opacity: 0.055,
                    blending: THREE.AdditiveBlending,
                    side: THREE.BackSide,
                    depthWrite: false
                })
            );
            halo.position.copy(position);
            halo.renderOrder = 2;
            halo.layers.enable(BLOOM_LAYER);
            nodeGroup.add(halo);
            mesh.userData.visuals.push(halo);
            const neuralSeed = [...String(node.id)].reduce(
                (hash, character) => ((hash * 31) + character.charCodeAt(0)) >>> 0,
                2166136261
            );
            mesh.userData.neuralPhase = neuralSeed * 0.0001;
            mesh.userData.neuralCharge = 0;
            mesh.userData.dimFactor = 0;
            /* Leichtes, blasengebundenes Wackeln (Phase 2): Basisposition und
             * -richtung merken, jeder Frame klemmt den Kandidatenpunkt über
             * die bereits vorhandene clampToAtlasBubble() zurück in die
             * Atlasblase — dieselbe Funktion, die auch Erstplatzierung und
             * Dendriten begrenzt. */
            mesh.userData.wanderBase = position.clone();
            mesh.userData.wanderDirection = direction.clone();
            mesh.userData.wanderRoom = room || null;
            mesh.userData.wanderSeedX = ((neuralSeed >>> 3) % 1000) / 1000;
            mesh.userData.wanderSeedY = ((neuralSeed >>> 11) % 1000) / 1000;
            mesh.userData.wanderSeedZ = ((neuralSeed >>> 19) % 1000) / 1000;
            const dendrites = this.createNodeDendrites(
                position,
                room,
                color,
                neuralSeed,
                radius,
                glow.material.map,
                Number(node.grad || 0)
            );
            dendrites.userData.lines?.layers.enable(BLOOM_LAYER);
            dendrites.userData.tips?.layers.enable(BLOOM_LAYER);
            nodeGroup.add(dendrites);
            mesh.userData.dendrites = dendrites;
            mesh.userData.visuals.push(dendrites);
            /* Die sichtbaren Punkte bleiben filigran. Für Maus und Touch
             * erhält jeder davon zusätzlich eine großzügige, unsichtbare
             * Trefferfläche – damit die Auswahl nicht vom Pixelglück abhängt. */
            const hitArea = new THREE.Mesh(
                new THREE.SphereGeometry(
                    Math.max(radius * 3.4, 0.38),
                    this.fastDevMode ? 8 : 16,
                    this.fastDevMode ? 6 : 12
                ),
                new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, depthTest: false })
            );
            hitArea.position.copy(position);
            hitArea.userData.node = node;
            hitArea.userData.vaultRegion = folder;
            hitArea.renderOrder = -1;
            nodeGroup.add(hitArea);
            mesh.userData.visuals.push(hitArea);
            this.interactionMeshes.push(hitArea);
            this.addLabel(node, position, color);
        }

        const pathGroup = new THREE.Group();
        pathGroup.name = "SecBrain-Leiterbahnen";
        this.scene.add(pathGroup);
        this.graphPathGroup = pathGroup;
        /* Geteilte Geometrie/Textur für die Signal-Pakete (Kern + Halo) –
         * 1:1 aus secbrain-neural-graph.html, einmal pro Graphaufbau erzeugt
         * und von jedem Puls wiederverwendet. */
        this.pulseGeometry = this.pulseGeometry || new THREE.SphereGeometry(1, 12, 10);
        this.pulseGlowTexture = this.makeGlowTexture();
        for (const edge of edges) {
            const source = positions.get(edge.from || edge.source);
            const target = positions.get(edge.to || edge.target);
            if (!source || !target) continue;
            const sourceId = edge.from || edge.source;
            const targetId = edge.to || edge.target;
            const sourceRegion = this.vaultFolderFor(nodeDataById.get(sourceId) || {});
            const targetRegion = this.vaultFolderFor(nodeDataById.get(targetId) || {});
            const intraRegion = sourceRegion === targetRegion;
            /* Zwei unabhängig verbogene Kontrollpunkte statt eines einzelnen
             * Scheitelpunkts – 1:1 aus der Neural-Graph-Demo (CubicBezierCurve3
             * statt CatmullRomCurve3). Die Eindämmung in die Atlasblase
             * (innerhalb einer Region) bzw. die Gehirn-Hülle (regionüber-
             * greifend) bleibt die bestehende, produktionsspezifische Logik
             * und wird auf beide Kontrollpunkte angewendet. */
            const middle = source.clone().lerp(target, 0.5);
            const chord = target.clone().sub(source);
            const radial = middle.clone().sub(this.brainCenter);
            const bend = new THREE.Vector3().crossVectors(chord, radial);
            if (bend.lengthSq() < 0.001) bend.set(0, 1, 0).cross(chord);
            const bendAmount = Math.min(0.72, Math.max(0.12, chord.length() * 0.075));
            bend.normalize().multiplyScalar(bendAmount);
            const c1 = source.clone().lerp(target, 0.3).add(bend);
            const c2 = source.clone().lerp(target, 0.7).add(bend);
            if (intraRegion && this.vaultRegionRooms.has(sourceRegion)) {
                this.clampToAtlasBubble(c1, this.vaultRegionRooms.get(sourceRegion), 0.72);
                this.clampToAtlasBubble(c2, this.vaultRegionRooms.get(sourceRegion), 0.72);
            } else {
                this.clampToInteriorEnvelope(c1, 0.92);
                this.clampToInteriorEnvelope(c2, 0.92);
            }
            const curve = new THREE.CubicBezierCurve3(source.clone(), c1, c2, target.clone());

            /* Jede Kante bekommt jetzt die volle Tube-Optik der Demo – kein
             * abgespeckter Linien-Fallback mehr für regionübergreifende
             * Kanten. */
            const sourceColor = new THREE.Color(this.vaultRegions()[sourceRegion]?.color ?? 0x42caff);
            const targetColor = new THREE.Color(this.vaultRegions()[targetRegion]?.color ?? 0x42caff);
            const tint = sourceColor.clone().lerp(targetColor, 0.5).lerp(new THREE.Color(0xffffff), intraRegion ? 0.25 : 0.55);
            const baseOpacity = intraRegion ? 0.46 : 0.34;
            const geometry = new THREE.TubeGeometry(
                curve, 44, Math.min(0.028, 0.016 + chord.length() * 0.0008), 6, false
            );
            const material = new THREE.MeshBasicMaterial({
                color: tint,
                transparent: true,
                opacity: baseOpacity,
                blending: THREE.AdditiveBlending,
                depthWrite: false
            });
            const path = new THREE.Mesh(geometry, material);
            path.userData = {
                sourceId,
                targetId,
                sourceRegion,
                targetRegion,
                baseOpacity,
                intraRegion
            };
            path.renderOrder = 1;
            path.layers.enable(BLOOM_LAYER);
            pathGroup.add(path);
            this.edgeVisuals.push(path);

            /* Diskrete Signal-Pakete statt eines durchgehenden Loop-Punkts –
             * jede Verbindung feuert unabhängig über einen eigenen Countdown,
             * 1:1 aus der Demo übernommen. Der bisherige Deckel auf 40
             * Kanten entfällt vollständig: jede Kante bekommt Pulse. */
            this.edgePaths.push({
                curve,
                tube: path,
                sourceMesh: meshByNodeId.get(sourceId) || null,
                targetMesh: meshByNodeId.get(targetId) || null,
                tint,
                nextFire: 0.2 + Math.random() * 5.8,
                pulses: []
            });
        }
    }

    spawnAxonPulse(axon, forward) {
        const from = forward ? axon.sourceMesh : axon.targetMesh;
        const to = forward ? axon.targetMesh : axon.sourceMesh;
        if (!from || !to) return;
        const fromColor = from.material?.color || axon.tint;
        const toColor = to.material?.color || axon.tint;
        const color = fromColor.clone().lerp(toColor, 0.4).multiplyScalar(1.6);
        const group = new THREE.Group();
        const core = new THREE.Mesh(this.pulseGeometry, new THREE.MeshBasicMaterial({ color: 0xffffff }));
        core.scale.setScalar(0.055);
        const halo = new THREE.Sprite(new THREE.SpriteMaterial({
            map: this.pulseGlowTexture,
            color,
            transparent: true,
            opacity: 0.9,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
            depthTest: false
        }));
        halo.scale.setScalar(0.75);
        core.layers.enable(BLOOM_LAYER);
        halo.layers.enable(BLOOM_LAYER);
        group.add(core, halo);
        group.renderOrder = 6;
        this.graphPathGroup.add(group);
        axon.pulses.push({
            group,
            halo,
            t: 0,
            speed: 0.34 + Math.random() * 0.28,
            forward,
            target: to
        });
        from.userData.neuralCharge = Math.min(1.2, (from.userData.neuralCharge || 0) + 0.45);
    }

    createNodeDendrites(position, room, color, seed, radius, glowTexture, grad = 0) {
        const group = new THREE.Group();
        group.name = "Neuronale Dendriten";
        const linePositions = [];
        const lineColors = [];
        const tips = [];
        let state = seed >>> 0;
        const random = () => {
            state = (state * 1664525 + 1013904223) >>> 0;
            return state / 4294967296;
        };
        const randomBetween = (minimum, maximum) => minimum + random() * (maximum - minimum);
        /* Die Dendriten gehören optisch zum Innenraum der Atlasblase – ihre
         * Reichweite darf deshalb nicht von dem deutlich kleineren Node-Kern
         * abhängen. Der radiale Clamp hält jeden Ast weiterhin sicher in der
         * zugehörigen, auch manuell verformten Blase. */
        const roomReach = room?.radii
            ? Math.min(room.radii.x, room.radii.y, room.radii.z) * 0.62
            : radius * 5.5;
        /* Komplexität der Dendriten richtet sich nach dem Grad des Knotens –
         * 1:1 aus secbrain-neural-graph.html übernommen. */
        const maxDepth = grad >= 8 ? 3 : 2;
        const innerColor = new THREE.Color(color).multiplyScalar(1.8);
        const outerColor = new THREE.Color(color).multiplyScalar(0.62);

        const grow = (start, direction, length, depth) => {
            let current = start.clone();
            const segments = 5;
            for (let segment = 0; segment < segments; segment += 1) {
                direction.add(new THREE.Vector3(
                    randomBetween(-0.22, 0.22),
                    randomBetween(-0.22, 0.22),
                    randomBetween(-0.22, 0.22)
                )).normalize();
                const next = current.clone().addScaledVector(direction, length / segments);
                if (room) this.clampToAtlasBubble(next, room, 0.82);
                linePositions.push(
                    current.x, current.y, current.z,
                    next.x, next.y, next.z
                );
                const blendStart = (depth + segment / segments) / 3;
                const blendEnd = (depth + (segment + 1) / segments) / 3;
                const startColor = innerColor.clone().lerp(outerColor, Math.min(1, blendStart));
                const endColor = innerColor.clone().lerp(outerColor, Math.min(1, blendEnd));
                lineColors.push(
                    startColor.r, startColor.g, startColor.b,
                    endColor.r, endColor.g, endColor.b
                );
                current = next;
            }
            if (depth < maxDepth) {
                const branches = depth === 0 ? 2 : (random() > 0.4 ? 2 : 1);
                for (let branch = 0; branch < branches; branch += 1) {
                    const childDirection = direction.clone().add(new THREE.Vector3(
                        randomBetween(-0.72, 0.72),
                        randomBetween(-0.72, 0.72),
                        randomBetween(-0.72, 0.72)
                    )).normalize();
                    grow(current, childDirection, length * randomBetween(0.48, 0.68), depth + 1);
                }
            } else {
                tips.push(current.x, current.y, current.z);
            }
        };

        const roots = grad >= 8 ? 12 : grad >= 3 ? 8 : 5;
        for (let index = 0; index < roots; index += 1) {
            const vertical = 1 - 2 * ((index + 0.5) / roots);
            const planar = Math.sqrt(Math.max(0, 1 - vertical * vertical));
            const angle = index * 2.399963229728653;
            const direction = new THREE.Vector3(
                Math.cos(angle) * planar,
                vertical,
                Math.sin(angle) * planar
            ).add(new THREE.Vector3(
                randomBetween(-0.18, 0.18),
                randomBetween(-0.18, 0.18),
                randomBetween(-0.18, 0.18)
            )).normalize();
            grow(
                position.clone().addScaledVector(direction, radius * 1.15),
                direction,
                roomReach * randomBetween(0.72, 1.05),
                0
            );
        }

        const lineGeometry = new THREE.BufferGeometry();
        lineGeometry.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));
        lineGeometry.setAttribute("color", new THREE.Float32BufferAttribute(lineColors, 3));
        const lines = new THREE.LineSegments(lineGeometry, new THREE.LineBasicMaterial({
            vertexColors: true,
            transparent: true,
            opacity: 0.62,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }));
        lines.renderOrder = 2;
        group.add(lines);

        const tipGeometry = new THREE.BufferGeometry();
        tipGeometry.setAttribute("position", new THREE.Float32BufferAttribute(tips, 3));
        const tipPoints = new THREE.Points(tipGeometry, new THREE.PointsMaterial({
            map: glowTexture,
            color,
            size: Math.max(0.045, radius * 0.58),
            transparent: true,
            opacity: 0.82,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }));
        tipPoints.renderOrder = 3;
        group.add(tipPoints);
        group.userData.lines = lines;
        group.userData.tips = tipPoints;
        return group;
    }

}
