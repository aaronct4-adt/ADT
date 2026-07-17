import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ============================================================
// HILLSIDE LANDSCAPE & RE-GRADING TOOL
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
        
        // Terrain settings
        this.terrainWidth = 60;  // feet across (parallel to beach)
        this.terrainDepth = 40;  // feet deep (house to water)
        this.segments = 80;      // resolution
        this.heightData = [];
        this.originalHeightData = [];
        
        // Tool state
        this.currentTool = 'raise';
        this.brushSize = 3;
        this.brushStrength = 0.5;
        this.targetHeight = 5;
        this.isEditing = false;
        
        // Structures
        this.structures = [];
        this.selectedStructure = null;
        
        // History for undo/redo
        this.history = [];
        this.historyIndex = -1;
        this.maxHistory = 30;
        
        // Grid and wireframe toggles
        this.gridVisible = true;
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
        this.scene.fog = new THREE.Fog(0x87CEEB, 80, 150);

        this.camera = new THREE.PerspectiveCamera(
            55, window.innerWidth / window.innerHeight, 0.1, 500
        );
        this.camera.position.set(30, 25, 45);
        this.camera.lookAt(0, 5, 0);

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
        this.controls.maxPolarAngle = Math.PI / 2.1;
        this.controls.minDistance = 10;
        this.controls.maxDistance = 100;
        this.controls.target.set(0, 5, 0);

        window.addEventListener('resize', () => this.onResize());
    }


    setupLighting() {
        const ambient = new THREE.AmbientLight(0xffffff, 0.5);
        this.scene.add(ambient);

        const sun = new THREE.DirectionalLight(0xfff5e6, 1.0);
        sun.position.set(20, 30, 10);
        sun.castShadow = true;
        sun.shadow.mapSize.width = 2048;
        sun.shadow.mapSize.height = 2048;
        sun.shadow.camera.near = 0.5;
        sun.shadow.camera.far = 100;
        sun.shadow.camera.left = -40;
        sun.shadow.camera.right = 40;
        sun.shadow.camera.top = 40;
        sun.shadow.camera.bottom = -40;
        this.scene.add(sun);

        const fill = new THREE.DirectionalLight(0x8ecae6, 0.3);
        fill.position.set(-10, 15, -10);
        this.scene.add(fill);
    }

    generateHeightData() {
        // Model the hillside: house at top (back), beach/water at bottom (front)
        // Based on the photo: ~20ft elevation from deck to water
        const data = [];
        const segs = this.segments;

        for (let j = 0; j <= segs; j++) {
            for (let i = 0; i <= segs; i++) {
                const x = i / segs; // 0=left, 1=right
                const z = j / segs; // 0=back(house), 1=front(water)

                // Main slope from house (20ft) down to water (0ft)
                // Use a slight S-curve for natural hillside feel
                let height = 20 * (1 - z);
                
                // Add the steeper section in the middle (where re-grading is needed)
                const midSteep = Math.exp(-((z - 0.5) ** 2) / 0.05) * 3;
                height += midSteep * (1 - z);

                // Natural undulations
                height += Math.sin(x * Math.PI * 3) * 0.5;
                height += Math.cos(z * Math.PI * 2) * 0.3;
                
                // Slight bowl shape (lower in center)
                const centerDist = Math.abs(x - 0.5) * 2;
                height += centerDist * 0.8;

                // Rock outcropping area (from photo - rocky areas on slope)
                if (z > 0.3 && z < 0.7 && x > 0.4 && x < 0.8) {
                    height += Math.random() * 0.3;
                }

                // Beach area (flat near water)
                if (z > 0.85) {
                    height = Math.max(height, 0.5) * 0.3;
                }

                // Ensure water level
                if (z > 0.92) {
                    height = Math.min(height, 0.2);
                }

                data.push(Math.max(0, height));
            }
        }
        return data;
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

        // Color the terrain based on height
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

        for (let i = 0; i < count; i++) {
            const y = positions[i * 3 + 1];
            const z = positions[i * 3 + 2]; // depth position
            let color = new THREE.Color();

            if (y < 0.5) {
                // Water/sand area
                color.setHex(0xc2b280);
            } else if (y < 3) {
                // Low grass / beach transition
                color.lerpColors(
                    new THREE.Color(0xc2b280),
                    new THREE.Color(0x7ab648),
                    (y - 0.5) / 2.5
                );
            } else if (y < 10) {
                // Mid slope grass
                color.lerpColors(
                    new THREE.Color(0x7ab648),
                    new THREE.Color(0x4a8c3f),
                    (y - 3) / 7
                );
            } else if (y < 16) {
                // Upper slope
                color.lerpColors(
                    new THREE.Color(0x4a8c3f),
                    new THREE.Color(0x2d5a27),
                    (y - 10) / 6
                );
            } else {
                // Top near house
                color.setHex(0x2d5a27);
            }

            // Add some noise for natural look
            const noise = 0.95 + Math.random() * 0.1;
            color.multiplyScalar(noise);

            colors[i * 3] = color.r;
            colors[i * 3 + 1] = color.g;
            colors[i * 3 + 2] = color.b;
        }

        this.terrainGeometry.setAttribute('color',
            new THREE.BufferAttribute(colors, 3));
    }


    createWater() {
        const waterGeom = new THREE.PlaneGeometry(80, 30);
        const waterMat = new THREE.MeshStandardMaterial({
            color: 0x4a90d9,
            transparent: true,
            opacity: 0.7,
            roughness: 0.1,
            metalness: 0.3,
            side: THREE.DoubleSide
        });
        this.water = new THREE.Mesh(waterGeom, waterMat);
        this.water.rotation.x = -Math.PI / 2;
        this.water.position.set(0, 0.1, 28);
        this.scene.add(this.water);
    }

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
            this.brushMarker.position.set(point.x, point.y + 0.2, point.z);
            this.brushMarker.scale.setScalar(this.brushSize);
            this.brushMarker.visible = true;
        } else {
            this.brushMarker.visible = false;
        }
    }

    setupGrid() {
        this.gridHelper = new THREE.GridHelper(60, 30, 0x444444, 0x333333);
        this.gridHelper.position.y = 0.05;
        this.scene.add(this.gridHelper);
    }


    // ============================================================
    // STRUCTURES: Stairs, Railings, Retaining Walls
    // ============================================================

    addStairs(x, z) {
        const group = new THREE.Group();
        group.userData = { type: 'stairs', id: Date.now() };
        
        const stepCount = 12;
        const stepWidth = 3;
        const stepDepth = 0.8;
        const stepHeight = 0.7;
        const woodColor = 0x8B6914;
        
        // Create individual steps
        for (let i = 0; i < stepCount; i++) {
            const stepGeom = new THREE.BoxGeometry(stepWidth, 0.15, stepDepth);
            const stepMat = new THREE.MeshStandardMaterial({
                color: woodColor,
                roughness: 0.8,
                metalness: 0.05
            });
            const step = new THREE.Mesh(stepGeom, stepMat);
            step.position.set(0, i * stepHeight + 0.1, i * stepDepth);
            step.castShadow = true;
            step.receiveShadow = true;
            group.add(step);

            // Stringers (side boards)
            if (i % 3 === 0) {
                const stringerGeom = new THREE.BoxGeometry(0.1, stepHeight * 3, stepDepth * 3.2);
                const stringerMat = new THREE.MeshStandardMaterial({
                    color: 0x654321, roughness: 0.8
                });
                const leftStringer = new THREE.Mesh(stringerGeom, stringerMat);
                leftStringer.position.set(-stepWidth / 2, i * stepHeight + stepHeight * 1.5, i * stepDepth + stepDepth * 1.5);
                leftStringer.castShadow = true;
                group.add(leftStringer);

                const rightStringer = leftStringer.clone();
                rightStringer.position.x = stepWidth / 2;
                group.add(rightStringer);
            }
        }

        // Position on terrain
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
        const woodColor = 0xDEB887;

        // Posts
        for (let i = 0; i < postCount; i++) {
            const postGeom = new THREE.BoxGeometry(0.25, railHeight, 0.25);
            const postMat = new THREE.MeshStandardMaterial({
                color: woodColor, roughness: 0.7
            });
            const post = new THREE.Mesh(postGeom, postMat);
            const t = i / (postCount - 1);
            post.position.set(t * railLength - railLength / 2, railHeight / 2, 0);
            post.castShadow = true;
            group.add(post);
        }

        // Top rail
        const topRailGeom = new THREE.BoxGeometry(railLength, 0.15, 0.12);
        const topRailMat = new THREE.MeshStandardMaterial({
            color: woodColor, roughness: 0.7
        });
        const topRail = new THREE.Mesh(topRailGeom, topRailMat);
        topRail.position.y = railHeight;
        topRail.castShadow = true;
        group.add(topRail);

        // Mid rail
        const midRail = topRail.clone();
        midRail.position.y = railHeight * 0.5;
        group.add(midRail);

        // Bottom rail
        const bottomRail = topRail.clone();
        bottomRail.position.y = railHeight * 0.25;
        group.add(bottomRail);

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
        
        const wallLength = 10;
        const wallHeight = 4;
        const postSpacing = 1.2;
        const postCount = Math.floor(wallLength / postSpacing) + 1;
        const postColor = 0x5C4033;
        const boardColor = 0x8B6914;

        // Vertical posts (driven into ground)
        for (let i = 0; i < postCount; i++) {
            const postGeom = new THREE.CylinderGeometry(0.15, 0.15, wallHeight + 1, 8);
            const postMat = new THREE.MeshStandardMaterial({
                color: postColor, roughness: 0.9
            });
            const post = new THREE.Mesh(postGeom, postMat);
            post.position.set(
                i * postSpacing - wallLength / 2,
                wallHeight / 2 - 0.5,
                0
            );
            post.castShadow = true;
            group.add(post);
        }

        // Horizontal retaining boards
        const boardCount = Math.floor(wallHeight / 0.4);
        for (let i = 0; i < boardCount; i++) {
            const boardGeom = new THREE.BoxGeometry(wallLength, 0.3, 0.15);
            const boardMat = new THREE.MeshStandardMaterial({
                color: boardColor, roughness: 0.85
            });
            const board = new THREE.Mesh(boardGeom, boardMat);
            board.position.set(0, i * 0.4 + 0.2, 0.1);
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
        // Convert world coords to grid indices
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
                    const strength = this.brushStrength * falloff * 0.3;
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
                            currentHeight += (this.targetHeight - currentHeight) * strength * 0.5;
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
        for (let dj = -1; dj <= 1; dj++) {
            for (let di = -1; di <= 1; di++) {
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
                const z = j / segs;
                // Gentle linear slope
                let height = 18 * (1 - z);
                // Slight natural variation
                const x = i / segs;
                height += Math.sin(x * Math.PI * 2) * 0.3;
                if (z > 0.9) height = Math.min(height, 0.3);
                this.heightData[idx] = Math.max(0, height);
            }
        }
        this.updateTerrainFromData();
        this.saveHistoryState();
    }

    applyPresetTerraced() {
        const segs = this.segments;
        const terraceCount = 4;
        for (let j = 0; j <= segs; j++) {
            for (let i = 0; i <= segs; i++) {
                const idx = j * (segs + 1) + i;
                const z = j / segs;
                // Create flat terraces
                let baseHeight = 20 * (1 - z);
                let terraceLevel = Math.floor(baseHeight / (20 / terraceCount));
                let height = terraceLevel * (20 / terraceCount);
                // Add transition slopes between terraces
                const fractional = (baseHeight % (20 / terraceCount)) / (20 / terraceCount);
                if (fractional > 0.8) {
                    height += (20 / terraceCount) * (fractional - 0.8) * 5;
                }
                if (z > 0.9) height = Math.min(height, 0.3);
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
                let height = 20 * (1 - z);
                // Create a stepped path down the center
                const centerDist = Math.abs(x - 0.5);
                if (centerDist < 0.1) {
                    // Stepped path
                    height = Math.round(height / 1.5) * 1.5;
                } else if (centerDist < 0.15) {
                    // Transition
                    const blend = (centerDist - 0.1) / 0.05;
                    const steppedH = Math.round(height / 1.5) * 1.5;
                    height = steppedH * (1 - blend) + height * blend;
                }
                if (z > 0.9) height = Math.min(height, 0.3);
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
        // Remove future states if we branched
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
        let max = -Infinity, min = Infinity, sum = 0;
        for (const h of this.heightData) {
            max = Math.max(max, h);
            min = Math.min(min, h);
            sum += h;
        }
        document.getElementById('stat-max').textContent = max.toFixed(1);
        document.getElementById('stat-min').textContent = min.toFixed(1);
        
        // Calculate average slope
        const avgSlope = Math.atan2(max - min, this.terrainDepth) * (180 / Math.PI);
        document.getElementById('stat-slope').textContent = avgSlope.toFixed(1);
        
        // Area
        const area = this.terrainWidth * this.terrainDepth;
        document.getElementById('stat-area').textContent = area.toFixed(0);
    }

    updateProfileCanvas() {
        const canvas = document.getElementById('profile-canvas');
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;

        ctx.clearRect(0, 0, w, h);

        // Background
        ctx.fillStyle = '#0d1b2a';
        ctx.fillRect(0, 0, w, h);

        // Draw center-line profile (cross section from house to water)
        const segs = this.segments;
        const centerI = Math.floor(segs / 2);

        ctx.beginPath();
        ctx.strokeStyle = '#4fc3f7';
        ctx.lineWidth = 2;

        for (let j = 0; j <= segs; j++) {
            const idx = j * (segs + 1) + centerI;
            const x = (j / segs) * w;
            const y = h - (this.heightData[idx] / 22) * (h - 10) - 5;
            if (j === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Draw original profile as reference
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(255,255,100,0.3)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        for (let j = 0; j <= segs; j++) {
            const idx = j * (segs + 1) + centerI;
            const x = (j / segs) * w;
            const y = h - (this.originalHeightData[idx] / 22) * (h - 10) - 5;
            if (j === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.setLineDash([]);

        // Labels
        ctx.fillStyle = '#888';
        ctx.font = '10px sans-serif';
        ctx.fillText('House', 5, 12);
        ctx.fillText('Beach', w - 35, 12);
        ctx.fillText('Current', w - 55, h - 5);
        ctx.fillStyle = 'rgba(255,255,100,0.5)';
        ctx.fillText('Original', w - 120, h - 5);
    }

    updateStructuresList() {
        const list = document.getElementById('structures-list');
        if (this.structures.length === 0) {
            list.innerHTML = '<li class="hint">No structures placed yet</li>';
            return;
        }
        list.innerHTML = this.structures.map((s, i) => {
            const label = s.userData.type.replace('-', ' ');
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
        // Deselect previous
        if (this.selectedStructure) {
            this.selectedStructure.traverse(child => {
                if (child.isMesh && child.userData.originalColor) {
                    child.material.emissive.setHex(0x000000);
                }
            });
        }

        this.selectedStructure = structure;

        if (structure) {
            structure.traverse(child => {
                if (child.isMesh) {
                    child.userData.originalColor = child.material.color.getHex();
                    child.material.emissive.setHex(0x222200);
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
            <p><strong>${type.replace('-', ' ')}</strong></p>
            <label>X Position</label>
            <input type="number" id="prop-x" value="${s.position.x.toFixed(1)}" step="0.5">
            <label>Z Position</label>
            <input type="number" id="prop-z" value="${s.position.z.toFixed(1)}" step="0.5">
            <label>Y (Height)</label>
            <input type="number" id="prop-y" value="${s.position.y.toFixed(1)}" step="0.5">
            <label>Rotation (degrees)</label>
            <input type="number" id="prop-rot" value="${(s.rotation.y * 180 / Math.PI).toFixed(0)}" step="15">
            <label>Scale</label>
            <input type="range" id="prop-scale" min="0.5" max="2" value="${s.scale.x.toFixed(1)}" step="0.1">
        `;

        panel.querySelector('#prop-x').addEventListener('change', e => {
            s.position.x = parseFloat(e.target.value);
        });
        panel.querySelector('#prop-z').addEventListener('change', e => {
            s.position.z = parseFloat(e.target.value);
        });
        panel.querySelector('#prop-y').addEventListener('change', e => {
            s.position.y = parseFloat(e.target.value);
        });
        panel.querySelector('#prop-rot').addEventListener('change', e => {
            s.rotation.y = parseFloat(e.target.value) * Math.PI / 180;
        });
        panel.querySelector('#prop-scale').addEventListener('input', e => {
            const sc = parseFloat(e.target.value);
            s.scale.set(sc, sc, sc);
        });
    }


    // ============================================================
    // EVENT LISTENERS
    // ============================================================

    setupEventListeners() {
        const canvas = document.getElementById('three-canvas');

        canvas.addEventListener('mousedown', (e) => {
            if (e.button === 0) { // Left click
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
            if (this.isEditing) {
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

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
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
        // Don't edit if we're in structure placement mode
        if (['add-stairs', 'add-railing', 'add-retaining-wall'].includes(this.currentTool)) {
            const intersect = this.getTerrainIntersect();
            if (intersect && e.type === 'mousedown') {
                const p = intersect.point;
                switch (this.currentTool) {
                    case 'add-stairs':
                        this.addStairs(p.x, p.z);
                        break;
                    case 'add-railing':
                        this.addRailing(p.x, p.z);
                        break;
                    case 'add-retaining-wall':
                        this.addRetainingWall(p.x, p.z);
                        break;
                }
                this.setTool('raise'); // reset after placing
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
        // Terrain tools
        const toolBtns = {
            'btn-raise': 'raise',
            'btn-lower': 'lower',
            'btn-flatten': 'flatten',
            'btn-smooth': 'smooth',
            'btn-terrace': 'terrace'
        };

        for (const [id, tool] of Object.entries(toolBtns)) {
            document.getElementById(id).addEventListener('click', () => this.setTool(tool));
        }

        // Structure buttons
        document.getElementById('btn-add-stairs').addEventListener('click', () => {
            this.setTool('add-stairs');
        });
        document.getElementById('btn-add-railing').addEventListener('click', () => {
            this.setTool('add-railing');
        });
        document.getElementById('btn-add-retaining-wall').addEventListener('click', () => {
            this.setTool('add-retaining-wall');
        });
        document.getElementById('btn-delete-structure').addEventListener('click', () => {
            this.deleteSelectedStructure();
        });

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
            this.camera.position.set(30, 25, 45);
            this.controls.target.set(0, 5, 0);
        });
        document.getElementById('btn-top-view').addEventListener('click', () => {
            this.camera.position.set(0, 50, 0.1);
            this.controls.target.set(0, 0, 0);
        });
        document.getElementById('btn-side-view').addEventListener('click', () => {
            this.camera.position.set(0, 8, 40);
            this.controls.target.set(0, 8, 0);
        });
        document.getElementById('btn-house-view').addEventListener('click', () => {
            this.camera.position.set(0, 22, -25);
            this.controls.target.set(0, 5, 10);
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
        // Update button states
        document.querySelectorAll('.tool-group .tool-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        const toolNames = {
            'raise': 'btn-raise', 'lower': 'btn-lower',
            'flatten': 'btn-flatten', 'smooth': 'btn-smooth',
            'terrace': 'btn-terrace'
        };
        if (toolNames[tool]) {
            document.getElementById(toolNames[tool]).classList.add('active');
        }

        // Update mode display
        const modeNames = {
            'raise': 'Raise Terrain', 'lower': 'Lower Terrain',
            'flatten': 'Flatten', 'smooth': 'Smooth',
            'terrace': 'Terrace',
            'add-stairs': 'Place Stairs (click terrain)',
            'add-railing': 'Place Railing (click terrain)',
            'add-retaining-wall': 'Place Retaining Wall (click terrain)'
        };
        document.getElementById('mode-info').textContent = 
            `Mode: ${modeNames[tool] || tool}`;
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
        
        // Animate water slightly
        if (this.water) {
            this.water.position.y = 0.1 + Math.sin(Date.now() * 0.001) * 0.05;
        }

        this.renderer.render(this.scene, this.camera);
    }
}

// ============================================================
// LAUNCH APP
// ============================================================
window.addEventListener('DOMContentLoaded', () => {
    new HillsideLandscapeApp();
});
