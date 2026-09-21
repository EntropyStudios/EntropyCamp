import * as THREE from "./assets/vendor/three.module.js";
import { TrackballControls } from "./assets/vendor/addons/controls/TrackballControls.js";

let rendererGeneration = 0;

const PLANET_SPECS = Object.freeze({
  "ash-twin": { radius: 0.2, axis: 5.0, color: 0xc9a46b },
  "ember-twin": { radius: 0.2, axis: 5.7, color: 0xd16b48 },
  "timber-hearth": { radius: 0.25, axis: 8.593, color: 0x76aa87 },
  attlerock: { radius: 0.1, axis: 9.65, color: 0xa7b1b4 },
  "quantum-moon": { radius: 0.11, axis: 10.595, color: 0xdad6c9 },
  "brittle-hollow": { radius: 0.3, axis: 11.691, color: 0x6eaac1 },
  "hollows-lantern": { radius: 0.13, axis: 13.05, color: 0xf08b55 },
  stranger: { radius: 0.8, displayScale: 0.75, axis: 14.4, color: 0x99adb8 },
  "giants-deep": { radius: 0.95, displayScale: 0.75, axis: 16.458, color: 0x8baa9c },
  "dark-bramble": { radius: 0.65, axis: 20.0, color: 0xa9c6cf },
  interloper: { radius: 0.11, axis: 24.1, color: 0xcadbe1, comet: true },
});
const PLANET_SCALE = Object.freeze({ idle: 1.5, working: 2.25, shattered: 1.875 });
const POINTER_BLACK_HOLE_RADIUS = 13.05;
const SUN_RADIUS = 2.5;
const INTERIOR_SHARD_COUNT = 4200;
const SOLAR_CYCLE_MS = 16 * 60 * 60 * 1000;
const SOLAR_DAY_MS = 24 * 60 * 60 * 1000;
const PROMINENCE_ROOT = "./assets/outer-wilds/effects/";
const Y_AXIS = new THREE.Vector3(0, 1, 0);
const ORBIT_OUTER_PIVOT = 12;
const ORBIT_OUTER_COMPRESSION = 0.62;
const MAX_ORBIT_APOAPSIS = 24;

const EFFORT_COLORS = {
  minimal: 0x5aa9ff, low: 0x5aa9ff, medium: 0x46d5d1,
  high: 0xa6d957, xhigh: 0xff9a4d, max: 0xef5b5b, ultra: 0xef5b5b,
};
const EFFORT_LABELS = {
  minimal: "最低", low: "低", medium: "中", high: "高",
  xhigh: "很高", max: "最高", ultra: "极高",
};

function effortColor(value) {
  return EFFORT_COLORS[String(value || "").toLowerCase()] || 0x86a1aa;
}

function effortLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return EFFORT_LABELS[normalized] || normalized.toUpperCase();
}

function textSeed(value, salt = 0) {
  let hash = (2166136261 + salt) >>> 0;
  for (const character of String(value || "")) hash = Math.imul(hash ^ character.charCodeAt(0), 16777619) >>> 0;
  return hash / 0xffffffff;
}

export function createOrbitSpec(id, index, count, comet = false, planetKey = "", sequence = index) {
  const seed = textSeed(id);
  const source = PLANET_SPECS[planetKey];
  const round = Math.floor(Math.max(0, Number(sequence) || 0) / Object.keys(PLANET_SPECS).length);
  const isComet = comet || source?.comet;
  const sourceAxis = source?.axis || (5.8 + (index % 7) * 1.65);
  const baseAxis = sourceAxis <= ORBIT_OUTER_PIVOT ? sourceAxis
    : ORBIT_OUTER_PIVOT + (sourceAxis - ORBIT_OUTER_PIVOT) * ORBIT_OUTER_COMPRESSION;
  const eccentricity = isComet ? 0.62 + textSeed(id, 41) * 0.16 : 0.08 + textSeed(id, 41) * 0.16;
  const requestedSemiMajor = baseAxis * (0.84 + seed * 0.34) + round * 0.55;
  const semiMajor = Math.min(requestedSemiMajor, MAX_ORBIT_APOAPSIS / (1 + eccentricity));
  return {
    semiMajor,
    semiMinor: semiMajor * Math.sqrt(1 - eccentricity ** 2),
    inclination: (textSeed(id, 83) - 0.5) * 1.18,
    tilt: (textSeed(id, 337) - 0.5) * 0.92,
    node: textSeed(id, 701) * Math.PI * 2,
    phase: (index / Math.max(1, count)) * Math.PI * 2 + seed * 0.62,
    speed: (isComet ? 0.031 : 0.022) / Math.sqrt(semiMajor),
    eccentricity,
  };
}

function eccentricAnomaly(meanAnomaly, eccentricity) {
  let value = meanAnomaly;
  for (let index = 0; index < 7; index += 1) {
    value -= (value - eccentricity * Math.sin(value) - meanAnomaly)
      / Math.max(0.08, 1 - eccentricity * Math.cos(value));
  }
  return value;
}

export function orbitPoint(spec, elapsed = 0, center = new THREE.Vector3()) {
  const anomaly = eccentricAnomaly(spec.phase + elapsed * spec.speed, spec.eccentricity);
  return new THREE.Vector3(
    spec.semiMajor * (Math.cos(anomaly) - spec.eccentricity),
    spec.semiMinor * Math.sin(anomaly),
    0,
  ).applyEuler(new THREE.Euler(spec.inclination, spec.tilt, spec.node)).add(center);
}

function runtimeLabel(node) {
  const raw = Number(node.phaseStartedAt);
  if (!raw || raw <= 0) return node.runtimeLabel || "";
  const startedAt = raw > 10_000_000_000 ? raw : raw * 1000;
  const age = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  if (age < 60) return `${age}秒`;
  if (age < 3600) return `${Math.floor(age / 60)}分${age % 60}秒`;
  return `${Math.floor(age / 3600)}小时${Math.floor(age / 60) % 60}分`;
}

function edgeLabel(node) {
  const effort = effortLabel(node.effort);
  return [node.modelLabel, effort ? `强度${effort}` : "", runtimeLabel(node)]
    .filter(Boolean).join(" · ");
}

function sunActivityLabel(groups) {
  const active = groups.map((group) => group.userData.node)
    .filter((node) => node.working && !node.shattered);
  if (!active.length) return "任务核心";
  const phases = active.map((node) => node.phaseLabel).filter(Boolean);
  const priority = ["推理中", "执行工具", "AI 输出", "倒计时", "处理中"];
  const phase = priority.find((label) => phases.some((value) => value.includes(label)))
    || phases[0] || "处理中";
  return `${phase} · ${active.length} 个任务`;
}

function seededValue(index, salt) {
  const value = Math.sin((index + 1) * 12.9898 + salt * 78.233) * 43758.5453;
  return value - Math.floor(value);
}

function buildFragmentAttributes(geometry, salt) {
  const positions = geometry.attributes.position;
  const centers = new Float32Array(positions.count * 3);
  const directions = new Float32Array(positions.count * 3);
  const seeds = new Float32Array(positions.count);
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const center = new THREE.Vector3(), direction = new THREE.Vector3();
  for (let vertex = 0; vertex < positions.count; vertex += 3) {
    a.fromBufferAttribute(positions, vertex);
    b.fromBufferAttribute(positions, vertex + 1);
    c.fromBufferAttribute(positions, vertex + 2);
    center.copy(a).add(b).add(c).multiplyScalar(1 / 3);
    direction.copy(center).normalize();
    if (direction.lengthSq() < 0.001) direction.set(0, 1, 0);
    const seed = seededValue(vertex / 3, salt);
    for (let corner = 0; corner < 3; corner += 1) {
      const target = vertex + corner;
      centers.set(center.toArray(), target * 3);
      directions.set(direction.toArray(), target * 3);
      seeds[target] = seed;
    }
  }
  geometry.setAttribute("aFragmentCenter", new THREE.BufferAttribute(centers, 3));
  geometry.setAttribute("aFragmentDirection", new THREE.BufferAttribute(directions, 3));
  geometry.setAttribute("aFragmentSeed", new THREE.BufferAttribute(seeds, 1));
}

let loaderPromise = null;
async function outerWildsLoader() {
  if (!loaderPromise) {
    loaderPromise = Promise.all([
      import("three/addons/loaders/GLTFLoader.js"),
      import("three/addons/libs/meshopt_decoder.module.js"),
    ]).then(async ([{ GLTFLoader }, { MeshoptDecoder }]) => {
      await MeshoptDecoder.ready;
      const loader = new GLTFLoader();
      loader.setMeshoptDecoder(MeshoptDecoder);
      return loader;
    });
  }
  return loaderPromise;
}

function materialTextures(material, target) {
  Object.values(material || {}).forEach((value) => { if (value?.isTexture) target.add(value); });
}

function createAssetLibrary() {
  const cache = new Map(), pending = new Map();
  let disposed = false;
  function disposeAsset(asset) {
    const geometries = new Set(), materials = new Set(), textures = new Set();
    asset.records.forEach((record) => {
      geometries.add(record.geometry);
      record.materials.forEach((material) => materials.add(material));
    });
    materials.forEach((material) => materialTextures(material, textures));
    textures.forEach((texture) => texture.dispose());
    materials.forEach((material) => material.dispose());
    geometries.forEach((geometry) => geometry.dispose());
  }
  async function prepare(key) {
    const loader = await outerWildsLoader();
    const gltf = await loader.loadAsync(`/assets/outer-wilds/models/${key}.glb`);
    gltf.scene.updateMatrixWorld(true);
    const records = [], originals = new Set();
    const bounds = new THREE.Box3();
    gltf.scene.traverse((object) => {
      if (!object.isMesh || !object.geometry?.attributes?.position) return;
      originals.add(object.geometry);
      const geometry = PLANET_SPECS[key] && object.geometry.index
        ? object.geometry.toNonIndexed() : object.geometry.clone();
      geometry.applyMatrix4(object.matrixWorld);
      geometry.computeBoundingBox();
      bounds.union(geometry.boundingBox);
      records.push({ geometry, materials: (Array.isArray(object.material) ? object.material : [object.material]).filter(Boolean) });
    });
    if (!records.length) throw new Error(`Outer Wilds asset ${key} has no mesh`);
    const center = bounds.getCenter(new THREE.Vector3());
    let radius = 0;
    records.forEach((record, index) => {
      record.geometry.translate(-center.x, -center.y, -center.z);
      record.geometry.computeBoundingSphere();
      radius = Math.max(radius, record.geometry.boundingSphere.radius);
      record.geometry.userData.outerWildsShared = true;
      if (PLANET_SPECS[key]) buildFragmentAttributes(record.geometry, index + 1);
    });
    originals.forEach((geometry) => geometry.dispose());
    return { key, records, radius: Math.max(radius, 0.001) };
  }
  function load(key) {
    if (cache.has(key)) return Promise.resolve(cache.get(key));
    if (pending.has(key)) return pending.get(key);
    const promise = prepare(key).then((asset) => {
      pending.delete(key);
      if (disposed) { disposeAsset(asset); throw new Error("Asset library disposed"); }
      cache.set(key, asset);
      return asset;
    }).catch((error) => { pending.delete(key); throw error; });
    pending.set(key, promise);
    return promise;
  }
  return {
    load,
    get size() { return cache.size; },
    dispose() { if (disposed) return; disposed = true; cache.forEach(disposeAsset); cache.clear(); },
  };
}

function preparePlanetMaterial(source, key, nodeUniforms) {
  const material = source.clone();
  material.side = THREE.DoubleSide;
  material.emissive?.setRGB(0, 0, 0);
  if ("emissiveIntensity" in material) material.emissiveIntensity = 0;
  if ("emissiveMap" in material) material.emissiveMap = null;
  if (key === "timber-hearth") {
    material.transparent = false; material.opacity = 1; material.alphaTest = 0.25;
    material.depthTest = true; material.depthWrite = true;
    if ("roughness" in material) material.roughness = Math.max(0.9, material.roughness);
    if ("metalness" in material) material.metalness = 0;
    if ("specularIntensity" in material) material.specularIntensity = 0;
    if ("specularColor" in material) material.specularColor.setRGB(0, 0, 0);
    if ("envMapIntensity" in material) material.envMapIntensity = 0;
  }
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, {
      uExplode: nodeUniforms.explode, uTime: nodeUniforms.time,
      uCloudRadius: nodeUniforms.cloudRadius, uBrightness: nodeUniforms.brightness,
    });
    shader.vertexShader = shader.vertexShader.replace("#include <common>", `
      #include <common>
      attribute vec3 aFragmentCenter; attribute vec3 aFragmentDirection; attribute float aFragmentSeed;
      uniform float uExplode; uniform float uTime; uniform float uCloudRadius; varying float vFragmentSeed;
      vec3 rotateFragment(vec3 v,vec3 a,float r){float c=cos(r);return v*c+cross(a,v)*sin(r)+a*dot(a,v)*(1.0-c);}
    `).replace("#include <begin_vertex>", `
      vec3 transformed=vec3(position);float amount=smoothstep(0.0,1.0,uExplode);vFragmentSeed=aFragmentSeed;
      vec3 radial=normalize(aFragmentDirection);vec3 tangent=normalize(cross(radial,vec3(.31,.87,.19)));
      vec3 axis=normalize(radial*.42+tangent*.82+vec3(.11,.17,.07));vec3 local=transformed-aFragmentCenter;
      float angle=amount*((aFragmentSeed-.5)*5.2)+uTime*amount*(aFragmentSeed-.5)*.16;
      local=rotateFragment(local,axis,angle)*mix(1.0,.62,amount);
      vec3 offset=radial*uCloudRadius*(.48+aFragmentSeed*.48)*amount;
      offset+=tangent*uCloudRadius*(aFragmentSeed-.5)*.22*amount;
      transformed=aFragmentCenter+local+offset;
    `);
    shader.fragmentShader = shader.fragmentShader.replace("#include <common>", `
      #include <common>
      uniform float uExplode;uniform float uTime;uniform float uBrightness;varying float vFragmentSeed;
    `).replace("#include <opaque_fragment>", `
      float molten=smoothstep(.08,.72,uExplode);float seed=fract(sin(vFragmentSeed*91.731+4.173)*43758.5453);
      float hot=smoothstep(.34,.92,seed);float warm=smoothstep(.18,.84,seed)*.62;
      float pulse=.86+.14*sin(uTime*(1.1+vFragmentSeed*1.7)+vFragmentSeed*19.0);
      vec3 rock=outgoingLight*vec3(.2,.013,.005)+vec3(.085,.003,.0012);
      vec3 ember=vec3(2.45,.13,.018)*(hot+warm)*pulse;
      outgoingLight=mix(outgoingLight,rock+ember,molten)*uBrightness;
      #include <opaque_fragment>
    `);
  };
  material.customProgramCacheKey = () => "entropycamp-planet-fragment-v1";
  material.needsUpdate = true;
  material.userData.outerWildsInstance = true;
  return material;
}

function createInteriorShardLayer(radius, key) {
  const geometry = new THREE.TetrahedronGeometry(radius * 0.04, 0);
  const palette = [new THREE.Color(0x4b0503), new THREE.Color(0x941307), new THREE.Color(0x240203), new THREE.Color(0xd13b0d)];
  const colors = new Float32Array(geometry.attributes.position.count * 3);
  for (let vertex = 0; vertex < geometry.attributes.position.count; vertex += 1) {
    const color = palette[Math.floor(vertex / 3) % palette.length];
    colors.set([color.r, color.g, color.b], vertex * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const material = new THREE.MeshStandardMaterial({
    color: 0xffffff, vertexColors: true, emissive: 0x240200, emissiveIntensity: 1.05,
    roughness: 0.72, metalness: 0.04, flatShading: true, depthWrite: true, depthTest: true,
  });
  material.userData.outerWildsInstance = true;
  const mesh = new THREE.InstancedMesh(geometry, material, INTERIOR_SHARD_COUNT);
  const dummy = new THREE.Object3D(), salt = Math.floor(textSeed(key, 1701) * 1_000_000);
  let coreCount = 0;
  for (let index = 0; index < INTERIOR_SHARD_COUNT; index += 1) {
    const direction = new THREE.Vector3(seededValue(index, salt + 1) * 2 - 1,
      seededValue(index, salt + 2) * 2 - 1, seededValue(index, salt + 3) * 2 - 1).normalize();
    const uniformVolume = Math.cbrt(seededValue(index, salt + 4));
    const coreBiased = Math.pow(seededValue(index, salt + 5), 2.4);
    const radialDistance = radius * THREE.MathUtils.lerp(uniformVolume, coreBiased, 0.84);
    if (radialDistance < radius * 0.35) coreCount += 1;
    dummy.position.copy(direction.multiplyScalar(radialDistance));
    dummy.rotation.set(seededValue(index, salt + 6) * Math.PI, seededValue(index, salt + 7) * Math.PI,
      seededValue(index, salt + 8) * Math.PI);
    const scale = 0.75 + seededValue(index, salt + 9) * 1.65;
    dummy.scale.set(scale * (0.65 + seededValue(index, salt + 10) * 0.7), scale,
      scale * (0.55 + seededValue(index, salt + 11) * 0.75));
    dummy.updateMatrix(); mesh.setMatrixAt(index, dummy.matrix);
  }
  mesh.instanceMatrix.needsUpdate = true; mesh.frustumCulled = false;
  const layer = new THREE.Group(); layer.name = "InteriorShardLayer"; layer.visible = false;
  layer.userData.interiorShardLayer = true; layer.userData.style = "hot-core-B";
  layer.userData.count = INTERIOR_SHARD_COUNT; layer.userData.coreCount = coreCount;
  layer.add(mesh); return layer;
}

function createVisualTextureLibrary() {
  const loader = new THREE.TextureLoader();
  let sunPromise = null, sunTextures = null, disposed = false;
  return {
    loadSun() {
      if (!sunPromise) {
        sunPromise = Promise.all([
          loader.loadAsync(`${PROMINENCE_ROOT}sun-height.png`),
          loader.loadAsync(`${PROMINENCE_ROOT}sun-color-ramp.png`),
        ]).then(([height, ramp]) => {
          if (disposed) { height.dispose(); ramp.dispose(); throw new Error("Visual texture library disposed"); }
          height.wrapS = height.wrapT = THREE.RepeatWrapping;
          ramp.colorSpace = THREE.SRGBColorSpace;
          sunTextures = { height, ramp };
          return sunTextures;
        });
      }
      return sunPromise;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      sunTextures?.height.dispose();
      sunTextures?.ramp.dispose();
      sunTextures = null;
    },
  };
}

function createProminenceLibrary() {
  const loader = new THREE.TextureLoader();
  let promise = null, resources = null, disposed = false;
  function geometryFrom(source) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(source.positions, 3));
    geometry.setAttribute("normal", new THREE.Float32BufferAttribute(source.normals, 3));
    geometry.setAttribute("uv", new THREE.Float32BufferAttribute(source.uv, 2));
    geometry.setIndex(source.indices); geometry.computeBoundingSphere();
    geometry.userData.outerWildsShared = true; return geometry;
  }
  return {
    load() {
      if (!promise) promise = Promise.all([
        fetch(`${PROMINENCE_ROOT}solar-prominence-geometry.json`).then((response) => {
          if (!response.ok) throw new Error("Official prominence geometry unavailable");
          return response.json();
        }),
        loader.loadAsync(`${PROMINENCE_ROOT}solar-flare-noise.png`),
        loader.loadAsync(`${PROMINENCE_ROOT}solar-flare-loop-mask.png`),
      ]).then(([data, noise, loopMask]) => {
        if (disposed) { noise.dispose(); loopMask.dispose(); throw new Error("Prominence library disposed"); }
        noise.wrapS = noise.wrapT = loopMask.wrapS = loopMask.wrapT = THREE.RepeatWrapping;
        resources = { data, noise, loopMask, geometries: {
          loop: geometryFrom(data.meshes.loop), dome: geometryFrom(data.meshes.dome),
        } };
        return resources;
      });
      return promise;
    },
    dispose() {
      if (disposed) return; disposed = true;
      resources?.noise.dispose(); resources?.loopMask.dispose();
      Object.values(resources?.geometries || {}).forEach((geometry) => geometry.dispose());
      resources = null;
    },
  };
}

function prominenceHermite(time, left, right) {
  const span = right.time - left.time;
  const x = THREE.MathUtils.clamp((time - left.time) / span, 0, 1), x2 = x * x, x3 = x2 * x;
  return (2 * x3 - 3 * x2 + 1) * left.value + (x3 - 2 * x2 + x) * span * (left.outSlope || 0)
    + (-2 * x3 + 3 * x2) * right.value + (x3 - x2) * span * (right.inSlope || 0);
}

function createProminenceMaterial(type, resources) {
  const dome = type === "dome";
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, depthTest: true, side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
    uniforms: {
      uNoise: { value: resources.noise }, uMask: { value: dome ? resources.noise : resources.loopMask },
      uHasMask: { value: dome ? 0 : 1 }, uLife: { value: 0 }, uAlpha: { value: 1 },
      uCutoff: { value: dome ? 0 : -1 }, uColor: { value: new THREE.Color(2.35, 0.31, 0.028) },
      uScroll: { value: new THREE.Vector2(1, dome ? 1 : 0) },
    },
    vertexShader: `varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `varying vec2 vUv;uniform sampler2D uNoise;uniform sampler2D uMask;uniform float uHasMask;uniform float uLife;uniform float uAlpha;uniform float uCutoff;uniform vec3 uColor;uniform vec2 uScroll;void main(){vec2 uv=vUv+uScroll*uLife;float noise=texture2D(uNoise,uv).r;float mask=mix(1.0,texture2D(uMask,vUv).r,uHasMask);if(mask<uCutoff)discard;float edge=smoothstep(uCutoff,uCutoff+.12,mask);float alpha=uAlpha*edge*(.16+noise*.7);gl_FragColor=vec4(uColor*(.22+noise*.92),alpha);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
  });
}

function createProminenceSystem(parent, camera, library) {
  const group = new THREE.Group(); parent.add(group);
  const clusters = []; let resources = null, serial = 0, elapsed = 0, nextSpawn = 1;
  const domeCurve = [{ time: 0, value: 1, outSlope: -4.08131 }, { time: 0.75, value: 0, inSlope: 0 }];
  function directionFor(index, showcase = false) {
    if (showcase) {
      const angle = textSeed(index, 901) * Math.PI * 2, z = 0.08 + textSeed(index, 902) * 0.16;
      const radius = Math.sqrt(1 - z * z); return new THREE.Vector3(Math.cos(angle) * radius, Math.sin(angle) * radius, z);
    }
    return new THREE.Vector3(textSeed(index, 903) * 2 - 1, textSeed(index, 904) * 2 - 1,
      textSeed(index, 905) * 2 - 1).normalize();
  }
  function spawn(age = 0, showcase = false) {
    if (!resources) return;
    const direction = directionFor(serial++, showcase), objects = ["loop", "dome"].map((type, index) => {
      const mesh = new THREE.Mesh(resources.geometries[type], createProminenceMaterial(type, resources));
      mesh.position.copy(direction).multiplyScalar(SUN_RADIUS * 1.025);
      mesh.quaternion.setFromUnitVectors(Y_AXIS, direction); mesh.rotateY((textSeed(serial, 910 + index) - 0.5) * 0.22);
      mesh.userData = { type, direction: direction.clone() }; mesh.frustumCulled = false; group.add(mesh); return mesh;
    });
    clusters.push({ age, objects });
  }
  Promise.resolve().then(() => library.load()).then((value) => {
    resources = value; [4, 7, 10, 12].forEach((age) => spawn(age, true));
  }).catch(() => { group.userData.failed = true; });
  return {
    group,
    update(delta, evolution, visible = true) {
      group.visible = visible; if (!resources || !visible) return;
      elapsed += delta;
      if (elapsed >= nextSpawn) { spawn(); nextSpawn = elapsed + THREE.MathUtils.lerp(6, 2.2, evolution); }
      const viewDirection = camera.position.clone().normalize();
      for (let index = clusters.length - 1; index >= 0; index -= 1) {
        const cluster = clusters[index]; cluster.age += delta; const life = THREE.MathUtils.clamp(cluster.age / 15, 0, 1);
        cluster.objects.forEach((mesh) => {
          const type = mesh.userData.type, spec = resources.data.meshes[type];
          const scale = SUN_RADIUS * 1.7 * THREE.MathUtils.lerp(0.02, 0.2, life);
          mesh.scale.set(spec.scaleFactor[0] * scale, spec.scaleFactor[1] * scale, spec.scaleFactor[2] * scale);
          mesh.material.uniforms.uLife.value = life;
          mesh.material.uniforms.uAlpha.value = type === "loop" ? 1 : life >= 0.75 ? 0 : THREE.MathUtils.clamp(prominenceHermite(life, domeCurve[0], domeCurve[1]), 0, 1);
          mesh.material.uniforms.uCutoff.value = type === "loop" ? (life <= 0.5 ? -1 : THREE.MathUtils.lerp(-1, 1, (life - 0.5) / 0.5)) : 0;
          mesh.visible = mesh.userData.direction.dot(viewDirection) > -0.04;
        });
        if (life >= 1) { cluster.objects.forEach((mesh) => { group.remove(mesh); mesh.material.dispose(); }); clusters.splice(index, 1); }
      }
    },
    dispose() { clusters.splice(0).forEach((cluster) => cluster.objects.forEach((mesh) => mesh.material.dispose())); group.removeFromParent(); },
  };
}

function sunMaterial(textures, nodeUniforms) {
  return new THREE.ShaderMaterial({
    uniforms: { time: nodeUniforms.time, evolution: nodeUniforms.evolution, collapse: nodeUniforms.collapse,
      heightMap: { value: textures.height }, colorRamp: { value: textures.ramp } },
    vertexShader: `varying vec2 u;varying vec3 n;void main(){u=uv;n=normalize(normalMatrix*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `varying vec2 u;varying vec3 n;uniform float time;uniform float evolution;uniform float collapse;uniform sampler2D heightMap;uniform sampler2D colorRamp;void main(){
      float h=texture2D(heightMap,u*3.5+vec2(time*.003,time*.002)).r;
      float h2=texture2D(heightMap,u*8.0-vec2(time*.005,time*.004)).r;
      float heat=clamp(h*.72+h2*.28,0.0,1.0);vec3 ramp=texture2D(colorRamp,vec2(heat,.5)).rgb;
      vec3 young=mix(vec3(4.8,.75,.05),vec3(9.0,4.1,.72),smoothstep(.32,.76,heat));
      vec3 giant=mix(vec3(3.8,.12,.018),vec3(10.0,1.0,.08),smoothstep(.25,.82,heat));
      vec3 c=mix(young,giant,evolution);
      c*=mix(vec3(1.0,.42,.08),ramp*1.5+vec3(.3,.15,.02),.35);c=mix(c,vec3(c.r*1.22,c.g*.16,c.b*.08),evolution*.9);c=mix(c,vec3(8.0,3.0,.65),collapse*.75);c+=mix(vec3(4.5,1.15,.06),vec3(5.5,.28,.025),evolution)*pow(1.0-abs(n.z),3.0);
      gl_FragColor=vec4(c,1.0);
    }`,
  });
}

function whiteHoleMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { time: { value: 0 } },
    vertexShader: `varying vec3 n;varying vec2 u;void main(){n=normalize(normalMatrix*normal);u=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `varying vec3 n;varying vec2 u;uniform float time;void main(){float r=pow(1.0-abs(n.z),1.8);float f=sin(u.y*42.0+time*1.4)*.5+.5;vec3 c=mix(vec3(.8,1.25,1.8),vec3(.22,.75,2.4),r)+vec3(.22,.35,.6)*f*.3;gl_FragColor=vec4(c,1.0);}`,
  });
}

function createSunHalo() {
  const material = new THREE.ShaderMaterial({
    uniforms: { color: { value: new THREE.Color(0xff8c42) } }, transparent: true,
    depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.BackSide,
    vertexShader: `varying vec3 n;void main(){n=normalize(normalMatrix*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `varying vec3 n;uniform vec3 color;void main(){float a=pow(1.0-abs(n.z),2.4)*.11;gl_FragColor=vec4(color,a);}`,
  });
  return new THREE.Mesh(new THREE.SphereGeometry(SUN_RADIUS * 1.075, 48, 32), material);
}

function createSolarFinaleEffects(parent) {
  const group = new THREE.Group(); parent.add(group);
  const shockMaterial = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.BackSide, blending: THREE.AdditiveBlending,
    uniforms: { alpha: { value: 0 } },
    vertexShader: `varying vec3 n;void main(){n=normalize(normalMatrix*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `varying vec3 n;uniform float alpha;void main(){float edge=pow(1.0-abs(n.z),8.0);gl_FragColor=vec4(vec3(.36,.78,1.0),edge*alpha);}`,
  });
  const shock = new THREE.Mesh(new THREE.SphereGeometry(1, 52, 32), shockMaterial); shock.visible = false; group.add(shock);
  const count = 1800, positions = new Float32Array(count * 3), seeds = new Float32Array(count);
  for (let index = 0; index < count; index += 1) {
    const direction = new THREE.Vector3(textSeed(index, 1201) * 2 - 1, textSeed(index, 1202) * 2 - 1,
      textSeed(index, 1203) * 2 - 1).normalize();
    positions.set(direction.toArray(), index * 3); seeds[index] = textSeed(index, 1204);
  }
  const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3)); geometry.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1));
  const burstMaterial = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { progress: { value: 0 } },
    vertexShader: `attribute float aSeed;uniform float progress;varying float alpha;void main(){float travel=1.0-pow(1.0-progress,2.2);vec3 p=normalize(position)*travel*(5.0+aSeed*20.0);vec4 view=modelViewMatrix*vec4(p,1.0);gl_Position=projectionMatrix*view;gl_PointSize=(.7+aSeed*1.8)*18.0/max(1.0,-view.z);alpha=smoothstep(.02,.16,progress)*(.16+aSeed*.42)*(1.0-progress*.5);}`,
    fragmentShader: `varying float alpha;void main(){float d=length(gl_PointCoord-.5);float a=(1.0-smoothstep(.16,.5,d))*alpha;gl_FragColor=vec4(vec3(.62,1.35,3.5),a);}`,
  });
  const burst = new THREE.Points(geometry, burstMaterial); burst.visible = false; burst.frustumCulled = false; group.add(burst);
  return {
    group,
    update(progress) {
      const value = THREE.MathUtils.clamp(progress, 0, 1), active = value > 0.001;
      group.visible = active; shock.visible = active; burst.visible = active;
      shock.scale.setScalar(0.3 + value * 34); shockMaterial.uniforms.alpha.value = Math.sin(value * Math.PI) * 0.38;
      burstMaterial.uniforms.progress.value = value;
    },
    dispose() { shock.geometry.dispose(); shockMaterial.dispose(); geometry.dispose(); burstMaterial.dispose(); group.removeFromParent(); },
  };
}

function createStarfield() {
  const count = 1900, positions = new Float32Array(count * 3), colors = new Float32Array(count * 3);
  for (let index = 0; index < count; index += 1) {
    const theta = textSeed(index, 11) * Math.PI * 2;
    const phi = Math.acos(textSeed(index, 37) * 2 - 1);
    const radius = 64 + textSeed(index, 83) * 54;
    positions.set([Math.sin(phi) * Math.cos(theta) * radius, Math.cos(phi) * radius,
      Math.sin(phi) * Math.sin(theta) * radius], index * 3);
    const warm = textSeed(index, 149) > 0.78;
    colors.set(warm ? [1, 0.72, 0.48] : [0.48, 0.72, 0.9], index * 3);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return new THREE.Points(geometry, new THREE.PointsMaterial({ size: 0.06, vertexColors: true,
    transparent: true, opacity: 0.8, depthWrite: false }));
}

function createLensingPass() {
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const material = new THREE.ShaderMaterial({
    uniforms: {
      tScene: { value: null }, uResolution: { value: new THREE.Vector2(1, 1) },
      uPointer: { value: new THREE.Vector2(-2, -2) }, uPointerActive: { value: 0 },
      uPointerRadius: { value: POINTER_BLACK_HOLE_RADIUS }, uWhiteHole: { value: new THREE.Vector3(0, 0, 0) },
      uSun: { value: new THREE.Vector3(0.5, 0.5, 0) },
    },
    vertexShader: `varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.0,1.0);}`,
    fragmentShader: `
      precision highp float;
      varying vec2 vUv;uniform sampler2D tScene;uniform vec2 uResolution;
      uniform vec2 uPointer;uniform float uPointerActive;uniform float uPointerRadius;
      uniform vec3 uWhiteHole;uniform vec3 uSun;
      vec2 bendAt(vec2 uv,vec2 center,float radius,float strength){
        vec2 delta=(uv-center)*uResolution;float d=max(length(delta),.001);
        float influence=1.0-smoothstep(radius*1.05,radius*4.1,d);
        return delta/d*influence*radius*radius/max(d+radius*.5,.001)*strength/uResolution;
      }
      void main(){
        vec2 warped=vUv+bendAt(vUv,uPointer,uPointerRadius,.95)*uPointerActive;
        if(uWhiteHole.z>0.0)warped-=bendAt(vUv,uWhiteHole.xy,uWhiteHole.z,.62);
        vec3 color=texture2D(tScene,clamp(warped,vec2(0.0),vec2(1.0))).rgb;
        float pointerDistance=length((vUv-uPointer)*uResolution);
        float core=(1.0-smoothstep(uPointerRadius*.72,uPointerRadius*.96,pointerDistance))*uPointerActive;
        color*=1.0-core;
        vec2 crossDistance=abs((vUv-uPointer)*uResolution);
        float crossHorizontal=(1.0-smoothstep(.55,1.05,crossDistance.y))*(1.0-smoothstep(3.7,4.5,crossDistance.x));
        float crossVertical=(1.0-smoothstep(.55,1.05,crossDistance.x))*(1.0-smoothstep(3.7,4.5,crossDistance.y));
        float crossMark=max(crossHorizontal,crossVertical)*uPointerActive;
        color=mix(color,vec3(.78,.82,.84),crossMark*.92);
        if(uWhiteHole.z>0.0){
          float d=length((vUv-uWhiteHole.xy)*uResolution);float r=uWhiteHole.z;
          float whiteCore=exp(-pow(d/max(r*.62,1.0),2.0));
          float whiteRing=exp(-pow((d-r*1.28)/max(r*.18,1.0),2.0));
          float whiteOuter=exp(-pow((d-r*2.0)/max(r*.55,1.5),2.0));
          color+=vec3(.78,1.08,1.5)*whiteCore*1.1+vec3(.24,.72,1.45)*whiteRing*.72+vec3(.08,.28,.65)*whiteOuter*.16;
        }
        float sunDistance=length((vUv-uSun.xy)*uResolution);float sunRadius=max(uSun.z,1.0);
        float sunGlow=exp(-pow(max(0.0,sunDistance-sunRadius)/max(sunRadius*.58,2.0),2.0));
        float pointerToSun=length((uPointer-uSun.xy)*uResolution);
        float sunCovered=smoothstep(sunRadius*.18,sunRadius,uPointerRadius-pointerToSun)*uPointerActive;
        color+=vec3(.48,.12,.012)*sunGlow*.22*(1.0-sunCovered)*(1.0-core);
        gl_FragColor=vec4(color,1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
    depthTest: false, depthWrite: false,
  });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  scene.add(quad);
  return { scene, camera, material, quad };
}

function disposeDynamicObject(object) {
  object.traverse((child) => {
    if (child.geometry && !child.geometry.userData?.outerWildsShared) child.geometry.dispose();
    const materials = Array.isArray(child.material) ? child.material : [child.material];
    materials.filter(Boolean).forEach((material) => {
      if (!material.userData?.outerWildsInstance) material.map?.dispose?.();
      material.dispose?.();
    });
    child.userData.disposed = true;
  });
}

function clearVisual(group) {
  [...group.children].forEach((child) => { disposeDynamicObject(child); group.remove(child); });
  group.userData.interiorShardLayer = null;
}

function instantiateAsset(asset, key, uniforms, special = "", textures = null) {
  const root = new THREE.Group();
  const specialMaterial = special === "sun" ? sunMaterial(textures, uniforms) : special === "white" ? whiteHoleMaterial() : null;
  asset.records.forEach((record) => {
    const materials = specialMaterial ? record.materials.map(() => specialMaterial)
      : record.materials.map((material) => preparePlanetMaterial(material, key, uniforms));
    const mesh = new THREE.Mesh(record.geometry, materials.length === 1 ? materials[0] : materials);
    mesh.frustumCulled = false; root.add(mesh);
  });
  if (PLANET_SPECS[key]) root.add(createInteriorShardLayer(asset.radius, key));
  root.scale.setScalar(1 / asset.radius);
  return root;
}

function createLabel(layer, node, edge = false) {
  const label = document.createElement("div");
  label.className = edge ? "graph-space-label is-edge" : `graph-space-label is-${node.kind || "thread"}`;
  label.dataset.graphLabel = node.id;
  const title = document.createElement("strong");
  title.textContent = edge ? edgeLabel(node) : node.label;
  label.append(title);
  if (!edge) {
    const subtitle = document.createElement("span");
    subtitle.textContent = node.kind === "thread" && node.working ? "" : node.statusLabel || "";
    label.append(subtitle);
  }
  layer.append(label); return label;
}

function setLabelText(element, title, subtitle) {
  if (!element) return;
  const strong = element.querySelector("strong"), span = element.querySelector("span");
  if (strong && strong.textContent !== title) strong.textContent = title;
  if (span && span.textContent !== subtitle) span.textContent = subtitle;
}

function quadraticPoint(start, control, end, progress, target = new THREE.Vector3()) {
  const inverse = 1 - progress;
  return target.copy(start).multiplyScalar(inverse * inverse)
    .addScaledVector(control, 2 * inverse * progress).addScaledVector(end, progress * progress);
}

function easeInOut(value) {
  const x = THREE.MathUtils.clamp(value, 0, 1);
  return x * x * x * (x * (x * 6 - 15) + 10);
}

function planetScale(node) {
  return node.shattered ? PLANET_SCALE.shattered : node.working ? PLANET_SCALE.working : PLANET_SCALE.idle;
}

function planetDisplayRadius(planet) {
  return planet.radius * (planet.displayScale || 1);
}

function normalizeSolarState(value = {}) {
  const mode = ["day", "working", "destroyed"].includes(value.mode) ? value.mode : "day";
  return {
    mode,
    event: typeof value.event === "string" ? value.event : "none",
    token: typeof value.token === "string" ? value.token : "",
    dayProgress: THREE.MathUtils.clamp(Number(value.dayProgress) || 0, 0, 1),
    cycleOffsetMs: Math.max(0, Number(value.cycleOffsetMs) || 0),
    sampledAt: Number(value.sampledAt) || Date.now(),
  };
}

export function createConversationGraph({ container, canvas, nodes, solarState = {}, reducedMotion = false, onNodeSelect, onNodeRecycle }) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: false, antialias: false, powerPreference: "high-performance" });
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 180);
  const root = new THREE.Group(), graphLayer = new THREE.Group();
  root.add(graphLayer); scene.add(root); scene.background = new THREE.Color(0x010407);
  camera.position.set(0.56, 0.42, 0.71);
  const controls = new TrackballControls(camera, canvas);
  controls.noPan = true; controls.staticMoving = false; controls.dynamicDampingFactor = 0.16;
  controls.rotateSpeed = 1.35; controls.zoomSpeed = 0.82;
  controls.target.set(0, 0, 0);
  const assetLibrary = createAssetLibrary();
  const visualTextureLibrary = createVisualTextureLibrary();
  const prominenceLibrary = createProminenceLibrary();
  const mainTarget = new THREE.WebGLRenderTarget(1, 1, { depthBuffer: true, stencilBuffer: false,
    minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
  mainTarget.samples = 2;
  const lensing = createLensingPass();
  lensing.material.uniforms.tScene.value = mainTarget.texture;
  const nodeGroups = [], edges = [], pickables = [], bindings = [];
  let sunGroup = null, whiteHoleGroup = null, prominenceSystem = null, solarEffects = null, labelLayer = null, resizeObserver = null;
  let disposed = false, active = true, frame = 0, frameCount = 0, width = 0, height = 0;
  let fitDistance = 18, zoom = 1, cameraFitted = false, extentX = 5, extentY = 4, selectedId = null, hoveredId = null;
  let dragging = false, dragged = false, lastX = 0, lastY = 0, orbitElapsed = 0, wallElapsed = 0, previousTime = 0;
  let signature = null, updateCount = 0, globalExplode = 0;
  let currentSolarState = normalizeSolarState(solarState), solarToken = currentSolarState.token, solarInitialized = false, solarLifecycle = null;
  const projected = new THREE.Vector3(), pointer = new THREE.Vector2(), raycaster = new THREE.Raycaster();
  const lensWorld = new THREE.Vector3(), lensView = new THREE.Vector3(), lensScreen = new THREE.Vector3();
  const generation = ++rendererGeneration;
  container.dataset.graphRendererGeneration = String(generation); container.dataset.graphUpdateCount = "0";

  function attachAsset(visual, key, uniforms, special = "") {
    const version = (visual.userData.assetVersion || 0) + 1; visual.userData.assetVersion = version;
    const textures = special === "sun" ? visualTextureLibrary.loadSun() : Promise.resolve(null);
    Promise.all([assetLibrary.load(key), textures]).then(([asset, visualTextures]) => {
      if (disposed || visual.userData.assetVersion !== version || !visual.parent) return;
      clearVisual(visual);
      const instance = instantiateAsset(asset, key, uniforms, special, visualTextures);
      visual.add(instance); visual.userData.interiorShardLayer = instance.getObjectByName("InteriorShardLayer") || null;
      uniforms.cloudRadius.value = asset.radius * 0.65;
      container.dataset.graphAssetCount = String(assetLibrary.size);
    }).catch(() => { container.dataset.graphAssetFallback = "true"; });
  }

  function placeholderVisual(color) {
    const mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 3), new THREE.MeshStandardMaterial({ color, roughness: 0.82 }));
    mesh.userData.placeholder = true; return mesh;
  }

  function createSpecialBody(key, radius, position, label, special) {
    const group = new THREE.Group(); group.position.copy(position);
    const visual = new THREE.Group(); visual.scale.setScalar(radius); visual.add(placeholderVisual(special === "sun" ? 0xffaa4d : 0xbdeeff));
    group.add(visual); graphLayer.add(group);
    let halo = null, light = null;
    if (special === "sun") {
      halo = createSunHalo(); group.add(halo);
      light = new THREE.PointLight(0xffc896, 165, 90, 1.4); group.add(light);
    } else if (special === "white") {
      light = new THREE.PointLight(0xc7f2ff, 4.5, 4.2, 1.5); group.add(light);
    }
    const node = { id: special, kind: special, label, statusLabel: special === "sun" ? "任务核心" : "回收出口" };
    const specialUniforms = { explode: { value: 0 }, time: { value: 0 }, cloudRadius: { value: 0 }, brightness: { value: 1 },
      evolution: { value: 0 }, collapse: { value: 0 } };
    group.userData = { node, radius, currentScale: radius, visual, halo, light, specialUniforms, label: createLabel(labelLayer, node), special };
    attachAsset(visual, key, specialUniforms, special);
    if (special === "sun") {
      prominenceSystem = createProminenceSystem(group, camera, prominenceLibrary);
      solarEffects = createSolarFinaleEffects(group);
    }
    return group;
  }

  function createConnection(group) {
    const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(29 * 3), 3));
    const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
    line.visible = false; graphLayer.add(line);
    const particles = Array.from({ length: 3 }, (_, index) => {
      const particle = new THREE.Mesh(new THREE.SphereGeometry(0.04, 8, 6), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.88, depthWrite: false }));
      particle.userData.offset = index / 3; particle.visible = false; graphLayer.add(particle); return particle;
    });
    const edge = { group, line, particles, curve: new THREE.QuadraticBezierCurve3(), label: createLabel(labelLayer, group.userData.node, true), phase: textSeed(group.userData.node.id, 511) * Math.PI * 2 };
    edges.push(edge); group.userData.edge = edge; return edge;
  }

  function registerTask(node, index, count) {
    const planet = PLANET_SPECS[node.planetKey] || PLANET_SPECS["timber-hearth"];
    const displayRadius = planetDisplayRadius(planet);
    const orbit = createOrbitSpec(node.id, index, count, planet.comet, node.planetKey, node.planetSequence);
    const group = new THREE.Group(), visual = new THREE.Group();
    const uniforms = { explode: { value: node.shattered ? 1 : 0 }, time: { value: 0 }, cloudRadius: { value: 0.65 }, brightness: { value: node.shattered ? 0.9 : node.working ? 1 : 0.55 } };
    visual.add(placeholderVisual(planet.color)); group.add(visual);
    const hitMesh = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }));
    hitMesh.userData.graphNode = node; group.add(hitMesh);
    const targetScale = displayRadius * planetScale(node);
    visual.scale.setScalar(targetScale);
    hitMesh.scale.setScalar(node.shattered ? Math.max(0.675, displayRadius * 3.375) : Math.max(0.33, targetScale));
    group.position.copy(orbitPoint(orbit, orbitElapsed));
    group.userData = { node, orbit, radius: planet.radius, displayRadius, visual, hitMesh, uniforms, currentScale: targetScale, targetScale,
      currentBrightness: uniforms.brightness.value, targetBrightness: uniforms.brightness.value,
      label: createLabel(labelLayer, node), lifecycle: null, recycled: false };
    graphLayer.add(group); nodeGroups.push(group); pickables.push(hitMesh); createConnection(group);
    attachAsset(visual, node.planetKey || "timber-hearth", uniforms);
    const age = node.rebirthAt ? Math.max(0, (Date.now() - node.rebirthAt) / 1000) : Infinity;
    if (age < 3) { group.userData.lifecycle = { type: "eject", start: wallElapsed - age, duration: 1.8 }; group.userData.currentScale = 0.001; visual.scale.setScalar(0.001); group.position.copy(whiteHoleGroup.position); }
    extentX = Math.max(extentX, orbit.semiMajor * (1 + orbit.eccentricity) + displayRadius * 3.6);
    extentY = Math.max(extentY, orbit.semiMinor + displayRadius * 3.6);
    return group;
  }

  function disposeGraphLayer() {
    prominenceSystem?.dispose(); prominenceSystem = null;
    solarEffects?.dispose(); solarEffects = null;
    nodeGroups.forEach((group) => { group.userData.disposed = true; });
    [...graphLayer.children].forEach(disposeDynamicObject); graphLayer.clear();
    nodeGroups.length = edges.length = pickables.length = 0;
  }

  function rebuildScene() {
    disposeGraphLayer(); labelLayer.replaceChildren(); extentX = 5; extentY = 4;
    const threads = nodes.filter((node) => node.kind === "thread");
    threads.forEach((node, index) => {
      const planet = PLANET_SPECS[node.planetKey] || PLANET_SPECS["timber-hearth"];
      const displayRadius = planetDisplayRadius(planet);
      const orbit = createOrbitSpec(node.id, index, threads.length, planet.comet, node.planetKey, node.planetSequence);
      extentX = Math.max(extentX, orbit.semiMajor * (1 + orbit.eccentricity) + displayRadius * 3.6);
      extentY = Math.max(extentY, orbit.semiMinor + displayRadius * 3.6);
    });
    sunGroup = createSpecialBody("sun", SUN_RADIUS, new THREE.Vector3(), "太阳", "sun");
    whiteHoleGroup = createSpecialBody("white-hole", 0.16, new THREE.Vector3(-extentX * 0.72, extentY * 0.46, -0.35), "白洞", "white");
    threads.forEach((node, index) => registerTask(node, index, threads.length));
    container.dataset.graphNodeCount = String(threads.length);
    container.dataset.graphCloudCount = String(threads.filter((node) => node.shattered).length);
  }

  function recalculateExtents() {
    extentX = 5; extentY = 4;
    nodeGroups.forEach((group) => {
      const { orbit, displayRadius } = group.userData;
      extentX = Math.max(extentX, orbit.semiMajor * (1 + orbit.eccentricity) + displayRadius * 3.6);
      extentY = Math.max(extentY, orbit.semiMinor + displayRadius * 3.6);
    });
    if (whiteHoleGroup) whiteHoleGroup.position.set(-extentX * 0.72, extentY * 0.46, -0.35);
  }

  function updateNode(group, node, index, count) {
    const previous = group.userData.node;
    const planetChanged = previous.planetKey !== node.planetKey || previous.planetSequence !== node.planetSequence;
    group.userData.node = node; group.userData.hitMesh.userData.graphNode = node;
    if (planetChanged) {
      const planet = PLANET_SPECS[node.planetKey] || PLANET_SPECS["timber-hearth"];
      group.userData.radius = planet.radius;
      group.userData.displayRadius = planetDisplayRadius(planet);
      group.userData.orbit = createOrbitSpec(node.id, index, count, planet.comet, node.planetKey, node.planetSequence);
      attachAsset(group.userData.visual, node.planetKey || "timber-hearth", group.userData.uniforms);
      if (!group.userData.lifecycle || group.userData.lifecycle.type !== "absorbing") {
        group.userData.lifecycle = reducedMotion ? null : {
          type: "relocate", start: wallElapsed, duration: 1.1, from: group.position.clone(),
        };
      }
    }
    if (node.shattered && (!previous.shattered || previous.completionToken !== node.completionToken)) {
      group.userData.uniforms.explode.value = reducedMotion ? 1 : 0;
      group.userData.lifecycle = reducedMotion ? null : { type: "explode", start: wallElapsed, duration: 1.65 };
    }
    if (!node.shattered && previous.shattered && group.userData.lifecycle?.type !== "eject") group.userData.uniforms.explode.value = 0;
    const rebirthAge = node.rebirthAt ? Math.max(0, (Date.now() - node.rebirthAt) / 1000) : Infinity;
    if (!node.shattered && node.rebirthAt !== previous.rebirthAt && rebirthAge < 3) {
      group.userData.lifecycle = reducedMotion ? null : { type: "eject", start: wallElapsed - rebirthAge, duration: 1.8 };
      group.userData.currentScale = reducedMotion ? group.userData.displayRadius * PLANET_SCALE.idle : 0.001;
      group.userData.visual.scale.setScalar(Math.max(0.001, group.userData.currentScale));
      group.position.copy(whiteHoleGroup.position); group.userData.recycled = false;
    }
    group.userData.targetScale = group.userData.displayRadius * planetScale(node);
    group.userData.targetBrightness = node.shattered ? 0.9 : node.working ? 1 : 0.55;
    setLabelText(group.userData.label, node.label, node.working ? "" : node.statusLabel);
    setLabelText(group.userData.edge.label, edgeLabel(node));
    return planetChanged;
  }

  function selectNode(node) {
    selectedId = node && selectedId !== node.id ? node.id : null;
    onNodeSelect?.(selectedId ? node : null); container.dataset.selectedNode = selectedId || "";
  }

  function updateSolarState(nextValue) {
    const next = normalizeSolarState(nextValue);
    if (!solarInitialized) {
      currentSolarState = next; solarToken = next.token; solarInitialized = true;
      globalExplode = next.mode === "destroyed" ? 1 : 0; return;
    }
    if (next.token !== solarToken) {
      const previousMode = currentSolarState.mode;
      if (!reducedMotion && next.event === "work-ended") {
        solarLifecycle = { type: "finale", start: wallElapsed, duration: 8,
          fromScale: sunGroup?.userData.currentScale || SUN_RADIUS, fromProgress: currentSolarState.dayProgress };
      } else if (!reducedMotion && next.event === "work-started" && previousMode === "destroyed") {
        solarLifecycle = { type: "rewind", start: wallElapsed, duration: 8 };
      } else solarLifecycle = null;
      solarToken = next.token;
    }
    currentSolarState = next;
  }

  function currentDayProgress() {
    const elapsed = Math.max(0, Date.now() - currentSolarState.sampledAt);
    const offset = (currentSolarState.cycleOffsetMs + elapsed) % SOLAR_DAY_MS;
    return offset < SOLAR_CYCLE_MS ? THREE.MathUtils.clamp(offset / SOLAR_CYCLE_MS, 0, 1) : 0;
  }

  function updateSolarCycle(delta) {
    if (!sunGroup) return;
    const dayProgress = currentDayProgress(), targetScale = SUN_RADIUS * (1 + dayProgress * 0.5);
    let scale = targetScale, evolution = dayProgress, collapse = 0, blast = 0, visible = true;
    if (solarLifecycle?.type === "finale") {
      const progress = THREE.MathUtils.clamp((wallElapsed - solarLifecycle.start) / solarLifecycle.duration, 0, 1);
      if (progress < 0.28) {
        const phase = easeInOut(progress / 0.28);
        scale = THREE.MathUtils.lerp(solarLifecycle.fromScale, SUN_RADIUS * 1.5, phase);
        evolution = THREE.MathUtils.lerp(solarLifecycle.fromProgress, 1, phase);
      } else if (progress < 0.5) {
        const phase = (progress - 0.28) / 0.22;
        scale = THREE.MathUtils.lerp(SUN_RADIUS * 1.5, SUN_RADIUS * 0.1, phase * phase);
        evolution = 1; collapse = phase;
      } else {
        const phase = easeInOut((progress - 0.5) / 0.5);
        scale = SUN_RADIUS * 0.1; evolution = 1; collapse = 1; blast = phase;
        visible = phase < 0.12; globalExplode = easeInOut((phase - 0.04) / 0.72);
      }
      if (progress >= 1) { solarLifecycle = null; globalExplode = 1; visible = false; }
    } else if (solarLifecycle?.type === "rewind") {
      const progress = THREE.MathUtils.clamp((wallElapsed - solarLifecycle.start) / solarLifecycle.duration, 0, 1);
      globalExplode = 1 - easeInOut(progress / 0.55);
      if (progress < 0.3) {
        blast = 1 - easeInOut(progress / 0.3); scale = SUN_RADIUS * 0.1; evolution = 1; collapse = 1;
        visible = progress > 0.13;
      } else if (progress < 0.62) {
        const phase = (progress - 0.3) / 0.32;
        scale = THREE.MathUtils.lerp(SUN_RADIUS * 1.5, SUN_RADIUS * 0.1, (1 - phase) * (1 - phase));
        evolution = 1; collapse = 1 - phase;
      } else {
        const phase = easeInOut((progress - 0.62) / 0.38);
        scale = THREE.MathUtils.lerp(SUN_RADIUS * 1.5, targetScale, phase);
        evolution = THREE.MathUtils.lerp(1, dayProgress, phase);
      }
      if (progress >= 1) { solarLifecycle = null; globalExplode = 0; scale = targetScale; evolution = dayProgress; }
    } else if (currentSolarState.mode === "destroyed") {
      scale = SUN_RADIUS * 0.1; evolution = 1; collapse = 1; visible = false; globalExplode = 1;
    } else globalExplode = 0;
    sunGroup.userData.currentScale = scale; sunGroup.userData.visual.visible = visible;
    if (sunGroup.userData.light) sunGroup.userData.light.intensity = visible ? 165 * (1 + evolution * 0.18) : 0;
    sunGroup.userData.visual.scale.setScalar(scale);
    if (sunGroup.userData.halo) { sunGroup.userData.halo.visible = visible; sunGroup.userData.halo.scale.setScalar(scale / SUN_RADIUS); }
    sunGroup.userData.specialUniforms.evolution.value = evolution;
    sunGroup.userData.specialUniforms.collapse.value = collapse;
    prominenceSystem?.update(delta, evolution, visible && collapse < 0.15 && blast < 0.01);
    if (prominenceSystem) prominenceSystem.group.scale.setScalar(scale / SUN_RADIUS);
    solarEffects?.update(blast);
    container.dataset.graphSolarMode = solarLifecycle?.type || currentSolarState.mode;
    container.dataset.graphSolarProgress = dayProgress.toFixed(4);
    container.dataset.graphGlobalExplode = globalExplode.toFixed(4);
  }

  function update({ nodes: nextNodes, solarState: nextSolarState = currentSolarState, reducedMotion: nextMotion = reducedMotion }) {
    if (disposed) return false; reducedMotion = nextMotion;
    updateSolarState(nextSolarState);
    nodes = [...nextNodes].sort((left, right) => left.id.localeCompare(right.id));
    const nextSignature = JSON.stringify(nodes.map((node) => [node.id, node.kind]));
    if (nextSignature !== signature) { rebuildScene(); signature = nextSignature; resize(true); }
    const byId = new Map(nodes.map((node) => [node.id, node]));
    let assignmentChanged = false;
    nodeGroups.forEach((group, index) => {
      const node = byId.get(group.userData.node.id);
      if (node) assignmentChanged = updateNode(group, node, index, nodeGroups.length) || assignmentChanged;
    });
    if (assignmentChanged) { recalculateExtents(); resize(false); }
    updateCount += 1; container.dataset.graphUpdateCount = String(updateCount);
    container.dataset.graphCloudCount = String(nodes.filter((node) => node.shattered).length);
    if (selectedId) { const selected = byId.get(selectedId); if (!selected) selectedId = null; onNodeSelect?.(selected || null); container.dataset.selectedNode = selectedId || ""; }
    return true;
  }

  function resize(forceFit = false) {
    if (disposed) return;
    const rect = container.getBoundingClientRect(), nextWidth = Math.max(1, Math.floor(rect.width)), nextHeight = Math.max(1, Math.floor(rect.height));
    const ratio = Math.min(window.devicePixelRatio || 1, 1.45);
    if (width !== nextWidth || height !== nextHeight || renderer.getPixelRatio() !== ratio) {
      width = nextWidth; height = nextHeight; if (renderer.getPixelRatio() !== ratio) renderer.setPixelRatio(ratio); renderer.setSize(width, height, false);
      mainTarget.setSize(Math.max(1, Math.floor(width * ratio)), Math.max(1, Math.floor(height * ratio)));
      lensing.material.uniforms.uResolution.value.set(width, height);
    }
    camera.aspect = width / height; camera.fov = width < 560 ? 49 : 42;
    const tangent = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const previousFit = fitDistance, currentDistance = camera.position.distanceTo(controls.target);
    fitDistance = Math.max(10, extentY / tangent, extentX / (tangent * camera.aspect)) + 1.2;
    const direction = camera.position.clone().sub(controls.target);
    if (direction.lengthSq() < 0.001) direction.set(0.56, 0.42, 0.71);
    direction.normalize();
    const relativeZoom = cameraFitted ? THREE.MathUtils.clamp(currentDistance / Math.max(previousFit, 0.001), 0.48, 1.65) : 1;
    controls.minDistance = fitDistance * 0.34; controls.maxDistance = fitDistance * 2.25;
    if (!cameraFitted || forceFit) camera.position.copy(controls.target).addScaledVector(direction, fitDistance * relativeZoom);
    else if (currentDistance < controls.minDistance || currentDistance > controls.maxDistance) {
      camera.position.copy(controls.target).addScaledVector(direction, THREE.MathUtils.clamp(currentDistance, controls.minDistance, controls.maxDistance));
    }
    cameraFitted = true; zoom = camera.position.distanceTo(controls.target) / fitDistance;
    camera.far = Math.max(180, fitDistance * 4.2); camera.updateProjectionMatrix(); controls.handleResize(); controls.update();
  }

  function updatePointer(event) {
    const rect = canvas.getBoundingClientRect();
    pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    lensing.material.uniforms.uPointer.value.set(pointer.x * 0.5 + 0.5, pointer.y * 0.5 + 0.5);
    lensing.material.uniforms.uPointerActive.value = 1;
    return pointer;
  }

  function pointerWorldAtNode(event, node) {
    updatePointer(event); raycaster.setFromCamera(pointer, camera);
    const group = nodeGroups.find((candidate) => candidate.userData.node.id === node?.id);
    const anchor = group?.getWorldPosition(new THREE.Vector3()) || controls.target;
    const normal = camera.getWorldDirection(new THREE.Vector3());
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, anchor);
    const world = raycaster.ray.intersectPlane(plane, new THREE.Vector3()) || anchor.clone();
    return root.worldToLocal(world);
  }

  function pickedNode(event) {
    updatePointer(event); raycaster.setFromCamera(pointer, camera);
    return raycaster.intersectObjects(pickables, false)[0]?.object?.userData?.graphNode || null;
  }

  function beginAbsorptionAt(node, target) {
    const group = nodeGroups.find((candidate) => candidate.userData.node.id === node.id);
    if (!group || !node.shattered || group.userData.lifecycle?.type === "absorbing") return;
    group.userData.lifecycle = { type: "absorbing", start: wallElapsed, duration: reducedMotion ? 0.01 : 1.05,
      from: group.position.clone(), target };
    group.userData.recycled = false; selectNode(null);
  }

  function beginAbsorption(node, event) {
    root.updateMatrixWorld(true);
    beginAbsorptionAt(node, pointerWorldAtNode(event, node));
  }

  function onPointerDown(event) {
    if ((event.button ?? 0) !== 0) return;
    canvas.focus({ preventScroll: true }); dragging = true; dragged = false; lastX = event.clientX; lastY = event.clientY;
    canvas.setPointerCapture?.(event.pointerId);
  }
  function onPointerMove(event) {
    updatePointer(event);
    if (!dragging) { hoveredId = pickedNode(event)?.id || null; canvas.style.cursor = "none"; return; }
    const dx = event.clientX - lastX, dy = event.clientY - lastY;
    if (Math.abs(dx) + Math.abs(dy) > 2) dragged = true;
    lastX = event.clientX; lastY = event.clientY;
  }
  function onPointerUp(event) {
    if ((event.button ?? 0) !== 0) return;
    if (!dragged) selectNode(pickedNode(event));
    dragging = false;
    canvas.releasePointerCapture?.(event.pointerId);
  }
  function onPointerCancel(event) { dragging = false; canvas.releasePointerCapture?.(event.pointerId); }
  function onPointerLeave() { hoveredId = null; lensing.material.uniforms.uPointerActive.value = 0; canvas.style.cursor = "grab"; }
  function onContextMenu(event) {
    event.preventDefault();
    const node = pickedNode(event);
    container.dataset.graphLastContextNode = node?.id || "";
    updatePointer(event);
    if (node?.shattered) {
      container.dataset.graphLastRecycleRequest = node.id;
      beginAbsorption(node, event);
    }
  }
  function onKeyDown(event) { if (event.key === "Escape") selectNode(null); }

  function project(point) {
    projected.copy(point).applyMatrix4(root.matrixWorld).project(camera);
    return { x: (projected.x * 0.5 + 0.5) * width, y: (-projected.y * 0.5 + 0.5) * height, z: projected.z };
  }

  function placeLabels() {
    const occupied = [];
    const entries = [sunGroup, whiteHoleGroup, ...nodeGroups].filter(Boolean).sort((left, right) => {
      const priority = (group) => group.userData.node.id === selectedId ? 0 : group.userData.special === "sun" ? 1 : group.userData.node.shattered ? 2 : 3;
      return priority(left) - priority(right);
    });
    function positionLabel(element, point, important = false) {
      if (!element) return;
      const w = element.offsetWidth || 90, h = element.offsetHeight || 28;
      let chosen = null;
      for (const offset of [-14, 18, -42, 44]) {
        const x = THREE.MathUtils.clamp(point.x - w / 2, 5, Math.max(5, width - w - 5));
        const y = THREE.MathUtils.clamp(point.y + offset - (offset < 0 ? h : 0), 4, height - h - 22);
        const rect = { x, y, w, h };
        if (!occupied.some((other) => rect.x < other.x + other.w + 8 && rect.x + rect.w + 8 > other.x && rect.y < other.y + other.h + 5 && rect.y + rect.h + 5 > other.y)) { chosen = rect; break; }
      }
      element.style.visibility = chosen && point.z < 1 ? "visible" : "hidden";
      if (!chosen) return;
      element.style.transform = `translate3d(${chosen.x.toFixed(1)}px, ${chosen.y.toFixed(1)}px, 0)`;
      element.style.opacity = important ? "1" : "0.82"; occupied.push(chosen);
    }
    entries.forEach((group) => {
      const radius = group.userData.currentScale || group.userData.radius || 0.2;
      const node = group.userData.node;
      const visible = Boolean(group.userData.special || node.working || node.shattered || node.id === selectedId || node.id === hoveredId);
      if (!visible) { group.userData.label.style.visibility = "hidden"; return; }
      positionLabel(group.userData.label, project(group.position.clone().add(new THREE.Vector3(0, radius, 0))),
        group.userData.special === "sun" || node.id === selectedId || node.working || node.shattered);
    });
    edges.forEach((edge) => {
      edge.label.style.visibility = edge.line.visible ? "visible" : "hidden";
      if (!edge.line.visible) return;
      const emphasize = edge.group.userData.node.id === selectedId || edge.group.userData.node.id === hoveredId;
      edge.label.classList.toggle("is-emphasized", emphasize); positionLabel(edge.label, project(edge.curve.getPoint(0.68)), emphasize);
    });
  }

  function updateConnection(edge) {
    const data = edge.group.userData, node = data.node;
    const enabled = Boolean(node.working && !node.shattered && data.lifecycle?.type !== "eject" && data.lifecycle?.type !== "absorbing");
    edge.line.visible = enabled; edge.particles.forEach((particle) => { particle.visible = enabled; }); edge.label.style.visibility = enabled ? "visible" : "hidden";
    if (!enabled) return;
    const color = effortColor(node.effort); edge.line.material.color.setHex(color);
    edge.curve.v0.copy(sunGroup.position); edge.curve.v2.copy(edge.group.position); edge.curve.v1.copy(sunGroup.position).lerp(edge.group.position, 0.5);
    const normal = edge.group.position.clone().cross(new THREE.Vector3(0.31, 1, 0.23));
    if (normal.lengthSq() > 0.001) edge.curve.v1.add(normal.normalize().multiplyScalar(Math.min(1.2, edge.group.position.length() * 0.055)));
    const attribute = edge.line.geometry.attributes.position;
    for (let step = 0; step < attribute.count; step += 1) { const p = edge.curve.getPoint(step / (attribute.count - 1)); attribute.setXYZ(step, p.x, p.y, p.z); }
    attribute.needsUpdate = true;
    edge.line.material.opacity = 0.14 + (0.5 + 0.5 * Math.sin(wallElapsed * 1.7 + edge.phase)) * 0.28;
    edge.particles.forEach((particle) => { particle.material.color.setHex(color); particle.position.copy(edge.curve.getPoint((wallElapsed * 0.18 + particle.userData.offset) % 1)); });
    setLabelText(edge.label, edgeLabel(node)); edge.label.style.setProperty("--effort-color", `#${new THREE.Color(color).getHexString()}`);
  }

  function updateTask(group, delta) {
    const data = group.userData, node = data.node, position = orbitPoint(data.orbit, orbitElapsed);
    const explodeTarget = Math.max(node.shattered ? 1 : 0, globalExplode);
    let scaleMultiplier = 1;
    if (data.lifecycle?.type === "explode") {
      const progress = easeInOut((wallElapsed - data.lifecycle.start) / data.lifecycle.duration); data.uniforms.explode.value = progress;
      if (progress >= 1) data.lifecycle = null;
    } else if (data.lifecycle?.type === "absorbing") {
      const progress = easeInOut((wallElapsed - data.lifecycle.start) / data.lifecycle.duration);
      group.position.lerpVectors(data.lifecycle.from, data.lifecycle.target, progress); scaleMultiplier = 1 - progress;
      if (progress >= 1 && !data.recycled) {
        data.recycled = true;
        Promise.resolve(onNodeRecycle?.(node)).then((accepted) => {
          if (accepted === false && !data.disposed) { data.lifecycle = null; data.recycled = false; data.uniforms.explode.value = 1; }
        }).catch(() => { if (!data.disposed) { data.lifecycle = null; data.recycled = false; } });
      }
    } else if (data.lifecycle?.type === "eject") {
      const progress = easeInOut((wallElapsed - data.lifecycle.start) / data.lifecycle.duration);
      const start = whiteHoleGroup.position, control = start.clone().lerp(position, 0.46).add(new THREE.Vector3(0, 2.1, 1.1));
      quadraticPoint(start, control, position, progress, group.position); data.currentScale = data.displayRadius * PLANET_SCALE.idle * progress;
      if (progress >= 1) data.lifecycle = null;
    } else if (data.lifecycle?.type === "relocate") {
      const progress = easeInOut((wallElapsed - data.lifecycle.start) / data.lifecycle.duration);
      group.position.lerpVectors(data.lifecycle.from, position, progress);
      if (progress >= 1) data.lifecycle = null;
    } else {
      group.position.copy(position); data.uniforms.explode.value += (explodeTarget - data.uniforms.explode.value) * Math.min(1, delta * 7);
    }
    if (data.lifecycle?.type !== "eject") data.currentScale += (data.targetScale - data.currentScale) * Math.min(1, delta * 5.5);
    data.currentBrightness += (data.targetBrightness - data.currentBrightness) * Math.min(1, delta * 5);
    data.uniforms.brightness.value = data.currentBrightness; data.uniforms.time.value = wallElapsed;
    const interior = data.visual.userData.interiorShardLayer;
    if (interior) {
      const amount = THREE.MathUtils.smoothstep(data.uniforms.explode.value, 0, 1);
      interior.visible = amount > 0.015;
      interior.scale.setScalar(0.12 + amount * 1.22);
      if (!reducedMotion) { interior.rotation.y += delta * 0.045 * amount; interior.rotation.x += delta * 0.012 * amount; }
    }
    data.visual.scale.setScalar(Math.max(0.001, data.currentScale * scaleMultiplier));
    const hitRadius = node.shattered ? Math.max(0.675, data.displayRadius * 3.375) : Math.max(0.33, data.currentScale);
    data.hitMesh.scale.setScalar(Math.max(0.001, hitRadius * scaleMultiplier));
    if (!reducedMotion && !selectedId) data.visual.rotation.y += delta * (node.shattered ? 0.09 : 0.035);
    updateConnection(data.edge);
  }

  function updateSunStatus() {
    if (!sunGroup) return;
    const status = solarLifecycle?.type === "finale" ? "恒星终局"
      : solarLifecycle?.type === "rewind" ? "时间回溯"
        : currentSolarState.mode === "destroyed" ? "等待下一次上班"
          : sunActivityLabel(nodeGroups);
    sunGroup.userData.node.statusLabel = status;
    setLabelText(sunGroup.userData.label, sunGroup.userData.node.label, status);
    container.dataset.graphSunStatus = status;
  }

  function updateLensAnchor(group, radius, uniform) {
    if (!group || !width || !height) { uniform.value.z = 0; return; }
    group.getWorldPosition(lensWorld); lensView.copy(lensWorld).applyMatrix4(camera.matrixWorldInverse);
    lensScreen.copy(lensWorld).project(camera);
    if (lensView.z >= -camera.near || Math.abs(lensScreen.x) > 1.15 || Math.abs(lensScreen.y) > 1.15) {
      uniform.value.z = 0; return;
    }
    const radiusPx = radius * height / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * -lensView.z);
    uniform.value.set(lensScreen.x * 0.5 + 0.5, lensScreen.y * 0.5 + 0.5,
      group === whiteHoleGroup ? THREE.MathUtils.clamp(radiusPx * 1.45, 3.2, 18) : Math.max(1, radiusPx));
  }

  function updateLensingAnchors() {
    camera.updateMatrixWorld(); root.updateMatrixWorld(true);
    updateLensAnchor(whiteHoleGroup, 0.16, lensing.material.uniforms.uWhiteHole);
    updateLensAnchor(sunGroup, sunGroup?.userData.currentScale || SUN_RADIUS, lensing.material.uniforms.uSun);
  }

  function renderOnce(delta = 0) {
    if (disposed) return false;
    wallElapsed += delta; if (!reducedMotion) orbitElapsed += delta;
    controls.update(); zoom = camera.position.distanceTo(controls.target) / fitDistance;
    updateSolarCycle(delta);
    nodeGroups.forEach((group) => updateTask(group, delta));
    updateSunStatus();
    [sunGroup, whiteHoleGroup].forEach((group) => group?.userData.visual?.traverse((object) => {
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.filter(Boolean).forEach((material) => {
        if (material.uniforms?.time) material.uniforms.time.value = wallElapsed;
      });
    }));
    updateLensingAnchors(); renderer.setRenderTarget(mainTarget); renderer.render(scene, camera);
    renderer.setRenderTarget(null); renderer.render(lensing.scene, lensing.camera); placeLabels();
    container.dataset.graphReady = "true";
    container.dataset.graphControls = "free-trackball"; container.dataset.graphLensing = "screen-space";
    container.dataset.graphNodePositions = JSON.stringify(nodeGroups.map((group) => ({
      id: group.userData.node.id,
      ...project(group.position),
    })));
    container.dataset.graphNodeStates = JSON.stringify(nodeGroups.map((group) => ({
      id: group.userData.node.id,
      planetKey: group.userData.node.planetKey,
      working: group.userData.node.working,
      shattered: group.userData.node.shattered,
      radius: group.userData.radius,
      displayRadius: group.userData.displayRadius,
      scale: group.userData.currentScale,
      brightness: group.userData.currentBrightness,
      explode: group.userData.uniforms.explode.value,
      interiorShards: group.userData.visual.userData.interiorShardLayer?.userData.count || 0,
      interiorCoreShards: group.userData.visual.userData.interiorShardLayer?.userData.coreCount || 0,
      fragmentStyle: group.userData.visual.userData.interiorShardLayer?.userData.style || "",
      lifecycle: group.userData.lifecycle?.type || "",
    })));
    container.dataset.graphActiveLinks = String(edges.filter((edge) => edge.line.visible).length);
    container.dataset.graphGeometryCount = String(renderer.info.memory.geometries);
    container.dataset.graphTextureCount = String(renderer.info.memory.textures);
    frameCount += 1; return true;
  }

  function animate(now) {
    frame = 0; if (disposed || !active) return;
    const delta = Math.min(0.05, previousTime ? (now - previousTime) / 1000 : 0); previousTime = now;
    renderOnce(delta); frame = requestAnimationFrame(animate);
  }
  function setActive(value) {
    if (disposed) return; active = Boolean(value);
    if (!active) { cancelAnimationFrame(frame); frame = 0; previousTime = 0; }
    else if (!frame) frame = requestAnimationFrame(animate);
  }

  function dispose() {
    if (disposed) return; disposed = true; active = false; cancelAnimationFrame(frame); resizeObserver?.disconnect();
    bindings.forEach(([type, listener, options]) => canvas.removeEventListener(type, listener, options)); labelLayer?.remove();
    controls.dispose(); disposeGraphLayer();
    scene.traverse((object) => {
      if (object.parent === graphLayer) return;
      if (object.geometry && !object.geometry.userData?.outerWildsShared) object.geometry.dispose?.();
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.filter(Boolean).forEach((material) => material.dispose?.());
    });
    lensing.quad.geometry.dispose(); lensing.material.dispose(); mainTarget.dispose();
    assetLibrary.dispose(); visualTextureLibrary.dispose(); prominenceLibrary.dispose(); renderer.dispose(); renderer.forceContextLoss(); canvas.width = 1; canvas.height = 1;
    renderer.info.memory.geometries = 0; renderer.info.memory.textures = 0; root.clear(); scene.clear(); nodes = []; selectedId = null;
    container.dataset.graphDisposed = "true";
  }

  try {
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.45)); renderer.setClearColor(0x010407, 1);
    renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.2;
    scene.add(new THREE.HemisphereLight(0xdce9f0, 0x10191a, 1.72)); scene.add(createStarfield());
    labelLayer = document.createElement("div"); labelLayer.className = "graph-space-labels"; labelLayer.setAttribute("aria-hidden", "true"); container.append(labelLayer);
    canvas.tabIndex = 0;
    for (const [type, listener, options] of [["pointerdown", onPointerDown], ["pointermove", onPointerMove], ["pointerup", onPointerUp], ["pointercancel", onPointerCancel], ["pointerleave", onPointerLeave], ["contextmenu", onContextMenu], ["keydown", onKeyDown]]) {
      canvas.addEventListener(type, listener, options); bindings.push([type, listener, options]);
    }
    update({ nodes, reducedMotion }); resizeObserver = new ResizeObserver(resize); resizeObserver.observe(container); setActive(true);
    return {
      renderer, scene, camera, update, setActive, renderOnce,
      getSelectedNode: () => nodes.find((node) => node.id === selectedId) || null,
      selectNode: (id) => selectNode(nodes.find((node) => node.id === id) || null),
      recycleNode(id) {
        const group = nodeGroups.find((candidate) => candidate.userData.node.id === id);
        if (!group?.userData.node.shattered) return false;
        beginAbsorptionAt(group.userData.node, new THREE.Vector3());
        return true;
      },
      clearSelection() { selectedId = null; container.dataset.selectedNode = ""; onNodeSelect?.(null); },
      getDiagnostics() {
        return { nodes: nodes.length, selectedId, orbitElapsed, wallElapsed, active, disposed, frameCount, sunRadius: SUN_RADIUS,
          solarMode: solarLifecycle?.type || currentSolarState.mode, solarProgress: currentDayProgress(), globalExplode,
          sunScale: sunGroup?.userData.currentScale || 0,
          rotation: camera.rotation.toArray(), camera: camera.position.toArray(), target: controls.target.toArray(), zoom,
          controls: "free-trackball", lensing: "screen-space",
          clouds: nodeGroups.filter((group) => group.userData.node.shattered).length,
          activeLinks: edges.filter((edge) => edge.line.visible).length,
          nodeStates: nodeGroups.map((group) => ({
            id: group.userData.node.id,
            planetKey: group.userData.node.planetKey,
            shattered: group.userData.node.shattered,
            working: group.userData.node.working,
            scale: group.userData.currentScale,
            brightness: group.userData.currentBrightness,
            explode: group.userData.uniforms.explode.value,
            interiorShards: group.userData.visual.userData.interiorShardLayer?.userData.count || 0,
            interiorCoreShards: group.userData.visual.userData.interiorShardLayer?.userData.coreCount || 0,
            fragmentStyle: group.userData.visual.userData.interiorShardLayer?.userData.style || "",
            lifecycle: group.userData.lifecycle?.type || "",
          })),
          geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures,
          programs: renderer.info.programs?.length || 0 };
      },
      dispose,
    };
  } catch (error) { dispose(); throw error; }
}
