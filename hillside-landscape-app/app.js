import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ============================================================
// HILLSIDE LANDSCAPE & RE-GRADING TOOL
// Based on actual site: A-frame house with deck on posts,
// concrete patio underneath, flat paver area, rock borders,
// steep hillside with existing stairs, lakeside dock, beach.
// ============================================================

class HillsideLandscapeApp {
    constructor() {
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.terrain = null;
        this.terrainGeometry = null;
        this.terrainMaterial = null;
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();
        this.brushMarker = null;

        // Terrain settings - scaled to approximate real dimensions
        // Width = across the lot (parallel to shoreline), Depth = house to water
        this.terrainWidth = 70;  // feet across
        this.terrainDepth = 55;  // feet from back of house to water
        this.segments = 100;     // resolution
        this.heightData = [];
        this.originalHeightData = [];

        // Tool state
        this.currentTool = 'raise';
        this.brushSize = 3;
        this.brushStrength = 0.5;
        this.targetHeight = 5;
        this.isEditing = false;

        // Structures (user-placed ones)
        this.structures = [];
        this.selectedStructure = null;
        // Fixed site structures (house, existing stairs, dock, etc.)
        this.siteStructures = [];

        // History for undo/redo
        this.history = [];
        this.historyIndex = -1;
        this.maxHistory = 30;

        // Grid and wireframe toggles
        this.gridVisible = false;
        this.wireframeMode = false;

        // Water
        this.water = null;

        this.init();
    }

    init() {
        this.setupScene();
        this.setupLighting();
        this.createTerrain();
        this.createWater();
        this.createSiteStructures();
        this.createBrushMarker();
        this.setupGrid();
        this.setupEventListeners();
        this.setupUIControls();
        this.saveHistoryState();
        this.updateStats();
        this.updateProfileCanvas();
        this.animate();
    }

    setupScene() {
        const canvas = document.getElementById('three-canvas');

        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x87CEEB);
        this.scene.fog = new THREE.Fog(0x87CEEB, 100, 200);

        this.camera = new THREE.PerspectiveCamera(
            50, window.innerWidth / window.innerHeight, 0.1, 500
        );
        // Default view: looking from the lake toward the house
        this.camera.position.set(5, 20, 50);
        this.camera.lookAt(0, 8, 0);

        this.renderer = new THREE.WebGLRenderer({
            canvas: canvas,
            antialias: true
        });
        this.renderer.setSize(canvas.clientWidth, canvas.clientHeight);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        this.controls = new OrbitControls(this.camera, canvas);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.08;
        this.controls.maxPolarAngle = Math.PI / 2.05;
        this.controls.minDistance = 8;
        this.controls.maxDistance = 120;
        this.controls.target.set(0, 6, 5);

        window.addEventListener('resize', () => this.onResize());
    }

    setupLighting() {
        const ambient = new THREE.AmbientLight(0xffffff, 0.45);
        this.scene.add(ambient);

        const sun = new THREE.DirectionalLight(0xfff5e6, 1.1);
        sun.position.set(25, 35, 15);
        sun.castShadow = true;
        sun.shadow.mapSize.width = 2048;
        sun.shadow.mapSize.height = 2048;
        sun.shadow.camera.near = 0.5;
        sun.shadow.camera.far = 120;
        sun.shadow.camera.left = -50;
        sun.shadow.camera.right = 50;
        sun.shadow.camera.top = 50;
        sun.shadow.camera.bottom = -50;
        this.scene.add(sun);

        const fill = new THREE.DirectionalLight(0x8ecae6, 0.3);
        fill.position.set(-15, 20, -10);
        this.scene.add(fill);

        // Hemisphere light for natural sky/ground bounce
        const hemi = new THREE.HemisphereLight(0x87CEEB, 0x3d5c3a, 0.25);
        this.scene.add(hemi);
    }


    // ============================================================
    // TERRAIN GENERATION - Matches actual site profile
    // Profile (house to water):
    //   z=0.0-0.15: Flat area at house level (~18ft) - yard behind house
    //   z=0.15-0.30: House footprint area, still mostly flat (~17-18ft)
    //   z=0.30-0.40: Concrete patio under deck + flat paver area (~15-17ft)
    //   z=0.40-0.48: Gentle transition, slight slope (~12-15ft)
    //   z=0.48-0.72: STEEP hillside section (~3-12ft) - this is what needs re-grading
    //   z=0.72-0.82: Lower transition, levels to beach (~1-3ft)
    //   z=0.82-0.88: Beach/sand area (~0.3-1ft)
    //   z=0.88-1.0:  Water level (0ft)
    // ============================================================

    generateHeightData() {
        const data = [];
        const segs = this.segments;

        for (let j = 0; j <= segs; j++) {
            for (let i = 0; i <= segs; i++) {
                const x = i / segs; // 0=left, 1=right (looking from lake)
                const z = j / segs; // 0=back(behind house), 1=front(water)

                let height = this.calculateProfileHeight(x, z);
                data.push(Math.max(0, height));
            }
        }
        return data;
    }

    calculateProfileHeight(x, z) {
        let height;

        // === MAIN PROFILE (house to water) ===
        if (z < 0.15) {
            // Behind house - flat yard at top elevation
            height = 18.5;
        } else if (z < 0.28) {
            // House area - stays flat (house sits on this)
            height = 18.0;
        } else if (z < 0.35) {
            // Concrete patio under deck - slight step down
            const t = (z - 0.28) / 0.07;
            height = 18.0 - t * 1.5; // drops from 18 to about 16.5
        } else if (z < 0.46) {
            // FLAT AREA (~15ft beyond the deck) - where patio furniture sits
            // This is relatively level, just slight grade for drainage
            const t = (z - 0.35) / 0.11;
            height = 16.5 - t * 1.5; // very gentle: 16.5 to 15.0
        } else if (z < 0.52) {
            // Transition from flat area to steep slope
            const t = (z - 0.46) / 0.06;
            height = 15.0 - t * 2.5; // 15.0 down to about 12.5
        } else if (z < 0.75) {
            // STEEP hillside - the main slope that needs re-grading
            const t = (z - 0.52) / 0.23;
            // S-curve for natural steep slope
            const curve = t * t * (3 - 2 * t); // smoothstep
            height = 12.5 - curve * 10.5; // 12.5 down to about 2.0
        } else if (z < 0.84) {
            // Lower area leveling to beach
            const t = (z - 0.75) / 0.09;
            height = 2.0 - t * 1.5; // 2.0 down to 0.5
        } else if (z < 0.90) {
            // Beach / sand
            const t = (z - 0.84) / 0.06;
            height = 0.5 - t * 0.3;
        } else {
            // Water
            height = 0.1;
        }

        // === LATERAL VARIATION (across the lot) ===
        const centerDist = Math.abs(x - 0.5) * 2;
        if (z > 0.40 && z < 0.80) {
            height += centerDist * 0.5;
        }

        // Natural undulations (subtle)
        height += Math.sin(x * Math.PI * 4) * 0.15;
        height += Math.cos(z * Math.PI * 3 + x * 2) * 0.12;

        // Rocky/rough area on the steep slope
        if (z > 0.52 && z < 0.75) {
            height += (Math.sin(x * 17 + z * 13) * 0.3 + 
                       Math.cos(x * 23 + z * 7) * 0.2);
        }

        return height;
    }


    createTerrain() {
        this.heightData = this.generateHeightData();
        this.originalHeightData = [...this.heightData];

        this.terrainGeometry = new THREE.PlaneGeometry(
            this.terrainWidth, this.terrainDepth,
            this.segments, this.segments
        );
        this.terrainGeometry.rotateX(-Math.PI / 2);

        // Apply height data to vertices
        const positions = this.terrainGeometry.attributes.position.array;
        for (let i = 0; i < this.heightData.length; i++) {
            positions[i * 3 + 1] = this.heightData[i];
        }
        this.terrainGeometry.computeVertexNormals();
        this.colorTerrain();

        this.terrainMaterial = new THREE.MeshStandardMaterial({
            vertexColors: true,
            flatShading: false,
            side: THREE.DoubleSide,
            roughness: 0.85,
            metalness: 0.05
        });

        this.terrain = new THREE.Mesh(this.terrainGeometry, this.terrainMaterial);
        this.terrain.receiveShadow = true;
        this.terrain.castShadow = true;
        this.scene.add(this.terrain);
    }

    colorTerrain() {
        const count = this.terrainGeometry.attributes.position.count;
        const colors = new Float32Array(count * 3);
        const positions = this.terrainGeometry.attributes.position.array;
        const segs = this.segments;

        for (let idx = 0; idx < count; idx++) {
            const y = positions[idx * 3 + 1];
            const xWorld = positions[idx * 3];
            const zWorld = positions[idx * 3 + 2];
            
            // Compute normalized z for zone detection
            const zNorm = (zWorld + this.terrainDepth / 2) / this.terrainDepth;
            
            let color = new THREE.Color();

            // Concrete patio area (gray)
            if (zNorm > 0.28 && zNorm < 0.35 && Math.abs(xWorld) < 12) {
                color.setHex(0x999999);
            }
            // Flat area beyond deck (packed earth/paver)
            else if (zNorm > 0.35 && zNorm < 0.46 && Math.abs(xWorld) < 14) {
                color.setHex(0x7a7560);
            }
            // Beach
            else if (y < 0.6) {
                color.setHex(0xc2b280);
            }
            // Low grass near beach
            else if (y < 3) {
                color.lerpColors(
                    new THREE.Color(0xc2b280),
                    new THREE.Color(0x7ab648),
                    (y - 0.6) / 2.4
                );
            }
            // Mid slope - mix of grass and dirt/rock
            else if (y < 8) {
                color.lerpColors(
                    new THREE.Color(0x7ab648),
                    new THREE.Color(0x5a7a3f),
                    (y - 3) / 5
                );
                // Add rocky patches on the steep slope
                if (zNorm > 0.50 && zNorm < 0.70) {
                    const rocky = Math.sin(xWorld * 3 + zWorld * 5) * 0.5 + 0.5;
                    if (rocky > 0.6) {
                        color.lerp(new THREE.Color(0x888070), 0.4);
                    }
                }
            }
            // Upper slope
            else if (y < 14) {
                color.lerpColors(
                    new THREE.Color(0x5a7a3f),
                    new THREE.Color(0x3d5c2d),
                    (y - 8) / 6
                );
            }
            // Top / yard
            else {
                color.setHex(0x4a7a3a);
            }

            // Slight noise
            const noise = 0.94 + Math.random() * 0.12;
            color.multiplyScalar(noise);

            colors[idx * 3] = color.r;
            colors[idx * 3 + 1] = color.g;
            colors[idx * 3 + 2] = color.b;
        }

        this.terrainGeometry.setAttribute('color',
            new THREE.BufferAttribute(colors, 3));
    }

    createWater() {
        const waterGeom = new THREE.PlaneGeometry(90, 25);
        const waterMat = new THREE.MeshStandardMaterial({
            color: 0x3a7abd,
            transparent: true,
            opacity: 0.75,
            roughness: 0.05,
            metalness: 0.3,
            side: THREE.DoubleSide
        });
        this.water = new THREE.Mesh(waterGeom, waterMat);
        this.water.rotation.x = -Math.PI / 2;
        this.water.position.set(0, 0.05, this.terrainDepth / 2 + 5);
        this.scene.add(this.water);
    }


    // ============================================================
    // SITE STRUCTURES - Pre-built to match existing property
    // ============================================================

    createSiteStructures() {
        this.createHouse();
        this.createExistingStairs();
        this.createLakesideDeck();
        this.createConcretePatio();
        this.createRockBorders();
        this.createTrees();
    }

    createHouse() {
        const house = new THREE.Group();
        house.userData = { type: 'house', fixed: true };

        const houseWidth = 28;
        const houseDepth = 18;
        const wallHeight = 12;
        const deckHeight = 7;

        // ---- Foundation posts (house is elevated) ----
        const postPositions = [];
        for (let px = -12; px <= 12; px += 6) {
            for (let pz = -7; pz <= 7; pz += 7) {
                postPositions.push([px, pz]);
            }
        }
        postPositions.forEach(([px, pz]) => {
            const postGeom = new THREE.BoxGeometry(0.5, deckHeight, 0.5);
            const postMat = new THREE.MeshStandardMaterial({ color: 0xBFA76F, roughness: 0.7 });
            const post = new THREE.Mesh(postGeom, postMat);
            post.position.set(px, deckHeight / 2, pz);
            post.castShadow = true;
            house.add(post);
        });

        // ---- Main house body ----
        const bodyGeom = new THREE.BoxGeometry(houseWidth, wallHeight, houseDepth);
        const bodyMat = new THREE.MeshStandardMaterial({ color: 0x6b7b8a, roughness: 0.6 });
        const body = new THREE.Mesh(bodyGeom, bodyMat);
        body.position.set(0, deckHeight + wallHeight / 2, 0);
        body.castShadow = true;
        body.receiveShadow = true;
        house.add(body);

        // ---- A-frame roof ----
        const roofShape = new THREE.Shape();
        roofShape.moveTo(-houseWidth / 2 - 1, 0);
        roofShape.lineTo(0, 7);
        roofShape.lineTo(houseWidth / 2 + 1, 0);
        roofShape.closePath();
        const roofExtrudeSettings = { depth: houseDepth + 1, bevelEnabled: false };
        const roofGeom = new THREE.ExtrudeGeometry(roofShape, roofExtrudeSettings);
        const roofMat = new THREE.MeshStandardMaterial({ color: 0x4a4a5a, roughness: 0.7 });
        const roof = new THREE.Mesh(roofGeom, roofMat);
        roof.position.set(0, deckHeight + wallHeight, -houseDepth / 2 - 0.5);
        roof.castShadow = true;
        house.add(roof);

        // ---- Wrap-around deck ----
        const deckGeom = new THREE.BoxGeometry(houseWidth + 6, 0.3, houseDepth + 6);
        const deckMat = new THREE.MeshStandardMaterial({ color: 0xBFA76F, roughness: 0.7 });
        const deck = new THREE.Mesh(deckGeom, deckMat);
        deck.position.set(0, deckHeight, 0);
        deck.castShadow = true;
        deck.receiveShadow = true;
        house.add(deck);

        // ---- Deck railing ----
        const railColor = 0xBFA76F;
        const railHeight = 3.2;
        // Front railing
        this.addDeckRailing(house, -houseWidth/2 - 3, houseWidth/2 + 3, 
            deckHeight, houseDepth/2 + 3, railColor, railHeight, 'x');
        // Left railing
        this.addDeckRailing(house, -houseDepth/2 - 3, houseDepth/2 + 3, 
            deckHeight, 0, railColor, railHeight, 'z', -houseWidth/2 - 3);
        // Right railing  
        this.addDeckRailing(house, -houseDepth/2 - 3, houseDepth/2 + 3, 
            deckHeight, 0, railColor, railHeight, 'z', houseWidth/2 + 3);

        // ---- Windows ----
        const winMat = new THREE.MeshStandardMaterial({ 
            color: 0x88ccff, roughness: 0.1, metalness: 0.3 
        });
        // Upper window (gable)
        const upperWinGeom = new THREE.BoxGeometry(5, 4, 0.2);
        const upperWin = new THREE.Mesh(upperWinGeom, winMat);
        upperWin.position.set(0, deckHeight + wallHeight + 2, houseDepth / 2 + 0.2);
        house.add(upperWin);
        // Lower windows (three across)
        for (let w = -8; w <= 8; w += 8) {
            const winGeom = new THREE.BoxGeometry(4, 5, 0.2);
            const win = new THREE.Mesh(winGeom, winMat);
            win.position.set(w, deckHeight + 5, houseDepth / 2 + 0.2);
            house.add(win);
        }

        // ---- Chimney (right side) ----
        const chimGeom = new THREE.BoxGeometry(2, 8, 2);
        const chimMat = new THREE.MeshStandardMaterial({ color: 0x6b4423, roughness: 0.9 });
        const chimney = new THREE.Mesh(chimGeom, chimMat);
        chimney.position.set(houseWidth / 2 - 1, deckHeight + wallHeight + 4, -2);
        chimney.castShadow = true;
        house.add(chimney);

        // Position the house on the terrain
        house.position.set(2, 11, -12);
        this.scene.add(house);
        this.siteStructures.push(house);
    }

    addDeckRailing(group, start, end, baseY, zPos, color, height, axis, xPos) {
        const length = Math.abs(end - start);
        const postCount = Math.floor(length / 2) + 1;
        const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.7 });

        for (let i = 0; i < postCount; i++) {
            const t = start + (i / (postCount - 1)) * (end - start);
            const postGeom = new THREE.BoxGeometry(0.15, height, 0.15);
            const post = new THREE.Mesh(postGeom, mat);
            if (axis === 'x') {
                post.position.set(t, baseY + height / 2, zPos);
            } else {
                post.position.set(xPos, baseY + height / 2, t);
            }
            post.castShadow = true;
            group.add(post);
        }

        // Top rail
        const railGeom = axis === 'x' 
            ? new THREE.BoxGeometry(length, 0.12, 0.12)
            : new THREE.BoxGeometry(0.12, 0.12, length);
        const rail = new THREE.Mesh(railGeom, mat);
        if (axis === 'x') {
            rail.position.set((start + end) / 2, baseY + height, zPos);
        } else {
            rail.position.set(xPos, baseY + height, (start + end) / 2);
        }
        group.add(rail);
    }


    createExistingStairs() {
        // Existing wooden stairs - from photo they go DOWN from upper area,
        // hit a landing/platform, then PIVOT 45 degrees before continuing down to dock.
        // Located to the LEFT when viewed from lake.
        const stairs = new THREE.Group();
        stairs.userData = { type: 'existing-stairs', fixed: true };

        const stepWidth = 3.5;
        const woodColor = 0xC4A35A;
        const stringerColor = 0x8B6914;

        // === UPPER SECTION: Going straight out from the hill (toward lake, +Z) ===
        // About 8 steps descending from patio level down to landing
        const upperSteps = 8;
        const upperRise = 5.0;
        const upperRun = 8.0;
        const upperRisePerStep = upperRise / upperSteps;
        const upperRunPerStep = upperRun / upperSteps;

        for (let i = 0; i < upperSteps; i++) {
            const stepGeom = new THREE.BoxGeometry(stepWidth, 0.18, 0.85);
            const stepMat = new THREE.MeshStandardMaterial({ color: woodColor, roughness: 0.75 });
            const step = new THREE.Mesh(stepGeom, stepMat);
            step.position.set(0, upperRise - i * upperRisePerStep, i * upperRunPerStep);
            step.castShadow = true;
            step.receiveShadow = true;
            stairs.add(step);
        }

        // Upper stringers
        const upperLen = Math.sqrt(upperRise ** 2 + upperRun ** 2);
        const upperAngle = Math.atan2(upperRise, upperRun);
        [-1, 1].forEach(side => {
            const sGeom = new THREE.BoxGeometry(0.15, 0.6, upperLen);
            const sMat = new THREE.MeshStandardMaterial({ color: stringerColor, roughness: 0.8 });
            const stringer = new THREE.Mesh(sGeom, sMat);
            stringer.position.set(side * (stepWidth / 2 + 0.12), upperRise / 2 + 0.2, upperRun / 2);
            stringer.rotation.x = upperAngle;
            stringer.castShadow = true;
            stairs.add(stringer);
        });

        // === LANDING PLATFORM (where the 45-degree pivot happens) ===
        const landingY = upperRise - upperSteps * upperRisePerStep;
        const landingZ = upperSteps * upperRunPerStep;
        const landingGeom = new THREE.BoxGeometry(5, 0.22, 5);
        const landingMat = new THREE.MeshStandardMaterial({ color: woodColor, roughness: 0.75 });
        const landing = new THREE.Mesh(landingGeom, landingMat);
        landing.position.set(0, landingY, landingZ + 2);
        landing.castShadow = true;
        stairs.add(landing);

        // === LOWER SECTION: Pivots 45 degrees to the left, descends to dock ===
        // Direction after 45-degree turn: goes in both -X and +Z simultaneously
        const lowerSteps = 12;
        const lowerRise = 8.0;
        const lowerHorizPerStep = 1.0; // horizontal distance per step
        const lowerRisePerStep = lowerRise / lowerSteps;
        // 45 degrees means equal X and Z components
        const cos45 = Math.cos(Math.PI / 4); // 0.707
        const sin45 = Math.sin(Math.PI / 4); // 0.707
        const pivotZ = landingZ + 4;
        const pivotX = 0;

        for (let i = 0; i < lowerSteps; i++) {
            const stepGeom = new THREE.BoxGeometry(stepWidth, 0.18, 0.85);
            const stepMat = new THREE.MeshStandardMaterial({ color: woodColor, roughness: 0.75 });
            const step = new THREE.Mesh(stepGeom, stepMat);
            // Move along the 45-degree direction (-X and +Z)
            const dx = -(i + 1) * lowerHorizPerStep * sin45;
            const dz = (i + 1) * lowerHorizPerStep * cos45;
            step.position.set(
                pivotX + dx,
                landingY - (i + 1) * lowerRisePerStep,
                pivotZ + dz
            );
            step.rotation.y = Math.PI / 4; // rotate step 45 degrees
            step.castShadow = true;
            step.receiveShadow = true;
            stairs.add(step);
        }

        // Lower stringers (along the 45-degree run)
        const lowerRunTotal = lowerSteps * lowerHorizPerStep;
        const lowerLen = Math.sqrt(lowerRise ** 2 + lowerRunTotal ** 2);
        const lowerAngle = Math.atan2(lowerRise, lowerRunTotal);
        const lowerCenterDx = -(lowerRunTotal / 2) * sin45;
        const lowerCenterDz = (lowerRunTotal / 2) * cos45;
        [-1, 1].forEach(side => {
            const sGeom = new THREE.BoxGeometry(0.15, 0.6, lowerLen);
            const sMat = new THREE.MeshStandardMaterial({ color: stringerColor, roughness: 0.8 });
            const stringer = new THREE.Mesh(sGeom, sMat);
            // Offset perpendicular to the 45-degree direction
            const perpX = side * (stepWidth / 2 + 0.12) * cos45;
            const perpZ = side * (stepWidth / 2 + 0.12) * sin45;
            stringer.position.set(
                pivotX + lowerCenterDx + perpX,
                landingY - lowerRise / 2 + 0.2,
                pivotZ + lowerCenterDz + perpZ
            );
            stringer.rotation.y = Math.PI / 4;
            stringer.rotation.x = lowerAngle;
            stringer.castShadow = true;
            stairs.add(stringer);
        });

        // Railing posts along upper section (left side)
        for (let i = 0; i <= upperSteps; i += 2) {
            const postGeom = new THREE.BoxGeometry(0.15, 3.2, 0.15);
            const postMat = new THREE.MeshStandardMaterial({ color: stringerColor, roughness: 0.8 });
            const post = new THREE.Mesh(postGeom, postMat);
            post.position.set(
                -(stepWidth / 2 + 0.25),
                upperRise - i * upperRisePerStep + 1.6,
                i * upperRunPerStep
            );
            post.castShadow = true;
            stairs.add(post);
        }

        // Railing posts along lower section (left side of 45-degree run)
        for (let i = 0; i <= lowerSteps; i += 3) {
            const postGeom = new THREE.BoxGeometry(0.15, 3.2, 0.15);
            const postMat = new THREE.MeshStandardMaterial({ color: stringerColor, roughness: 0.8 });
            const post = new THREE.Mesh(postGeom, postMat);
            const dx = -(i + 1) * lowerHorizPerStep * sin45;
            const dz = (i + 1) * lowerHorizPerStep * cos45;
            // Offset to left side (perpendicular to 45-degree direction)
            const perpX = -(stepWidth / 2 + 0.25) * cos45;
            const perpZ = -(stepWidth / 2 + 0.25) * sin45;
            post.position.set(
                pivotX + dx + perpX,
                landingY - (i + 1) * lowerRisePerStep + 1.6,
                pivotZ + dz + perpZ
            );
            post.castShadow = true;
            stairs.add(post);
        }

        // Position: left side of property, upper section starts at patio area
        stairs.position.set(-12, 8.5, 3);
        this.scene.add(stairs);
        this.siteStructures.push(stairs);
    }

    createLakesideDeck() {
        // The dock/deck at the water level (visible in both photos)
        const dock = new THREE.Group();
        dock.userData = { type: 'lakeside-deck', fixed: true };

        const deckColor = 0xC4A35A;
        const postColor = 0x8B6914;

        // Main dock platform
        const mainDeckGeom = new THREE.BoxGeometry(12, 0.25, 8);
        const mainDeckMat = new THREE.MeshStandardMaterial({ color: deckColor, roughness: 0.7 });
        const mainDeck = new THREE.Mesh(mainDeckGeom, mainDeckMat);
        mainDeck.position.set(0, 1.8, 0);
        mainDeck.castShadow = true;
        mainDeck.receiveShadow = true;
        dock.add(mainDeck);

        // Deck posts (pilings)
        const pilingPositions = [
            [-5, -3], [-5, 3], [5, -3], [5, 3], [0, -3], [0, 3]
        ];
        pilingPositions.forEach(([px, pz]) => {
            const pilingGeom = new THREE.CylinderGeometry(0.2, 0.2, 4, 8);
            const pilingMat = new THREE.MeshStandardMaterial({ color: postColor, roughness: 0.85 });
            const piling = new THREE.Mesh(pilingGeom, pilingMat);
            piling.position.set(px, 0, pz);
            piling.castShadow = true;
            dock.add(piling);
        });

        // Railing on lake side
        const railMat = new THREE.MeshStandardMaterial({ color: deckColor, roughness: 0.7 });
        for (let rx = -5; rx <= 5; rx += 2.5) {
            const railPostGeom = new THREE.BoxGeometry(0.15, 3, 0.15);
            const railPost = new THREE.Mesh(railPostGeom, railMat);
            railPost.position.set(rx, 3.3, 4);
            dock.add(railPost);
        }
        const topRailGeom = new THREE.BoxGeometry(12, 0.12, 0.12);
        const topRail = new THREE.Mesh(topRailGeom, railMat);
        topRail.position.set(0, 4.8, 4);
        dock.add(topRail);

        // Dock extension into water
        const extensionGeom = new THREE.BoxGeometry(4, 0.2, 6);
        const extension = new THREE.Mesh(extensionGeom, mainDeckMat);
        extension.position.set(-6, 1.7, 5);
        extension.castShadow = true;
        dock.add(extension);

        // Position at beach level, to the left (matching photo - dock is left of stairs)
        dock.position.set(-18, -0.3, 23);
        this.scene.add(dock);
        this.siteStructures.push(dock);
    }

    createConcretePatio() {
        // Concrete patio under the house deck - NO wall in front
        // Just a flat concrete pad
        const patio = new THREE.Group();
        patio.userData = { type: 'concrete-patio', fixed: true };

        // Main concrete slab under the deck
        const slabGeom = new THREE.BoxGeometry(24, 0.3, 14);
        const slabMat = new THREE.MeshStandardMaterial({ 
            color: 0x9a9a8e, roughness: 0.9, metalness: 0.0 
        });
        const slab = new THREE.Mesh(slabGeom, slabMat);
        slab.position.set(0, 0.15, 0);
        slab.receiveShadow = true;
        patio.add(slab);

        // Flat area ~15ft beyond the deck (where patio furniture is in photos)
        // This is the open area between the concrete pad and where slope begins
        const flatAreaGeom = new THREE.BoxGeometry(28, 0.2, 15);
        const flatAreaMat = new THREE.MeshStandardMaterial({
            color: 0x7a7560,  // packed earth/paver tone
            roughness: 0.95,
            metalness: 0.0
        });
        const flatArea = new THREE.Mesh(flatAreaGeom, flatAreaMat);
        flatArea.position.set(0, -0.5, 14); // extends 15ft beyond the patio
        flatArea.receiveShadow = true;
        patio.add(flatArea);

        // Position under the house
        patio.position.set(2, 14.5, -5);
        this.scene.add(patio);
        this.siteStructures.push(patio);
    }


    createRockBorders() {
        // Rock/boulder borders visible in the sketch - they curve around
        // the flat upper area and along the bottom of the slope

        // Upper rock border (curves around the patio/paver area)
        this.createRockLine([
            [-18, 14, -1], [-14, 14.2, 1], [-10, 14.5, 3],
            [-6, 14.8, 4.5], [-2, 15, 5], [2, 15, 5.5],
            [6, 15, 5.8], [10, 14.8, 5.5], [14, 14.5, 4],
            [18, 14.2, 2], [22, 14, 0]
        ]);

        // Lower rock border (at bottom of slope, before beach)
        this.createRockLine([
            [-22, 1.5, 18], [-18, 1.6, 18.5], [-14, 1.7, 19],
            [-10, 1.8, 19.5], [-6, 1.8, 19.8], [-2, 1.7, 20],
            [2, 1.7, 20], [6, 1.8, 19.8], [10, 1.8, 19.5],
            [14, 1.7, 19], [18, 1.6, 18.5], [22, 1.5, 18]
        ]);
    }

    createRockLine(points) {
        const rockGroup = new THREE.Group();
        rockGroup.userData = { type: 'rock-border', fixed: true };

        points.forEach((p, i) => {
            // Create 2-4 rocks at each point for a natural look
            const rockCount = 2 + Math.floor(Math.random() * 3);
            for (let r = 0; r < rockCount; r++) {
                const size = 0.4 + Math.random() * 0.8;
                const rockGeom = new THREE.SphereGeometry(
                    size, 6, 5
                );
                // Deform slightly for natural boulder look
                const positions = rockGeom.attributes.position;
                for (let v = 0; v < positions.count; v++) {
                    const vx = positions.getX(v);
                    const vy = positions.getY(v);
                    const vz = positions.getZ(v);
                    positions.setXYZ(v,
                        vx * (0.8 + Math.random() * 0.4),
                        vy * (0.6 + Math.random() * 0.3),
                        vz * (0.8 + Math.random() * 0.4)
                    );
                }
                rockGeom.computeVertexNormals();

                const grayShade = 0.4 + Math.random() * 0.25;
                const rockMat = new THREE.MeshStandardMaterial({
                    color: new THREE.Color(grayShade, grayShade * 0.95, grayShade * 0.9),
                    roughness: 0.95,
                    flatShading: true
                });
                const rock = new THREE.Mesh(rockGeom, rockMat);
                rock.position.set(
                    p[0] + (Math.random() - 0.5) * 1.5,
                    p[1] + size * 0.3,
                    p[2] + (Math.random() - 0.5) * 1.2
                );
                rock.rotation.set(
                    Math.random() * 0.5,
                    Math.random() * Math.PI,
                    Math.random() * 0.3
                );
                rock.castShadow = true;
                rockGroup.add(rock);
            }
        });

        this.scene.add(rockGroup);
        this.siteStructures.push(rockGroup);
    }

    createTrees() {
        // Trees visible in both photos (birch trees, pines on sides)
        const treePositions = [
            // Birch trees (thin white trunks) near the stairs
            { x: -14, z: -5, type: 'birch', height: 20 },
            { x: -12, z: 2, type: 'birch', height: 18 },
            { x: -16, z: 8, type: 'birch', height: 22 },
            // Pine trees on the sides
            { x: -25, z: -10, type: 'pine', height: 25 },
            { x: -28, z: 0, type: 'pine', height: 22 },
            { x: 22, z: -8, type: 'pine', height: 24 },
            { x: 25, z: -4, type: 'pine', height: 20 },
            { x: 24, z: 5, type: 'pine', height: 26 },
            { x: -26, z: 10, type: 'pine', height: 18 },
            // Background trees
            { x: -20, z: -18, type: 'pine', height: 28 },
            { x: 0, z: -22, type: 'pine', height: 26 },
            { x: 15, z: -20, type: 'pine', height: 24 },
        ];

        treePositions.forEach(tp => {
            const tree = new THREE.Group();
            const terrainH = this.getHeightAt(tp.x, tp.z) || 15;

            if (tp.type === 'birch') {
                // White trunk
                const trunkGeom = new THREE.CylinderGeometry(0.15, 0.2, tp.height, 8);
                const trunkMat = new THREE.MeshStandardMaterial({ 
                    color: 0xf0ead6, roughness: 0.6 
                });
                const trunk = new THREE.Mesh(trunkGeom, trunkMat);
                trunk.position.set(tp.x, terrainH + tp.height / 2, tp.z);
                trunk.castShadow = true;
                tree.add(trunk);

                // Leaf canopy
                const canopyGeom = new THREE.SphereGeometry(3, 8, 6);
                const canopyMat = new THREE.MeshStandardMaterial({ 
                    color: 0x4a8a3a, roughness: 0.8 
                });
                const canopy = new THREE.Mesh(canopyGeom, canopyMat);
                canopy.position.set(tp.x, terrainH + tp.height * 0.8, tp.z);
                canopy.scale.set(1, 1.3, 1);
                canopy.castShadow = true;
                tree.add(canopy);
            } else {
                // Pine tree - cone shape
                const trunkGeom = new THREE.CylinderGeometry(0.2, 0.35, tp.height * 0.4, 8);
                const trunkMat = new THREE.MeshStandardMaterial({ 
                    color: 0x4a3020, roughness: 0.9 
                });
                const trunk = new THREE.Mesh(trunkGeom, trunkMat);
                trunk.position.set(tp.x, terrainH + tp.height * 0.2, tp.z);
                trunk.castShadow = true;
                tree.add(trunk);

                // Multiple cone layers
                for (let layer = 0; layer < 3; layer++) {
                    const coneH = tp.height * 0.35;
                    const coneR = 3.5 - layer * 0.7;
                    const coneGeom = new THREE.ConeGeometry(coneR, coneH, 8);
                    const coneMat = new THREE.MeshStandardMaterial({ 
                        color: new THREE.Color(0x2d5a27).multiplyScalar(0.9 + layer * 0.1),
                        roughness: 0.85 
                    });
                    const cone = new THREE.Mesh(coneGeom, coneMat);
                    cone.position.set(
                        tp.x, 
                        terrainH + tp.height * 0.35 + layer * coneH * 0.6, 
                        tp.z
                    );
                    cone.castShadow = true;
                    tree.add(cone);
                }
            }

            this.scene.add(tree);
            this.siteStructures.push(tree);
        });
    }


    // ============================================================
    // BRUSH & GRID
    // ============================================================

    createBrushMarker() {
        const markerGeom = new THREE.RingGeometry(0.8, 1, 32);
        const markerMat = new THREE.MeshBasicMaterial({
            color: 0xffff00,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.6
        });
        this.brushMarker = new THREE.Mesh(markerGeom, markerMat);
        this.brushMarker.rotation.x = -Math.PI / 2;
        this.brushMarker.visible = false;
        this.scene.add(this.brushMarker);
    }

    updateBrushMarker(point) {
        if (point) {
            this.brushMarker.position.set(point.x, point.y + 0.3, point.z);
            this.brushMarker.scale.setScalar(this.brushSize);
            this.brushMarker.visible = true;
        } else {
            this.brushMarker.visible = false;
        }
    }

    setupGrid() {
        this.gridHelper = new THREE.GridHelper(70, 35, 0x444444, 0x333333);
        this.gridHelper.position.y = 0.1;
        this.gridHelper.visible = this.gridVisible;
        this.scene.add(this.gridHelper);
    }

    // ============================================================
    // USER-PLACEABLE STRUCTURES
    // ============================================================

    addStairs(x, z) {
        const group = new THREE.Group();
        group.userData = { type: 'stairs', id: Date.now() };

        const stepCount = 14;
        const stepWidth = 3.5;
        const stepDepth = 0.9;
        const stepHeight = 0.6;
        const woodColor = 0xC4A35A;
        const stringerColor = 0x8B6914;

        for (let i = 0; i < stepCount; i++) {
            const stepGeom = new THREE.BoxGeometry(stepWidth, 0.15, stepDepth);
            const stepMat = new THREE.MeshStandardMaterial({ color: woodColor, roughness: 0.75 });
            const step = new THREE.Mesh(stepGeom, stepMat);
            step.position.set(0, i * stepHeight + 0.1, i * stepDepth * 0.85);
            step.castShadow = true;
            step.receiveShadow = true;
            group.add(step);
        }

        // Side stringers
        const totalRun = stepCount * stepDepth * 0.85;
        const totalRise = stepCount * stepHeight;
        const stringerLen = Math.sqrt(totalRun ** 2 + totalRise ** 2);
        const angle = Math.atan2(totalRise, totalRun);

        [-1, 1].forEach(side => {
            const sGeom = new THREE.BoxGeometry(0.12, 0.6, stringerLen);
            const sMat = new THREE.MeshStandardMaterial({ color: stringerColor, roughness: 0.8 });
            const stringer = new THREE.Mesh(sGeom, sMat);
            stringer.position.set(side * (stepWidth / 2 + 0.1), totalRise / 2, totalRun / 2);
            stringer.rotation.x = -angle;
            stringer.castShadow = true;
            group.add(stringer);
        });

        // Railing
        for (let i = 0; i <= stepCount; i += 3) {
            const postGeom = new THREE.BoxGeometry(0.15, 3, 0.15);
            const postMat = new THREE.MeshStandardMaterial({ color: stringerColor, roughness: 0.8 });
            const post = new THREE.Mesh(postGeom, postMat);
            post.position.set(-stepWidth / 2 - 0.2, i * stepHeight + 1.5, i * stepDepth * 0.85);
            post.castShadow = true;
            group.add(post);
        }

        const terrainHeight = this.getHeightAt(x, z) || 5;
        group.position.set(x, terrainHeight, z);
        group.rotation.y = Math.PI;

        this.scene.add(group);
        this.structures.push(group);
        this.updateStructuresList();
        return group;
    }

    addRailing(x, z) {
        const group = new THREE.Group();
        group.userData = { type: 'railing', id: Date.now() };

        const railLength = 8;
        const postCount = 5;
        const railHeight = 3;
        const woodColor = 0xC4A35A;

        for (let i = 0; i < postCount; i++) {
            const postGeom = new THREE.BoxGeometry(0.2, railHeight, 0.2);
            const postMat = new THREE.MeshStandardMaterial({ color: woodColor, roughness: 0.7 });
            const post = new THREE.Mesh(postGeom, postMat);
            const t = i / (postCount - 1);
            post.position.set(t * railLength - railLength / 2, railHeight / 2, 0);
            post.castShadow = true;
            group.add(post);
        }

        // Top and mid rails
        [1.0, 0.5].forEach(hFrac => {
            const railGeom = new THREE.BoxGeometry(railLength, 0.12, 0.08);
            const railMat = new THREE.MeshStandardMaterial({ color: woodColor, roughness: 0.7 });
            const rail = new THREE.Mesh(railGeom, railMat);
            rail.position.y = railHeight * hFrac;
            rail.castShadow = true;
            group.add(rail);
        });

        const terrainHeight = this.getHeightAt(x, z) || 5;
        group.position.set(x, terrainHeight, z);
        this.scene.add(group);
        this.structures.push(group);
        this.updateStructuresList();
        return group;
    }

    addRetainingWall(x, z) {
        const group = new THREE.Group();
        group.userData = { type: 'retaining-wall', id: Date.now() };

        const wallLength = 12;
        const wallHeight = 3.5;
        const postSpacing = 1.5;
        const postCount = Math.floor(wallLength / postSpacing) + 1;
        const postColor = 0x5C4033;
        const boardColor = 0x8B6914;

        // Vertical posts
        for (let i = 0; i < postCount; i++) {
            const postGeom = new THREE.CylinderGeometry(0.15, 0.18, wallHeight + 1.5, 8);
            const postMat = new THREE.MeshStandardMaterial({ color: postColor, roughness: 0.9 });
            const post = new THREE.Mesh(postGeom, postMat);
            post.position.set(i * postSpacing - wallLength / 2, wallHeight / 2 - 0.5, 0);
            post.castShadow = true;
            group.add(post);
        }

        // Horizontal boards
        const boardCount = Math.floor(wallHeight / 0.35);
        for (let i = 0; i < boardCount; i++) {
            const boardGeom = new THREE.BoxGeometry(wallLength, 0.25, 0.2);
            const boardMat = new THREE.MeshStandardMaterial({ color: boardColor, roughness: 0.85 });
            const board = new THREE.Mesh(boardGeom, boardMat);
            board.position.set(0, i * 0.35 + 0.2, 0.15);
            board.castShadow = true;
            group.add(board);
        }

        const terrainHeight = this.getHeightAt(x, z) || 3;
        group.position.set(x, terrainHeight, z);
        this.scene.add(group);
        this.structures.push(group);
        this.updateStructuresList();
        return group;
    }

    deleteSelectedStructure() {
        if (this.selectedStructure) {
            this.scene.remove(this.selectedStructure);
            this.structures = this.structures.filter(s => s !== this.selectedStructure);
            this.selectedStructure = null;
            this.updateStructuresList();
            this.updateStructureProps();
        }
    }

    getHeightAt(x, z) {
        const halfW = this.terrainWidth / 2;
        const halfD = this.terrainDepth / 2;
        const gridX = Math.round(((x + halfW) / this.terrainWidth) * this.segments);
        const gridZ = Math.round(((z + halfD) / this.terrainDepth) * this.segments);

        if (gridX < 0 || gridX > this.segments || gridZ < 0 || gridZ > this.segments) {
            return null;
        }
        const idx = gridZ * (this.segments + 1) + gridX;
        return this.heightData[idx] || 0;
    }


    // ============================================================
    // TERRAIN EDITING TOOLS
    // ============================================================

    editTerrain(intersectPoint) {
        if (!intersectPoint) return;

        const positions = this.terrainGeometry.attributes.position.array;
        const halfW = this.terrainWidth / 2;
        const halfD = this.terrainDepth / 2;
        const segs = this.segments;

        for (let j = 0; j <= segs; j++) {
            for (let i = 0; i <= segs; i++) {
                const idx = j * (segs + 1) + i;
                const vx = (i / segs) * this.terrainWidth - halfW;
                const vz = (j / segs) * this.terrainDepth - halfD;

                const dist = Math.sqrt(
                    (vx - intersectPoint.x) ** 2 +
                    (vz - intersectPoint.z) ** 2
                );

                if (dist < this.brushSize) {
                    const falloff = 1 - (dist / this.brushSize);
                    const strength = this.brushStrength * falloff * 0.25;
                    let currentHeight = this.heightData[idx];

                    switch (this.currentTool) {
                        case 'raise':
                            currentHeight += strength;
                            break;
                        case 'lower':
                            currentHeight -= strength;
                            currentHeight = Math.max(0, currentHeight);
                            break;
                        case 'flatten':
                            currentHeight += (this.targetHeight - currentHeight) * strength * 0.4;
                            break;
                        case 'smooth':
                            const neighbors = this.getNeighborAvg(i, j);
                            currentHeight += (neighbors - currentHeight) * strength;
                            break;
                        case 'terrace':
                            const terraceHeight = Math.round(currentHeight / 2) * 2;
                            currentHeight += (terraceHeight - currentHeight) * strength * 0.3;
                            break;
                    }

                    this.heightData[idx] = currentHeight;
                    positions[idx * 3 + 1] = currentHeight;
                }
            }
        }

        this.terrainGeometry.attributes.position.needsUpdate = true;
        this.terrainGeometry.computeVertexNormals();
        this.colorTerrain();
        this.terrainGeometry.attributes.color.needsUpdate = true;
    }

    getNeighborAvg(i, j) {
        const segs = this.segments;
        let sum = 0;
        let count = 0;
        for (let dj = -2; dj <= 2; dj++) {
            for (let di = -2; di <= 2; di++) {
                const ni = i + di;
                const nj = j + dj;
                if (ni >= 0 && ni <= segs && nj >= 0 && nj <= segs) {
                    sum += this.heightData[nj * (segs + 1) + ni];
                    count++;
                }
            }
        }
        return sum / count;
    }

    // ============================================================
    // TERRAIN PRESETS
    // ============================================================

    applyPresetOriginal() {
        this.heightData = [...this.originalHeightData];
        this.updateTerrainFromData();
        this.saveHistoryState();
    }

    applyPresetGentle() {
        const segs = this.segments;
        for (let j = 0; j <= segs; j++) {
            for (let i = 0; i <= segs; i++) {
                const idx = j * (segs + 1) + i;
                const x = i / segs;
                const z = j / segs;
                let height;
                if (z < 0.30) {
                    height = 18.0; // keep house area flat
                } else if (z < 0.40) {
                    height = 18.0 - ((z - 0.30) / 0.10) * 2.5;
                } else if (z > 0.85) {
                    height = 0.3;
                } else {
                    // Gentle consistent slope from patio to beach
                    const t = (z - 0.40) / 0.45;
                    height = 15.5 - t * 15.0;
                }
                height += Math.sin(x * Math.PI * 3) * 0.15;
                this.heightData[idx] = Math.max(0, height);
            }
        }
        this.updateTerrainFromData();
        this.saveHistoryState();
    }

    applyPresetTerraced() {
        const segs = this.segments;
        for (let j = 0; j <= segs; j++) {
            for (let i = 0; i <= segs; i++) {
                const idx = j * (segs + 1) + i;
                const x = i / segs;
                const z = j / segs;
                let height;
                if (z < 0.30) {
                    height = 18.0;
                } else if (z < 0.40) {
                    height = 18.0 - ((z - 0.30) / 0.10) * 2.5;
                } else if (z > 0.85) {
                    height = 0.3;
                } else {
                    // 4 terraces on the slope
                    const t = (z - 0.40) / 0.45;
                    const baseH = 15.5 - t * 15.0;
                    const terraceLevel = Math.floor(baseH / 4);
                    height = terraceLevel * 4 + 0.5;
                }
                height += Math.sin(x * Math.PI * 2) * 0.1;
                this.heightData[idx] = Math.max(0, height);
            }
        }
        this.updateTerrainFromData();
        this.saveHistoryState();
    }

    applyPresetStepped() {
        const segs = this.segments;
        for (let j = 0; j <= segs; j++) {
            for (let i = 0; i <= segs; i++) {
                const idx = j * (segs + 1) + i;
                const x = i / segs;
                const z = j / segs;
                let height;
                if (z < 0.30) {
                    height = 18.0;
                } else if (z < 0.40) {
                    height = 18.0 - ((z - 0.30) / 0.10) * 2.5;
                } else if (z > 0.85) {
                    height = 0.3;
                } else {
                    const t = (z - 0.40) / 0.45;
                    height = 15.5 - t * 15.0;
                    // Stepped path down the center
                    const centerDist = Math.abs(x - 0.4);
                    if (centerDist < 0.08) {
                        height = Math.round(height / 1.5) * 1.5;
                    } else if (centerDist < 0.12) {
                        const blend = (centerDist - 0.08) / 0.04;
                        const stepped = Math.round(height / 1.5) * 1.5;
                        height = stepped * (1 - blend) + height * blend;
                    }
                }
                this.heightData[idx] = Math.max(0, height);
            }
        }
        this.updateTerrainFromData();
        this.saveHistoryState();
    }

    updateTerrainFromData() {
        const positions = this.terrainGeometry.attributes.position.array;
        for (let i = 0; i < this.heightData.length; i++) {
            positions[i * 3 + 1] = this.heightData[i];
        }
        this.terrainGeometry.attributes.position.needsUpdate = true;
        this.terrainGeometry.computeVertexNormals();
        this.colorTerrain();
        this.terrainGeometry.attributes.color.needsUpdate = true;
        this.updateStats();
        this.updateProfileCanvas();
    }


    // ============================================================
    // HISTORY (Undo/Redo)
    // ============================================================

    saveHistoryState() {
        this.history = this.history.slice(0, this.historyIndex + 1);
        this.history.push([...this.heightData]);
        if (this.history.length > this.maxHistory) {
            this.history.shift();
        }
        this.historyIndex = this.history.length - 1;
    }

    undo() {
        if (this.historyIndex > 0) {
            this.historyIndex--;
            this.heightData = [...this.history[this.historyIndex]];
            this.updateTerrainFromData();
        }
    }

    redo() {
        if (this.historyIndex < this.history.length - 1) {
            this.historyIndex++;
            this.heightData = [...this.history[this.historyIndex]];
            this.updateTerrainFromData();
        }
    }

    // ============================================================
    // UI & STATS
    // ============================================================

    updateStats() {
        let max = -Infinity, min = Infinity;
        for (const h of this.heightData) {
            max = Math.max(max, h);
            min = Math.min(min, h);
        }
        document.getElementById('stat-max').textContent = max.toFixed(1);
        document.getElementById('stat-min').textContent = min.toFixed(1);

        // Average slope of the main hillside section
        // Sample center line from z=0.40 to z=0.82
        const segs = this.segments;
        const centerI = Math.floor(segs * 0.5);
        const topJ = Math.floor(segs * 0.40);
        const botJ = Math.floor(segs * 0.82);
        const topH = this.heightData[topJ * (segs + 1) + centerI];
        const botH = this.heightData[botJ * (segs + 1) + centerI];
        const run = (0.82 - 0.40) * this.terrainDepth;
        const rise = topH - botH;
        const slopeAngle = Math.atan2(rise, run) * (180 / Math.PI);
        document.getElementById('stat-slope').textContent = slopeAngle.toFixed(1);

        const area = this.terrainWidth * this.terrainDepth;
        document.getElementById('stat-area').textContent = area.toFixed(0);
    }

    updateProfileCanvas() {
        const canvas = document.getElementById('profile-canvas');
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;

        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = '#0d1b2a';
        ctx.fillRect(0, 0, w, h);

        const segs = this.segments;
        const centerI = Math.floor(segs * 0.45); // Slightly left of center (where stairs are)

        // Current profile
        ctx.beginPath();
        ctx.strokeStyle = '#4fc3f7';
        ctx.lineWidth = 2;
        for (let j = 0; j <= segs; j++) {
            const idx = j * (segs + 1) + centerI;
            const x = (j / segs) * w;
            const y = h - (this.heightData[idx] / 20) * (h - 15) - 5;
            if (j === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Original profile
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(255,255,100,0.35)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        for (let j = 0; j <= segs; j++) {
            const idx = j * (segs + 1) + centerI;
            const x = (j / segs) * w;
            const y = h - (this.originalHeightData[idx] / 20) * (h - 15) - 5;
            if (j === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.setLineDash([]);

        // Zone labels
        ctx.fillStyle = '#666';
        ctx.font = '9px sans-serif';
        ctx.fillText('House', 2, 10);
        ctx.fillText('Patio', w * 0.32, 10);
        ctx.fillText('Slope', w * 0.55, 10);
        ctx.fillText('Beach', w * 0.82, 10);

        // Legend
        ctx.fillStyle = '#4fc3f7';
        ctx.fillText('Current', w - 50, h - 3);
        ctx.fillStyle = 'rgba(255,255,100,0.6)';
        ctx.fillText('Original', w - 110, h - 3);
    }

    updateStructuresList() {
        const list = document.getElementById('structures-list');
        if (this.structures.length === 0) {
            list.innerHTML = '<li class="hint">No user structures placed yet</li>';
            return;
        }
        list.innerHTML = this.structures.map((s, i) => {
            const label = s.userData.type.replace(/-/g, ' ');
            const selected = s === this.selectedStructure ? ' style="background:#1a4a7a"' : '';
            return `<li${selected} data-idx="${i}">${label} #${i + 1}</li>`;
        }).join('');

        list.querySelectorAll('li').forEach(li => {
            li.addEventListener('click', () => {
                const idx = parseInt(li.dataset.idx);
                this.selectStructure(this.structures[idx]);
            });
        });
    }

    selectStructure(structure) {
        if (this.selectedStructure) {
            this.selectedStructure.traverse(child => {
                if (child.isMesh && child.userData.originalEmissive !== undefined) {
                    child.material.emissive.setHex(child.userData.originalEmissive);
                }
            });
        }

        this.selectedStructure = structure;

        if (structure) {
            structure.traverse(child => {
                if (child.isMesh) {
                    child.userData.originalEmissive = child.material.emissive.getHex();
                    child.material.emissive.setHex(0x333300);
                }
            });
        }
        this.updateStructureProps();
        this.updateStructuresList();
    }

    updateStructureProps() {
        const panel = document.getElementById('structure-props');
        if (!this.selectedStructure) {
            panel.innerHTML = '<p class="hint">Select a structure to edit properties</p>';
            return;
        }

        const s = this.selectedStructure;
        const type = s.userData.type;
        panel.innerHTML = `
            <p><strong>${type.replace(/-/g, ' ')}</strong></p>
            <label>X Position</label>
            <input type="number" id="prop-x" value="${s.position.x.toFixed(1)}" step="0.5">
            <label>Z Position (depth)</label>
            <input type="number" id="prop-z" value="${s.position.z.toFixed(1)}" step="0.5">
            <label>Y (Height)</label>
            <input type="number" id="prop-y" value="${s.position.y.toFixed(1)}" step="0.5">
            <label>Rotation (degrees)</label>
            <input type="number" id="prop-rot" value="${(s.rotation.y * 180 / Math.PI).toFixed(0)}" step="15">
            <label>Scale</label>
            <input type="range" id="prop-scale" min="0.3" max="2.5" value="${s.scale.x.toFixed(2)}" step="0.1">
        `;

        const bind = (id, fn) => panel.querySelector(id).addEventListener('change', fn);
        const bindInput = (id, fn) => panel.querySelector(id).addEventListener('input', fn);
        bind('#prop-x', e => { s.position.x = parseFloat(e.target.value); });
        bind('#prop-z', e => { s.position.z = parseFloat(e.target.value); });
        bind('#prop-y', e => { s.position.y = parseFloat(e.target.value); });
        bind('#prop-rot', e => { s.rotation.y = parseFloat(e.target.value) * Math.PI / 180; });
        bindInput('#prop-scale', e => {
            const sc = parseFloat(e.target.value);
            s.scale.set(sc, sc, sc);
        });
    }


    // ============================================================
    // EVENT LISTENERS
    // Controls: 
    //   Left-click drag = Orbit/Rotate camera (default)
    //   Shift + Left-click = Edit terrain / Place structures
    //   Right-click drag = Pan camera
    //   Scroll = Zoom
    // ============================================================

    setupEventListeners() {
        const canvas = document.getElementById('three-canvas');

        // Track shift key state for edit mode
        this.shiftHeld = false;
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Shift') {
                this.shiftHeld = true;
                // Disable orbit controls while shift is held so we can edit
                this.controls.enabled = false;
            }
            if (e.ctrlKey && e.key === 'z') {
                e.preventDefault();
                this.undo();
            } else if (e.ctrlKey && e.key === 'y') {
                e.preventDefault();
                this.redo();
            } else if (e.key === 'Delete') {
                this.deleteSelectedStructure();
            }
        });
        document.addEventListener('keyup', (e) => {
            if (e.key === 'Shift') {
                this.shiftHeld = false;
                this.controls.enabled = true;
            }
        });

        canvas.addEventListener('mousedown', (e) => {
            if (e.button === 0 && this.shiftHeld) {
                // Shift+Left click = terrain edit
                this.isEditing = true;
                this.handleTerrainEdit(e);
            }
        });

        canvas.addEventListener('mousemove', (e) => {
            this.updateMousePosition(e);
            const intersect = this.getTerrainIntersect();
            if (intersect) {
                this.updateBrushMarker(intersect.point);
                document.getElementById('elevation-info').textContent =
                    `Elevation: ${intersect.point.y.toFixed(1)} ft`;
                document.getElementById('coords-info').textContent =
                    `Position: (${intersect.point.x.toFixed(1)}, ${intersect.point.z.toFixed(1)})`;
            } else {
                this.updateBrushMarker(null);
            }
            if (this.isEditing && this.shiftHeld) {
                this.handleTerrainEdit(e);
            }
        });

        canvas.addEventListener('mouseup', (e) => {
            if (e.button === 0 && this.isEditing) {
                this.isEditing = false;
                this.saveHistoryState();
                this.updateStats();
                this.updateProfileCanvas();
            }
        });

        canvas.addEventListener('mouseleave', () => {
            this.isEditing = false;
            this.updateBrushMarker(null);
        });
    }

    updateMousePosition(e) {
        const canvas = document.getElementById('three-canvas');
        const rect = canvas.getBoundingClientRect();
        this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    }

    getTerrainIntersect() {
        this.raycaster.setFromCamera(this.mouse, this.camera);
        const intersects = this.raycaster.intersectObject(this.terrain);
        return intersects.length > 0 ? intersects[0] : null;
    }

    handleTerrainEdit(e) {
        if (['add-stairs', 'add-railing', 'add-retaining-wall'].includes(this.currentTool)) {
            const intersect = this.getTerrainIntersect();
            if (intersect && e.type === 'mousedown') {
                const p = intersect.point;
                switch (this.currentTool) {
                    case 'add-stairs': this.addStairs(p.x, p.z); break;
                    case 'add-railing': this.addRailing(p.x, p.z); break;
                    case 'add-retaining-wall': this.addRetainingWall(p.x, p.z); break;
                }
                this.setTool('raise');
            }
            return;
        }

        const intersect = this.getTerrainIntersect();
        if (intersect) {
            this.editTerrain(intersect.point);
        }
    }

    // ============================================================
    // UI CONTROLS SETUP
    // ============================================================

    setupUIControls() {
        const toolBtns = {
            'btn-raise': 'raise', 'btn-lower': 'lower',
            'btn-flatten': 'flatten', 'btn-smooth': 'smooth',
            'btn-terrace': 'terrace'
        };
        for (const [id, tool] of Object.entries(toolBtns)) {
            document.getElementById(id).addEventListener('click', () => this.setTool(tool));
        }

        document.getElementById('btn-add-stairs').addEventListener('click', () => this.setTool('add-stairs'));
        document.getElementById('btn-add-railing').addEventListener('click', () => this.setTool('add-railing'));
        document.getElementById('btn-add-retaining-wall').addEventListener('click', () => this.setTool('add-retaining-wall'));
        document.getElementById('btn-delete-structure').addEventListener('click', () => this.deleteSelectedStructure());

        // Sliders
        document.getElementById('brush-size').addEventListener('input', (e) => {
            this.brushSize = parseFloat(e.target.value);
            document.getElementById('brush-size-val').textContent = this.brushSize;
        });
        document.getElementById('brush-strength').addEventListener('input', (e) => {
            this.brushStrength = parseFloat(e.target.value);
            document.getElementById('brush-strength-val').textContent = this.brushStrength;
        });
        document.getElementById('target-height').addEventListener('input', (e) => {
            this.targetHeight = parseFloat(e.target.value);
            document.getElementById('target-height-val').textContent = this.targetHeight;
        });

        // View controls
        document.getElementById('btn-reset-view').addEventListener('click', () => {
            this.camera.position.set(5, 20, 50);
            this.controls.target.set(0, 6, 5);
        });
        document.getElementById('btn-top-view').addEventListener('click', () => {
            this.camera.position.set(0, 55, 5);
            this.controls.target.set(0, 0, 5);
        });
        document.getElementById('btn-side-view').addEventListener('click', () => {
            this.camera.position.set(0, 10, 55);
            this.controls.target.set(0, 8, 0);
        });
        document.getElementById('btn-house-view').addEventListener('click', () => {
            this.camera.position.set(0, 22, -30);
            this.controls.target.set(0, 8, 10);
        });

        // Presets
        document.getElementById('btn-preset-original').addEventListener('click', () => this.applyPresetOriginal());
        document.getElementById('btn-preset-gentle').addEventListener('click', () => this.applyPresetGentle());
        document.getElementById('btn-preset-terraced').addEventListener('click', () => this.applyPresetTerraced());
        document.getElementById('btn-preset-stepped').addEventListener('click', () => this.applyPresetStepped());

        // Actions
        document.getElementById('btn-undo').addEventListener('click', () => this.undo());
        document.getElementById('btn-redo').addEventListener('click', () => this.redo());
        document.getElementById('btn-export').addEventListener('click', () => this.exportData());
        document.getElementById('btn-toggle-grid').addEventListener('click', () => {
            this.gridVisible = !this.gridVisible;
            this.gridHelper.visible = this.gridVisible;
        });
        document.getElementById('btn-toggle-wireframe').addEventListener('click', () => {
            this.wireframeMode = !this.wireframeMode;
            this.terrainMaterial.wireframe = this.wireframeMode;
        });
    }

    setTool(tool) {
        this.currentTool = tool;
        document.querySelectorAll('.tool-group .tool-btn').forEach(btn => btn.classList.remove('active'));
        const toolNames = {
            'raise': 'btn-raise', 'lower': 'btn-lower',
            'flatten': 'btn-flatten', 'smooth': 'btn-smooth',
            'terrace': 'btn-terrace'
        };
        if (toolNames[tool]) {
            document.getElementById(toolNames[tool]).classList.add('active');
        }
        const modeNames = {
            'raise': 'Raise Terrain', 'lower': 'Lower Terrain',
            'flatten': 'Flatten to Target', 'smooth': 'Smooth',
            'terrace': 'Create Terrace',
            'add-stairs': 'Click to Place Stairs',
            'add-railing': 'Click to Place Railing',
            'add-retaining-wall': 'Click to Place Retaining Wall'
        };
        document.getElementById('mode-info').textContent = `Mode: ${modeNames[tool] || tool}`;
    }

    // ============================================================
    // EXPORT
    // ============================================================

    exportData() {
        const data = {
            terrain: {
                width: this.terrainWidth,
                depth: this.terrainDepth,
                segments: this.segments,
                heightData: this.heightData
            },
            structures: this.structures.map(s => ({
                type: s.userData.type,
                position: { x: s.position.x, y: s.position.y, z: s.position.z },
                rotation: s.rotation.y,
                scale: s.scale.x
            }))
        };
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'hillside-landscape-data.json';
        a.click();
        URL.revokeObjectURL(url);
    }

    // ============================================================
    // RENDER LOOP
    // ============================================================

    onResize() {
        const container = document.getElementById('viewport');
        const w = container.clientWidth;
        const h = container.clientHeight;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        this.controls.update();

        // Subtle water animation
        if (this.water) {
            this.water.position.y = 0.05 + Math.sin(Date.now() * 0.0008) * 0.04;
        }

        this.renderer.render(this.scene, this.camera);
    }
}

// ============================================================
// LAUNCH
// ============================================================
window.addEventListener('DOMContentLoaded', () => {
    new HillsideLandscapeApp();
});
