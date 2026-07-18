import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ============================================================
// HILLSIDE LANDSCAPE & RE-GRADING TOOL v3
// All structures are moveable. Multi-select + group move.
// Rock placement snaps to terrain. No preset rocks.
// ============================================================

class App {
    constructor() {
        // Core Three.js
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();

        // Terrain
        this.terrain = null;
        this.terrainGeom = null;
        this.terrainMat = null;
        this.terrainWidth = 70;
        this.terrainDepth = 55;
        this.segments = 100;
        this.heightData = [];
        this.originalHeightData = [];
        this.water = null;
        this.brushMarker = null;

        // Modes: 'camera', 'terrain', 'select', 'place'
        this.mode = 'camera';
        this.terrainTool = 'raise';
        this.placeType = null; // 'stairs','railing','retaining-wall','rock','tree'
        this.brushSize = 3;
        this.brushStrength = 0.5;
        this.targetHeight = 5;

        // Structures - ALL are moveable (including house, stairs, dock, etc.)
        this.structures = []; // all structure groups in scene
        this.selected = [];   // currently selected structures
        this.isDragging = false;
        this.dragStart = new THREE.Vector3();
        this.dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

        // History
        this.history = [];
        this.historyIdx = -1;
        // Structure deletion undo stack
        this.deletedStructures = [];

        // Grid
        this.gridHelper = null;
        this.gridVisible = false;
        // Rear and side grids
        this.rearGrid = null;
        this.sideGrid = null;

        // Cross-section editor
        this.sliceDirection = 'xz'; // 'xz' = house-to-lake, 'lr' = left-to-right
        this.slicePosition = 50; // percentage along the perpendicular axis
        this.profileEditing = false;
        this.sliceLine = null; // 3D visualization of slice position

        this.init();
    }

    init() {
        this.setupScene();
        this.setupLighting();
        this.createTerrain();
        this.createWater();
        this.createBrushMarker();
        this.setupGrid();
        this.createSliceLine();
        this.createSiteStructures();
        this.setupEvents();
        this.setupUI();
        this.setupProfileInteraction();
        this.saveHistory();
        this.updateStats();
        this.updateProfile();
        this.animate();
    }


    // ============================================================
    // SCENE SETUP
    // ============================================================
    setupScene() {
        const canvas = document.getElementById('three-canvas');
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x87CEEB);
        this.scene.fog = new THREE.Fog(0x87CEEB, 100, 200);

        this.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 500);
        this.camera.position.set(5, 20, 50);

        this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
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

        this.onResize();
        window.addEventListener('resize', () => this.onResize());
    }

    setupLighting() {
        this.scene.add(new THREE.AmbientLight(0xffffff, 0.45));
        const sun = new THREE.DirectionalLight(0xfff5e6, 1.1);
        sun.position.set(25, 35, 15);
        sun.castShadow = true;
        sun.shadow.mapSize.set(2048, 2048);
        sun.shadow.camera.near = 0.5;
        sun.shadow.camera.far = 120;
        [-50, 50, 50, -50].forEach((v, i) => {
            ['left','right','top','bottom'][i].split('').length; // just structure
        });
        sun.shadow.camera.left = -50;
        sun.shadow.camera.right = 50;
        sun.shadow.camera.top = 50;
        sun.shadow.camera.bottom = -50;
        this.scene.add(sun);
        this.scene.add(new THREE.DirectionalLight(0x8ecae6, 0.3).translateX(-15).translateY(20));
        this.scene.add(new THREE.HemisphereLight(0x87CEEB, 0x3d5c3a, 0.25));
    }

    onResize() {
        const el = document.getElementById('viewport');
        const w = el.clientWidth, h = el.clientHeight;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    }


    // ============================================================
    // TERRAIN
    // ============================================================
    createTerrain() {
        this.heightData = this.genHeight();
        this.originalHeightData = [...this.heightData];
        this.terrainGeom = new THREE.PlaneGeometry(this.terrainWidth, this.terrainDepth, this.segments, this.segments);
        this.terrainGeom.rotateX(-Math.PI / 2);
        const pos = this.terrainGeom.attributes.position.array;
        for (let i = 0; i < this.heightData.length; i++) pos[i * 3 + 1] = this.heightData[i];
        this.terrainGeom.computeVertexNormals();
        this.colorTerrain();
        this.terrainMat = new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, roughness: 0.85 });
        this.terrain = new THREE.Mesh(this.terrainGeom, this.terrainMat);
        this.terrain.receiveShadow = true;
        this.terrain.castShadow = true;
        this.scene.add(this.terrain);
    }

    genHeight() {
        const d = [], s = this.segments;
        for (let j = 0; j <= s; j++) {
            for (let i = 0; i <= s; i++) {
                const x = i / s, z = j / s;
                d.push(Math.max(0, this.profileH(x, z)));
            }
        }
        return d;
    }

    profileH(x, z) {
        let h;
        if (z < 0.15) h = 18.5;
        else if (z < 0.28) h = 18.0;
        else if (z < 0.35) { const t = (z - 0.28) / 0.07; h = 18.0 - t * 1.5; }
        else if (z < 0.46) { const t = (z - 0.35) / 0.11; h = 16.5 - t * 1.5; } // flat area
        else if (z < 0.52) { const t = (z - 0.46) / 0.06; h = 15.0 - t * 2.5; }
        else if (z < 0.75) { const t = (z - 0.52) / 0.23; const c = t*t*(3-2*t); h = 12.5 - c * 10.5; }
        else if (z < 0.84) { const t = (z - 0.75) / 0.09; h = 2.0 - t * 1.5; }
        else if (z < 0.90) { const t = (z - 0.84) / 0.06; h = 0.5 - t * 0.3; }
        else h = 0.1;
        // lateral
        const cd = Math.abs(x - 0.5) * 2;
        if (z > 0.40 && z < 0.80) h += cd * 0.5;
        h += Math.sin(x * Math.PI * 4) * 0.15 + Math.cos(z * Math.PI * 3 + x * 2) * 0.12;
        if (z > 0.52 && z < 0.75) h += Math.sin(x*17+z*13)*0.3 + Math.cos(x*23+z*7)*0.2;
        return h;
    }

    colorTerrain() {
        const count = this.terrainGeom.attributes.position.count;
        const colors = new Float32Array(count * 3);
        const pos = this.terrainGeom.attributes.position.array;
        for (let i = 0; i < count; i++) {
            const y = pos[i*3+1], zW = pos[i*3+2];
            const zN = (zW + this.terrainDepth/2) / this.terrainDepth;
            const c = new THREE.Color();
            if (zN > 0.28 && zN < 0.35 && Math.abs(pos[i*3]) < 12) c.setHex(0x999999);
            else if (zN > 0.35 && zN < 0.46 && Math.abs(pos[i*3]) < 14) c.setHex(0x6b7a5a);
            else if (y < 0.6) c.setHex(0xc2b280);
            else if (y < 3) c.lerpColors(new THREE.Color(0xc2b280), new THREE.Color(0x7ab648), (y-0.6)/2.4);
            else if (y < 8) c.lerpColors(new THREE.Color(0x7ab648), new THREE.Color(0x5a7a3f), (y-3)/5);
            else if (y < 14) c.lerpColors(new THREE.Color(0x5a7a3f), new THREE.Color(0x3d5c2d), (y-8)/6);
            else c.setHex(0x4a7a3a);
            c.multiplyScalar(0.94 + Math.random()*0.12);
            colors[i*3] = c.r; colors[i*3+1] = c.g; colors[i*3+2] = c.b;
        }
        this.terrainGeom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    }

    createWater() {
        const g = new THREE.PlaneGeometry(90, 25);
        const m = new THREE.MeshStandardMaterial({ color: 0x3a7abd, transparent: true, opacity: 0.75, roughness: 0.05, metalness: 0.3, side: THREE.DoubleSide });
        this.water = new THREE.Mesh(g, m);
        this.water.rotation.x = -Math.PI / 2;
        this.water.position.set(0, 0.05, this.terrainDepth / 2 + 5);
        this.scene.add(this.water);
    }

    createBrushMarker() {
        // Use a disc/ring that represents the actual brush radius
        // Inner radius slightly smaller than outer for a clear ring
        const g = new THREE.RingGeometry(0.85, 1, 48);
        const m = new THREE.MeshBasicMaterial({ color: 0xffff00, side: THREE.DoubleSide, transparent: true, opacity: 0.7 });
        this.brushMarker = new THREE.Mesh(g, m);
        this.brushMarker.rotation.x = -Math.PI / 2;
        this.brushMarker.visible = false;
        this.scene.add(this.brushMarker);

        // Add a filled disc inside for better visibility
        const fillGeo = new THREE.CircleGeometry(0.85, 48);
        const fillMat = new THREE.MeshBasicMaterial({ color: 0xffff00, side: THREE.DoubleSide, transparent: true, opacity: 0.12 });
        this.brushFill = new THREE.Mesh(fillGeo, fillMat);
        this.brushFill.rotation.x = -Math.PI / 2;
        this.brushFill.visible = false;
        this.scene.add(this.brushFill);
    }

    setupGrid() {
        // Floor grid
        this.gridHelper = new THREE.GridHelper(70, 35, 0x444444, 0x333333);
        this.gridHelper.position.y = 0.1;
        this.gridHelper.visible = this.gridVisible;
        this.scene.add(this.gridHelper);

        // Rear grid (vertical, at the back — shows elevation from the side)
        const rearGridGeo = new THREE.PlaneGeometry(70, 25);
        const rearGridMat = new THREE.MeshBasicMaterial({
            color: 0x333355, transparent: true, opacity: 0.15, side: THREE.DoubleSide, wireframe: true
        });
        this.rearGrid = new THREE.Mesh(rearGridGeo, rearGridMat);
        this.rearGrid.position.set(0, 12.5, -this.terrainDepth/2);
        this.rearGrid.visible = this.gridVisible;
        this.scene.add(this.rearGrid);

        // Side grid (vertical, on the left — shows elevation profile)
        const sideGridGeo = new THREE.PlaneGeometry(55, 25);
        const sideGridMat = new THREE.MeshBasicMaterial({
            color: 0x335533, transparent: true, opacity: 0.15, side: THREE.DoubleSide, wireframe: true
        });
        this.sideGrid = new THREE.Mesh(sideGridGeo, sideGridMat);
        this.sideGrid.rotation.y = Math.PI / 2;
        this.sideGrid.position.set(-this.terrainWidth/2, 12.5, 0);
        this.sideGrid.visible = this.gridVisible;
        this.scene.add(this.sideGrid);
    }

    createSliceLine() {
        // A bright colored line in 3D showing where the cross-section slice is
        const material = new THREE.LineBasicMaterial({ color: 0xff4444, linewidth: 2, transparent: true, opacity: 0.8 });
        const points = [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 25, 0)];
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        this.sliceLine = new THREE.Line(geometry, material);
        this.sliceLine.visible = true;
        this.scene.add(this.sliceLine);

        // Also add a semi-transparent slice plane to make it more visible
        const planeGeo = new THREE.PlaneGeometry(1, 25);
        const planeMat = new THREE.MeshBasicMaterial({
            color: 0xff4444, transparent: true, opacity: 0.08, side: THREE.DoubleSide
        });
        this.slicePlane = new THREE.Mesh(planeGeo, planeMat);
        this.scene.add(this.slicePlane);

        this.updateSliceLine();
    }

    updateSliceLine() {
        if (!this.sliceLine) return;
        const hw = this.terrainWidth / 2;
        const hd = this.terrainDepth / 2;
        const sliceNorm = this.slicePosition / 100;

        const positions = [];
        const s = this.segments;

        if (this.sliceDirection === 'xz') {
            // Slice is at a fixed X position, runs along Z (house-to-lake)
            const xPos = sliceNorm * this.terrainWidth - hw;
            // Build a line that follows the terrain surface at this X
            const ci = Math.floor(s * sliceNorm);
            for (let j = 0; j <= s; j += 2) {
                const idx = j * (s + 1) + ci;
                const zPos = (j / s) * this.terrainDepth - hd;
                const h = this.heightData[idx] + 0.3;
                positions.push(new THREE.Vector3(xPos, h, zPos));
            }
            // Update slice plane
            this.slicePlane.geometry.dispose();
            this.slicePlane.geometry = new THREE.PlaneGeometry(0.1, 25);
            this.slicePlane.position.set(xPos, 12.5, 0);
            this.slicePlane.rotation.set(0, 0, 0);
            this.slicePlane.scale.set(1, 1, this.terrainDepth);
        } else {
            // Slice is at a fixed Z position, runs along X (left-to-right)
            const zPos = sliceNorm * this.terrainDepth - hd;
            const cj = Math.floor(s * sliceNorm);
            for (let i = 0; i <= s; i += 2) {
                const idx = cj * (s + 1) + i;
                const xPos = (i / s) * this.terrainWidth - hw;
                const h = this.heightData[idx] + 0.3;
                positions.push(new THREE.Vector3(xPos, h, zPos));
            }
            // Update slice plane
            this.slicePlane.geometry.dispose();
            this.slicePlane.geometry = new THREE.PlaneGeometry(0.1, 25);
            this.slicePlane.position.set(0, 12.5, zPos);
            this.slicePlane.rotation.set(0, Math.PI / 2, 0);
            this.slicePlane.scale.set(1, 1, this.terrainWidth);
        }

        // Update the line geometry
        this.sliceLine.geometry.dispose();
        this.sliceLine.geometry = new THREE.BufferGeometry().setFromPoints(positions);
    }

    getTerrainHeightAt(x, z) {
        const hw = this.terrainWidth/2, hd = this.terrainDepth/2;
        const gi = Math.round(((x+hw)/this.terrainWidth)*this.segments);
        const gj = Math.round(((z+hd)/this.terrainDepth)*this.segments);
        if (gi < 0 || gi > this.segments || gj < 0 || gj > this.segments) return 0;
        return this.heightData[gj*(this.segments+1)+gi] || 0;
    }


    // ============================================================
    // SITE STRUCTURES (all moveable)
    // ============================================================
    createSiteStructures() {
        this.addHouse(2, -12);
        this.addExistingStairs(-12, 3);
        this.addDock(-18, 23);
        this.addPatio(2, -2);
        // A few trees to start (user can move/delete/add more)
        [[-14,-5],[-12,2],[-16,8],[-25,-10],[22,-8],[24,5]].forEach(([tx,tz]) => {
            this.placeSiteTree(tx, tz);
        });
    }

    // Register a group as a structure
    registerStructure(group) {
        this.structures.push(group);
        this.scene.add(group);
        this.updateStructuresList();
    }

    addHouse(x, z) {
        // HOUSE BODY (walls, roof, windows, chimney) - separate from deck
        const g = new THREE.Group();
        g.userData = { type: 'house', label: 'House (body)' };
        const W = 28, D = 18, wallH = 12, deckH = 7;
        // Posts
        for (let px = -12; px <= 12; px += 6)
            for (let pz = -7; pz <= 7; pz += 7) {
                const p = this.box(0.5, deckH, 0.5, 0xBFA76F);
                p.position.set(px, deckH/2, pz);
                g.add(p);
            }
        // Body
        const body = this.box(W, wallH, D, 0x6b7b8a);
        body.position.y = deckH + wallH/2;
        g.add(body);
        // Roof
        const rs = new THREE.Shape();
        rs.moveTo(-W/2-1, 0); rs.lineTo(0, 7); rs.lineTo(W/2+1, 0); rs.closePath();
        const roof = new THREE.Mesh(new THREE.ExtrudeGeometry(rs, {depth:D+1,bevelEnabled:false}),
            new THREE.MeshStandardMaterial({color:0x4a4a5a,roughness:0.7}));
        roof.position.set(0, deckH+wallH, -D/2-0.5);
        roof.castShadow = true;
        g.add(roof);
        // Windows
        const wm = new THREE.MeshStandardMaterial({color:0x88ccff,roughness:0.1,metalness:0.3});
        const uw = new THREE.Mesh(new THREE.BoxGeometry(5,4,0.2), wm);
        uw.position.set(0, deckH+wallH+2, D/2+0.2);
        g.add(uw);
        for (let wx = -8; wx <= 8; wx += 8) {
            const w = new THREE.Mesh(new THREE.BoxGeometry(4,5,0.2), wm);
            w.position.set(wx, deckH+5, D/2+0.2);
            g.add(w);
        }
        // Chimney
        const ch = this.box(2, 8, 2, 0x6b4423);
        ch.position.set(W/2-1, deckH+wallH+4, -2);
        g.add(ch);

        const tH = this.getTerrainHeightAt(x, z);
        g.position.set(x, tH, z);
        this.registerStructure(g);

        // DECK (separate structure so it can be moved independently)
        this.addUpperDeck(x, z);
    }

    addUpperDeck(x, z) {
        const g = new THREE.Group();
        g.userData = { type: 'deck', label: 'Upper Deck' };
        const W = 28, D = 18, deckH = 7;
        // Deck surface
        const deck = this.box(W+6, 0.3, D+6, 0xBFA76F);
        deck.position.y = deckH;
        g.add(deck);
        // Railing (front)
        for (let rx = -W/2-3; rx <= W/2+3; rx += 2) {
            const post = this.box(0.15, 3.2, 0.15, 0xBFA76F);
            post.position.set(rx, deckH+1.6, D/2+3);
            g.add(post);
        }
        const topR = this.box(W+6, 0.12, 0.12, 0xBFA76F);
        topR.position.set(0, deckH+3.2, D/2+3);
        g.add(topR);
        // Side railings
        for (let rz = -D/2-3; rz <= D/2+3; rz += 2) {
            const postL = this.box(0.15, 3.2, 0.15, 0xBFA76F);
            postL.position.set(-W/2-3, deckH+1.6, rz);
            g.add(postL);
            const postR = this.box(0.15, 3.2, 0.15, 0xBFA76F);
            postR.position.set(W/2+3, deckH+1.6, rz);
            g.add(postR);
        }

        const tH = this.getTerrainHeightAt(x, z);
        g.position.set(x, tH, z);
        this.registerStructure(g);
    }

    addExistingStairs(x, z) {
        const g = new THREE.Group();
        g.userData = { type: 'stairs', label: 'Existing Stairs' };
        const wc = 0xC4A35A, sc = 0x8B6914, sw = 3.5;
        // Upper run: 8 steps going DOWN toward the lake (+Z direction)
        const uSteps = 8, uRise = 5, uRun = 8;
        for (let i = 0; i < uSteps; i++) {
            const s = this.box(sw, 0.18, 0.85, wc);
            s.position.set(0, -i*(uRise/uSteps), i*(uRun/uSteps));
            g.add(s);
        }
        // Landing platform (at bottom of upper run)
        const landY = -(uRise);
        const landZ = uRun;
        const land = this.box(5, 0.22, 4, wc);
        land.position.set(0, landY, landZ + 1.5);
        g.add(land);
        // Lower run: pivots LEFT (−X direction), continues descending toward dock
        const lSteps = 12, lRise = 8, lRun = 12;
        for (let i = 0; i < lSteps; i++) {
            const s = this.box(0.85, 0.18, sw, wc);
            s.position.set(-(i+1)*(lRun/lSteps), landY -(i+1)*(lRise/lSteps), landZ + 2);
            g.add(s);
        }
        // Railing posts upper run (left side)
        for (let i = 0; i <= uSteps; i += 2) {
            const p = this.box(0.15, 3.2, 0.15, sc);
            p.position.set(-sw/2-0.2, -i*(uRise/uSteps)+1.6, i*(uRun/uSteps));
            g.add(p);
        }
        // Railing posts lower run (lake-facing side)
        for (let i = 0; i <= lSteps; i += 3) {
            const p = this.box(0.15, 3.2, 0.15, sc);
            p.position.set(-(i+1)*(lRun/lSteps), landY-(i+1)*(lRise/lSteps)+1.6, landZ+2+sw/2+0.2);
            g.add(p);
        }
        const tH = this.getTerrainHeightAt(x, z);
        g.position.set(x, tH, z);
        this.registerStructure(g);
    }

    addDock(x, z) {
        const g = new THREE.Group();
        g.userData = { type: 'dock', label: 'Lakeside Dock' };
        const dc = 0xC4A35A, pc = 0x8B6914;
        // Platform
        const plat = this.box(12, 0.25, 8, dc);
        plat.position.y = 1.8;
        g.add(plat);
        // Pilings
        [[-5,-3],[-5,3],[5,-3],[5,3],[0,-3],[0,3]].forEach(([px,pz]) => {
            const p = new THREE.Mesh(new THREE.CylinderGeometry(0.2,0.2,4,8),
                new THREE.MeshStandardMaterial({color:pc,roughness:0.85}));
            p.position.set(px, 0, pz);
            g.add(p);
        });
        // Railing
        for (let rx = -5; rx <= 5; rx += 2.5) {
            const p = this.box(0.15, 3, 0.15, dc);
            p.position.set(rx, 3.3, 4);
            g.add(p);
        }
        const tr = this.box(12, 0.12, 0.12, dc);
        tr.position.set(0, 4.8, 4);
        g.add(tr);
        // Extension
        const ext = this.box(4, 0.2, 6, dc);
        ext.position.set(-6, 1.7, 5);
        g.add(ext);

        const tH = this.getTerrainHeightAt(x, z);
        g.position.set(x, Math.max(tH, 0), z);
        this.registerStructure(g);
    }

    addPatio(x, z) {
        const g = new THREE.Group();
        g.userData = { type: 'patio', label: 'Concrete Patio' };
        // Just the concrete slab (no wall)
        const slab = this.box(24, 0.3, 12, 0x9a9a8e);
        slab.position.y = 0.15;
        g.add(slab);
        const tH = this.getTerrainHeightAt(x, z);
        g.position.set(x, tH, z);
        this.registerStructure(g);
    }

    placeSiteTree(x, z) {
        const g = new THREE.Group();
        g.userData = { type: 'tree', label: 'Tree' };
        const h = 15 + Math.random() * 10;
        const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.35, h*0.4, 8),
            new THREE.MeshStandardMaterial({color:0x4a3020,roughness:0.9}));
        trunk.position.y = h * 0.2;
        trunk.castShadow = true;
        g.add(trunk);
        for (let l = 0; l < 3; l++) {
            const cone = new THREE.Mesh(new THREE.ConeGeometry(3.5-l*0.7, h*0.35, 8),
                new THREE.MeshStandardMaterial({color:0x2d5a27,roughness:0.85}));
            cone.position.y = h*0.35 + l*h*0.2;
            cone.castShadow = true;
            g.add(cone);
        }
        const tH = this.getTerrainHeightAt(x, z);
        g.position.set(x, tH, z);
        this.registerStructure(g);
    }

    // Helper
    box(w, h, d, color) {
        const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d),
            new THREE.MeshStandardMaterial({color, roughness:0.75}));
        m.castShadow = true; m.receiveShadow = true;
        return m;
    }


    // ============================================================
    // PLACEABLE ITEMS (user-triggered)
    // ============================================================
    placeStairs(x, z) {
        const g = new THREE.Group();
        g.userData = { type: 'stairs', label: 'New Stairs' };
        const wc = 0xC4A35A, sc = 0x8B6914, sw = 3.5;
        const steps = 12, rise = 8, run = 12;
        for (let i = 0; i < steps; i++) {
            const s = this.box(sw, 0.18, 0.9, wc);
            s.position.set(0, rise - i*(rise/steps), i*(run/steps));
            g.add(s);
        }
        for (let i = 0; i <= steps; i += 3) {
            const p = this.box(0.15, 3.2, 0.15, sc);
            p.position.set(-sw/2-0.2, rise - i*(rise/steps)+1.6, i*(run/steps));
            g.add(p);
        }
        g.position.set(x, this.getTerrainHeightAt(x,z), z);
        this.registerStructure(g);
    }

    placeRailing(x, z) {
        const g = new THREE.Group();
        g.userData = { type: 'railing', label: 'Railing' };
        const len = 8, h = 3, c = 0xC4A35A;
        for (let i = 0; i < 5; i++) {
            const p = this.box(0.2, h, 0.2, c);
            p.position.set(i*len/4 - len/2, h/2, 0);
            g.add(p);
        }
        const tr = this.box(len, 0.12, 0.08, c);
        tr.position.y = h; g.add(tr);
        const mr = this.box(len, 0.12, 0.08, c);
        mr.position.y = h*0.5; g.add(mr);
        g.position.set(x, this.getTerrainHeightAt(x,z), z);
        this.registerStructure(g);
    }

    placeRetainingWall(x, z) {
        const g = new THREE.Group();
        g.userData = { type: 'retaining-wall', label: 'Wood Retaining Wall' };
        const len = 12, wH = 3.5, pc = 0x5C4033, bc = 0x8B6914;
        const pCount = Math.floor(len/1.5)+1;
        for (let i = 0; i < pCount; i++) {
            const p = new THREE.Mesh(new THREE.CylinderGeometry(0.15,0.18,wH+1.5,8),
                new THREE.MeshStandardMaterial({color:pc,roughness:0.9}));
            p.position.set(i*1.5-len/2, wH/2-0.5, 0);
            p.castShadow = true; g.add(p);
        }
        const bCount = Math.floor(wH/0.35);
        for (let i = 0; i < bCount; i++) {
            const b = this.box(len, 0.25, 0.2, bc);
            b.position.set(0, i*0.35+0.2, 0.15);
            g.add(b);
        }
        g.position.set(x, this.getTerrainHeightAt(x,z), z);
        g.rotation.y = Math.PI; // Default rotated 180 degrees (boards face uphill)
        this.registerStructure(g);
    }

    placeBlockWall(x, z) {
        // Low block/stone retaining wall (like the ones in the original photos)
        const g = new THREE.Group();
        g.userData = { type: 'block-wall', label: 'Low Block Wall' };
        const len = 10, wallH = 2.0;
        const blockW = 1.2, blockH = 0.4, blockD = 0.8;
        const blockColor = 0x6a6a60;
        const rows = Math.floor(wallH / blockH);
        const blocksPerRow = Math.floor(len / blockW);

        for (let row = 0; row < rows; row++) {
            // Offset every other row for masonry pattern
            const offset = (row % 2 === 0) ? 0 : blockW * 0.5;
            for (let col = 0; col < blocksPerRow; col++) {
                const bx = col * blockW - len / 2 + blockW / 2 + offset;
                if (bx > len / 2) continue;
                // Slight color variation per block
                const shade = 0.35 + Math.random() * 0.15;
                const blockMat = new THREE.MeshStandardMaterial({
                    color: new THREE.Color(shade, shade * 0.95, shade * 0.85),
                    roughness: 0.92,
                    flatShading: true
                });
                const block = new THREE.Mesh(
                    new THREE.BoxGeometry(blockW - 0.05, blockH - 0.02, blockD),
                    blockMat
                );
                block.position.set(bx, row * blockH + blockH / 2, 0);
                block.castShadow = true;
                g.add(block);
            }
        }
        // Cap stones on top (slightly wider and different color)
        for (let col = 0; col < blocksPerRow; col++) {
            const bx = col * blockW - len / 2 + blockW / 2;
            const capMat = new THREE.MeshStandardMaterial({
                color: 0x7a7a70, roughness: 0.85
            });
            const cap = new THREE.Mesh(
                new THREE.BoxGeometry(blockW - 0.02, 0.15, blockD + 0.1),
                capMat
            );
            cap.position.set(bx, rows * blockH + 0.08, 0);
            cap.castShadow = true;
            g.add(cap);
        }

        g.position.set(x, this.getTerrainHeightAt(x, z), z);
        this.registerStructure(g);
    }

    placeRock(x, z) {
        const g = new THREE.Group();
        g.userData = { type: 'rock', label: 'Rock' };
        const size = 0.5 + Math.random() * 1.0;
        const geo = new THREE.SphereGeometry(size, 7, 5);
        const positions = geo.attributes.position;
        for (let v = 0; v < positions.count; v++) {
            positions.setXYZ(v,
                positions.getX(v)*(0.7+Math.random()*0.6),
                positions.getY(v)*(0.5+Math.random()*0.4),
                positions.getZ(v)*(0.7+Math.random()*0.6));
        }
        geo.computeVertexNormals();
        const shade = 0.4 + Math.random()*0.25;
        const rock = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
            color: new THREE.Color(shade, shade*0.95, shade*0.9), roughness:0.95, flatShading:true}));
        rock.castShadow = true;
        g.add(rock);
        // Snap to terrain
        const tH = this.getTerrainHeightAt(x, z);
        g.position.set(x, tH + size*0.3, z);
        this.registerStructure(g);
    }

    placeTree(x, z) {
        this.placeSiteTree(x, z);
    }


    // ============================================================
    // SELECTION & MOVEMENT
    // ============================================================
    selectStructure(struct, addToSelection) {
        if (!addToSelection) {
            // Deselect all
            this.selected.forEach(s => this.highlightGroup(s, false));
            this.selected = [];
        }
        if (this.selected.includes(struct)) {
            // Toggle off
            this.selected = this.selected.filter(s => s !== struct);
            this.highlightGroup(struct, false);
        } else {
            this.selected.push(struct);
            this.highlightGroup(struct, true);
        }
        this.updateStructureProps();
        this.updateStructuresList();
    }

    deselectAll() {
        this.selected.forEach(s => this.highlightGroup(s, false));
        this.selected = [];
        this.updateStructureProps();
        this.updateStructuresList();
    }

    highlightGroup(group, on) {
        group.traverse(child => {
            if (child.isMesh && child.material) {
                if (on) {
                    child.material = child.material.clone();
                    child.material.emissive = new THREE.Color(0x444400);
                } else {
                    child.material = child.material.clone();
                    child.material.emissive = new THREE.Color(0x000000);
                }
            }
        });
    }

    deleteSelected() {
        // Save deleted structures for undo
        this.selected.forEach(s => {
            this.deletedStructures.push({ struct: s, position: s.position.clone(), rotation: s.rotation.y });
            this.scene.remove(s);
            this.structures = this.structures.filter(st => st !== s);
        });
        this.selected = [];
        this.updateStructuresList();
        this.updateStructureProps();
    }

    groupSelected() {
        if (this.selected.length < 2) return;
        const g = new THREE.Group();
        g.userData = { type: 'group', label: `Group (${this.selected.length})` };
        // Calculate center
        const center = new THREE.Vector3();
        this.selected.forEach(s => center.add(s.position));
        center.divideScalar(this.selected.length);
        g.position.copy(center);
        this.selected.forEach(s => {
            this.scene.remove(s);
            this.structures = this.structures.filter(st => st !== s);
            s.position.sub(center);
            g.add(s);
        });
        this.highlightGroup(g, false);
        this.selected = [g];
        this.registerStructure(g);
        this.highlightGroup(g, true);
    }

    ungroupSelected() {
        const toUngroup = this.selected.filter(s => s.userData.type === 'group');
        toUngroup.forEach(g => {
            const children = [...g.children];
            const gPos = g.position.clone();
            this.scene.remove(g);
            this.structures = this.structures.filter(s => s !== g);
            children.forEach(child => {
                g.remove(child);
                child.position.add(gPos);
                this.scene.add(child);
                this.structures.push(child);
            });
        });
        this.selected = [];
        this.updateStructuresList();
    }

    snapSelectedToGround() {
        this.selected.forEach(s => {
            const tH = this.getTerrainHeightAt(s.position.x, s.position.z);
            s.position.y = tH;
        });
    }

    moveSelected(dx, dy, dz) {
        this.selected.forEach(s => {
            s.position.x += dx;
            s.position.y += dy;
            s.position.z += dz;
        });
        this.updateStructureProps();
    }

    // Hit-test structures
    pickStructure(event) {
        const canvas = document.getElementById('three-canvas');
        const rect = canvas.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left)/rect.width)*2 - 1;
        this.mouse.y = -((event.clientY - rect.top)/rect.height)*2 + 1;
        this.raycaster.setFromCamera(this.mouse, this.camera);
        // Test all structure meshes
        const allMeshes = [];
        this.structures.forEach(s => {
            s.traverse(c => { if (c.isMesh) allMeshes.push(c); });
        });
        const hits = this.raycaster.intersectObjects(allMeshes);
        if (hits.length > 0) {
            // Find which top-level structure group this belongs to
            let obj = hits[0].object;
            while (obj.parent && !this.structures.includes(obj)) obj = obj.parent;
            if (this.structures.includes(obj)) return obj;
        }
        return null;
    }


    // ============================================================
    // TERRAIN EDITING
    // ============================================================
    editTerrain(point) {
        if (!point) return;
        const pos = this.terrainGeom.attributes.position.array;
        const s = this.segments, hw = this.terrainWidth/2, hd = this.terrainDepth/2;
        for (let j = 0; j <= s; j++) for (let i = 0; i <= s; i++) {
            const idx = j*(s+1)+i;
            const vx = (i/s)*this.terrainWidth - hw;
            const vz = (j/s)*this.terrainDepth - hd;
            const dist = Math.hypot(vx-point.x, vz-point.z);
            if (dist < this.brushSize) {
                const f = 1 - dist/this.brushSize;
                const str = this.brushStrength * f * 0.25;
                let h = this.heightData[idx];
                switch(this.terrainTool) {
                    case 'raise': h += str; break;
                    case 'lower': h = Math.max(0, h - str); break;
                    case 'flatten': h += (this.targetHeight - h)*str*0.4; break;
                    case 'smooth':
                        let sum=0, cnt=0;
                        for (let dj=-2;dj<=2;dj++) for(let di=-2;di<=2;di++){
                            const ni=i+di, nj=j+dj;
                            if(ni>=0&&ni<=s&&nj>=0&&nj<=s){sum+=this.heightData[nj*(s+1)+ni];cnt++;}
                        }
                        h += (sum/cnt - h)*str; break;
                    case 'terrace': h += (Math.round(h/2)*2 - h)*str*0.3; break;
                }
                this.heightData[idx] = h;
                pos[idx*3+1] = h;
            }
        }
        this.terrainGeom.attributes.position.needsUpdate = true;
        this.terrainGeom.computeVertexNormals();
        this.colorTerrain();
        this.terrainGeom.attributes.color.needsUpdate = true;
    }

    terrainIntersect(event) {
        const canvas = document.getElementById('three-canvas');
        const rect = canvas.getBoundingClientRect();
        this.mouse.x = ((event.clientX-rect.left)/rect.width)*2-1;
        this.mouse.y = -((event.clientY-rect.top)/rect.height)*2+1;
        this.raycaster.setFromCamera(this.mouse, this.camera);
        const hits = this.raycaster.intersectObject(this.terrain);
        return hits.length > 0 ? hits[0] : null;
    }

    // ============================================================
    // TERRAIN PRESETS
    // ============================================================
    applyPreset(type) {
        const s = this.segments;
        for (let j=0;j<=s;j++) for(let i=0;i<=s;i++){
            const idx = j*(s+1)+i;
            const x = i/s, z = j/s;
            let h;
            if (type === 'original') { h = this.originalHeightData[idx]; }
            else if (type === 'gentle') {
                if (z<0.30) h = 18;
                else if (z<0.40) h = 18 - (z-0.30)/0.10*2.5;
                else if (z>0.85) h = 0.3;
                else { h = 15.5 - ((z-0.40)/0.45)*15; }
                h += Math.sin(x*Math.PI*3)*0.15;
            } else { // terraced
                if (z<0.30) h = 18;
                else if (z<0.40) h = 18 - (z-0.30)/0.10*2.5;
                else if (z>0.85) h = 0.3;
                else { const bh = 15.5-((z-0.40)/0.45)*15; h = Math.floor(bh/4)*4+0.5; }
            }
            this.heightData[idx] = Math.max(0, h);
        }
        this.refreshTerrain();
        this.saveHistory();
    }

    refreshTerrain() {
        const pos = this.terrainGeom.attributes.position.array;
        for (let i=0;i<this.heightData.length;i++) pos[i*3+1]=this.heightData[i];
        this.terrainGeom.attributes.position.needsUpdate = true;
        this.terrainGeom.computeVertexNormals();
        this.colorTerrain();
        this.terrainGeom.attributes.color.needsUpdate = true;
        this.updateStats();
        this.updateProfile();
    }

    // ============================================================
    // HISTORY
    // ============================================================
    saveHistory() {
        this.history = this.history.slice(0, this.historyIdx+1);
        this.history.push([...this.heightData]);
        if (this.history.length > 30) this.history.shift();
        this.historyIdx = this.history.length - 1;
    }
    undo() {
        // First check if there are deleted structures to restore
        if (this.deletedStructures.length > 0) {
            const last = this.deletedStructures.pop();
            last.struct.position.copy(last.position);
            last.struct.rotation.y = last.rotation;
            this.scene.add(last.struct);
            this.structures.push(last.struct);
            this.updateStructuresList();
            return;
        }
        // Otherwise undo terrain
        if(this.historyIdx>0){this.historyIdx--;this.heightData=[...this.history[this.historyIdx]];this.refreshTerrain();}
    }
    redo() { if(this.historyIdx<this.history.length-1){this.historyIdx++;this.heightData=[...this.history[this.historyIdx]];this.refreshTerrain();} }


    // ============================================================
    // EVENT HANDLING
    // ============================================================
    setupEvents() {
        const canvas = document.getElementById('three-canvas');
        let isTerrainEditing = false;
        let dragTarget = null;
        let lastDragPoint = null;

        canvas.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            if (this.mode === 'camera') return; // orbit controls handle it

            if (this.mode === 'terrain') {
                this.controls.enabled = false;
                isTerrainEditing = true;
                const hit = this.terrainIntersect(e);
                if (hit) this.editTerrain(hit.point);
            }
            else if (this.mode === 'select') {
                const struct = this.pickStructure(e);
                if (struct) {
                    if (!e.ctrlKey && !this.selected.includes(struct)) {
                        this.deselectAll();
                    }
                    this.selectStructure(struct, e.ctrlKey);
                    // Start drag
                    if (this.selected.length > 0) {
                        this.controls.enabled = false;
                        dragTarget = struct;
                        const hit = this.terrainIntersect(e);
                        lastDragPoint = hit ? hit.point.clone() : null;
                    }
                } else if (!e.ctrlKey) {
                    this.deselectAll();
                }
            }
            else if (this.mode === 'place') {
                const hit = this.terrainIntersect(e);
                if (hit) {
                    const p = hit.point;
                    switch(this.placeType) {
                        case 'stairs': this.placeStairs(p.x, p.z); break;
                        case 'railing': this.placeRailing(p.x, p.z); break;
                        case 'retaining-wall': this.placeRetainingWall(p.x, p.z); break;
                        case 'block-wall': this.placeBlockWall(p.x, p.z); break;
                        case 'rock': this.placeRock(p.x, p.z); break;
                        case 'tree': this.placeTree(p.x, p.z); break;
                    }
                }
            }
        });

        canvas.addEventListener('mousemove', (e) => {
            // Update info overlay
            const hit = this.terrainIntersect(e);
            if (hit) {
                document.getElementById('elevation-info').textContent = `Elev: ${hit.point.y.toFixed(1)} ft`;
                document.getElementById('coords-info').textContent = `(${hit.point.x.toFixed(1)}, ${hit.point.z.toFixed(1)})`;
                if (this.mode === 'terrain') {
                    this.brushMarker.position.set(hit.point.x, hit.point.y+0.3, hit.point.z);
                    this.brushMarker.scale.setScalar(this.brushSize);
                    this.brushMarker.visible = true;
                    this.brushFill.position.set(hit.point.x, hit.point.y+0.25, hit.point.z);
                    this.brushFill.scale.setScalar(this.brushSize);
                    this.brushFill.visible = true;
                }
            } else {
                this.brushMarker.visible = false;
                this.brushFill.visible = false;
            }

            if (isTerrainEditing && this.mode === 'terrain') {
                if (hit) this.editTerrain(hit.point);
            }

            // Drag move
            if (dragTarget && this.mode === 'select' && lastDragPoint && hit) {
                const delta = hit.point.clone().sub(lastDragPoint);
                delta.y = 0; // only move in XZ
                this.selected.forEach(s => { s.position.x += delta.x; s.position.z += delta.z; });
                lastDragPoint = hit.point.clone();
                this.updateStructureProps();
            }
        });

        canvas.addEventListener('mouseup', (e) => {
            if (isTerrainEditing) {
                isTerrainEditing = false;
                this.controls.enabled = true;
                this.saveHistory();
                this.updateStats();
                this.updateProfile();
            }
            if (dragTarget) {
                dragTarget = null;
                lastDragPoint = null;
                this.controls.enabled = true;
            }
        });

        canvas.addEventListener('mouseleave', () => {
            isTerrainEditing = false;
            dragTarget = null;
            this.brushMarker.visible = false;
            this.controls.enabled = true;
        });

        // Keyboard
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'z') { e.preventDefault(); this.undo(); }
            else if (e.ctrlKey && e.key === 'y') { e.preventDefault(); this.redo(); }
            else if (e.key === 'Delete' || e.key === 'Backspace') { this.deleteSelected(); }
            // Arrow keys nudge selected
            else if (this.selected.length > 0) {
                const step = e.shiftKey ? 0.2 : 1;
                if (e.key === 'ArrowLeft') this.moveSelected(-step, 0, 0);
                else if (e.key === 'ArrowRight') this.moveSelected(step, 0, 0);
                else if (e.key === 'ArrowUp') this.moveSelected(0, 0, -step);
                else if (e.key === 'ArrowDown') this.moveSelected(0, 0, step);
                else if (e.key === 'PageUp') this.moveSelected(0, step, 0);
                else if (e.key === 'PageDown') this.moveSelected(0, -step, 0);
            }
        });
    }


    // ============================================================
    // UI SETUP
    // ============================================================
    setupUI() {
        // Mode buttons
        const modes = ['camera','terrain','select','place'];
        modes.forEach(m => {
            document.getElementById(`btn-mode-${m}`).addEventListener('click', () => this.setMode(m));
        });
        // Terrain tools
        ['raise','lower','flatten','smooth','terrace'].forEach(t => {
            document.getElementById(`btn-${t}`).addEventListener('click', () => {
                this.terrainTool = t;
                document.querySelectorAll('#terrain-tools-section .tool-group .tool-btn').forEach(b=>b.classList.remove('active'));
                document.getElementById(`btn-${t}`).classList.add('active');
                // Show/hide Target Height slider (only relevant for Flatten)
                document.getElementById('target-height-group').style.display = (t === 'flatten') ? '' : 'none';
            });
        });
        // Sliders
        document.getElementById('brush-size').addEventListener('input', e => {
            this.brushSize = +e.target.value;
            document.getElementById('brush-size-val').textContent = this.brushSize;
        });
        document.getElementById('brush-strength').addEventListener('input', e => {
            this.brushStrength = +e.target.value;
            document.getElementById('brush-strength-val').textContent = this.brushStrength;
        });
        document.getElementById('target-height').addEventListener('input', e => {
            this.targetHeight = +e.target.value;
            document.getElementById('target-height-val').textContent = this.targetHeight;
        });
        // Place buttons
        ['stairs','railing','retaining-wall','block-wall','rock','tree'].forEach(t => {
            document.getElementById(`btn-place-${t}`).addEventListener('click', () => {
                this.placeType = t;
                this.setMode('place');
            });
        });
        // Select tools
        document.getElementById('btn-group-selected').addEventListener('click', () => this.groupSelected());
        document.getElementById('btn-ungroup').addEventListener('click', () => this.ungroupSelected());
        document.getElementById('btn-snap-ground').addEventListener('click', () => this.snapSelectedToGround());
        document.getElementById('btn-delete-selected').addEventListener('click', () => this.deleteSelected());
        // Views
        document.getElementById('btn-reset-view').addEventListener('click', () => { this.camera.position.set(5,20,50); this.controls.target.set(0,6,5); });
        document.getElementById('btn-top-view').addEventListener('click', () => { this.camera.position.set(0,55,5); this.controls.target.set(0,0,5); });
        document.getElementById('btn-side-view').addEventListener('click', () => { this.camera.position.set(0,10,55); this.controls.target.set(0,8,0); });
        document.getElementById('btn-house-view').addEventListener('click', () => { this.camera.position.set(0,22,-30); this.controls.target.set(0,8,10); });
        // Presets
        document.getElementById('btn-preset-original').addEventListener('click', () => this.applyPreset('original'));
        document.getElementById('btn-preset-gentle').addEventListener('click', () => this.applyPreset('gentle'));
        document.getElementById('btn-preset-terraced').addEventListener('click', () => this.applyPreset('terraced'));
        // Actions
        document.getElementById('btn-undo').addEventListener('click', () => this.undo());
        document.getElementById('btn-redo').addEventListener('click', () => this.redo());
        document.getElementById('btn-export').addEventListener('click', () => this.exportData());
        document.getElementById('btn-import').addEventListener('click', () => this.importData());
        document.getElementById('btn-toggle-grid').addEventListener('click', () => { this.gridVisible=!this.gridVisible; this.gridHelper.visible=this.gridVisible; this.rearGrid.visible=this.gridVisible; this.sideGrid.visible=this.gridVisible; });
        document.getElementById('btn-toggle-wireframe').addEventListener('click', () => { this.terrainMat.wireframe=!this.terrainMat.wireframe; });
    }

    setMode(mode) {
        this.mode = mode;
        // Fix: deselect ALL mode buttons, then highlight current
        ['camera','terrain','select','place'].forEach(m => {
            document.getElementById(`btn-mode-${m}`).classList.remove('active');
        });
        document.getElementById(`btn-mode-${mode}`).classList.add('active');
        // Show/hide relevant sections
        document.getElementById('terrain-tools-section').style.display = mode==='terrain'?'':'none';
        document.getElementById('place-tools-section').style.display = mode==='place'?'':'none';
        document.getElementById('select-tools-section').style.display = mode==='select'?'':'none';
        // Controls: orbit enabled in camera mode AND select mode (for when not dragging)
        this.controls.enabled = (mode === 'camera' || mode === 'select');
        this.brushMarker.visible = false;
        if (this.brushFill) this.brushFill.visible = false;
        // Mode info
        const labels = {camera:'Camera (rotate/zoom)',terrain:'Terrain Edit',select:'Select/Move',place:`Place: ${this.placeType||'(pick item)'}`};
        document.getElementById('mode-info').textContent = `Mode: ${labels[mode]}`;
    }


    // ============================================================
    // UI UPDATES
    // ============================================================
    updateStructuresList() {
        const list = document.getElementById('structures-list');
        if (this.structures.length === 0) { list.innerHTML = '<li class="hint">No structures</li>'; return; }
        list.innerHTML = this.structures.map((s, i) => {
            const sel = this.selected.includes(s) ? ' style="background:#1a4a7a"' : '';
            return `<li${sel} data-idx="${i}">${s.userData.label || s.userData.type} </li>`;
        }).join('');
        list.querySelectorAll('li').forEach(li => {
            li.addEventListener('click', (e) => {
                const idx = +li.dataset.idx;
                this.setMode('select');
                this.selectStructure(this.structures[idx], e.ctrlKey);
            });
        });
    }

    updateStructureProps() {
        const panel = document.getElementById('structure-props');
        if (this.selected.length === 0) { panel.innerHTML = '<p class="hint">Click a structure to select it</p>'; return; }
        if (this.selected.length > 1) {
            panel.innerHTML = `<p><strong>${this.selected.length} selected</strong></p><p style="font-size:11px;color:#aaa">Drag to move, arrows to nudge, or use Group.</p>`;
            return;
        }
        const s = this.selected[0];
        panel.innerHTML = `
            <p><strong>${s.userData.label || s.userData.type}</strong></p>
            <label>X</label><input type="number" id="sp-x" value="${s.position.x.toFixed(1)}" step="0.5">
            <label>Z (depth)</label><input type="number" id="sp-z" value="${s.position.z.toFixed(1)}" step="0.5">
            <label>Y (height)</label><input type="number" id="sp-y" value="${s.position.y.toFixed(1)}" step="0.5">
            <label>Rotation &deg;</label><input type="number" id="sp-r" value="${(s.rotation.y*180/Math.PI).toFixed(0)}" step="15">
        `;
        const bind = (id, fn) => panel.querySelector(id).addEventListener('change', fn);
        bind('#sp-x', e => { s.position.x = +e.target.value; });
        bind('#sp-z', e => { s.position.z = +e.target.value; });
        bind('#sp-y', e => { s.position.y = +e.target.value; });
        bind('#sp-r', e => { s.rotation.y = +e.target.value * Math.PI/180; });
    }

    updateStats() {
        let max=-Infinity, min=Infinity;
        for (const h of this.heightData) { max=Math.max(max,h); min=Math.min(min,h); }
        document.getElementById('stat-max').textContent = max.toFixed(1);
        document.getElementById('stat-min').textContent = min.toFixed(1);
        const s = this.segments;
        const ci = Math.floor(s*0.5);
        const tJ = Math.floor(s*0.40), bJ = Math.floor(s*0.82);
        const tH = this.heightData[tJ*(s+1)+ci], bH = this.heightData[bJ*(s+1)+ci];
        const slope = Math.atan2(tH-bH, (0.82-0.40)*this.terrainDepth)*180/Math.PI;
        document.getElementById('stat-slope').textContent = slope.toFixed(1);
        document.getElementById('stat-area').textContent = (this.terrainWidth*this.terrainDepth).toFixed(0);
    }

    updateProfile() {
        const canvas = document.getElementById('profile-canvas');
        const ctx = canvas.getContext('2d');
        const w = canvas.width, h = canvas.height;
        ctx.clearRect(0,0,w,h);
        ctx.fillStyle = '#0d1b2a'; ctx.fillRect(0,0,w,h);
        const s = this.segments;
        // Determine which slice to draw based on direction and position
        const sliceNorm = this.slicePosition / 100;
        const hw = this.terrainWidth / 2;
        const hd = this.terrainDepth / 2;

        if (this.sliceDirection === 'xz') {
            // House→Lake (along Z axis), slice position is X position
            const ci = Math.floor(s * sliceNorm);
            const sliceX = sliceNorm * this.terrainWidth - hw;
            // Current
            ctx.beginPath(); ctx.strokeStyle='#4fc3f7'; ctx.lineWidth=2;
            for(let j=0;j<=s;j++){const idx=j*(s+1)+ci;const px=(j/s)*w;const py=h-(this.heightData[idx]/20)*(h-20)-8;j===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
            ctx.stroke();
            // Original
            ctx.beginPath(); ctx.strokeStyle='rgba(255,255,100,0.35)'; ctx.lineWidth=1; ctx.setLineDash([4,4]);
            for(let j=0;j<=s;j++){const idx=j*(s+1)+ci;const px=(j/s)*w;const py=h-(this.originalHeightData[idx]/20)*(h-20)-8;j===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
            ctx.stroke(); ctx.setLineDash([]);
            // Labels
            ctx.fillStyle='#666'; ctx.font='9px sans-serif';
            ctx.fillText('House',2,10); ctx.fillText('Slope',w*0.55,10); ctx.fillText('Beach',w*0.82,10);

            // Draw structures that intersect this slice
            this.drawStructuresOnProfile(ctx, w, h, 'xz', sliceX);
        } else {
            // Left→Right (along X axis), slice position is Z position
            const cj = Math.floor(s * sliceNorm);
            const sliceZ = sliceNorm * this.terrainDepth - hd;
            ctx.beginPath(); ctx.strokeStyle='#4fc3f7'; ctx.lineWidth=2;
            for(let i=0;i<=s;i++){const idx=cj*(s+1)+i;const px=(i/s)*w;const py=h-(this.heightData[idx]/20)*(h-20)-8;i===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
            ctx.stroke();
            ctx.beginPath(); ctx.strokeStyle='rgba(255,255,100,0.35)'; ctx.lineWidth=1; ctx.setLineDash([4,4]);
            for(let i=0;i<=s;i++){const idx=cj*(s+1)+i;const px=(i/s)*w;const py=h-(this.originalHeightData[idx]/20)*(h-20)-8;i===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
            ctx.stroke(); ctx.setLineDash([]);
            ctx.fillStyle='#666'; ctx.font='9px sans-serif';
            ctx.fillText('Left',2,10); ctx.fillText('Right',w-30,10);

            // Draw structures that intersect this slice
            this.drawStructuresOnProfile(ctx, w, h, 'lr', sliceZ);
        }
        // Slice position label
        ctx.fillStyle='#4fc3f7'; ctx.font='9px sans-serif';
        ctx.fillText(`Slice: ${this.slicePosition}%`, w-60, h-3);

        // Draw vertical scale marks
        ctx.strokeStyle = 'rgba(255,255,255,0.1)'; ctx.lineWidth = 0.5;
        for (let ft = 0; ft <= 20; ft += 5) {
            const y = h - (ft/20)*(h-20) - 8;
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
            ctx.fillStyle='#555'; ctx.fillText(`${ft}'`, 0, y-2);
        }
    }

    drawStructuresOnProfile(ctx, canvasW, canvasH, direction, sliceWorldPos) {
        // Draw structures that are near the slice as colored markers
        const proximity = 4; // how close (in feet) a structure must be to the slice to show
        const hw = this.terrainWidth / 2;
        const hd = this.terrainDepth / 2;

        // Color map for structure types
        const typeColors = {
            'house': '#ff6b6b',
            'deck': '#ffa94d',
            'stairs': '#ffe066',
            'dock': '#74c0fc',
            'patio': '#adb5bd',
            'tree': '#69db7c',
            'retaining-wall': '#d2691e',
            'block-wall': '#868e96',
            'railing': '#f59f00',
            'rock': '#aaa9a5',
            'group': '#cc5de8'
        };

        this.structures.forEach(struct => {
            const pos = struct.position;
            let dist, profilePos;

            if (direction === 'xz') {
                // Slice is at a fixed X; structures show by their Z position
                dist = Math.abs(pos.x - sliceWorldPos);
                // Map structure Z to canvas X: Z ranges from -hd to +hd → 0 to canvasW
                profilePos = (pos.z + hd) / this.terrainDepth;
            } else {
                // Slice is at a fixed Z; structures show by their X position
                dist = Math.abs(pos.z - sliceWorldPos);
                // Map structure X to canvas X: X ranges from -hw to +hw → 0 to canvasW
                profilePos = (pos.x + hw) / this.terrainWidth;
            }

            if (dist > proximity) return; // too far from slice

            const alpha = 1.0 - (dist / proximity) * 0.6; // closer = more opaque
            const px = profilePos * canvasW;
            const py = canvasH - (pos.y / 20) * (canvasH - 20) - 8;

            // Get bounding box height for the structure
            const bbox = new THREE.Box3().setFromObject(struct);
            const structH = bbox.max.y - bbox.min.y;
            const topPy = canvasH - ((pos.y + structH) / 20) * (canvasH - 20) - 8;

            const color = typeColors[struct.userData.type] || '#ffffff';
            ctx.save();
            ctx.globalAlpha = alpha;

            // Draw a vertical bar representing the structure's cross-section
            ctx.fillStyle = color;
            ctx.fillRect(px - 3, topPy, 6, py - topPy);

            // Outline
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.strokeRect(px - 3, topPy, 6, py - topPy);

            // Label (small)
            ctx.fillStyle = color;
            ctx.font = '8px sans-serif';
            const label = struct.userData.label || struct.userData.type;
            ctx.fillText(label, px + 5, topPy + 6);

            ctx.restore();
        });
    }

    popoutProfile() {
        const popWin = window.open('', 'ProfileEditor', 'width=700,height=450,resizable=yes');
        if (!popWin) { alert('Popup blocked! Please allow popups for this site.'); return; }

        popWin.document.write(`<!DOCTYPE html><html><head><title>Cross-Section Editor</title>
        <style>
            body { margin:0; background:#0d1b2a; font-family:sans-serif; color:#eee; display:flex; flex-direction:column; height:100vh; }
            #controls { padding:8px 12px; background:#16213e; display:flex; gap:12px; align-items:center; font-size:12px; flex-wrap:wrap; }
            #controls label { color:#aaa; }
            #controls input[type=range] { width:200px; }
            #controls button { background:#0f3460; color:#eee; border:1px solid #1a4a7a; border-radius:3px; padding:4px 10px; cursor:pointer; }
            #controls button.active { background:#4fc3f7; color:#111; }
            canvas { flex:1; width:100%; cursor:crosshair; }
            .legend { padding:4px 12px; font-size:10px; color:#888; display:flex; gap:12px; flex-wrap:wrap; }
            .legend span { display:inline-flex; align-items:center; gap:3px; }
            .legend .swatch { width:10px; height:10px; border-radius:2px; }
        </style></head><body>
        <div id="controls">
            <label>Slice: <span id="pop-slice-val">50</span>%</label>
            <input type="range" id="pop-slice" min="0" max="100" value="${this.slicePosition}" step="1">
            <button id="pop-xz" class="${this.sliceDirection==='xz'?'active':''}">House→Lake</button>
            <button id="pop-lr" class="${this.sliceDirection==='lr'?'active':''}">Left→Right</button>
            <span style="color:#888;font-size:10px;">Click &amp; drag to edit terrain</span>
        </div>
        <canvas id="pop-canvas"></canvas>
        <div class="legend">
            <span><span class="swatch" style="background:#ff6b6b"></span>House</span>
            <span><span class="swatch" style="background:#ffa94d"></span>Deck</span>
            <span><span class="swatch" style="background:#ffe066"></span>Stairs</span>
            <span><span class="swatch" style="background:#74c0fc"></span>Dock</span>
            <span><span class="swatch" style="background:#adb5bd"></span>Patio</span>
            <span><span class="swatch" style="background:#69db7c"></span>Tree</span>
            <span><span class="swatch" style="background:#d2691e"></span>Wood Wall</span>
            <span><span class="swatch" style="background:#868e96"></span>Block Wall</span>
        </div>
        </body></html>`);
        popWin.document.close();

        const popCanvas = popWin.document.getElementById('pop-canvas');
        const resize = () => {
            popCanvas.width = popWin.innerWidth;
            popCanvas.height = popWin.innerHeight - 80;
        };
        resize();
        popWin.addEventListener('resize', resize);

        // Draw function using the same logic
        const drawPop = () => {
            if (popWin.closed) return;
            resize();
            const ctx = popCanvas.getContext('2d');
            const w = popCanvas.width, h = popCanvas.height;
            ctx.clearRect(0,0,w,h);
            ctx.fillStyle='#0d1b2a'; ctx.fillRect(0,0,w,h);
            const s = this.segments;
            const sliceNorm = this.slicePosition / 100;
            const hw = this.terrainWidth/2, hd = this.terrainDepth/2;

            if (this.sliceDirection === 'xz') {
                const ci = Math.floor(s * sliceNorm);
                const sliceX = sliceNorm * this.terrainWidth - hw;
                ctx.beginPath(); ctx.strokeStyle='#4fc3f7'; ctx.lineWidth=2;
                for(let j=0;j<=s;j++){const idx=j*(s+1)+ci;const px=(j/s)*w;const py=h-(this.heightData[idx]/20)*(h-20)-8;j===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
                ctx.stroke();
                ctx.beginPath(); ctx.strokeStyle='rgba(255,255,100,0.35)'; ctx.lineWidth=1; ctx.setLineDash([4,4]);
                for(let j=0;j<=s;j++){const idx=j*(s+1)+ci;const px=(j/s)*w;const py=h-(this.originalHeightData[idx]/20)*(h-20)-8;j===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
                ctx.stroke(); ctx.setLineDash([]);
                ctx.fillStyle='#666'; ctx.font='11px sans-serif';
                ctx.fillText('House',4,14); ctx.fillText('Slope',w*0.55,14); ctx.fillText('Beach',w*0.82,14);
                this.drawStructuresOnProfile(ctx, w, h, 'xz', sliceX);
            } else {
                const cj = Math.floor(s * sliceNorm);
                const sliceZ = sliceNorm * this.terrainDepth - hd;
                ctx.beginPath(); ctx.strokeStyle='#4fc3f7'; ctx.lineWidth=2;
                for(let i=0;i<=s;i++){const idx=cj*(s+1)+i;const px=(i/s)*w;const py=h-(this.heightData[idx]/20)*(h-20)-8;i===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
                ctx.stroke();
                ctx.beginPath(); ctx.strokeStyle='rgba(255,255,100,0.35)'; ctx.lineWidth=1; ctx.setLineDash([4,4]);
                for(let i=0;i<=s;i++){const idx=cj*(s+1)+i;const px=(i/s)*w;const py=h-(this.originalHeightData[idx]/20)*(h-20)-8;i===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
                ctx.stroke(); ctx.setLineDash([]);
                ctx.fillStyle='#666'; ctx.font='11px sans-serif';
                ctx.fillText('Left',4,14); ctx.fillText('Right',w-40,14);
                this.drawStructuresOnProfile(ctx, w, h, 'lr', sliceZ);
            }
            // Scale marks
            ctx.strokeStyle='rgba(255,255,255,0.12)'; ctx.lineWidth=0.5;
            for(let ft=0;ft<=20;ft+=5){const y=h-(ft/20)*(h-20)-8;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();ctx.fillStyle='#555';ctx.font='10px sans-serif';ctx.fillText(`${ft} ft`,2,y-3);}
        };

        // Interaction in popout
        let popDragging = false;
        popCanvas.addEventListener('mousedown', (e) => { popDragging = true; this.editProfileAtCanvas(popCanvas, e); drawPop(); });
        popCanvas.addEventListener('mousemove', (e) => { if(popDragging){this.editProfileAtCanvas(popCanvas, e); drawPop();} });
        popCanvas.addEventListener('mouseup', () => { popDragging=false; this.saveHistory(); this.updateStats(); this.updateProfile(); });

        // Controls in popout
        popWin.document.getElementById('pop-slice').addEventListener('input', (e) => {
            this.slicePosition = +e.target.value;
            popWin.document.getElementById('pop-slice-val').textContent = this.slicePosition;
            document.getElementById('slice-pos').value = this.slicePosition;
            document.getElementById('slice-pos-val').textContent = this.slicePosition;
            this.updateSliceLine();
            drawPop();
            this.updateProfile();
        });
        popWin.document.getElementById('pop-xz').addEventListener('click', () => {
            this.sliceDirection = 'xz';
            popWin.document.getElementById('pop-xz').classList.add('active');
            popWin.document.getElementById('pop-lr').classList.remove('active');
            document.getElementById('btn-slice-xz').classList.add('active');
            document.getElementById('btn-slice-lr').classList.remove('active');
            this.updateSliceLine(); drawPop(); this.updateProfile();
        });
        popWin.document.getElementById('pop-lr').addEventListener('click', () => {
            this.sliceDirection = 'lr';
            popWin.document.getElementById('pop-lr').classList.add('active');
            popWin.document.getElementById('pop-xz').classList.remove('active');
            document.getElementById('btn-slice-lr').classList.add('active');
            document.getElementById('btn-slice-xz').classList.remove('active');
            this.updateSliceLine(); drawPop(); this.updateProfile();
        });

        // Keep popout in sync - redraw periodically
        const syncInterval = setInterval(() => {
            if (popWin.closed) { clearInterval(syncInterval); return; }
            drawPop();
        }, 500);

        drawPop();
    }

    editProfileAtCanvas(canvas, e) {
        const rect = canvas.getBoundingClientRect();
        const mx = (e.clientX - rect.left) / rect.width;
        const my = 1 - (e.clientY - rect.top) / rect.height;
        const targetHeight = my * 20;
        const s = this.segments;
        const sliceNorm = this.slicePosition / 100;
        const brushWidth = 3;
        const pos = this.terrainGeom.attributes.position.array;

        if (this.sliceDirection === 'xz') {
            const ci = Math.floor(s * sliceNorm);
            const targetJ = Math.floor(mx * s);
            for (let dj=-brushWidth;dj<=brushWidth;dj++){const j=targetJ+dj;if(j<0||j>s)continue;const f=1-Math.abs(dj)/(brushWidth+1);for(let di=-1;di<=1;di++){const i=ci+di;if(i<0||i>s)continue;const idx=j*(s+1)+i;this.heightData[idx]+=(targetHeight-this.heightData[idx])*f*0.3;pos[idx*3+1]=this.heightData[idx];}}
        } else {
            const cj = Math.floor(s * sliceNorm);
            const targetI = Math.floor(mx * s);
            for(let di=-brushWidth;di<=brushWidth;di++){const i=targetI+di;if(i<0||i>s)continue;const f=1-Math.abs(di)/(brushWidth+1);for(let dj=-1;dj<=1;dj++){const j=cj+dj;if(j<0||j>s)continue;const idx=j*(s+1)+i;this.heightData[idx]+=(targetHeight-this.heightData[idx])*f*0.3;pos[idx*3+1]=this.heightData[idx];}}
        }
        this.terrainGeom.attributes.position.needsUpdate = true;
        this.terrainGeom.computeVertexNormals();
        this.colorTerrain();
        this.terrainGeom.attributes.color.needsUpdate = true;
        this.updateSliceLine();
    }

    setupProfileInteraction() {
        const canvas = document.getElementById('profile-canvas');
        let isDragging = false;

        canvas.addEventListener('mousedown', (e) => {
            isDragging = true;
            this.editProfileAt(e);
        });
        canvas.addEventListener('mousemove', (e) => {
            if (isDragging) this.editProfileAt(e);
        });
        canvas.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                this.saveHistory();
                this.updateStats();
            }
        });
        canvas.addEventListener('mouseleave', () => { isDragging = false; });

        // Popout button
        document.getElementById('btn-popout-profile').addEventListener('click', () => this.popoutProfile());

        // Resize observer: when the right panel is resized, resize the canvas to match
        const panel = document.getElementById('info-panel');
        const resizeObs = new ResizeObserver(() => {
            const pw = panel.clientWidth - 30; // account for padding
            if (pw > 100) {
                canvas.width = pw;
                canvas.height = Math.max(120, Math.floor(pw * 0.55));
                this.updateProfile();
            }
        });
        resizeObs.observe(panel);

        // Slice controls
        document.getElementById('slice-pos').addEventListener('input', (e) => {
            this.slicePosition = +e.target.value;
            document.getElementById('slice-pos-val').textContent = this.slicePosition;
            this.updateProfile();
            this.updateSliceLine();
        });
        document.getElementById('btn-slice-xz').addEventListener('click', () => {
            this.sliceDirection = 'xz';
            document.getElementById('btn-slice-xz').classList.add('active');
            document.getElementById('btn-slice-lr').classList.remove('active');
            this.updateProfile();
            this.updateSliceLine();
        });
        document.getElementById('btn-slice-lr').addEventListener('click', () => {
            this.sliceDirection = 'lr';
            document.getElementById('btn-slice-lr').classList.add('active');
            document.getElementById('btn-slice-xz').classList.remove('active');
            this.updateProfile();
            this.updateSliceLine();
        });
    }

    editProfileAt(e) {
        const canvas = document.getElementById('profile-canvas');
        const rect = canvas.getBoundingClientRect();
        const mx = (e.clientX - rect.left) / rect.width;  // 0-1 along the profile
        const my = 1 - (e.clientY - rect.top) / rect.height; // 0-1 from bottom
        const targetHeight = my * 20; // map to 0-20 ft
        const s = this.segments;
        const sliceNorm = this.slicePosition / 100;

        // Edit a band of vertices around the click position
        const brushWidth = 3; // how many vertices wide the brush is
        const pos = this.terrainGeom.attributes.position.array;

        if (this.sliceDirection === 'xz') {
            const ci = Math.floor(s * sliceNorm);
            const targetJ = Math.floor(mx * s);
            for (let dj = -brushWidth; dj <= brushWidth; dj++) {
                const j = targetJ + dj;
                if (j < 0 || j > s) continue;
                const falloff = 1 - Math.abs(dj) / (brushWidth + 1);
                for (let di = -1; di <= 1; di++) {
                    const i = ci + di;
                    if (i < 0 || i > s) continue;
                    const idx = j * (s + 1) + i;
                    const diff = targetHeight - this.heightData[idx];
                    this.heightData[idx] += diff * falloff * 0.3;
                    pos[idx * 3 + 1] = this.heightData[idx];
                }
            }
        } else {
            const cj = Math.floor(s * sliceNorm);
            const targetI = Math.floor(mx * s);
            for (let di = -brushWidth; di <= brushWidth; di++) {
                const i = targetI + di;
                if (i < 0 || i > s) continue;
                const falloff = 1 - Math.abs(di) / (brushWidth + 1);
                for (let dj = -1; dj <= 1; dj++) {
                    const j = cj + dj;
                    if (j < 0 || j > s) continue;
                    const idx = j * (s + 1) + i;
                    const diff = targetHeight - this.heightData[idx];
                    this.heightData[idx] += diff * falloff * 0.3;
                    pos[idx * 3 + 1] = this.heightData[idx];
                }
            }
        }

        this.terrainGeom.attributes.position.needsUpdate = true;
        this.terrainGeom.computeVertexNormals();
        this.colorTerrain();
        this.terrainGeom.attributes.color.needsUpdate = true;
        this.updateProfile();
        this.updateSliceLine();
    }

    exportData() {
        const data = { terrain: { width:this.terrainWidth, depth:this.terrainDepth, segments:this.segments, heightData:this.heightData },
            structures: this.structures.map(s=>({type:s.userData.type, label:s.userData.label, position:{x:s.position.x,y:s.position.y,z:s.position.z}, rotation:s.rotation.y}))
        };
        const blob = new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
        const a = document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='hillside-data.json'; a.click();
    }

    importData() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';
        input.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (ev) => {
                try {
                    const data = JSON.parse(ev.target.result);
                    if (data.terrain && data.terrain.heightData) {
                        this.heightData = data.terrain.heightData;
                        this.refreshTerrain();
                        this.saveHistory();
                    }
                    // Note: structure positions are logged but full import of
                    // structure geometry would require matching by type.
                    // For now we just restore terrain.
                    if (data.structures) {
                        console.log('Imported structure positions:', data.structures);
                        alert(`Terrain imported. ${data.structures.length} structure positions logged to console (move them manually to match).`);
                    }
                } catch(err) {
                    alert('Error reading file: ' + err.message);
                }
            };
            reader.readAsText(file);
        });
        input.click();
    }

    // ============================================================
    // RENDER LOOP
    // ============================================================
    animate() {
        requestAnimationFrame(() => this.animate());
        this.controls.update();
        if (this.water) this.water.position.y = 0.05 + Math.sin(Date.now()*0.0008)*0.04;
        this.renderer.render(this.scene, this.camera);
    }
}

// Launch
window.addEventListener('DOMContentLoaded', () => new App());
