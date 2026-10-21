import * as THREE from "three";
import vaultAtlasDefaults from "./vault-atlas-defaults.js";

export class VaultGraphAtlasMethods {
    buildCorticalAtlas() {
        if (!this.brain || !this.innerRegionAxes) return;

        /*
         * Der Atlas ist als Satz geschlossener, organischer Innenräume
         * aufgebaut. Diese Blasen sind bewusst kleiner als das konservative
         * Innenellipsoid des GLB-Modells und überschneiden sich nicht. Genau
         * dieselben Mittelpunkt-/Radiusdaten begrenzen später die Knoten.
         */
        const atlas = new THREE.Group();
        atlas.name = "SecBrain-Atlasblasen";
        Object.entries(this.vaultRegions()).forEach(([folder, region]) => {
            const defaultRoomData = this.resolveVaultRoom(region);
            const roomData = this.resolveVaultRoomWithOverride(folder, defaultRoomData);
            /* Jede Atlasblase nutzt dieselbe Geometrie- und Editor-Pipeline.
             * Der Ordnername verändert weder Topologie noch Bedienung. */
            const geometry = this.createAtlasBubbleGeometry(
                region.atlasIndex,
                roomData.surfaceOffsets,
                null,
                roomData.surfaceDisplacements
            );
            const room = new THREE.Group();
            room.name = `Atlasblase: ${folder}`;
            room.position.copy(roomData.center);
            room.scale.copy(roomData.radii);

            const fill = new THREE.Mesh(
                geometry,
                new THREE.MeshBasicMaterial({
                    color: region.color,
                    transparent: true,
                    opacity: 0.035,
                    side: THREE.DoubleSide,
                    depthWrite: false,
                    depthTest: true
                })
            );
            fill.name = `Atlasblase-Füllung: ${folder}`;
            fill.renderOrder = 0;
            room.add(fill);

            const boundary = new THREE.Mesh(
                geometry,
                new THREE.MeshBasicMaterial({
                    color: region.color,
                    transparent: true,
                    opacity: 0.18,
                    wireframe: true,
                    blending: THREE.AdditiveBlending,
                    depthWrite: false,
                    depthTest: true
                })
            );
            boundary.name = `Atlasblase-Grenze: ${folder}`;
            boundary.scale.setScalar(1.008);
            boundary.renderOrder = 1;
            room.add(boundary);

            const glow = new THREE.Mesh(
                geometry,
                this.createAtlasBubbleGlowMaterial(region.color)
            );
            glow.name = `Atlasblase-Leuchtrand: ${folder}`;
            glow.scale.setScalar(1.012);
            glow.renderOrder = 2;
            /* Leuchtrand der Atlasblase auf Wunsch entfernt: das Mesh wird
             * weiterhin erzeugt und in room.userData referenziert (damit
             * setActiveVaultRegion() & Co. unverändert bleiben können), aber
             * nicht mehr der Szene hinzugefügt – dadurch bleibt es unsichtbar,
             * ohne dass an anderer Stelle Code angepasst werden musste. */

            room.userData = {
                folder,
                region,
                fill,
                boundary,
                glow,
                geometry,
                defaultCenter: defaultRoomData.center.clone(),
                defaultRadii: defaultRoomData.radii.clone(),
                ...roomData
            };
            atlas.add(room);
            this.vaultRegionVolumes.push(room);
            this.vaultRegionRooms.set(folder, room.userData);
        });
        this.scene.add(atlas);
        this.corticalAtlasGroup = atlas;
        this.corticalVolumeGroup = atlas;
        this.vaultRegionVolumeGroup = atlas;
        this.setBrainTransparency(this.atlasBrainOpacity);
    }

    resolveVaultRoom(region) {
        const room = region.room || { center: [0, 0, 0], radius: [0.16, 0.16, 0.22] };
        const radii = new THREE.Vector3(
            room.radius[0] * this.innerRegionAxes.x,
            room.radius[1] * this.innerRegionAxes.y,
            room.radius[2] * this.innerRegionAxes.z
        );
        let center = this.brainCenter.clone().add(new THREE.Vector3(
            room.center[0] * this.innerRegionAxes.x,
            room.center[1] * this.innerRegionAxes.y,
            room.center[2] * this.innerRegionAxes.z
        ));

        return {
            center,
            radii
        };
    }

    resolveVaultRoomWithOverride(folder, roomData) {
        const override = this.atlasOverrides?.[folder];
        const validVector = value => Array.isArray(value)
            && value.length === 3
            && value.every(Number.isFinite);
        return {
            center: validVector(override?.center)
                ? new THREE.Vector3().fromArray(override.center)
                : roomData.center.clone(),
            radii: validVector(override?.radii)
                ? new THREE.Vector3().fromArray(override.radii)
                : roomData.radii.clone(),
            surfaceOffsets: this.sanitizeAtlasSurfaceOffsets(override?.surfaceOffsets),
            surfaceDisplacements: this.sanitizeAtlasSurfaceDisplacements(override?.surfaceDisplacements)
        };
    }

    sanitizeAtlasSurfaceOffsets(value) {
        if (!value || typeof value !== "object" || Array.isArray(value)) return {};
        const allowedKeys = new Set(this.getAtlasSurfaceAnchors().map(anchor => anchor.id));
        return Object.fromEntries(Object.entries(value)
            .filter(([key, offset]) => allowedKeys.has(key) && Number.isFinite(offset))
            /* Größerer Arbeitsbereich für echte Mesh-Formung. Die frühere
             * Obergrenze 0.85 ließ die Griffe schon nach kurzer Mausbewegung
             * hart anschlagen. */
            .map(([key, offset]) => [key, Number(THREE.MathUtils.clamp(offset, -0.94, 8).toFixed(4))]));
    }

    sanitizeAtlasSurfaceDisplacements(value) {
        if (!value || typeof value !== "object" || Array.isArray(value)) return {};
        const allowedKeys = new Set(this.getAtlasSurfaceAnchors().map(anchor => anchor.id));
        return Object.fromEntries(Object.entries(value)
            .filter(([key, vector]) => allowedKeys.has(key)
                && Array.isArray(vector)
                && vector.length === 3
                && vector.every(Number.isFinite))
            .map(([key, vector]) => {
                const displacement = new THREE.Vector3().fromArray(vector);
                if (displacement.length() > 1.8) displacement.setLength(1.8);
                return [key, displacement.toArray().map(component => Number(component.toFixed(4)))];
            }));
    }

    cloneDefaultAtlasOverrides() {
        return JSON.parse(JSON.stringify(vaultAtlasDefaults));
    }

    loadAtlasOverrides() {
        const defaults = this.cloneDefaultAtlasOverrides();
        try {
            const raw = window.localStorage?.getItem(this.atlasOverrideStorageKey);
            const parsed = raw ? JSON.parse(raw) : {};
            return parsed && typeof parsed === "object" && !Array.isArray(parsed)
                ? { ...defaults, ...parsed }
                : defaults;
        } catch {
            return defaults;
        }
    }

    saveAtlasOverrides() {
        try {
            window.localStorage?.setItem(this.atlasOverrideStorageKey, JSON.stringify(this.atlasOverrides));
        } catch {
            // Der Editor bleibt nutzbar, auch falls der Browser-Speicher gesperrt ist.
        }
    }

    serializeAtlasVector(vector) {
        return vector.toArray().map(value => Number(value.toFixed(4)));
    }

  getVaultRegionRoom(folder) {
    return this.vaultRegionVolumes.find(room => room.userData.folder === folder) || null;
  }

  setAtlasDevMode(enabled) {
    this.atlasDevMode = Boolean(enabled);
    if (this.atlasDevMode) this.fastDevMode = true;
    try {
      window.localStorage?.setItem(this.atlasDevModeStorageKey, String(this.atlasDevMode));
    } catch {
      // Der Modus bleibt für die laufende Sitzung trotzdem aktiv.
    }
    this.root?.classList.toggle("is-atlas-editor-active", this.atlasDevMode);

    const toggle = this.regionMenu?.querySelector(".graph-region-menu__dev-toggle");
    const panel = this.regionMenu?.querySelector(".graph-region-menu__dev-panel");
    if (toggle) {
      toggle.classList.toggle("is-active", this.atlasDevMode);
      toggle.setAttribute("aria-pressed", String(this.atlasDevMode));
      toggle.textContent = this.atlasDevMode ? "ATLAS-EDITOR: AN" : "ATLAS-EDITOR: AUS";
    }
    if (panel) panel.hidden = !this.atlasDevMode;

    if (this.atlasDevMode) {
      this.clearGraphVisualization();
      this.setAtlasEditorMode(this.atlasEditorMode);
    }
    else {
      this.disposeAtlasEditorGizmo();
      if (!this.graphNodeGroup && !this.graphPathGroup) this.buildGraph();
      this.setActiveVaultRegion(this.activeVaultRegion, this.hasVaultRegionSelection);
      this.updateAtlasDevStatus();
    }
  }

  setAtlasEditorMode(mode) {
    const nextMode = mode === "volume" ? "volume" : "position";
    this.atlasEditorMode = nextMode;
    this.regionMenu?.querySelectorAll("[data-atlas-mode]").forEach(button => {
      const active = button.dataset.atlasMode === nextMode;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    if (this.atlasDevMode) this.setAtlasEditorSelection(this.activeVaultRegion);
    this.updateAtlasDevStatus(
      nextMode === "position"
        ? "Positionsmodus: Mittelpunkt ziehen."
        : "Volumenmodus: weiße Oberflächenpunkte oder Eckpunkte ziehen."
    );
  }

  isAtlasHandleAllowedForMode(handle) {
    const kind = handle?.userData?.atlasHandle;
    if (this.atlasEditorMode === "position") return kind === "move";
    return kind === "resize" || kind === "surface";
  }

  setAtlasEditorSelection(folder) {
    this.disposeAtlasEditorGizmo();
    if (!this.atlasDevMode || !folder || !this.scene) return;

    const room = this.getVaultRegionRoom(folder);
    if (!room) return;

    const color = room.userData.region.color;
    const group = new THREE.Group();
    group.name = `Atlas-Editor: ${folder}`;
    group.position.copy(room.position);
    group.userData = { room };

    const boundary = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(2, 2, 2)),
      new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9, depthTest: false })
    );
    boundary.renderOrder = 30;
    boundary.visible = this.atlasEditorMode === "volume";
    group.add(boundary);
    group.userData.boundary = boundary;

    const createHandle = (kind, signs = [], anchor = null) => {
      const isSurfaceHandle = kind === "surface";
      const material = new THREE.MeshBasicMaterial({
        color: kind === "move" ? 0xffffff : isSurfaceHandle ? 0xd9fbff : color,
        transparent: true,
        opacity: 0.98,
        depthTest: false
      });
      const handle = new THREE.Mesh(
        new THREE.SphereGeometry(kind === "move" ? 0.22 : isSurfaceHandle ? 0.065 : 0.13, 10, 7),
        material
      );
      handle.renderOrder = 31;
      handle.userData = { atlasHandle: kind, folder, signs, anchor };
      group.add(handle);
      this.atlasEditorHandles.push(handle);
      return handle;
    };

    if (this.atlasEditorMode === "position") {
      createHandle("move");
    } else {
      for (const x of [-1, 1]) {
        for (const y of [-1, 1]) {
          for (const z of [-1, 1]) createHandle("resize", [x, y, z]);
        }
      }
      this.getAtlasSurfaceAnchors(folder).forEach(anchor => createHandle("surface", [], anchor));
    }

    this.scene.add(group);
    this.atlasEditorGizmo = group;
    this.updateAtlasEditorGizmo();
  }

  updateAtlasEditorGizmo() {
    const gizmo = this.atlasEditorGizmo;
    const room = gizmo?.userData.room;
    if (!gizmo || !room) return;

    gizmo.position.copy(room.position);
    gizmo.userData.boundary.scale.copy(room.scale).multiplyScalar(1.035);
    this.atlasEditorHandles.forEach(handle => {
      if (handle.userData.atlasHandle === "move") {
        handle.position.set(0, 0, 0);
        return;
      }
      if (handle.userData.atlasHandle === "surface") {
        handle.position.copy(this.getAtlasSurfaceAnchorPosition(room, handle.userData.anchor));
        /* Die Position stammt bereits aus der deformierten Geometrie. Eine
         * zweite manuelle Verschiebung ließ den aktiven Punkt der Maus
         * davonlaufen und machte die Bearbeitung sprunghaft. */
        return;
      }
      const [x, y, z] = handle.userData.signs;
      handle.position.set(
        x * room.scale.x * 1.035,
        y * room.scale.y * 1.035,
        z * room.scale.z * 1.035
      );
    });
  }

  disposeObject3D(object) {
    if (!object) return;
    object.traverse(item => {
      item.geometry?.dispose?.();
      if (Array.isArray(item.material)) item.material.forEach(material => material?.dispose?.());
      else item.material?.dispose?.();
    });
    object.parent?.remove(object);
  }

  disposeAtlasEditorGizmo() {
    this.setAtlasHandleHover(null);
    if (this.atlasEditorGizmo) this.disposeObject3D(this.atlasEditorGizmo);
    this.atlasEditorGizmo = null;
    this.atlasEditorHandles = [];
    this.atlasEditorDrag = null;
    this.canvas?.classList.remove("is-atlas-editor-hover", "is-atlas-editor-dragging");
  }

  clearGraphVisualization() {
    this.labelSprites.forEach(sprite => {
      sprite.material?.map?.dispose?.();
      sprite.material?.dispose?.();
      sprite.parent?.remove(sprite);
    });
    this.labelSprites = [];
    this.disposeObject3D(this.graphNodeGroup);
    this.disposeObject3D(this.graphPathGroup);
    this.graphNodeGroup = null;
    this.graphPathGroup = null;
    this.nodeByMesh.clear();
    this.nodeVisuals.clear();
    this.interactionMeshes = [];
    this.nodeMeshes = [];
    this.edgeVisuals = [];
    this.edgePaths = [];
    this.edgeSignals = null;
    /* Die geteilte Puls-Geometrie hängt evtl. noch an gerade entsorgten
     * Signal-Paketen im disposeObject3D()-Aufruf oben – neu anlegen lassen,
     * statt eine bereits dispose()-te Geometrie weiterzuverwenden. */
    this.pulseGeometry = null;
    this.activeNode = null;
    this.hoveredNode = null;
    this.setNodeHover(null);
  }

  syncAtlasRoomData(room) {
    room.userData.center = room.position.clone();
    room.userData.radii = room.scale.clone();
    this.vaultRegionRooms.set(room.userData.folder, room.userData);
  }

  loadAtlasDevMode() {
    try {
      return window.localStorage?.getItem(this.atlasDevModeStorageKey) === "true";
    } catch {
      return false;
    }
  }

  commitAtlasRoomOverride(room) {
    if (!room?.userData?.folder) return;
    this.atlasOverrides[room.userData.folder] = {
      center: this.serializeAtlasVector(room.position),
      radii: this.serializeAtlasVector(room.scale),
      surfaceOffsets: this.sanitizeAtlasSurfaceOffsets(room.userData.surfaceOffsets),
      surfaceDisplacements: this.sanitizeAtlasSurfaceDisplacements(room.userData.surfaceDisplacements)
    };
    this.saveAtlasOverrides();
  }

  commitAtlasPositionOverride(room) {
    if (!room?.userData?.folder) return;
    const previous = this.atlasOverrides[room.userData.folder] || {};
    this.atlasOverrides[room.userData.folder] = {
      ...previous,
      center: this.serializeAtlasVector(room.position),
      radii: previous.radii || this.serializeAtlasVector(room.scale),
      surfaceOffsets: previous.surfaceOffsets || this.sanitizeAtlasSurfaceOffsets(room.userData.surfaceOffsets),
      surfaceDisplacements: previous.surfaceDisplacements || this.sanitizeAtlasSurfaceDisplacements(room.userData.surfaceDisplacements)
    };
    this.saveAtlasOverrides();
  }

  commitAtlasVolumeOverride(room) {
    if (!room?.userData?.folder) return;
    const previous = this.atlasOverrides[room.userData.folder] || {};
    this.atlasOverrides[room.userData.folder] = {
      ...previous,
      center: previous.center || this.serializeAtlasVector(room.position),
      radii: this.serializeAtlasVector(room.scale),
      surfaceOffsets: this.sanitizeAtlasSurfaceOffsets(room.userData.surfaceOffsets),
      surfaceDisplacements: this.sanitizeAtlasSurfaceDisplacements(room.userData.surfaceDisplacements)
    };
    this.saveAtlasOverrides();
  }

  autoFitActiveAtlasRoom() {
    if (!this.atlasDevMode || !this.surfaceMeshes.length) {
      this.updateAtlasDevStatus("Atlas-Editor aktivieren, um die Räume automatisch einzupassen.");
      return;
    }
    if (this.activeVaultRegion === "00 Regelwerk") {
      this.updateAtlasDevStatus("00 Regelwerk bleibt unverändert. Automatik gilt für alle anderen Atlasblasen.");
      return;
    }

    const rooms = this.vaultRegionVolumes.filter(room => room.userData.folder !== "00 Regelwerk");
    if (!rooms.length) return;
    let fittedRooms = 0;
    rooms.forEach(room => {
      const collisionRooms = this.vaultRegionVolumes.filter(candidate => candidate !== room);
      if (this.autoFitAtlasRoom(room, collisionRooms, false)) fittedRooms += 1;
    });
    this.updateAtlasEditorGizmo();
    this.updateAtlasDevStatus(`${fittedRooms}/${rooms.length} Atlasblasen gleichmäßig bis Gehirn- oder Nachbargrenze expandiert; 00 Regelwerk unverändert.`);
  }

  autoFitAtlasRoom(room, collisionRooms = [], announce = true) {
    if (!room) return false;

    if (this.atlasEditorMode !== "volume") this.setAtlasEditorMode("volume");
    room.updateWorldMatrix(true, false);
    const center = room.getWorldPosition(new THREE.Vector3());
    const raycaster = new THREE.Raycaster();
    raycaster.near = 0.001;
    raycaster.far = 90;
    const materialSides = [];
    this.surfaceMeshes.forEach(mesh => {
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      materials.forEach(material => {
        if (!material) return;
        materialSides.push([material, material.side]);
        /* Ein Strahl startet innerhalb des Gehirns. DoubleSide ist für den
         * inneren Austritt erforderlich und wird direkt danach restauriert. */
        material.side = THREE.DoubleSide;
      });
    });

    /* Ein Auto-Fit von einem Punkt außerhalb des Zielvolumens würde den
     * ersten Eintritt statt des inneren Austritts verwenden. Drei unabhängige
     * Paritätstests verhindern diesen Fall auch bei ungünstigen Kantenlagen. */
    const insideDirections = [
      new THREE.Vector3(1, 0.013, 0.007).normalize(),
      new THREE.Vector3(0.009, 1, 0.017).normalize(),
      new THREE.Vector3(0.011, 0.019, 1).normalize()
    ];
    const insideVotes = insideDirections.filter(direction => {
      raycaster.set(center, direction);
      const hits = raycaster.intersectObjects(this.surfaceMeshes, false)
        .filter(hit => hit.distance > 0.01)
        .sort((left, right) => left.distance - right.distance);
      const uniqueDistances = hits.reduce((distances, hit) => {
        if (!distances.length || Math.abs(hit.distance - distances[distances.length - 1]) > 0.002) {
          distances.push(hit.distance);
        }
        return distances;
      }, []);
      return uniqueDistances.length % 2 === 1;
    }).length;
    if (insideVotes < 2) {
      materialSides.forEach(([material, side]) => { material.side = side; });
      if (announce) this.updateAtlasDevStatus("Auto-Fit gestoppt: Mittelpunkt liegt nicht sicher innerhalb des 3D-Gehirnmodells. Erst Position korrigieren.");
      return false;
    }

    const offsets = {};
    const unresolvedAnchors = [];
    let fitted = 0;
    try {
      this.getAtlasSurfaceAnchors().forEach(anchor => {
        const localDirection = new THREE.Vector3(...anchor.direction).normalize();
        const worldDirection = localDirection.clone().transformDirection(room.matrixWorld);
        /* Ein einzelner Strahl kann genau durch eine offene Modellkante oder
         * zwischen zwei Dreiecke laufen. Kleine Kegelproben liefern dort eine
         * stabile lokale Grenze, ohne zusätzliche Mesh- oder Editorpunkte. */
        const tangentA = new THREE.Vector3().crossVectors(
          worldDirection,
          Math.abs(worldDirection.y) < 0.9
            ? new THREE.Vector3(0, 1, 0)
            : new THREE.Vector3(1, 0, 0)
        ).normalize();
        const tangentB = new THREE.Vector3().crossVectors(worldDirection, tangentA).normalize();
        raycaster.set(center, worldDirection);
        let hit = raycaster.intersectObjects(this.surfaceMeshes, false)
          .find(intersection => intersection.distance > 0.01) || null;
        const fallbackDirections = [
          worldDirection.clone().addScaledVector(tangentA, 0.035).normalize(),
          worldDirection.clone().addScaledVector(tangentA, -0.035).normalize(),
          worldDirection.clone().addScaledVector(tangentB, 0.035).normalize(),
          worldDirection.clone().addScaledVector(tangentB, -0.035).normalize()
        ];
        if (!hit) {
          hit = fallbackDirections.reduce((nearest, direction) => {
            raycaster.set(center, direction);
            const candidate = raycaster.intersectObjects(this.surfaceMeshes, false)
              .find(intersection => intersection.distance > 0.01);
            return candidate && (!nearest || candidate.distance < nearest.distance)
              ? candidate
              : nearest;
          }, null);
        }
        if (!hit) {
          unresolvedAnchors.push(anchor);
          return;
        }

        const baseDistance = new THREE.Vector3(
          localDirection.x * room.scale.x,
          localDirection.y * room.scale.y,
          localDirection.z * room.scale.z
        ).length();
        /* Auto-Fit bleibt garantiert auf der Innenseite: feste Einrückung
         * plus sechs Prozent Reserve für Bereiche zwischen zwei Rays. */
        const measuredSafeDistance = Math.max(
          baseDistance * 0.06,
          Math.max(0, hit.distance - 0.28) * 0.94
        );
        /* Der Mittelpunkt wurde zuvor als innen verifiziert. Deshalb darf die
         * Atlasblase entlang dieses Strahls bis zur gemessenen, eingerückten
         * Innenfläche wachsen; eine zusätzliche prozentuale Volumenbremse
         * würde den verfügbaren Gehirnraum unnötig ungenutzt lassen. */
        /* Gleichzeitiges Wachstum endet auf der mittleren Trennebene zweier
         * Atlaszentren. Diese Voronoi-Grenzen sind für beide Seiten identisch
         * und verhindern Überschneidungen der automatisch erzeugten Räume.
         * Das feste Regelwerk wird zusätzlich als reales Mesh geprüft. */
        let neighborDistance = Infinity;
        collisionRooms.forEach(otherRoom => {
          const otherCenter = otherRoom.getWorldPosition(new THREE.Vector3());
          const centerDelta = otherCenter.sub(center);
          const projection = worldDirection.dot(centerDelta);
          if (projection > 0.001) {
            neighborDistance = Math.min(
              neighborDistance,
              centerDelta.lengthSq() / (2 * projection) - 0.08
            );
          }
          if (otherRoom.userData.folder !== "00 Regelwerk" || !otherRoom.userData.fill) return;
          raycaster.set(center, worldDirection);
          const ruleHit = raycaster.intersectObject(otherRoom.userData.fill, false)
            .find(intersection => intersection.distance > 0.01);
          if (ruleHit) neighborDistance = Math.min(neighborDistance, ruleHit.distance - 0.08);
        });
        const safeDistance = Math.max(
          baseDistance * 0.06,
          Math.min(measuredSafeDistance, neighborDistance)
        );
        offsets[anchor.id] = THREE.MathUtils.clamp(
          safeDistance / Math.max(baseDistance, 0.001) - 1,
          -0.94,
          8
        );
        fitted += 1;
      });

      /* Seltene komplett offene Richtungen übernehmen einen konservativen,
       * geglätteten Wert ihrer räumlich nächsten gültigen Nachbarn. Das
       * verhindert den bisherigen Pol-Kollaps und hält die Griffpunkte
       * gleichmäßig auf der sichtbaren Blasenoberfläche verteilt. */
      unresolvedAnchors.forEach(anchor => {
        const direction = new THREE.Vector3(...anchor.direction).normalize();
        const neighbors = this.getAtlasSurfaceAnchors()
          .filter(candidate => Number.isFinite(offsets[candidate.id]))
          .map(candidate => ({
            offset: offsets[candidate.id],
            alignment: direction.dot(new THREE.Vector3(...candidate.direction).normalize())
          }))
          .sort((left, right) => right.alignment - left.alignment)
          .slice(0, 6);
        if (!neighbors.length) return;
        const interpolation = neighbors.reduce((result, neighbor) => {
          const weight = Math.pow(Math.max(0.001, neighbor.alignment), 8);
          result.value += neighbor.offset * weight;
          result.weight += weight;
          return result;
        }, { value: 0, weight: 0 });
        offsets[anchor.id] = THREE.MathUtils.clamp(
          interpolation.value / Math.max(interpolation.weight, 0.001) - 0.06,
          -0.94,
          8
        );
      });

      /* Die Atlasblase ist eine radiale Hülle um ihren lokalen Mittelpunkt.
       * Jeder gerade ermittelte Wert ist die harte Innenraumgrenze seines
       * Strahls. Zwei Relaxationsschritte verteilen die Radien gleichmäßig,
       * dürfen diese individuelle Grenze aber niemals überschreiten. */
      const radialLimits = { ...offsets };
      const anchors = this.getAtlasSurfaceAnchors();
      const relaxationSteps = collisionRooms.length ? 0 : 2;
      for (let iteration = 0; iteration < relaxationSteps; iteration += 1) {
        const previous = { ...offsets };
        anchors.forEach(anchor => {
          if (!Number.isFinite(radialLimits[anchor.id])) return;
          const direction = new THREE.Vector3(...anchor.direction).normalize();
          const neighbors = anchors
            .filter(candidate => candidate.id !== anchor.id && Number.isFinite(previous[candidate.id]))
            .map(candidate => ({
              id: candidate.id,
              alignment: direction.dot(new THREE.Vector3(...candidate.direction).normalize())
            }))
            .sort((left, right) => right.alignment - left.alignment)
            .slice(0, 6);
          if (!neighbors.length) return;
          const average = neighbors.reduce((sum, neighbor) => sum + previous[neighbor.id], 0)
            / neighbors.length;
          const relaxed = previous[anchor.id] * 0.45 + average * 0.55;
          offsets[anchor.id] = THREE.MathUtils.clamp(
            Math.min(relaxed, radialLimits[anchor.id]),
            -0.94,
            8
          );
        });
      }
    } finally {
      materialSides.forEach(([material, side]) => { material.side = side; });
    }

    if (!fitted) {
      if (announce) this.updateAtlasDevStatus("Keine sichere Gehirnoberfläche für diese Atlasblase gefunden.");
      return false;
    }
    room.userData.surfaceOffsets = this.sanitizeAtlasSurfaceOffsets(offsets);
    room.userData.surfaceDisplacements = {};
    this.updateAtlasSurfaceGeometryPreview(room, false);
    this.syncAtlasRoomData(room);
    this.commitAtlasVolumeOverride(room);
    if (announce) {
      this.updateAtlasEditorGizmo();
      this.updateAtlasDevStatus(`${room.userData.folder}: vom Mittelpunkt bis Gehirn- oder Nachbargrenze eingepasst und gespeichert.`);
    }
    return true;
  }

  updateAtlasDevStatus(message = "") {
    if (message) this.atlasDevNotice = message;
    const status = this.regionMenu?.querySelector(".graph-region-menu__dev-status");
    if (!status) return;
    if (!this.atlasDevMode) {
      status.textContent = "Lokal im Browser – keine Vault-Änderungen.";
      return;
    }
    const room = this.getVaultRegionRoom(this.activeVaultRegion);
    if (!room) {
      status.textContent = "Bereich auswählen, um ihn zu bearbeiten.";
      return;
    }
    const center = this.serializeAtlasVector(room.position).join(", ");
    const radii = this.serializeAtlasVector(room.scale).join(", ");
    status.textContent = this.atlasDevNotice || `Mitte: ${center} · Raum: ${radii} · Oberflächenpunkte ziehen, um Volumen lokal zu erweitern.`;
  }

  resetAtlasOverride(folder) {
    if (!folder || !vaultAtlasDefaults[folder]) {
      this.updateAtlasDevStatus("Für diesen Bereich gibt es keine feste Atlas-Vorgabe.");
      return;
    }
    this.atlasOverrides[folder] = JSON.parse(JSON.stringify(vaultAtlasDefaults[folder]));
    this.saveAtlasOverrides();
    this.atlasDevNotice = `${folder} wurde auf den fest gespeicherten Stand zurückgesetzt.`;
    this.rebuildAtlasAndGraph();
  }

  resetAllAtlasOverrides() {
    this.atlasOverrides = this.cloneDefaultAtlasOverrides();
    this.saveAtlasOverrides();
    this.atlasDevNotice = "Alle Atlasblasen wurden auf den fest gespeicherten Stand zurückgesetzt.";
    this.rebuildAtlasAndGraph();
  }

  async copyAtlasOverrides() {
    const json = JSON.stringify(this.atlasOverrides, null, 2);
    try {
      await navigator.clipboard.writeText(json);
      this.updateAtlasDevStatus("Atlas-Overrides als JSON in die Zwischenablage kopiert.");
    } catch {
      this.updateAtlasDevStatus("Zwischenablage nicht verfügbar – JSON bleibt lokal gespeichert.");
    }
  }

  rebuildAtlasAndGraph() {
    const activeRegion = this.activeVaultRegion;
    const hasRegionSelection = this.hasVaultRegionSelection;
    this.disposeAtlasEditorGizmo();
    this.labelSprites.forEach(sprite => {
      sprite.material?.map?.dispose?.();
      sprite.material?.dispose?.();
      sprite.parent?.remove(sprite);
    });
    this.labelSprites = [];
    this.disposeObject3D(this.graphNodeGroup);
    this.disposeObject3D(this.graphPathGroup);
    this.disposeObject3D(this.corticalAtlasGroup);
    this.graphNodeGroup = null;
    this.graphPathGroup = null;
    this.corticalAtlasGroup = null;
    this.vaultRegionVolumes = [];
    this.vaultRegionRooms.clear();
    this.nodeByMesh.clear();
    this.nodeVisuals.clear();
    this.interactionMeshes = [];
    this.nodeMeshes = [];
    this.edgeVisuals = [];
    this.edgePaths = [];
    this.edgeSignals = null;
    /* Die geteilte Puls-Geometrie hängt evtl. noch an gerade entsorgten
     * Signal-Paketen im disposeObject3D()-Aufruf oben – neu anlegen lassen,
     * statt eine bereits dispose()-te Geometrie weiterzuverwenden. */
    this.pulseGeometry = null;
    this.activeNode = null;
    this.hoveredNode = null;
    this.buildCorticalAtlas();
    if (!this.atlasDevMode) this.buildGraph();
    this.setActiveVaultRegion(activeRegion, hasRegionSelection);
  }

  rebuildGraphAfterAtlasEdit() {
    const activeRegion = this.activeVaultRegion;
    const hasRegionSelection = this.hasVaultRegionSelection;
    if (this.atlasDevMode) {
      this.clearGraphVisualization();
      this.setActiveVaultRegion(activeRegion, hasRegionSelection);
      return;
    }
    this.disposeAtlasEditorGizmo();
    this.labelSprites.forEach(sprite => {
      sprite.material?.map?.dispose?.();
      sprite.material?.dispose?.();
      sprite.parent?.remove(sprite);
    });
    this.labelSprites = [];
    this.disposeObject3D(this.graphNodeGroup);
    this.disposeObject3D(this.graphPathGroup);
    this.graphNodeGroup = null;
    this.graphPathGroup = null;
    this.nodeByMesh.clear();
    this.nodeVisuals.clear();
    this.interactionMeshes = [];
    this.nodeMeshes = [];
    this.edgeVisuals = [];
    this.edgePaths = [];
    this.edgeSignals = null;
    /* Die geteilte Puls-Geometrie hängt evtl. noch an gerade entsorgten
     * Signal-Paketen im disposeObject3D()-Aufruf oben – neu anlegen lassen,
     * statt eine bereits dispose()-te Geometrie weiterzuverwenden. */
    this.pulseGeometry = null;
    this.activeNode = null;
    this.hoveredNode = null;
    this.buildGraph();
    this.setActiveVaultRegion(activeRegion, hasRegionSelection);
  }

  updatePointerFromEvent(event) {
    if (!this.canvas) return false;
    const bounds = this.canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return false;
    this.pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
    this.pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
    return true;
  }

  findAtlasEditorHandle(event) {
    if (!this.atlasDevMode || !this.atlasEditorHandles.length || !this.updatePointerFromEvent(event)) return null;
    const modeHandles = this.atlasEditorHandles.filter(handle => this.isAtlasHandleAllowedForMode(handle));
    const bounds = this.canvas.getBoundingClientRect();
    const pointer = new THREE.Vector2(event.clientX, event.clientY);
    /* Editorgriffe werden ohne Depth-Test gezeichnet. Ein normaler Raycast
     * sortiert dennoch nach 3D-Tiefe und kann dadurch beim Klick auf die
     * hintere/rechte Kontur einen davorliegenden Griff auswählen. Für das
     * 2D-Editor-Overlay zählt deshalb der sichtbare Abstand zum Cursor. */
    const screenHit = modeHandles
      .map(handle => {
        const projected = handle.getWorldPosition(new THREE.Vector3()).project(this.camera);
        const screen = new THREE.Vector2(
          bounds.left + (projected.x + 1) * bounds.width * 0.5,
          bounds.top + (1 - projected.y) * bounds.height * 0.5
        );
        return { object: handle, point: handle.getWorldPosition(new THREE.Vector3()), screenDistance: screen.distanceTo(pointer) };
      })
      .filter(hit => hit.screenDistance <= 26)
      .sort((left, right) => left.screenDistance - right.screenDistance)[0];
    if (screenHit) return screenHit;

    this.atlasEditorRaycaster.setFromCamera(this.pointer, this.camera);
    const hits = this.atlasEditorRaycaster.intersectObjects(modeHandles, false);
    return hits.find(hit => hit.object.userData.atlasHandle === "surface") || hits[0] || null;
  }

  setAtlasHandleHover(handle) {
    if (this.atlasHoveredHandle === handle) return;
    if (this.atlasHoveredHandle) this.atlasHoveredHandle.scale.setScalar(1);
    this.atlasHoveredHandle = handle || null;
    if (this.atlasHoveredHandle) this.atlasHoveredHandle.scale.setScalar(1.45);
  }

  getAtlasSurfaceAnchors() {
    if (this.atlasSurfaceAnchors?.length) return this.atlasSurfaceAnchors;

    /* Die Richtungen stammen direkt aus derselben Detail-2-Icosahedron-
     * Topologie wie das Dev-Mesh. Rundungs-Deduplizierung entfernt lediglich
     * mehrfach gespeicherte Triangle-Vertices; das sichtbare Mesh ändert sich
     * dabei nicht. */
    const source = new THREE.IcosahedronGeometry(1, 2);
    const attribute = source.getAttribute("position");
    const unique = new Map();
    const point = new THREE.Vector3();
    for (let index = 0; index < attribute.count; index += 1) {
      point.fromBufferAttribute(attribute, index).normalize();
      const key = `${point.x.toFixed(5)}:${point.y.toFixed(5)}:${point.z.toFixed(5)}`;
      if (!unique.has(key)) unique.set(key, point.clone());
    }
    source.dispose();

    const candidates = [...unique.values()];
    const selected = [];
    const targetCount = Math.min(96, candidates.length);
    /* Farthest-Point-Sampling wählt immer den Vertex mit dem größten Abstand
     * zu allen bereits gewählten Punkten. So entstehen weder ein Dot-Knäuel
     * unten noch unbesetzte Pole oben. */
    const first = candidates.reduce((top, candidate) => candidate.y > top.y ? candidate : top);
    selected.push(first);
    while (selected.length < targetCount) {
      let best = null;
      let bestDistance = -Infinity;
      candidates.forEach(candidate => {
        if (selected.includes(candidate)) return;
        const nearestDistance = selected.reduce(
          (distance, chosen) => Math.min(distance, candidate.distanceToSquared(chosen)),
          Infinity
        );
        if (nearestDistance > bestDistance) {
          bestDistance = nearestDistance;
          best = candidate;
        }
      });
      if (!best) break;
      selected.push(best);
    }

    this.atlasSurfaceAnchors = selected.map((direction, index) => ({
      id: `surface-mesh-${index + 1}`,
      direction: direction.toArray()
    }));
    return this.atlasSurfaceAnchors;
  }

  getAtlasSurfaceAnchorPosition(room, anchor) {
    if (!room || !anchor) return new THREE.Vector3();
    const direction = new THREE.Vector3(...anchor.direction).normalize();
    const seed = room.userData.region.atlasIndex;
    const organic = 1
      + Math.sin(direction.x * 5.1 + seed * 1.71) * 0.026
      + Math.sin(direction.y * 6.3 - seed * 0.83) * 0.021
      + Math.sin(direction.z * 4.7 + seed * 1.19) * 0.019;
    const position = direction.multiplyScalar(organic * (1 + this.getAtlasSurfaceOffsetAtDirection(
      this.getAtlasSurfaceAnchors(), room.userData.surfaceOffsets, direction
    )));
    position.add(this.getAtlasSurfaceDisplacementAtDirection(
      this.getAtlasSurfaceAnchors(), room.userData.surfaceDisplacements, direction
    ));
    return position.multiply(room.scale);
  }

  getAtlasSurfaceDragDirection(room, anchor) {
    return new THREE.Vector3(
      anchor.direction[0] * room.scale.x,
      anchor.direction[1] * room.scale.y,
      anchor.direction[2] * room.scale.z
    ).normalize();
  }

  getAtlasSurfaceDragScale(room, anchor) {
    if (Number.isFinite(anchor.localY)) return Math.min(room.scale.x, room.scale.z);
    const direction = anchor.direction;
    return Math.max(0.001, Math.abs(direction[0] * room.scale.x) + Math.abs(direction[1] * room.scale.y) + Math.abs(direction[2] * room.scale.z));
  }

  getAtlasSurfaceOffsetAtDirection(anchors, surfaceOffsets, direction, localY = null) {
    if (!Array.isArray(anchors) || !anchors.length || !surfaceOffsets) return 0;

    const sampleDirection = direction.clone().normalize();
    const influence = anchors.reduce((result, anchor) => {
      const amount = Number(surfaceOffsets[anchor.id] || 0);
      if (!amount) return result;

      const anchorDirection = new THREE.Vector3(
        anchor.direction[0],
        anchor.direction[1],
        anchor.direction[2]
      ).normalize();
      const alignment = sampleDirection.dot(anchorDirection);
      const neighborhood = THREE.MathUtils.clamp((alignment - 0.80) / 0.20, 0, 1);
      /* Der Einfluss beginnt erst innerhalb von rund 37 Grad. Damit kann ein
       * Dot seine lokale Meshzone frei formen; nur direkte Nachbarvertices
       * folgen über einen weichen Smoothstep-Übergang. */
      const directionWeight = neighborhood * neighborhood * (3 - 2 * neighborhood);
      const heightWeight = Number.isFinite(localY) && Number.isFinite(anchor.localY)
        ? Math.exp(-Math.pow(localY - anchor.localY, 2) / (2 * Math.pow(0.72, 2)))
        : 1;

      const weight = directionWeight * heightWeight;
      result.offset += amount * weight;
      result.weight += weight;
      return result;
    }, { offset: 0, weight: 0 });
    /* Einflüsse werden gemischt, nicht addiert. So können benachbarte
     * Auto-Fit-Punkte ihre jeweils sichere Innenbegrenzung niemals gemeinsam
     * überschießen. Der Nenner 1 erhält den weichen lokalen Falloff eines
     * einzelnen manuell gezogenen Dots. */
    const combinedOffset = influence.offset / Math.max(1, influence.weight);
    return THREE.MathUtils.clamp(combinedOffset, -0.94, 8);
  }

  getAtlasSurfaceDisplacementAtDirection(anchors, surfaceDisplacements, direction) {
    if (!surfaceDisplacements) return new THREE.Vector3();
    const sampleDirection = direction.clone().normalize();
    const displacement = new THREE.Vector3();
    let totalWeight = 0;
    anchors.forEach(anchor => {
      const stored = surfaceDisplacements[anchor.id];
      if (!Array.isArray(stored) || stored.length !== 3) return;
      const anchorDirection = new THREE.Vector3(...anchor.direction).normalize();
      const alignment = sampleDirection.dot(anchorDirection);
      const neighborhood = THREE.MathUtils.clamp((alignment - 0.86) / 0.14, 0, 1);
      const weight = neighborhood * neighborhood * (3 - 2 * neighborhood);
      if (!weight) return;
      displacement.addScaledVector(new THREE.Vector3().fromArray(stored), weight);
      totalWeight += weight;
    });
    if (totalWeight > 1) displacement.multiplyScalar(1 / totalWeight);
    return displacement;
  }

  updateAtlasSurfaceGeometryPreview(room, lightweight = false) {
    if (!room?.userData?.geometry) return;

    const previousGeometry = room.userData.geometry;
    const roomData = {
      center: room.position.clone(),
      radii: room.scale.clone()
    };
    const geometry = this.createAtlasBubbleGeometry(
      room.userData.region.atlasIndex,
      room.userData.surfaceOffsets,
      lightweight ? 2 : null,
      room.userData.surfaceDisplacements
    );

    room.userData.fill.geometry = geometry;
    room.userData.boundary.geometry = geometry;
    room.userData.glow.geometry = geometry;
    room.userData.geometry = geometry;
    previousGeometry.dispose();
  }

  shouldRefreshAtlasSurfacePreview() {
    /* Die analytische Dev-Hülle umfasst nur wenige Vertices und kann dem
     * Pointer direkt folgen. Im Normalmodus bleibt die Vorschau gedrosselt. */
    const previewInterval = this.fastDevMode ? 0 : 80;
    const now = performance.now();
    if (now - this.atlasSurfacePreviewAt < previewInterval) return false;
    this.atlasSurfacePreviewAt = now;
    return true;
  }

  beginAtlasEditorDrag(event, hit) {
    const handle = hit?.object;
    const room = this.getVaultRegionRoom(handle?.userData?.folder);
    if (!handle || !room || !this.isAtlasHandleAllowedForMode(handle) || !this.updatePointerFromEvent(event)) return false;

    const normal = this.camera.getWorldDirection(new THREE.Vector3()).normalize();
    const handlePosition = handle.getWorldPosition(new THREE.Vector3());
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, handlePosition);
    const startPoint = new THREE.Vector3();
    this.atlasEditorRaycaster.setFromCamera(this.pointer, this.camera);
    if (!this.atlasEditorRaycaster.ray.intersectPlane(plane, startPoint)) startPoint.copy(handlePosition);

    const surfaceDirection = handle.userData.anchor
      ? this.getAtlasSurfaceDragDirection(room, handle.userData.anchor)
      : null;
    const surfaceDragScale = handle.userData.anchor
      ? this.getAtlasSurfaceDragScale(room, handle.userData.anchor)
      : 1;
    const projectedStart = handlePosition.clone().project(this.camera);
    const anchorCenterLocal = new THREE.Vector3(
      0,
      Number.isFinite(handle.userData.anchor?.localY) ? handle.userData.anchor.localY : 0,
      0
    );
    const roomCenter = room.localToWorld(anchorCenterLocal).project(this.camera);
    const projectedEnd = surfaceDirection
      ? handlePosition.clone().addScaledVector(surfaceDirection, surfaceDragScale).project(this.camera)
      : projectedStart.clone();
    const canvasBounds = this.canvas.getBoundingClientRect();
    const projectedAxis = new THREE.Vector2(
      (projectedEnd.x - projectedStart.x) * canvasBounds.width * 0.5,
      -(projectedEnd.y - projectedStart.y) * canvasBounds.height * 0.5
    );
    /* Primär gilt die sichtbare Richtung vom Blasenmittelpunkt zum exakt
     * gewählten Griff. Damit erhalten linke und rechte Seite spiegelgleiches
     * Verhalten, unabhängig davon, welche Seite näher an der Kamera liegt. */
    const surfaceScreenAxis = new THREE.Vector2(
      (projectedStart.x - roomCenter.x) * canvasBounds.width * 0.5,
      -(projectedStart.y - roomCenter.y) * canvasBounds.height * 0.5
    );
    if (surfaceScreenAxis.lengthSq() < 1) surfaceScreenAxis.copy(projectedAxis);
    const surfacePixelsPerOffset = Math.max(projectedAxis.length(), surfaceScreenAxis.length());
    if (surfacePixelsPerOffset > 0.001) surfaceScreenAxis.normalize();

    this.atlasEditorDrag = {
      room,
      kind: handle.userData.atlasHandle,
      signs: handle.userData.signs || [0, 0, 0],
      plane,
      startPoint,
      startCenter: room.position.clone(),
      startRadii: room.scale.clone(),
      anchor: handle.userData.anchor || null,
      startSurfaceOffsets: { ...this.sanitizeAtlasSurfaceOffsets(room.userData.surfaceOffsets) },
      startSurfaceDisplacements: this.sanitizeAtlasSurfaceDisplacements(room.userData.surfaceDisplacements),
      surfaceDirection,
      surfaceDragScale,
      surfaceScreenAxis,
      surfacePixelsPerOffset,
      startClient: new THREE.Vector2(event.clientX, event.clientY),
      startNodeVisuals: handle.userData.atlasHandle === "move"
        ? this.nodeMeshes
            .filter(mesh => mesh.userData.vaultRegion === room.userData.folder)
            .flatMap(mesh => mesh.userData.visuals || [mesh])
            .map(object => ({ object, position: object.position.clone() }))
        : []
    };
    this.atlasSurfacePreviewAt = 0;
    this.setAtlasHandleHover(handle);
    this.controls.enabled = false;
    this.canvas?.setPointerCapture?.(event.pointerId);
    this.canvas?.classList.add("is-atlas-editor-dragging");
    event.preventDefault();
    return true;
  }

  updateAtlasEditorDrag(event) {
    const drag = this.atlasEditorDrag;
    if (!drag || !this.updatePointerFromEvent(event)) return;
    this.atlasEditorRaycaster.setFromCamera(this.pointer, this.camera);
    const point = new THREE.Vector3();
    if (!this.atlasEditorRaycaster.ray.intersectPlane(drag.plane, point)) return;
    const delta = point.sub(drag.startPoint);

    if (drag.kind === "move") {
      drag.room.scale.copy(drag.startRadii);
      drag.room.userData.surfaceOffsets = { ...drag.startSurfaceOffsets };
      drag.room.userData.surfaceDisplacements = { ...drag.startSurfaceDisplacements };
      drag.room.position.copy(drag.startCenter).add(delta);
      /* Die Punkte reisen bereits während des Ziehens mit ihrer Atlasblase.
       * Beim Loslassen setzt der normale Graph-Neuaufbau sie anschließend
       * exakt aus dem gespeicherten Raumprofil neu. */
      drag.startNodeVisuals.forEach(({ object, position }) => {
        object.position.copy(position).add(delta);
      });
    } else if (drag.kind === "surface" && drag.anchor && drag.surfaceDirection) {
      drag.room.position.copy(drag.startCenter);
      drag.room.scale.copy(drag.startRadii);
      const pointerDelta = new THREE.Vector2(event.clientX, event.clientY).sub(drag.startClient);
      const worldDelta = event.shiftKey
        ? this.camera.getWorldDirection(new THREE.Vector3()).multiplyScalar(-pointerDelta.y * 0.012)
        : delta.clone();
      const localStart = drag.room.worldToLocal(drag.startPoint.clone());
      const localEnd = drag.room.worldToLocal(drag.startPoint.clone().add(worldDelta));
      const localDelta = localEnd.sub(localStart);
      const starting = new THREE.Vector3().fromArray(
        drag.startSurfaceDisplacements[drag.anchor.id] || [0, 0, 0]
      );
      const displacement = starting.add(localDelta);
      if (displacement.length() > 1.8) displacement.setLength(1.8);
      drag.room.userData.surfaceDisplacements = {
        ...drag.startSurfaceDisplacements,
        [drag.anchor.id]: displacement.toArray()
      };
      /* Im Dev-Modus ist auch die Regelwerk-Hülle analytisch. Damit folgen
       * Griff und Volumen während des Ziehens ohne Brain-Mesh-Raycasts. */
      if (this.shouldRefreshAtlasSurfacePreview()) {
        this.updateAtlasSurfaceGeometryPreview(drag.room, true);
      }
      this.atlasDevNotice = event.shiftKey
        ? `Meshpunkt ${drag.anchor.id}: Tiefe wird angepasst.`
        : `Meshpunkt ${drag.anchor.id}: freie 3D-Position wird angepasst.`;
    } else {
      drag.room.position.copy(drag.startCenter);
      drag.room.userData.surfaceOffsets = { ...drag.startSurfaceOffsets };
      drag.room.userData.surfaceDisplacements = { ...drag.startSurfaceDisplacements };
      const [x, y, z] = drag.signs;
      drag.room.scale.set(
        Math.max(0.12, drag.startRadii.x + (delta.x * x)),
        Math.max(0.12, drag.startRadii.y + (delta.y * y)),
        Math.max(0.12, drag.startRadii.z + (delta.z * z))
      );
    }

    this.syncAtlasRoomData(drag.room);
    this.updateAtlasEditorGizmo();
    if (drag.kind !== "surface") this.atlasDevNotice = "";
    this.updateAtlasDevStatus();
    event.preventDefault();
  }

  finishAtlasEditorDrag(event) {
    const drag = this.atlasEditorDrag;
    if (!drag) return;
    if (drag.kind === "surface") this.updateAtlasSurfaceGeometryPreview(drag.room, false);
    this.atlasEditorDrag = null;
    this.setAtlasHandleHover(null);
    this.controls.enabled = true;
    this.canvas?.releasePointerCapture?.(event?.pointerId);
    this.canvas?.classList.remove("is-atlas-editor-dragging");
    if (drag.kind === "move") this.commitAtlasPositionOverride(drag.room);
    else this.commitAtlasVolumeOverride(drag.room);
    this.atlasDevNotice = drag.kind === "surface"
      ? `${drag.room.userData.folder}: lokale Volumenform wurde gespeichert.`
      : `${drag.room.userData.folder} wurde lokal gespeichert.`;
    this.rebuildGraphAfterAtlasEdit();
    event?.preventDefault?.();
  }

  createAtlasBubbleGeometry(seed = 0, surfaceOffsets = {}, detailOverride = null, surfaceDisplacements = {}) {
        const detail = Number.isInteger(detailOverride)
          ? detailOverride
          : this.fastDevMode ? 2 : 4;
        const geometry = new THREE.IcosahedronGeometry(1, detail);
        const positions = geometry.getAttribute("position");
        const point = new THREE.Vector3();
        for (let index = 0; index < positions.count; index += 1) {
            point.fromBufferAttribute(positions, index).normalize();
            const organic = 1
                + Math.sin(point.x * 5.1 + seed * 1.71) * 0.026
                + Math.sin(point.y * 6.3 - seed * 0.83) * 0.021
                + Math.sin(point.z * 4.7 + seed * 1.19) * 0.019;
            point.multiplyScalar(organic * (1 + this.getAtlasSurfaceOffsetAtDirection(
              this.getAtlasSurfaceAnchors(""), surfaceOffsets, point
            )));
            point.add(this.getAtlasSurfaceDisplacementAtDirection(
              this.getAtlasSurfaceAnchors(), surfaceDisplacements, point
            ));
            positions.setXYZ(index, point.x, point.y, point.z);
        }
        geometry.computeVertexNormals();
        geometry.computeBoundingSphere();
        return geometry;
    }

    createMedullaAtlasBubbleGeometry(room, surfaceOffsets = {}) {
        /* Nur der Regelwerk-Raum wird an der realen Innenkontur des
         * Hirnstamms ausgerichtet. Die feste Raumposition und -skalierung
         * bleiben dabei unverändert: je Höhenebene messen wir von seinem
         * bereits korrekten Mittelpunkt bis zur GLB-Innenhülle. */
        /* Der Hirnstamm umfasst nicht nur die untere Medulla, sondern setzt
         * sich anatomisch über Pons bis zum Mittelhirn fort. Die Ebenen
         * folgen deshalb dem kompletten, nach oben anschließenden Stammraum.
         * Sie verändern ausschließlich die Regelwerk-Hülle – ihr verankerter
         * Mittelpunkt und alle anderen Atlasräume bleiben unverändert. */
        const levels = this.fastDevMode ? [
            -0.72, -0.48, 0.24, 0.96, 1.68, 2.40,
            3.12, 3.72, 4.20, 4.72, 5.28
        ] : [
            -0.72, -0.48, -0.24, 0.00, 0.24, 0.48, 0.72, 0.96,
            1.20, 1.44, 1.68, 1.92, 2.20, 2.52, 2.88, 3.28,
            3.72, 4.20, 4.72, 5.28
        ];
        const segments = this.fastDevMode ? 8 : 10;
        const rings = [];

        levels.forEach(localY => {
            const center = room.center.clone().add(new THREE.Vector3(0, localY * room.radii.y, 0));
            const interiorCenter = this.findMedullaInteriorCenter(center, room);
            if (!interiorCenter) return;

            const distances = [];
            for (let segment = 0; segment < segments; segment += 1) {
                const angle = (segment / segments) * Math.PI * 2;
                const direction = new THREE.Vector3(Math.cos(angle), 0, Math.sin(angle));
                distances.push(this.measureInteriorExitDistance(interiorCenter, direction));
            }
            /* Einzelne Richtungen können an offenen oder nicht-manifold GLB-
             * Kanten keinen Schnitt liefern. Statt den ganzen Querschnitt
             * (und damit den oberen Hirnstamm) zu verwerfen, wird daraus ein
             * enger, garantiert inskribierter Ring gebildet. Die valide
             * Minimaldistanz begrenzt auch jene Richtungen ohne Treffer. */
            const validDistances = distances.filter(distance => distance > 0.0005);
            if (validDistances.length < 3) return;
            const interiorRadius = Math.min(...validDistances) * 0.72;
            const points = [];
            distances.forEach((distance, segment) => {
                const angle = (segment / segments) * Math.PI * 2;
                const direction = new THREE.Vector3(Math.cos(angle), 0, Math.sin(angle));
                /* Der Sicherheitsabstand hält Drahtgitter und Glow sicher
                 * innerhalb der sichtbaren Gehirnoberfläche. */
                let safeDistance = distance > 0.0005
                    ? Math.max(interiorRadius, distance * 0.84)
                    : interiorRadius;
                /* Horizontale Strahlen können ab der Medulla direkt in das
                 * seitlich anschließende Kleinhirn laufen. Dieser Ausläufer
                 * gehört nicht zur Regelwerk-Hülle. Deshalb gilt über die
                 * gesamte Höhe eine schmale Stamm-Querausdehnung; lediglich
                 * die oberste Spitze wird weiter verjüngt. Die y-Positionen,
                 * also Länge und Lage des bereits korrekten Stiels, bleiben
                 * vollständig unverändert. */
                const stemRadius = localY < 3.72
                    ? 0.64
                    : localY < 4.20
                        ? 0.56
                        : localY < 4.72
                            ? 0.48
                            : 0.40;
                const horizontalLimit = Math.min(room.radii.x, room.radii.z) * stemRadius;
                safeDistance = Math.min(safeDistance, horizontalLimit);
                /* Oberflächen-Griffe dehnen nur ihren unmittelbaren
                 * Querschnitt aus. Die gemessene Innenhülle bleibt dabei
                 * die harte Grenze; ein kleiner Abstand verhindert, dass
                 * Wireframe oder Partikel sichtbar durch das GLB treten. */
                const surfaceExpansion = this.getAtlasSurfaceOffsetAtDirection(
                    this.getAtlasSurfaceAnchors(),
                    surfaceOffsets,
                    direction,
                    localY
                );
                if (Math.abs(surfaceExpansion) > 0.0001) {
                    const minimumDistance = surfaceExpansion < 0
                        ? horizontalLimit * 0.06
                        : Math.min(safeDistance, interiorRadius * 0.70);
                    const maximumDistance = distance > 0.0005
                        ? Math.min(distance * 0.90, horizontalLimit * 1.32)
                        : horizontalLimit * 1.16;
                    safeDistance = THREE.MathUtils.clamp(
                        safeDistance * (1 + surfaceExpansion),
                        minimumDistance,
                        Math.max(safeDistance, maximumDistance)
                    );
                }
                const localCenterX = (interiorCenter.x - room.center.x) / room.radii.x;
                const localCenterZ = (interiorCenter.z - room.center.z) / room.radii.z;
                points.push(new THREE.Vector2(
                    localCenterX + (direction.x * safeDistance) / room.radii.x,
                    localCenterZ + (direction.z * safeDistance) / room.radii.z
                ));
            });
            rings.push({ localY, points });
        });

        if (rings.length < 3) return this.createMedullaFallbackGeometry();

        const positions = [];
        const indices = [];
        rings.forEach(ring => ring.points.forEach(point => positions.push(point.x, ring.localY, point.y)));
        for (let ring = 0; ring < rings.length - 1; ring += 1) {
            for (let segment = 0; segment < segments; segment += 1) {
                const next = (segment + 1) % segments;
                const a = ring * segments + segment;
                const b = ring * segments + next;
                const c = (ring + 1) * segments + next;
                const d = (ring + 1) * segments + segment;
                indices.push(a, b, d, b, c, d);
            }
        }
        /* Deckel schließen den tatsächlichen Atlasraum, ohne seine Lage zu
         * verändern. Die Mittelpunkte bleiben ebenfalls Mesh-intern. */
        const addCap = (ringIndex, reverse) => {
            const ring = rings[ringIndex];
            const centerIndex = positions.length / 3;
            const average = ring.points.reduce((sum, point) => sum.add(point), new THREE.Vector2()).multiplyScalar(1 / segments);
            positions.push(average.x, ring.localY, average.y);
            for (let segment = 0; segment < segments; segment += 1) {
                const next = (segment + 1) % segments;
                const a = ringIndex * segments + segment;
                const b = ringIndex * segments + next;
                indices.push(...(reverse ? [centerIndex, b, a] : [centerIndex, a, b]));
            }
        };
        addCap(0, true);
        addCap(rings.length - 1, false);

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geometry.setIndex(indices);
        geometry.computeVertexNormals();
        geometry.computeBoundingSphere();
        geometry.userData.medullaProfile = { rings, segments };
        return geometry;
    }

    createDevMedullaAtlasBubbleGeometry(room, surfaceOffsets = {}) {
        /* Der Atlas-Editor braucht keine anatomische Kollisionsabfrage: Die
         * gespeicherte Blase ist hier selbst die Begrenzung. Dieses Profil
         * liefert dieselben Höhenanker wie die Produktionshülle, kommt aber
         * vollständig ohne Raycasts gegen das große Brain-Mesh aus. */
        const levels = [
            -0.72, -0.48, 0.24, 0.96, 1.68, 2.40,
            3.12, 3.72, 4.20, 4.72, 5.28
        ];
        const segments = 12;
        const anchors = this.getAtlasSurfaceAnchors();
        const rings = levels.map(localY => {
            const stemRadius = localY < 3.72
                ? 0.64
                : localY < 4.20
                    ? 0.56
                    : localY < 4.72
                        ? 0.48
                        : 0.40;
            const endpointScale = localY <= -0.70 || localY >= 5.25 ? 0.36 : 1;
            const points = [];
            for (let segment = 0; segment < segments; segment += 1) {
                const angle = (segment / segments) * Math.PI * 2;
                const direction = new THREE.Vector3(Math.cos(angle), 0, Math.sin(angle));
                const expansion = this.getAtlasSurfaceOffsetAtDirection(
                    anchors,
                    surfaceOffsets,
                    direction,
                    localY
                );
                const organic = 1 + Math.sin(angle * 3 + localY * 0.73) * 0.025;
                const radius = Math.max(
                    stemRadius * 0.06,
                    stemRadius * endpointScale * organic * (1 + expansion)
                );
                points.push(new THREE.Vector2(
                    direction.x * radius,
                    direction.z * radius * 0.82
                ));
            }
            return { localY, points };
        });

        const positions = [];
        const indices = [];
        rings.forEach(ring => ring.points.forEach(point => positions.push(point.x, ring.localY, point.y)));
        for (let ring = 0; ring < rings.length - 1; ring += 1) {
            for (let segment = 0; segment < segments; segment += 1) {
                const next = (segment + 1) % segments;
                const a = ring * segments + segment;
                const b = ring * segments + next;
                const c = (ring + 1) * segments + next;
                const d = (ring + 1) * segments + segment;
                indices.push(a, b, d, b, c, d);
            }
        }
        const addCap = (ringIndex, reverse) => {
            const ring = rings[ringIndex];
            const centerIndex = positions.length / 3;
            const average = ring.points.reduce(
                (sum, point) => sum.add(point),
                new THREE.Vector2()
            ).multiplyScalar(1 / segments);
            positions.push(average.x, ring.localY, average.y);
            for (let segment = 0; segment < segments; segment += 1) {
                const next = (segment + 1) % segments;
                const a = ringIndex * segments + segment;
                const b = ringIndex * segments + next;
                indices.push(...(reverse ? [centerIndex, b, a] : [centerIndex, a, b]));
            }
        };
        addCap(0, true);
        addCap(rings.length - 1, false);

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geometry.setIndex(indices);
        geometry.computeVertexNormals();
        geometry.computeBoundingSphere();
        geometry.userData.medullaProfile = { rings, segments };
        return geometry;
    }

    createMedullaFallbackGeometry() {
        const profile = [
            new THREE.Vector2(0.00, -0.72), new THREE.Vector2(0.12, -0.68),
            new THREE.Vector2(0.19, -0.48), new THREE.Vector2(0.26, -0.12),
            new THREE.Vector2(0.31, 0.27), new THREE.Vector2(0.34, 0.62),
            new THREE.Vector2(0.29, 0.93), new THREE.Vector2(0.00, 1.06)
        ];
        const geometry = new THREE.LatheGeometry(profile, 16);
        geometry.scale(0.58, 1, 0.46);
        geometry.computeVertexNormals();
        geometry.computeBoundingSphere();
        return geometry;
    }

    findMedullaInteriorCenter(center, room) {
        if (this.isPointInsideBrain(center)) return center;
        /* Kleine, begrenzte Suche nur in der lokalen Stamm-Scheibe. Sie
         * korrigiert GLB-Asymmetrien, ohne die festgelegte Raumposition zu
         * ersetzen oder andere Atlasblasen zu berühren. */
        const offsets = (this.fastDevMode ? [
            [0.08, 0], [-0.08, 0], [0, 0.08], [0, -0.08]
        ] : [
            [0.08, 0], [-0.08, 0], [0, 0.08], [0, -0.08],
            [0.06, 0.06], [-0.06, -0.06], [0.16, 0], [-0.16, 0],
            [0, 0.16], [0, -0.16], [0.12, 0.12], [-0.12, -0.12]
        ]);
        for (const [x, z] of offsets) {
            const candidate = center.clone().add(new THREE.Vector3(x * room.radii.x, 0, z * room.radii.z));
            if (this.isPointInsideBrain(candidate)) return candidate;
        }
        return null;
    }

    measureInteriorExitDistance(point, direction) {
        if (!this.brainContainmentMeshes.length) return 0;
        this.brainContainmentRaycaster.set(point, direction);
        this.brainContainmentRaycaster.near = 0.0001;
        this.brainContainmentRaycaster.far = 12;
        const hit = this.brainContainmentRaycaster
            .intersectObjects(this.brainContainmentMeshes, false)
            .find(candidate => candidate.distance > 0.0005);
        return hit?.distance || 0;
    }

    createAtlasBubbleGlowMaterial(color) {
        return new THREE.ShaderMaterial({
            transparent: true,
            depthWrite: false,
            depthTest: true,
            side: THREE.BackSide,
            blending: THREE.AdditiveBlending,
            uniforms: {
                uColor: { value: new THREE.Color(color) },
                uOpacity: { value: 0.12 }
            },
            vertexShader: `
                varying vec3 vNormal;
                varying vec3 vViewDirection;
                void main() {
                    vec4 worldPosition = modelMatrix * vec4(position, 1.0);
                    vNormal = normalize(normalMatrix * normal);
                    vViewDirection = normalize(cameraPosition - worldPosition.xyz);
                    gl_Position = projectionMatrix * viewMatrix * worldPosition;
                }
            `,
            fragmentShader: `
                uniform vec3 uColor;
                uniform float uOpacity;
                varying vec3 vNormal;
                varying vec3 vViewDirection;
                void main() {
                    float rim = pow(1.0 - abs(dot(normalize(vNormal), normalize(vViewDirection))), 2.15);
                    gl_FragColor = vec4(uColor * (0.72 + rim * 1.35), uOpacity * (0.18 + rim));
                }
            `
        });
    }

    insetSurfaceMatrix(surface, scale) {
        const toCenter = new THREE.Matrix4().makeTranslation(
            this.brainCenter.x,
            this.brainCenter.y,
            this.brainCenter.z
        );
        const shrink = new THREE.Matrix4().makeScale(scale, scale, scale);
        const fromCenter = new THREE.Matrix4().makeTranslation(
            -this.brainCenter.x,
            -this.brainCenter.y,
            -this.brainCenter.z
        );
        return toCenter.multiply(shrink).multiply(fromCenter).multiply(surface.matrixWorld);
    }

    createCorticalAtlasMaterial({
        activeOpacity = 0.56,
        inactiveOpacity = 0.025,
        overviewOpacity = 0.24,
        axesScale = 1
    } = {}) {
        return new THREE.ShaderMaterial({
            transparent: true,
            depthWrite: false,
            depthTest: true,
            side: THREE.DoubleSide,
            uniforms: {
                uCenter: { value: this.brainCenter.clone() },
                uAxes: { value: this.corticalAtlasAxes.clone().multiplyScalar(axesScale) },
                uActiveOpacity: { value: activeOpacity },
                uInactiveOpacity: { value: inactiveOpacity },
                uOverviewOpacity: { value: overviewOpacity },
                uActiveRegion: { value: -1 }
            },
            vertexShader: `
                varying vec3 vWorldPosition;
                varying vec3 vWorldNormal;
                void main() {
                    vec4 worldPosition = modelMatrix * vec4(position, 1.0);
                    vWorldPosition = worldPosition.xyz;
                    vWorldNormal = normalize(mat3(modelMatrix) * normal);
                    gl_Position = projectionMatrix * viewMatrix * worldPosition;
                }
            `,
            fragmentShader: `
                uniform vec3 uCenter;
                uniform vec3 uAxes;
                uniform float uActiveOpacity;
                uniform float uInactiveOpacity;
                uniform float uOverviewOpacity;
                uniform float uActiveRegion;
                varying vec3 vWorldPosition;
                varying vec3 vWorldNormal;

                int regionIndex(vec3 p) {
                    /* Lappenähnliche, lückenlose Partition: Kleinhirn/Stamm,
                     * temporal, frontal, parietal, okzipital und medial. */
                    if (p.y < -0.64) return 0;  // Werkzeuge
                    if (p.y < -0.34) {
                        if (p.x < -0.36) return 1; // Daily Notes
                        if (p.x <  0.08) return 2; // Archiv
                        if (p.x <  0.48) return 3; // Anhänge
                        return 4;                  // KI-Wissen
                    }
                    if (p.x < -0.48) return 5;                         // Inbox
                    if (p.x < -0.12) return 6;                         // Projekte
                    if (p.x < 0.28 && p.y > 0.30) return 7;            // Bereiche
                    if (p.x > 0.58) return 8;                          // Ressourcen
                    if (abs(p.z) < 0.20) return 9;                     // Regelwerk
                    return 10;                                         // Kontext
                }

                vec3 regionColor(int region) {
                    if (region == 0) return vec3(1.00, 0.53, 0.43);
                    if (region == 1) return vec3(0.96, 0.43, 0.62);
                    if (region == 2) return vec3(0.39, 0.53, 0.70);
                    if (region == 3) return vec3(0.29, 0.85, 0.82);
                    if (region == 4) return vec3(0.65, 0.89, 0.36);
                    if (region == 5) return vec3(0.21, 0.84, 1.00);
                    if (region == 6) return vec3(0.73, 0.46, 1.00);
                    if (region == 7) return vec3(0.00, 0.90, 0.63);
                    if (region == 8) return vec3(1.00, 0.74, 0.24);
                    if (region == 9) return vec3(0.21, 0.85, 1.00);
                    return vec3(0.56, 0.47, 1.00);
                }

                void main() {
                    vec3 p = normalize((vWorldPosition - uCenter) / max(uAxes, vec3(0.001)));
                    int region = regionIndex(p);
                    vec3 color = regionColor(region);
                    float hasSelection = uActiveRegion > -0.5 ? 1.0 : 0.0;
                    float isActive = abs(float(region) - uActiveRegion) < 0.5 ? 1.0 : 0.0;
                    vec3 lightDirection = normalize(vec3(-0.42, 0.72, 0.58));
                    float light = 0.54 + 0.46 * max(dot(normalize(vWorldNormal), lightDirection), 0.0);
                    vec3 shadedColor = hasSelection > 0.5
                        ? mix(color * 0.12, color, isActive)
                        : color * 0.72;
                    float selectedOpacity = mix(uInactiveOpacity, uActiveOpacity, isActive);
                    float opacity = mix(uOverviewOpacity, selectedOpacity, hasSelection);
                    gl_FragColor = vec4(shadedColor * light, opacity);
                }
            `
        });
    }

    /* Legacy-Generator bewusst erhalten, aber nicht mehr im Renderpfad:
     * kugelige Innen-Sektoren waren sichtbar überlappend und werden durch
     * die echte, flächenbündige Cortex-Parzellierung ersetzt. */
    buildVaultRegionVolumes() {
        const regions = this.vaultRegions();
        const volumeGroup = new THREE.Group();
        volumeGroup.name = "SecBrain-Vault-Räume";

        Object.entries(regions).forEach(([folder, region]) => {
            const geometry = this.createInteriorRegionGeometry(region.sector);
            if (!geometry) return;

            /* Die Vault-Räume sind keine unabhängigen Kugeln mehr. Jeder Raum
             * belegt einen exklusiven Richtungssektor vom inneren Kern bis zur
             * nach innen versetzten Cortex-Oberfläche. So füllen alle Räume
             * gemeinsam das Hirnvolumen und teilen nur gemeinsame Grenzen. */
            const room = new THREE.Group();
            room.name = "Vault-Raum: " + folder;

            const shell = new THREE.Mesh(
                geometry,
                new THREE.MeshBasicMaterial({
                    color: region.color,
                    transparent: true,
                    opacity: 0.095,
                    side: THREE.DoubleSide,
                    depthWrite: false
                })
            );
            shell.renderOrder = 1;
            room.add(shell);

            const outline = new THREE.LineSegments(
                geometry.userData.outline,
                new THREE.LineBasicMaterial({
                    color: region.color,
                    transparent: true,
                    opacity: 0.42,
                    depthWrite: false
                })
            );
            outline.renderOrder = 2;
            room.add(outline);

            room.userData = { folder, region, shell, outline };
            volumeGroup.add(room);
            this.vaultRegionVolumes.push(room);
        });
        this.scene.add(volumeGroup);
        this.vaultRegionVolumeGroup = volumeGroup;
    }

    createInteriorRegionGeometry(sector) {
        if (!sector || !this.innerRegionAxes) return null;

        const thetaSegments = 8;
        const phiSegments = 12;
        const inset = 0.34;
        /* Alle Sektoren schließen bis fast zum gemeinsamen Zentrum. Der
         * minimale Wert verhindert nur z-Flackern genau im Mittelpunkt,
         * erzeugt aber keinen sichtbaren Leerraum im Hirnvolumen. */
        const coreRadius = 0.04;
        const direction = new THREE.Vector3();
        const outer = [];
        const inner = [];
        const positions = [];
        const indices = [];
        const outlinePositions = [];
        const columns = phiSegments + 1;
        const indexAt = (thetaIndex, phiIndex) => thetaIndex * columns + phiIndex;

        for (let thetaIndex = 0; thetaIndex <= thetaSegments; thetaIndex += 1) {
            const theta = sector.thetaStart
                + ((sector.thetaEnd - sector.thetaStart) * thetaIndex / thetaSegments);
            for (let phiIndex = 0; phiIndex <= phiSegments; phiIndex += 1) {
                const phi = sector.phiStart
                    + ((sector.phiEnd - sector.phiStart) * phiIndex / phiSegments);
                direction.set(
                    Math.cos(phi) * Math.sin(theta),
                    Math.cos(theta),
                    Math.sin(phi) * Math.sin(theta)
                ).normalize();
                const axes = this.innerRegionAxes;
                const denominator = Math.sqrt(
                    (direction.x * direction.x / (axes.x * axes.x))
                    + (direction.y * direction.y / (axes.y * axes.y))
                    + (direction.z * direction.z / (axes.z * axes.z))
                );
                const radius = 1 / Math.max(denominator, 0.0001);
                outer.push(this.brainCenter.clone().addScaledVector(
                    direction,
                    Math.max(coreRadius + inset, radius - inset)
                ));
                inner.push(this.brainCenter.clone().addScaledVector(direction, coreRadius));
            }
        }

        outer.forEach((point, index) => {
            positions.push(point.x, point.y, point.z);
            const corePoint = inner[index];
            positions.push(corePoint.x, corePoint.y, corePoint.z);
        });

        const outerIndex = index => index * 2;
        const innerIndex = index => index * 2 + 1;
        const addQuad = (a, b, c, d, flip = false) => {
            if (flip) {
                indices.push(a, c, b, a, d, c);
            } else {
                indices.push(a, b, c, a, c, d);
            }
        };

        for (let thetaIndex = 0; thetaIndex < thetaSegments; thetaIndex += 1) {
            for (let phiIndex = 0; phiIndex < phiSegments; phiIndex += 1) {
                const a = indexAt(thetaIndex, phiIndex);
                const b = indexAt(thetaIndex + 1, phiIndex);
                const c = indexAt(thetaIndex + 1, phiIndex + 1);
                const d = indexAt(thetaIndex, phiIndex + 1);
                addQuad(outerIndex(a), outerIndex(b), outerIndex(c), outerIndex(d));
                addQuad(innerIndex(a), innerIndex(d), innerIndex(c), innerIndex(b), true);
            }
        }

        for (let thetaIndex = 0; thetaIndex < thetaSegments; thetaIndex += 1) {
            const startA = indexAt(thetaIndex, 0);
            const startB = indexAt(thetaIndex + 1, 0);
            const endA = indexAt(thetaIndex, phiSegments);
            const endB = indexAt(thetaIndex + 1, phiSegments);
            addQuad(outerIndex(startA), innerIndex(startA), innerIndex(startB), outerIndex(startB));
            addQuad(outerIndex(endB), innerIndex(endB), innerIndex(endA), outerIndex(endA));
        }

        for (let phiIndex = 0; phiIndex < phiSegments; phiIndex += 1) {
            const topA = indexAt(0, phiIndex);
            const topB = indexAt(0, phiIndex + 1);
            const bottomA = indexAt(thetaSegments, phiIndex);
            const bottomB = indexAt(thetaSegments, phiIndex + 1);
            addQuad(outerIndex(topB), innerIndex(topB), innerIndex(topA), outerIndex(topA));
            addQuad(outerIndex(bottomA), innerIndex(bottomA), innerIndex(bottomB), outerIndex(bottomB));
        }

        const addOutline = points => {
            for (let index = 1; index < points.length; index += 1) {
                outlinePositions.push(
                    points[index - 1].x, points[index - 1].y, points[index - 1].z,
                    points[index].x, points[index].y, points[index].z
                );
            }
        };
        addOutline(Array.from({ length: thetaSegments + 1 }, (_, index) => outer[indexAt(index, 0)]));
        addOutline(Array.from({ length: thetaSegments + 1 }, (_, index) => outer[indexAt(index, phiSegments)]));
        addOutline(Array.from({ length: phiSegments + 1 }, (_, index) => outer[indexAt(0, index)]));
        addOutline(Array.from({ length: phiSegments + 1 }, (_, index) => outer[indexAt(thetaSegments, index)]));

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geometry.setIndex(indices);
        geometry.computeVertexNormals();
        const outline = new THREE.BufferGeometry();
        outline.setAttribute("position", new THREE.Float32BufferAttribute(outlinePositions, 3));
        geometry.userData.outline = outline;
        return geometry;
    }

    createInteriorPositions(nodes) {
        const grouped = new Map();
        nodes.forEach(node => {
            const key = this.vaultFolderFor(node);
            if (!grouped.has(key)) grouped.set(key, []);
            grouped.get(key).push(node);
        });
        const positions = new Map();
        [...grouped.entries()].forEach(([cluster, members], clusterIndex) => {
            const region = this.vaultRegionFor(cluster, clusterIndex);
            const room = this.vaultRegionRooms.get(cluster) || this.resolveVaultRoom(region);
            members.forEach((node, index) => {
                /* Jeder Knoten erhält eine deterministische Position innerhalb
                 * seiner Atlasblase. WICHTIG: room.radii ist nur die nominelle
                 * Basis-Ellipse – die tatsächliche, sichtbare Blasenoberfläche
                 * liegt durch die organischen surfaceOffsets/-Displacements
                 * (die die Blase an die echte Hirnanatomie anschmiegen) oft
                 * ein Vielfaches weiter außen. Eine Position bei "depth * radii"
                 * landete deshalb immer nur in einem kleinen Kern nahe der
                 * Mitte, weit entfernt vom sichtbaren Blasenrand.
                 * Der Fix: den Kandidatenpunkt bewusst weit über jede
                 * realistische Blasengröße hinaus in Zielrichtung setzen und
                 * per clampToAtlasBubble() auf genau "depth" Anteil der ECHTEN
                 * Oberfläche zurückziehen lassen – dieselbe Methode, mit der
                 * bereits die Dendriten (0.82) und Kanten-Scheitelpunkte
                 * (0.72) korrekt bis nah an den sichtbaren Rand reichen. */
                const sequence = index + clusterIndex * 17;
                const azimuth = sequence * 2.399963229728653;
                const vertical = 1 - 2 * ((index + 0.5) / Math.max(members.length, 1));
                const planar = Math.sqrt(Math.max(0, 1 - vertical * vertical));
                const depth = 0.28 + (((sequence + 1) * 0.61803398875) % 1) * 0.58;
                const direction = new THREE.Vector3(
                    Math.cos(azimuth) * planar,
                    vertical,
                    Math.sin(azimuth) * planar
                );
                const position = room.center.clone().add(new THREE.Vector3(
                    direction.x * room.radii.x * 12,
                    direction.y * room.radii.y * 12,
                    direction.z * room.radii.z * 12
                ));
                this.clampToAtlasBubble(position, room, depth);
                positions.set(node.id, position);
            });
        });
        return positions;
    }

    createMedullaNodePosition(room, index, count) {
        if (!room?.center || !room?.radii) return null;
        const profile = room.medullaProfile;
        if (profile?.rings?.length) {
            /* Regelwerk-Knoten folgen derselben konturgenauen Hülle wie die
             * Atlasblase. Dadurch können sie weder in andere Räume noch über
             * die Hirnstamm-Silhouette wandern. */
            for (let attempt = 0; attempt < 10; attempt += 1) {
                const sequence = index + attempt * Math.max(count, 1);
                const ringIndex = Math.min(
                    profile.rings.length - 1,
                    Math.floor((((index + 0.5) / Math.max(count, 1)) + attempt * 0.38196601125) % 1 * profile.rings.length)
                );
                const ring = profile.rings[ringIndex];
                const angle = sequence * 2.399963229728653;
                const segmentPosition = ((angle / (Math.PI * 2)) % 1 + 1) % 1 * profile.segments;
                const leftIndex = Math.floor(segmentPosition) % profile.segments;
                const rightIndex = (leftIndex + 1) % profile.segments;
                const blend = segmentPosition - Math.floor(segmentPosition);
                const boundary = ring.points[leftIndex].clone().lerp(ring.points[rightIndex], blend);
                const depth = 0.22 + (((sequence + 1) * 0.61803398875) % 1) * 0.38;
                const candidate = room.center.clone().add(new THREE.Vector3(
                    boundary.x * room.radii.x * depth,
                    ring.localY * room.radii.y,
                    boundary.y * room.radii.z * depth
                ));
                if (this.fastDevMode || this.isPointInsideBrain(candidate)) return candidate;
            }
            return null;
        }
        const goldenAngle = 2.399963229728653;
        /* Maximal 12 Kandidaten je Regelwerk-Knoten. Das ist absichtlich
         * klein: keine globale, teure Mesh-Abtastung und damit kein erneuter
         * Raycast-Timeout beim Aufbau des Graphen. */
        for (let attempt = 0; attempt < 12; attempt += 1) {
            const sequence = index + attempt * Math.max(count, 1);
            const normalizedY = -0.50 + ((((index + 0.5) / Math.max(count, 1)) + attempt * 0.38196601125) % 1) * 1.18;
            const profileT = THREE.MathUtils.clamp((normalizedY + 0.72) / 1.78, 0, 1);
            const profileRadius = 0.10 + Math.sin(profileT * Math.PI) * 0.23 + profileT * 0.035;
            const radial = profileRadius * (0.18 + (((sequence + 1) * 0.61803398875) % 1) * 0.48);
            const angle = sequence * goldenAngle;
            const candidate = room.center.clone().add(new THREE.Vector3(
                Math.cos(angle) * radial * room.radii.x,
                normalizedY * room.radii.y,
                Math.sin(angle) * radial * room.radii.z
            ));
            if (this.fastDevMode || this.isPointInsideBrain(candidate)) return candidate;
        }
        return null;
    }

    isPointInsideBrain(point) {
        if (!this.brainContainmentMeshes.length) return false;
        /* Eine leicht schräge, feste Richtung vermeidet degenerierte Treffer
         * auf Dreieckskanten. Ungerade Schnittanzahl bedeutet: Punkt liegt
         * im geschlossenen Brain-Mesh. */
        const direction = new THREE.Vector3(1, 0.00037, 0.00019).normalize();
        this.brainContainmentRaycaster.set(point, direction);
        this.brainContainmentRaycaster.near = 0.0001;
        this.brainContainmentRaycaster.far = 90;
        const hits = this.brainContainmentRaycaster
            .intersectObjects(this.brainContainmentMeshes, false)
            .sort((left, right) => left.distance - right.distance);
        let crossings = 0;
        let previousDistance = -Infinity;
        hits.forEach(hit => {
            if (Math.abs(hit.distance - previousDistance) > 0.0005) {
                crossings += 1;
                previousDistance = hit.distance;
            }
        });
        return crossings % 2 === 1;
    }

    clampToVaultRoom(point, room, limit = 0.68) {
        if (!room?.center || !room?.radii) return point;
        const relative = point.clone().sub(room.center);
        const normalizedRadius = Math.sqrt(
            (relative.x * relative.x) / Math.max(room.radii.x * room.radii.x, 0.0001)
            + (relative.y * relative.y) / Math.max(room.radii.y * room.radii.y, 0.0001)
            + (relative.z * relative.z) / Math.max(room.radii.z * room.radii.z, 0.0001)
        );
        if (normalizedRadius > limit) relative.multiplyScalar(limit / normalizedRadius);
        return point.copy(room.center).add(relative);
    }

    clampToAtlasBubble(point, room, limit = 0.68) {
        if (!room?.center || !room?.radii) return point;
        const relative = point.clone().sub(room.center);
        const normalized = new THREE.Vector3(
            relative.x / Math.max(room.radii.x, 0.0001),
            relative.y / Math.max(room.radii.y, 0.0001),
            relative.z / Math.max(room.radii.z, 0.0001)
        );
        const normalizedRadius = normalized.length();
        if (normalizedRadius < 0.0001) return point;
        const direction = normalized.clone().normalize();
        const seed = room.region?.atlasIndex || 0;
        const organic = 1
            + Math.sin(direction.x * 5.1 + seed * 1.71) * 0.026
            + Math.sin(direction.y * 6.3 - seed * 0.83) * 0.021
            + Math.sin(direction.z * 4.7 + seed * 1.19) * 0.019;
        const surface = direction.clone().multiplyScalar(organic * (1 + this.getAtlasSurfaceOffsetAtDirection(
            this.getAtlasSurfaceAnchors(), room.surfaceOffsets, direction
        )));
        surface.add(this.getAtlasSurfaceDisplacementAtDirection(
            this.getAtlasSurfaceAnchors(), room.surfaceDisplacements, direction
        ));
        const safeRadius = Math.max(0.04, direction.dot(surface) * limit);
        if (normalizedRadius > safeRadius) normalized.multiplyScalar(safeRadius / normalizedRadius);
        return point.copy(room.center).add(new THREE.Vector3(
            normalized.x * room.radii.x,
            normalized.y * room.radii.y,
            normalized.z * room.radii.z
        ));
    }

    regionDirection(region, index, count, fallbackIndex = 0) {
        const seed = region.seed || [
            Math.cos(fallbackIndex * 2.399963229728653),
            Math.sin(fallbackIndex * 2.399963229728653) * 0.7,
            0.55
        ];
        const spread = region.spread || [0.12, 0.12, 0.16];
        const wanted = region.atlasIndex;
        const golden = 2.399963229728653;
        for (let attempt = 0; attempt < 72; attempt += 1) {
            const sequence = index + attempt * Math.max(count, 1);
            const angle = sequence * golden;
            const radius = Math.sqrt((sequence % 17 + 0.45) / 17);
            const candidate = new THREE.Vector3(
                seed[0] + Math.cos(angle) * spread[0] * radius,
                seed[1] + Math.sin(angle) * spread[1] * radius,
                seed[2] + Math.sin(angle * 0.57 + 0.8) * spread[2] * radius
            ).normalize();
            if (wanted === undefined || this.atlasRegionIndex(candidate) === wanted) return candidate;
        }
        return new THREE.Vector3(...seed).normalize();
    }

    atlasRegionIndex(direction) {
        const p = direction.clone().normalize();
        if (p.y < -0.64) return 0;
        if (p.y < -0.34) {
            if (p.x < -0.36) return 1;
            if (p.x < 0.08) return 2;
            if (p.x < 0.48) return 3;
            return 4;
        }
        if (p.x < -0.48) return 5;
        if (p.x < -0.12) return 6;
        if (p.x < 0.28 && p.y > 0.30) return 7;
        if (p.x > 0.58) return 8;
        if (Math.abs(p.z) < 0.20) return 9;
        return 10;
    }

    clampToInteriorEnvelope(point, limit = 0.92) {
        if (!this.innerRegionAxes) return point;
        const relative = point.clone().sub(this.brainCenter);
        const normalizedRadius = Math.sqrt(
            (relative.x * relative.x) / (this.innerRegionAxes.x * this.innerRegionAxes.x)
            + (relative.y * relative.y) / (this.innerRegionAxes.y * this.innerRegionAxes.y)
            + (relative.z * relative.z) / (this.innerRegionAxes.z * this.innerRegionAxes.z)
        );
        if (normalizedRadius > limit) {
            relative.multiplyScalar(limit / normalizedRadius);
            point.copy(this.brainCenter).add(relative);
        }
        return point;
    }

    medullaPosition(cluster, index, count) {
        const anchor = this.getMedullaAnchor();
        const outward = anchor.clone().sub(this.brainCenter).normalize();
        const lateral = new THREE.Vector3(1, 0, 0);
        const vertical = new THREE.Vector3().crossVectors(outward, lateral).normalize();
        const groupOffset = cluster === "00 Kontext" ? -0.11 : 0.11;
        const angle = index * 2.399963229728653;
        const radius = Math.sqrt((index + 0.35) / Math.max(count, 1)) * 0.105;
        return anchor.clone()
            .addScaledVector(outward, 0.18)
            .addScaledVector(lateral, groupOffset + Math.cos(angle) * radius)
            .addScaledVector(vertical, Math.sin(angle) * radius * 0.65);
    }

    getMedullaAnchor() {
        if (this.medullaAnchor) return this.medullaAnchor;
        let lowest = null;
        this.surfaceMeshes.forEach(mesh => {
            const positions = mesh.geometry?.getAttribute("position");
            if (!positions) return;
            const sampleStep = Math.max(1, Math.floor(positions.count / 12000));
            const point = new THREE.Vector3();
            for (let index = 0; index < positions.count; index += sampleStep) {
                point.fromBufferAttribute(positions, index).applyMatrix4(mesh.matrixWorld);
                if (!lowest || point.y < lowest.y) lowest = point.clone();
            }
        });
        /* Der unterste Punkt des geladenen anatomischen Modells ist der
         * tatsächliche Hirnstamm, nicht eine angenäherte Bildschirmrichtung. */
        this.medullaAnchor = (lowest || new THREE.Vector3(0, -6, 0)).clone();
        return this.medullaAnchor;
    }

    vaultFolderFor(node) {
        if (node.cluster) return node.cluster;
        const path = node.path || "";
        return path.split("/").find(Boolean) || "Ohne Cluster";
    }

    vaultRegions() {
        const fullTurn = Math.PI * 2;
        return {
            /*
             * `room` beschreibt exklusive, geschlossene Atlasblasen im
             * konservativen Innenellipsoid des GLB-Gehirns. Mittelpunkt und
             * Radien sind normiert. Die alternierende Tiefe trennt benachbarte
             * Räume auch in der dritten Dimension; die Radien lassen zwischen
             * allen Blasen einen sichtbaren Sicherheitsabstand.
             */
            "00 Kontext": {
                atlasIndex: 10, seed: [0.42, 0.08, 0.90], spread: [0.07, 0.08, 0.13], color: 0x8e78ff,
                room: { center: [-0.50, 0.46, 0.10], radius: [0.16, 0.17, 0.21] },
                sector: { thetaStart: fullTurn * 0.375, thetaEnd: Math.PI, phiStart: 0, phiEnd: fullTurn / 3 }
            },
            "00 Regelwerk": {
                atlasIndex: 9, seed: [0.50, 0.84, 0.10], spread: [0.06, 0.08, 0.035], color: 0x35d9ff,
                room: { center: [0.00, 0.48, -0.12], radius: [0.16, 0.17, 0.21] },
                sector: { thetaStart: fullTurn * 0.375, thetaEnd: Math.PI, phiStart: fullTurn / 3, phiEnd: fullTurn * 2 / 3 }
            },
            "01 Inbox": {
                atlasIndex: 5, seed: [-0.72, 0.08, 0.58], spread: [0.06, 0.10, 0.11], color: 0x36d5ff,
                room: { center: [-0.56, 0.04, -0.12], radius: [0.15, 0.17, 0.21] },
                sector: { thetaStart: 0, thetaEnd: Math.PI * 0.375, phiStart: 0, phiEnd: fullTurn / 4 }
            },
            "02 Projekte": {
                atlasIndex: 6, seed: [-0.36, 0.22, 0.72], spread: [0.07, 0.12, 0.12], color: 0xbb76ff,
                room: { center: [-0.19, 0.06, 0.14], radius: [0.15, 0.17, 0.21] },
                sector: { thetaStart: 0, thetaEnd: Math.PI * 0.375, phiStart: fullTurn / 4, phiEnd: fullTurn / 2 }
            },
            "03 Bereiche": {
                atlasIndex: 7, seed: [0.02, 0.66, 0.70], spread: [0.12, 0.08, 0.12], color: 0x00e5a0,
                room: { center: [0.19, 0.06, -0.14], radius: [0.15, 0.17, 0.21] },
                sector: { thetaStart: 0, thetaEnd: Math.PI * 0.375, phiStart: fullTurn / 2, phiEnd: fullTurn * 0.75 }
            },
            "04 Ressourcen": {
                atlasIndex: 8, seed: [0.78, 0.08, 0.54], spread: [0.045, 0.11, 0.10], color: 0xffbd3d,
                room: { center: [0.50, 0.46, 0.10], radius: [0.16, 0.17, 0.21] },
                sector: { thetaStart: 0, thetaEnd: Math.PI * 0.375, phiStart: fullTurn * 0.75, phiEnd: fullTurn }
            },
            "05 Daily Notes": {
                atlasIndex: 1, seed: [-0.65, -0.58, 0.48], spread: [0.06, 0.05, 0.09], color: 0xff6e9d,
                room: { center: [-0.48, -0.36, 0.10], radius: [0.14, 0.15, 0.20] },
                sector: { thetaStart: Math.PI * 0.375, thetaEnd: Math.PI * 0.75, phiStart: 0, phiEnd: fullTurn / 4 }
            },
            "06 Archiv": {
                atlasIndex: 2, seed: [-0.08, -0.46, 0.74], spread: [0.08, 0.045, 0.08], color: 0x6386b2,
                room: { center: [-0.16, -0.38, -0.14], radius: [0.14, 0.15, 0.20] },
                sector: { thetaStart: Math.PI * 0.375, thetaEnd: Math.PI * 0.75, phiStart: fullTurn / 4, phiEnd: fullTurn / 2 }
            },
            "07 Anhänge": {
                atlasIndex: 3, seed: [0.24, -0.48, 0.72], spread: [0.08, 0.045, 0.08], color: 0x49d8d2,
                room: { center: [0.16, -0.38, 0.14], radius: [0.14, 0.15, 0.20] },
                sector: { thetaStart: Math.PI * 0.375, thetaEnd: Math.PI * 0.75, phiStart: fullTurn / 2, phiEnd: fullTurn * 0.75 }
            },
            "08 KI-Wissensbank": {
                atlasIndex: 4, seed: [0.62, -0.44, 0.58], spread: [0.045, 0.05, 0.08], color: 0xa6e35b,
                room: { center: [0.56, 0.04, 0.12], radius: [0.15, 0.17, 0.21] },
                sector: { thetaStart: Math.PI * 0.375, thetaEnd: Math.PI * 0.75, phiStart: fullTurn * 0.75, phiEnd: fullTurn }
            },
            "09 Werkzeuge": {
                atlasIndex: 0, seed: [0.04, -0.94, 0.22], spread: [0.10, 0.035, 0.12], color: 0xff876e,
                room: { center: [0.48, -0.36, -0.10], radius: [0.15, 0.15, 0.20] },
                sector: { thetaStart: fullTurn * 0.375, thetaEnd: Math.PI, phiStart: fullTurn * 2 / 3, phiEnd: fullTurn }
            }
        };
    }

    vaultRegionFor(folder, fallbackIndex) {
        const regions = this.vaultRegions();
        if (regions[folder]) return regions[folder];
        const angle = fallbackIndex * 2.399963229728653;
        return {
            seed: [Math.cos(angle), Math.sin(angle) * 0.7, 0.55],
            spread: [0.1, 0.1, 0.12],
            room: {
                center: [Math.cos(angle) * 0.46, Math.sin(angle) * 0.32, Math.sin(angle * 0.7) * 0.12],
                radius: [0.13, 0.14, 0.18]
            }
        };
    }

}
