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

        // Grid
        this.gridHelper = null;
        this.gridVisible = false;

        this.init();
    }

    init() {
        this.setupScene();
        this.setupLighting();
        this.createTerrain();
        this.createWater();
        this.createBrushMarker();
        this.setupGrid();
        this.createSiteStructures();
        this.setupEvents();
        this.setupUI();
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
        const g = new THREE.RingGeometry(0.8, 1, 32);
        const m = new THREE.MeshBasicMaterial({ color: 0xffff00, side: THREE.DoubleSide, transparent: true, opacity: 0.6 });
        this.brushMarker = new THREE.Mesh(g, m);
        this.brushMarker.rotation.x = -Math.PI / 2;
        this.brushMarker.visible = false;
        this.scene.add(this.brushMarker);
    }

    setupGrid() {
        this.gridHelper = new THREE.GridHelper(70, 35, 0x444444, 0x333333);
        this.gridHelper.position.y = 0.1;
        this.gridHelper.visible = this.gridVisible;
        this.scene.add(this.gridHelper);
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
        const g = new THREE.Group();
        g.userData = { type: 'house', label: 'House' };
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
        // Deck
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
    }

    addExistingStairs(x, z) {
        const g = new THREE.Group();
        g.userData = { type: 'stairs', label: 'Existing Stairs' };
        const wc = 0xC4A35A, sc = 0x8B6914, sw = 3.5;
        // Upper run: 8 steps going toward lake (+Z)
        const uSteps = 8, uRise = 5, uRun = 8;
        for (let i = 0; i < uSteps; i++) {
            const s = this.box(sw, 0.18, 0.85, wc);
            s.position.set(0, uRise - i*(uRise/uSteps), i*(uRun/uSteps));
            g.add(s);
        }
        // Landing
        const land = this.box(5, 0.22, 4, wc);
        land.position.set(0, 0, uRun+1.5);
        g.add(land);
        // Lower run: pivots left, 12 steps going in -X direction
        const lSteps = 12, lRise = 8, lRun = 12;
        for (let i = 0; i < lSteps; i++) {
            const s = this.box(0.85, 0.18, sw, wc);
            s.position.set(-(i+1)*(lRun/lSteps), -(i+1)*(lRise/lSteps), uRun+2);
            g.add(s);
        }
        // Railing posts upper (left side)
        for (let i = 0; i <= uSteps; i += 2) {
            const p = this.box(0.15, 3.2, 0.15, sc);
            p.position.set(-sw/2-0.2, uRise - i*(uRise/uSteps)+1.6, i*(uRun/uSteps));
            g.add(p);
        }
        // Railing posts lower (lake side)
        for (let i = 0; i <= lSteps; i += 3) {
            const p = this.box(0.15, 3.2, 0.15, sc);
            p.position.set(-(i+1)*(lRun/lSteps), -(i+1)*(lRise/lSteps)+1.6, uRun+2+sw/2+0.2);
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
        g.userData = { type: 'retaining-wall', label: 'Retaining Wall' };
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
        this.selected.forEach(s => {
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
    undo() { if(this.historyIdx>0){this.historyIdx--;this.heightData=[...this.history[this.historyIdx]];this.refreshTerrain();} }
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
                }
            } else {
                this.brushMarker.visible = false;
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
        ['stairs','railing','retaining-wall','rock','tree'].forEach(t => {
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
        document.getElementById('btn-toggle-grid').addEventListener('click', () => { this.gridVisible=!this.gridVisible; this.gridHelper.visible=this.gridVisible; });
        document.getElementById('btn-toggle-wireframe').addEventListener('click', () => { this.terrainMat.wireframe=!this.terrainMat.wireframe; });
    }

    setMode(mode) {
        this.mode = mode;
        document.querySelectorAll('#toolbar .tool-section:first-child .tool-btn').forEach(b=>b.classList.remove('active'));
        document.getElementById(`btn-mode-${mode}`).classList.add('active');
        // Show/hide relevant sections
        document.getElementById('terrain-tools-section').style.display = mode==='terrain'?'':'none';
        document.getElementById('place-tools-section').style.display = mode==='place'?'':'none';
        document.getElementById('select-tools-section').style.display = mode==='select'?'':'none';
        // Controls
        this.controls.enabled = (mode === 'camera');
        this.brushMarker.visible = false;
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
        const s = this.segments, ci = Math.floor(s*0.45);
        ctx.beginPath(); ctx.strokeStyle='#4fc3f7'; ctx.lineWidth=2;
        for(let j=0;j<=s;j++){const idx=j*(s+1)+ci;const px=(j/s)*w;const py=h-(this.heightData[idx]/20)*(h-15)-5;j===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
        ctx.stroke();
        ctx.beginPath(); ctx.strokeStyle='rgba(255,255,100,0.35)'; ctx.lineWidth=1; ctx.setLineDash([4,4]);
        for(let j=0;j<=s;j++){const idx=j*(s+1)+ci;const px=(j/s)*w;const py=h-(this.originalHeightData[idx]/20)*(h-15)-5;j===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}
        ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle='#666'; ctx.font='9px sans-serif';
        ctx.fillText('House',2,10); ctx.fillText('Slope',w*0.55,10); ctx.fillText('Beach',w*0.82,10);
    }

    exportData() {
        const data = { terrain: { width:this.terrainWidth, depth:this.terrainDepth, segments:this.segments, heightData:this.heightData },
            structures: this.structures.map(s=>({type:s.userData.type, label:s.userData.label, position:{x:s.position.x,y:s.position.y,z:s.position.z}, rotation:s.rotation.y}))
        };
        const blob = new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
        const a = document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='hillside-data.json'; a.click();
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
