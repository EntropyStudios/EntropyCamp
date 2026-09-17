import * as THREE from "./assets/vendor/three.module.js";

let rendererGeneration = 0;

const STATE_STYLE = {
  due: { radius: 0.68, color: 0xe6f5eb },
  processing: { radius: 0.34, color: 0x83c7ab },
  countdown: { radius: 0.3, color: 0x82bada },
  attention: { radius: 0.085, color: 0xa3bcc8 },
  idle: { radius: 0.075, color: 0x88969c },
  paused: { radius: 0.065, color: 0x6e7a81 },
};
const PLANET_COLORS = [0x88bea9, 0x6daabc, 0xc5a17b, 0xa3a4c3, 0xb9c399, 0xc68786];
const STAR_COLORS = [0xffce78, 0xffecd0, 0xffad65, 0xffda91];
const EFFORT_COLORS = {
  minimal: 0x5aa9ff, low: 0x5aa9ff, medium: 0x46d5d1,
  high: 0xa6d957, xhigh: 0xff9a4d, max: 0xef5b5b, ultra: 0xef5b5b,
};
const EFFORT_LABELS = {
  minimal: "最低", low: "低", medium: "中", high: "高",
  xhigh: "很高", max: "最高", ultra: "极高",
};

function effortColor(value) {
  return EFFORT_COLORS[String(value || "").toLowerCase()] || 0x89939c;
}

function effortLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return EFFORT_LABELS[normalized] || normalized.toUpperCase();
}

function textSeed(value, salt = 0) {
  let hash = 2166136261 + salt;
  for (const character of String(value || "")) hash = Math.imul(hash ^ character.charCodeAt(0), 16777619) >>> 0;
  return hash / 0xffffffff;
}

export function createOrbitSpec(id, index, count, comet = false) {
  const seed = textSeed(id);
  const semiMajor = comet ? 4.5 + seed * 1.7 : 1.65 + (index % 5) * 0.48 + Math.floor(index / 5) * 0.35;
  return {
    semiMajor,
    semiMinor: semiMajor * (comet ? 0.45 + seed * 0.16 : 0.72 + seed * 0.23),
    inclination: (textSeed(id, 83) - 0.5) * (comet ? 1.05 : 0.92),
    tilt: (textSeed(id, 337) - 0.5) * 0.62,
    phase: (index / Math.max(1, count)) * Math.PI * 2 + seed * 0.28,
    speed: (comet ? 0.006 : 0.016) / Math.sqrt(semiMajor) * (index % 2 ? -1 : 1),
    eccentricity: comet ? 0.34 : seed * 0.16,
  };
}

export function orbitPoint(spec, elapsed = 0, center = new THREE.Vector3()) {
  const angle = spec.phase + elapsed * spec.speed;
  return new THREE.Vector3(
    (Math.cos(angle) - spec.eccentricity) * spec.semiMajor,
    Math.sin(angle) * spec.semiMinor,
    0,
  ).applyEuler(new THREE.Euler(spec.inclination, spec.tilt, 0)).add(center);
}

function modelCenters(models) {
  if (models.length <= 1) return models.map(() => new THREE.Vector3());
  const columns = Math.ceil(Math.sqrt(models.length * 1.5));
  const rows = Math.ceil(models.length / columns);
  return models.map((node, index) => new THREE.Vector3(
    (index % columns - (Math.min(columns, models.length - Math.floor(index / columns) * columns) - 1) / 2) * 8.6,
    (Math.floor(index / columns) - (rows - 1) / 2) * -7.4,
    (textSeed(node.id) - 0.5) * 0.9,
  ));
}

function threadNodeSubtitle(node) {
  return node.statusLabel || "";
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

function threadEdgeLabel(node) {
  const effort = effortLabel(node.effort);
  return [node.phaseLabel, effort ? `推理${effort}` : "", runtimeLabel(node)].filter(Boolean).join(" · ");
}

function planetTexture(seed, color) {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 128;
  const context = canvas.getContext("2d");
  const image = context.createImageData(256, 128);
  const base = new THREE.Color(color);
  for (let y = 0; y < 128; y += 1) {
    for (let x = 0; x < 256; x += 1) {
      const longitude = x / 256 * Math.PI * 2;
      const latitude = y / 128 * Math.PI;
      const continents = Math.sin(longitude * 3 + Math.cos(latitude * 5 + seed * 12))
        + Math.sin(longitude * 7 - latitude * 6 + seed * 20) * 0.35;
      const bands = Math.sin(latitude * 23 + Math.sin(longitude * 2) * 0.35) * 0.08;
      const shade = 0.58 + (continents > 0.7 ? 0.3 : 0.05) + bands;
      const offset = (y * 256 + x) * 4;
      image.data[offset] = Math.min(255, base.r * 255 * shade);
      image.data[offset + 1] = Math.min(255, base.g * 255 * shade);
      image.data[offset + 2] = Math.min(255, base.b * 255 * shade);
      image.data[offset + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function starMaterial(color) {
  return new THREE.ShaderMaterial({
    uniforms: { time: { value: 0 }, starColor: { value: new THREE.Color(color) } },
    vertexShader: `varying vec3 vNormal; varying vec3 vPosition;
      void main() { vNormal = normalize(normalMatrix * normal); vPosition = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `varying vec3 vNormal; varying vec3 vPosition; uniform float time; uniform vec3 starColor;
      float turbulence(vec3 p) {
        float n = 0.0; float amplitude = 0.5;
        for (int i = 0; i < 4; i++) { n += amplitude * sin(p.x + sin(p.y) + cos(p.z)); p = p * 2.7 + 1.4; amplitude *= 0.5; }
        return n;
      }
      void main() {
        float plasma = turbulence(vPosition * 13.0 + vec3(time * 0.05, time * 0.02, 0.0));
        float rim = pow(1.0 - abs(vNormal.z), 2.0);
        vec3 hot = mix(starColor * 0.56, vec3(1.0, 0.97, 0.78), 0.46 + plasma * 0.35);
        gl_FragColor = vec4(hot + starColor * rim * 0.35, 1.0);
      }`,
  });
}

function createNode(node, index, resources) {
  const isModel = node.kind === "model";
  const style = STATE_STYLE[node.state] || STATE_STYLE.attention;
  const comet = !isModel && !node.modelId && !["processing", "due", "countdown"].includes(node.state);
  const radius = isModel ? 0.61 : style.radius * (comet ? 1 : 0.86 + textSeed(node.id) * 0.26);
  const color = isModel ? STAR_COLORS[Math.floor(textSeed(node.id) * STAR_COLORS.length)]
    : comet ? style.color : node.state === "due" ? style.color : PLANET_COLORS[index % PLANET_COLORS.length];
  const group = new THREE.Group();
  const material = isModel ? starMaterial(color) : new THREE.MeshStandardMaterial({
    color: comet ? color : 0xffffff,
    map: comet ? null : planetTexture(textSeed(node.id), color),
    roughness: 0.7, metalness: 0.05,
    emissive: comet ? color : node.state === "due" ? 0x728e7d : 0x000000,
    emissiveIntensity: comet ? 0.6 : node.state === "due" ? 0.33 : 0,
  });
  let effortRing = null;
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, comet ? 12 : 32, comet ? 8 : 20), material);
  group.add(mesh);
  if (isModel) {
    resources.starMaterials.push(material);
    group.add(new THREE.Mesh(new THREE.SphereGeometry(radius * 1.36, 32, 20), new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.BackSide,
      uniforms: { glowColor: { value: new THREE.Color(color) } },
      vertexShader: `varying vec3 vNormal; void main() { vNormal = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: `varying vec3 vNormal; uniform vec3 glowColor; void main() {
        float rim = pow(1.0 - abs(vNormal.z), 3.8); gl_FragColor = vec4(glowColor, rim * 0.33); }`,
    })));
    group.add(new THREE.PointLight(color, 13, 7, 1.7));
  } else if (!comet) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(radius * 1.12, 0.008, 6, 64),
      new THREE.MeshBasicMaterial({
        color: node.kind === "thread" && node.effort ? effortColor(node.effort) : color,
        transparent: true, opacity: node.effort ? 0.65 : 0.2,
      }));
    ring.rotation.x = -0.2;
    group.add(ring);
    effortRing = ring;
  }
  const hitMesh = new THREE.Mesh(new THREE.SphereGeometry(Math.max(radius, 0.2), 12, 8),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }));
  hitMesh.userData.graphNode = node;
  group.add(hitMesh);
  group.userData = { node, radius, comet, mesh, hitMesh, effortRing, base: new THREE.Vector3() };
  return group;
}

function createLabel(layer, node, edge = false) {
  const label = document.createElement("div");
  label.className = edge ? "graph-space-label is-edge" : `graph-space-label is-${node.kind}`;
  label.dataset.graphLabel = node.id;
  label.dataset.kind = edge ? "edge" : node.kind;
  const title = document.createElement("strong");
  title.textContent = edge ? threadEdgeLabel(node) : node.label;
  label.append(title);
  if (!edge) {
    const subtitle = document.createElement("span");
    subtitle.textContent = node.kind === "model" ? `${node.threadCount || 0} 个工作对话` : threadNodeSubtitle(node);
    label.append(subtitle);
  }
  if (edge) label.style.setProperty("--effort-color", `#${new THREE.Color(effortColor(node.effort)).getHexString()}`);
  layer.append(label);
  return label;
}

function disposeObject(object) {
  object.traverse((child) => {
    child.geometry?.dispose?.();
    const materials = Array.isArray(child.material) ? child.material : [child.material];
    materials.filter(Boolean).forEach((material) => { material.map?.dispose?.(); material.dispose?.(); });
  });
}

export function createConversationGraph({ container, canvas, nodes, reducedMotion = false, onNodeSelect }) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" });
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 150);
  const root = new THREE.Group();
  const graphLayer = new THREE.Group();
  root.rotation.set(0.1, -0.1, 0);
  root.add(graphLayer);
  scene.add(root);
  const resources = { starMaterials: [] };
  const nodeGroups = [];
  const pickables = [];
  const flowParticles = [];
  const edges = [];
  const bindings = [];
  let labelLayer = null;
  let resizeObserver = null;
  let disposed = false;
  let active = true;
  let frame = 0;
  let frameCount = 0;
  let width = 0;
  let height = 0;
  let fitDistance = 14;
  let zoom = 1;
  let extentX = 3;
  let extentY = 2.5;
  let selectedId = null;
  let hoveredId = null;
  let dragging = false;
  let dragged = false;
  let lastX = 0;
  let lastY = 0;
  let elapsed = 0;
  let previousTime = 0;
  let signature = null;
  let updateCount = 0;
  const generation = ++rendererGeneration;
  container.dataset.graphRendererGeneration = String(generation);
  container.dataset.graphUpdateCount = "0";

  function dispose() {
    if (disposed) return;
    disposed = true;
    active = false;
    cancelAnimationFrame(frame);
    resizeObserver?.disconnect();
    bindings.forEach(([type, listener, options]) => canvas.removeEventListener(type, listener, options));
    labelLayer?.remove();
    try {
      disposeObject(root);
    } finally {
      try {
        renderer.dispose();
      } finally {
        renderer.forceContextLoss();
        canvas.width = 1;
        canvas.height = 1;
        renderer.info.memory.geometries = 0;
        renderer.info.memory.textures = 0;
      }
    }
    nodeGroups.length = pickables.length = flowParticles.length = edges.length = 0;
    resources.starMaterials.length = 0;
    root.clear();
    scene.clear();
    nodes = [];
    selectedId = null;
    container.dataset.graphDisposed = "true";
  }

  try {
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7));
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    scene.add(new THREE.HemisphereLight(0xe8efe9, 0x172019, 1.15));
    const key = new THREE.DirectionalLight(0xfff0d4, 1.8);
    key.position.set(3, 4, 8);
    scene.add(key);
    labelLayer = document.createElement("div");
    labelLayer.className = "graph-space-labels";
    labelLayer.setAttribute("aria-hidden", "true");
    container.append(labelLayer);

    function rebuildScene() {
      disposeObject(graphLayer);
      graphLayer.clear();
      labelLayer.replaceChildren();
      nodeGroups.length = pickables.length = flowParticles.length = edges.length = 0;
      resources.starMaterials.length = 0;
      extentX = 3;
      extentY = 2.5;
      const modelNodes = nodes.filter((node) => node.kind === "model");
      const threadNodes = nodes.filter((node) => node.kind === "thread");
      const centers = modelCenters(modelNodes);
      const modelPositions = new Map(modelNodes.map((node, index) => [node.id, centers[index]]));
      const modelGroups = new Map();
  function registerNode(node, index, center, orbit) {
    const group = createNode(node, index, resources);
    group.userData.base.copy(center);
    group.userData.orbit = orbit;
    group.position.copy(orbit ? orbitPoint(orbit, elapsed, center) : center);
    graphLayer.add(group);
    nodeGroups.push(group);
    pickables.push(group.userData.hitMesh);
    if (!group.userData.comet) group.userData.label = createLabel(labelLayer, node);
    const bound = orbit ? orbit.semiMajor * (1 + orbit.eccentricity) : group.userData.radius;
    extentX = Math.max(extentX, Math.abs(center.x) + bound + 0.65);
    extentY = Math.max(extentY, Math.abs(center.y) + (orbit ? orbit.semiMinor : bound) + 0.9);
    if (orbit && !group.userData.comet) {
      graphLayer.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(
        Array.from({ length: 100 }, (_, step) => orbitPoint({ ...orbit, phase: step / 100 * Math.PI * 2 }, 0, center)),
      ), new THREE.LineBasicMaterial({ color: 0xa3a7a2, transparent: true, opacity: 0.1, depthWrite: false })));
    }
    if (group.userData.comet) {
      const positions = new Float32Array(9 * 3);
      const colors = new Float32Array(9 * 3);
      const tailColor = new THREE.Color(STATE_STYLE[node.state]?.color || 0xa3bcc8);
      for (let step = 0; step < 9; step += 1) {
        const brightness = (1 - step / 9) * 0.34;
        colors.set([tailColor.r * brightness, tailColor.g * brightness, tailColor.b * brightness], step * 3);
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      const tail = new THREE.Line(geometry, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.6, depthWrite: false }));
      graphLayer.add(tail);
      group.userData.tail = tail;
    }
    return group;
  }

  modelNodes.forEach((node, index) => modelGroups.set(node.id, registerNode(node, index, centers[index], null)));
  const workByModel = new Map();
  threadNodes.filter((node) => node.modelId).forEach((node) => {
    if (!workByModel.has(node.modelId)) workByModel.set(node.modelId, []);
    workByModel.get(node.modelId).push(node);
  });
  const dormantThreads = threadNodes.filter((node) => !node.modelId);
  threadNodes.forEach((node, index) => {
    const family = node.modelId ? workByModel.get(node.modelId) || [] : dormantThreads;
    const orbitSeed = textSeed(node.id);
    const comet = !node.modelId && !["processing", "due", "countdown"].includes(node.state);
    const center = modelPositions.get(node.modelId) || centers[index % Math.max(1, centers.length)] || new THREE.Vector3();
    const spec = createOrbitSpec(node.id, family.indexOf(node), family.length, comet);
    if (!node.modelId && !comet) spec.semiMajor += 2 + orbitSeed;
    const group = registerNode(node, index, center, spec);
    const modelGroup = modelGroups.get(node.modelId);
    if (!modelGroup) return;
    const color = effortColor(node.effort);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(25 * 3), 3));
    const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.42, depthWrite: false }));
    graphLayer.add(line);
    const edge = { node, group, modelGroup, line, curve: new THREE.QuadraticBezierCurve3(), label: createLabel(labelLayer, node, true) };
    edges.push(edge);
    for (let step = 0; step < 2; step += 1) {
      const particle = new THREE.Mesh(new THREE.SphereGeometry(0.026, 8, 6), new THREE.MeshBasicMaterial({ color }));
      particle.userData = { edge, offset: step / 2 };
      graphLayer.add(particle);
      flowParticles.push(particle);
    }
  });


    }

  const starPositions = new Float32Array(320 * 3);
  for (let index = 0; index < 320; index += 1) {
    starPositions.set([(textSeed(index, 11) - 0.5) * 50, (textSeed(index, 357) - 0.5) * 34, -9 - textSeed(index, 29) * 14], index * 3);
  }
  const stars = new THREE.BufferGeometry();
  stars.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
  root.add(new THREE.Points(stars, new THREE.PointsMaterial({ color: 0x9fafa9, size: 0.02, transparent: true, opacity: 0.55 })));


    function resize() {
      if (disposed) return;
      const rect = container.getBoundingClientRect();
      const nextWidth = Math.max(1, Math.floor(rect.width));
      const nextHeight = Math.max(1, Math.floor(rect.height));
      const ratio = Math.min(window.devicePixelRatio || 1, 1.7);
      // Assigning canvas dimensions can reallocate its drawing buffer.
      if (width !== nextWidth || height !== nextHeight || renderer.getPixelRatio() !== ratio) {
        width = nextWidth;
        height = nextHeight;
        if (renderer.getPixelRatio() !== ratio) renderer.setPixelRatio(ratio);
        renderer.setSize(width, height, false);
      }
      camera.aspect = width / height;
      camera.fov = width < 560 ? 49 : 42;
      const tangent = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
      fitDistance = Math.max(8, extentY / tangent, extentX / (tangent * camera.aspect)) + 2.1;
      camera.position.z = fitDistance * zoom;
      camera.far = Math.max(150, fitDistance * 3);
      camera.updateProjectionMatrix();
    }
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  function pickedNode(event) {
    const rect = canvas.getBoundingClientRect();
    pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    return raycaster.intersectObjects(pickables, false)[0]?.object?.userData?.graphNode || null;
  }
  function selectNode(node) {
    selectedId = node && selectedId !== node.id ? node.id : null;
    onNodeSelect?.(selectedId ? node : null);
    container.dataset.selectedNode = selectedId || "";
  }
  function onPointerDown(event) {
    canvas.focus({ preventScroll: true });
    dragging = true;
    dragged = false;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.setPointerCapture?.(event.pointerId);
  }
  function onPointerMove(event) {
    if (!dragging) {
      hoveredId = pickedNode(event)?.id || null;
      canvas.style.cursor = hoveredId ? "pointer" : "grab";
      return;
    }
    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;
    if (Math.abs(dx) + Math.abs(dy) > 2) dragged = true;
    root.rotation.y = THREE.MathUtils.clamp(root.rotation.y + dx * 0.004, -0.7, 0.7);
    root.rotation.x = THREE.MathUtils.clamp(root.rotation.x + dy * 0.004, -0.65, 0.65);
    lastX = event.clientX;
    lastY = event.clientY;
  }
  function onPointerUp(event) {
    if (!dragged) selectNode(pickedNode(event));
    dragging = false;
    canvas.releasePointerCapture?.(event.pointerId);
  }
  function onPointerCancel(event) {
    dragging = false;
    canvas.releasePointerCapture?.(event.pointerId);
  }
  function onWheel(event) {
    event.preventDefault();
    zoom = THREE.MathUtils.clamp(zoom + event.deltaY * 0.00065, 0.48, 1.6);
    camera.position.z = fitDistance * zoom;
  }
  function onKeyDown(event) {
    if (event.key === "Escape") selectNode(null);
  }
  canvas.tabIndex = 0;
  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerCancel);
  canvas.addEventListener("wheel", onWheel, { passive: false });
  canvas.addEventListener("keydown", onKeyDown);


    bindings.push(["pointerdown", onPointerDown], ["pointermove", onPointerMove],
      ["pointerup", onPointerUp], ["pointercancel", onPointerCancel],
      ["wheel", onWheel, { passive: false }], ["keydown", onKeyDown]);
  const projected = new THREE.Vector3();
  function project(point) {
    projected.copy(point).applyMatrix4(root.matrixWorld).project(camera);
    return { x: (projected.x * 0.5 + 0.5) * width, y: (-projected.y * 0.5 + 0.5) * height, z: projected.z };
  }
  function placeLabels() {
    const occupied = [];
    const labels = nodeGroups.filter((group) => group.userData.label).sort((a, b) => {
      const priority = (group) => group.userData.node.id === selectedId ? 0
        : group.userData.node.kind === "model" ? 1 : group.userData.node.state === "due" ? 2 : 3;
      return priority(a) - priority(b);
    });
    function positionLabel(element, point, preferredSide, important = false) {
      const labelWidth = element.offsetWidth;
      const labelHeight = element.offsetHeight;
      const candidates = [preferredSide, 1, -1, 2, -2];
      let chosen = null;
      for (const side of candidates) {
        const x = THREE.MathUtils.clamp(point.x - labelWidth / 2, 5, Math.max(5, width - labelWidth - 5));
        const y = side === 1 ? point.y - labelHeight - 12 : side === -1 ? point.y + 12
          : side === 2 ? point.y - labelHeight - 42 : point.y + 42;
        const rect = { x, y, w: labelWidth, h: labelHeight };
        if (y < 4 || y + labelHeight > height - 22) continue;
        if (!occupied.some((other) => rect.x < other.x + other.w + 8 && rect.x + rect.w + 8 > other.x
          && rect.y < other.y + other.h + 5 && rect.y + rect.h + 5 > other.y)) {
          chosen = rect;
          break;
        }
      }
      element.style.visibility = chosen && point.z < 1 ? "visible" : "hidden";
      if (!chosen) return;
      element.style.transform = `translate3d(${chosen.x.toFixed(1)}px, ${chosen.y.toFixed(1)}px, 0)`;
      element.style.opacity = important ? "1" : "0.85";
      occupied.push(chosen);
    }
    labels.forEach((group) => {
      const point = project(group.position.clone().add(new THREE.Vector3(0, group.userData.radius, 0)));
      positionLabel(group.userData.label, point, 1, group.userData.node.kind === "model" || group.userData.node.id === selectedId);
    });
    edges.forEach((edge) => {
      const point = project(edge.curve.getPoint(0.65));
      const emphasize = edge.node.id === selectedId || edge.node.id === hoveredId;
      edge.label.classList.toggle("is-emphasized", emphasize);
      positionLabel(edge.label, point, -1, emphasize);
    });
  }


    function setLabelText(element, title, subtitle) {
      if (!element) return;
      const strong = element.querySelector("strong");
      const span = element.querySelector("span");
      if (strong && strong.textContent !== title) strong.textContent = title;
      if (span && span.textContent !== subtitle) span.textContent = subtitle;
    }

    function update({ nodes: nextNodes, reducedMotion: nextMotion = reducedMotion }) {
      if (disposed) return false;
      reducedMotion = nextMotion;
      nodes = [...nextNodes].sort((left, right) => left.id.localeCompare(right.id));
      const nextSignature = JSON.stringify(nodes.map((node) => [node.id, node.kind, node.state, node.modelId]));
      if (nextSignature !== signature) {
        rebuildScene();
        signature = nextSignature;
        resize();
      }
      const byId = new Map(nodes.map((node) => [node.id, node]));
      nodeGroups.forEach((group) => {
        const node = byId.get(group.userData.node.id);
        group.userData.node = node;
        group.userData.hitMesh.userData.graphNode = node;
        setLabelText(group.userData.label, node.label, node.kind === "model"
          ? (node.threadCount || 0) + " 个工作对话" : threadNodeSubtitle(node));
        if (group.userData.effortRing) {
          group.userData.effortRing.material.color.setHex(node.effort ? effortColor(node.effort)
            : STATE_STYLE[node.state]?.color || 0xa3bcc8);
          group.userData.effortRing.material.opacity = node.effort ? 0.65 : 0.2;
        }
      });
      edges.forEach((edge) => {
        edge.node = byId.get(edge.node.id);
        edge.line.material.color.setHex(effortColor(edge.node.effort));
        edge.label.style.setProperty("--effort-color", "#" + edge.line.material.color.getHexString());
        setLabelText(edge.label, threadEdgeLabel(edge.node));
      });
      flowParticles.forEach((particle) => particle.material.color.setHex(effortColor(particle.userData.edge.node.effort)));
      container.dataset.graphNodeCount = String(nodes.length);
      container.dataset.graphCometCount = String(nodeGroups.filter((group) => group.userData.comet).length);
      updateCount += 1;
      container.dataset.graphUpdateCount = String(updateCount);
      if (selectedId) {
        const selected = byId.get(selectedId);
        if (!selected) selectedId = null;
        onNodeSelect?.(selected || null);
        container.dataset.selectedNode = selectedId || "";
      }
      return true;
    }

    function renderOnce(delta = 0) {
      if (disposed) return false;
      if (!reducedMotion && !dragging && !selectedId) elapsed += delta;
      nodeGroups.forEach((group) => {
        const { orbit, base, mesh, tail } = group.userData;
        if (orbit) group.position.copy(orbitPoint(orbit, elapsed, base));
        if (!reducedMotion && !selectedId) mesh.rotation.y += delta * 0.04;
        if (tail) {
          const attribute = tail.geometry.attributes.position;
          for (let step = 0; step < attribute.count; step += 1) {
            const point = orbitPoint(orbit, elapsed - step * 1.8, base);
            attribute.setXYZ(step, point.x, point.y, point.z);
          }
          attribute.needsUpdate = true;
        }
      });
      resources.starMaterials.forEach((material) => { material.uniforms.time.value = reducedMotion ? 0 : elapsed; });
      edges.forEach((edge) => {
        edge.curve.v0.copy(edge.modelGroup.position);
        edge.curve.v2.copy(edge.group.position);
        edge.curve.v1.copy(edge.curve.v0).lerp(edge.curve.v2, 0.5);
        edge.curve.v1.z += 0.15;
        const attribute = edge.line.geometry.attributes.position;
        for (let step = 0; step < attribute.count; step += 1) {
          const point = edge.curve.getPoint(step / (attribute.count - 1));
          attribute.setXYZ(step, point.x, point.y, point.z);
        }
        attribute.needsUpdate = true;
        setLabelText(edge.label, threadEdgeLabel(edge.node));
      });
      flowParticles.forEach((particle) => {
        particle.position.copy(particle.userData.edge.curve.getPoint((elapsed * 0.23 + particle.userData.offset) % 1));
      });
      renderer.render(scene, camera);
      placeLabels();
      container.dataset.graphReady = "true";
      frameCount += 1;
      return true;
    }

    function animate(now) {
      frame = 0;
      if (disposed || !active) return;
      const delta = Math.min(0.05, previousTime ? (now - previousTime) / 1000 : 0);
      previousTime = now;
      renderOnce(delta);
      frame = requestAnimationFrame(animate);
    }

    function setActive(value) {
      if (disposed) return;
      active = Boolean(value);
      if (!active) {
        cancelAnimationFrame(frame);
        frame = 0;
        previousTime = 0;
      } else if (!frame) {
        frame = requestAnimationFrame(animate);
      }
    }

    update({ nodes, reducedMotion });
    resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);
    setActive(true);

    return {
      renderer, scene, camera, update, setActive, renderOnce,
      getSelectedNode: () => nodes.find((node) => node.id === selectedId) || null,
      selectNode: (id) => selectNode(nodes.find((node) => node.id === id) || null),
      clearSelection() { selectedId = null; container.dataset.selectedNode = ""; },
      getDiagnostics() {
        return { nodes: nodes.length, selectedId, elapsed, active, disposed, frameCount,
          rotation: root.rotation.toArray(), camera: camera.position.toArray(), zoom,
          geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures,
          programs: renderer.info.programs?.length || 0 };
      },
      dispose,
    };
  } catch (error) {
    dispose();
    throw error;
  }
}
