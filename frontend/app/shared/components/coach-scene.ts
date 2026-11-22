import {
  AmbientLight, CapsuleGeometry, CylinderGeometry, DirectionalLight, Group,
  HemisphereLight, Mesh, MeshStandardMaterial, OrthographicCamera, Scene,
  SphereGeometry, TorusGeometry, TubeGeometry, CatmullRomCurve3, Vector3, WebGLRenderer,
  type BufferGeometry,
} from "three";

export type CoachPose = "idle" | "thinking" | "speaking";
export interface CoachMotion { pose: CoachPose; wave: number }

export function mountCoach(canvas: HTMLCanvasElement, motion: () => CoachMotion) {
  const renderer = new WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.65));
  const scene = new Scene();
  const camera = new OrthographicCamera(-1, 1, 1, -1, 0.1, 20);
  camera.position.set(0, 0.22, 5.3);
  camera.lookAt(0, 0.16, 0);

  scene.add(new HemisphereLight(0xf2ffff, 0x173150, 2.1), new AmbientLight(0xeef7ff, 0.35));
  const key = new DirectionalLight(0xffe9d3, 2.5);
  key.position.set(-3, 5, 4);
  const rim = new DirectionalLight(0x5bebd7, 2.2);
  rim.position.set(3, 1, -2);
  scene.add(key, rim);

  const materials = {
    skin: new MeshStandardMaterial({ color: 0xc47f52, roughness: 0.7 }),
    cheek: new MeshStandardMaterial({ color: 0xcf7952, roughness: 0.8 }),
    hair: new MeshStandardMaterial({ color: 0x251d25, roughness: 0.64 }),
    hairLight: new MeshStandardMaterial({ color: 0x362634, roughness: 0.58 }),
    dark: new MeshStandardMaterial({ color: 0x1c202c, roughness: 0.5 }),
    navy: new MeshStandardMaterial({ color: 0x145780, roughness: 0.74 }),
    deep: new MeshStandardMaterial({ color: 0x123654, roughness: 0.8 }),
    mint: new MeshStandardMaterial({ color: 0x50e4ba, roughness: 0.45 }),
    white: new MeshStandardMaterial({ color: 0xfff7e4, roughness: 0.58 }),
    gold: new MeshStandardMaterial({ color: 0xf6b554, roughness: 0.4, metalness: 0.22 }),
    mouth: new MeshStandardMaterial({ color: 0x683b3e, roughness: 0.82 }),
  };
  const geometries = new Set<BufferGeometry>();

  function mesh(parent: Group, geo: BufferGeometry, material: MeshStandardMaterial, x: number, y: number, z: number) {
    geometries.add(geo);
    const object = new Mesh(geo, material);
    object.position.set(x, y, z);
    parent.add(object);
    return object;
  }

  const sphere = new SphereGeometry(1, 24, 16);
  function oval(parent: Group, material: MeshStandardMaterial, at: [number, number, number], size: [number, number, number]) {
    const object = mesh(parent, sphere, material, ...at);
    object.scale.set(...size);
    return object;
  }

  function line(parent: Group, material: MeshStandardMaterial, points: [number, number, number][], radius: number) {
    const path = new CatmullRomCurve3(points.map((point) => new Vector3(...point)));
    return mesh(parent, new TubeGeometry(path, 18, radius, 6), material, 0, 0, 0);
  }

  function group(parent: Group, x: number, y: number, z: number) {
    const child = new Group();
    child.position.set(x, y, z);
    parent.add(child);
    return child;
  }

  const body = new Group();
  scene.add(body);
  oval(body, materials.deep, [0, -0.81, 0], [0.40, 0.31, 0.23]);
  oval(body, materials.navy, [0, -0.35, 0], [0.47, 0.59, 0.26]);
  oval(body, materials.deep, [0, 0.14, 0.003], [0.28, 0.13, 0.215]);
  mesh(body, new CylinderGeometry(0.128, 0.155, 0.33, 20), materials.skin, 0, 0.29, 0);
  line(body, materials.white, [[0, 0.09, 0.228], [0, -0.33, 0.265], [0, -0.74, 0.19]], 0.012);
  line(body, materials.mint, [
    [-0.14, 0.22, 0.12], [-0.13, 0.03, 0.20], [-0.088, -0.16, 0.25],
    [0.025, -0.35, 0.281], [0.13, -0.02, 0.224], [0.15, 0.17, 0.14],
  ], 0.017);
  oval(body, materials.gold, [0.025, -0.37, 0.288], [0.064, 0.052, 0.027]);
  oval(body, materials.dark, [0.015, -0.368, 0.313], [0.016, 0.015, 0.003]);
  oval(body, materials.mint, [-0.24, -0.16, 0.216], [0.063, 0.052, 0.018]);
  line(body, materials.deep, [[-0.27, -0.169, 0.23], [-0.248, -0.183, 0.232], [-0.219, -0.142, 0.231]], 0.008);

  const head = group(body, 0, 0.56, 0.025);
  oval(head, materials.skin, [0, 0.015, 0], [0.363, 0.425, 0.325]);
  oval(head, materials.skin, [0, -0.15, 0.09], [0.285, 0.254, 0.257]);
  for (const side of [-1, 1]) {
    oval(head, materials.skin, [side * 0.345, -0.041, -0.008], [0.078, 0.118, 0.059]);
    oval(head, materials.cheek, [side * 0.376, -0.043, 0.033], [0.037, 0.065, 0.019]);
  }
  const cap = mesh(head, new SphereGeometry(1, 26, 16, 0, Math.PI * 2, 0, 1.48), materials.hair, 0, 0.075, -0.023);
  cap.scale.set(0.377, 0.421, 0.336);
  for (const side of [-1, 1]) {
    oval(head, materials.hair, [side * 0.314, 0.123, 0.02], [0.064, 0.16, 0.166])
      .rotation.z = side * -0.17;
  }
  oval(head, materials.hair, [-0.09, 0.329, 0.17], [0.30, 0.15, 0.20]).rotation.z = 0.33;
  oval(head, materials.hairLight, [-0.115, 0.378, 0.165], [0.255, 0.105, 0.158]).rotation.z = 0.39;
  oval(head, materials.hair, [0.14, 0.321, 0.178], [0.21, 0.107, 0.16]).rotation.z = -0.42;
  oval(head, materials.hairLight, [-0.185, 0.405, 0.15], [0.136, 0.072, 0.118]).rotation.z = 0.53;

  const eyes = [-1, 1].map((side) => {
    const eye = group(head, side * 0.131, 0.025, 0.287);
    oval(eye, materials.white, [0, 0, 0], [0.083, 0.064, 0.043]);
    const pupil = group(eye, 0.004, -0.004, 0.036);
    oval(pupil, materials.dark, [0, 0, 0], [0.031, 0.039, 0.017]);
    oval(pupil, materials.white, [-0.010, 0.014, 0.014], [0.010, 0.010, 0.006]);
    const brow = oval(head, materials.hair, [side * 0.139, 0.128, 0.288], [0.088, 0.022, 0.023]);
    brow.rotation.z = side * -0.14;
    return { eye, pupil, brow };
  });
  oval(head, materials.skin, [0, -0.055, 0.327], [0.049, 0.059, 0.054]);
  const smile = line(head, materials.mouth, [[-0.112, -0.144, 0.303], [-0.045, -0.185, 0.342], [0.039, -0.185, 0.344], [0.102, -0.149, 0.308]], 0.016);
  const talking = oval(head, materials.mouth, [0, -0.166, 0.333], [0.091, 0.044, 0.016]);
  talking.visible = false;
  const teeth = oval(head, materials.white, [0, -0.151, 0.348], [0.063, 0.012, 0.009]);
  teeth.visible = false;

  function arm(side: number) {
    const shoulder = group(body, side * 0.36, -0.04, 0);
    oval(shoulder, materials.navy, [0, -0.065, 0], [0.172, 0.18, 0.18]);
    mesh(shoulder, new CapsuleGeometry(0.123, 0.23, 5, 16), materials.navy, 0, -0.21, 0);
    line(shoulder, materials.mint, [[side * 0.111, -0.05, 0.085], [side * 0.105, -0.2, 0.065], [side * 0.08, -0.34, 0.056]], 0.011);
    const elbow = group(shoulder, 0, -0.38, 0.008);
    mesh(elbow, new CapsuleGeometry(0.103, 0.17, 5, 16), materials.navy, 0, -0.125, 0.012);
    mesh(elbow, new CylinderGeometry(0.103, 0.097, 0.056, 18), materials.deep, 0, -0.248, 0.012);
    oval(elbow, materials.skin, [0, -0.324, 0.024], [0.091, 0.108, 0.067]);
    oval(elbow, materials.skin, [-side * 0.063, -0.311, 0.05], [0.034, 0.066, 0.039]).rotation.z = side * -0.43;
    return { shoulder, elbow };
  }
  const left = arm(-1);
  const right = arm(1);
  mesh(left.elbow, new TorusGeometry(0.099, 0.023, 7, 20), materials.gold, 0, -0.236, 0.012).rotation.x = Math.PI / 2;

  const pointer = { x: 0, y: 0 };
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const start = performance.now();
  let observedWave = -1;
  let waveAt = -1e5;
  let frame = 0;
  let lastFrame = 0;
  let contextAvailable = true;

  function render(now: number) {
    const state = motion();
    const seconds = (now - start) / 1000;
    if (state.wave !== observedWave) {
      observedWave = state.wave;
      waveAt = now;
    }
    const still = reduceMotion.matches;
    const elapsed = (now - waveAt) / 1000;
    const waving = state.wave > 0 && elapsed < 1.55;
    const wave = waving ? Math.sin(Math.PI * Math.min(1, elapsed / 1.55)) : 0;
    const speaking = state.pose === "speaking" && !still;
    const thinking = state.pose === "thinking";
    body.position.y = still ? 0 : 0.013 * Math.sin(seconds * 2.1);
    body.rotation.y = still ? -0.065 : -0.065 + pointer.x * 0.08;
    head.rotation.y = still ? 0 : pointer.x * 0.22 + 0.063 * Math.sin(seconds * 1.16);
    head.rotation.x = still ? 0 : -pointer.y * 0.085 + (speaking ? 0.055 * Math.sin(seconds * 6.4) : 0.025);
    head.rotation.z = still ? 0 : thinking ? -0.135 : (waving ? -0.1 * wave : 0.018);
    const blinkCycle = (seconds + 1.65) % 3.95;
    const blink = still ? 1 : 1 - 0.94 * Math.exp(-((blinkCycle - 2.92) ** 2) / 0.004);
    for (const { eye, pupil, brow } of eyes) {
      eye.scale.y = blink;
      pupil.position.x = still ? 0 : pointer.x * 0.022;
      pupil.position.y = still ? 0 : pointer.y * 0.014;
      brow.position.y = thinking && !still ? 0.146 : 0.128;
    }
    talking.visible = speaking;
    teeth.visible = speaking;
    smile.visible = !speaking;
    talking.scale.y = (0.025 + 0.027 * Math.abs(Math.sin(seconds * 13))) * (speaking ? 1 : 0.5);
    left.shoulder.rotation.z = -0.23;
    left.elbow.rotation.z = -0.12;
    left.elbow.rotation.x = -0.44;
    right.shoulder.rotation.z = still ? 0.21 : 0.22 + 1.56 * wave + (speaking ? 0.19 * (1 + Math.sin(seconds * 5)) : 0);
    right.elbow.rotation.z = still ? 0.16 : 0.2 + wave * (0.68 + 0.56 * Math.sin(elapsed * 19));
    right.elbow.rotation.x = -0.23 - (thinking && !still ? 0.44 : 0);
    renderer.render(scene, camera);
  }

  function draw(now: number) {
    frame = requestAnimationFrame(draw);
    if (now - lastFrame >= 1000 / 30) {
      render(now);
      lastFrame = now;
    }
  }

  function update() {
    cancelAnimationFrame(frame);
    if (!contextAvailable || document.hidden) return;
    render(performance.now());
    if (!reduceMotion.matches) frame = requestAnimationFrame(draw);
  }

  function resize() {
    const { clientWidth, clientHeight } = canvas;
    if (!clientWidth || !clientHeight) return;
    renderer.setSize(clientWidth, clientHeight, false);
    const halfHeight = 1.12;
    const halfWidth = halfHeight * clientWidth / clientHeight;
    camera.left = -halfWidth;
    camera.right = halfWidth;
    camera.top = halfHeight;
    camera.bottom = -halfHeight;
    camera.updateProjectionMatrix();
    if (contextAvailable && !document.hidden) render(performance.now());
  }

  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  const lookAtPointer = (event: PointerEvent) => {
    const bounds = canvas.getBoundingClientRect();
    pointer.x = (event.clientX - bounds.left) / bounds.width * 2 - 1;
    pointer.y = 1 - (event.clientY - bounds.top) / bounds.height * 2;
  };
  const lookForward = () => { pointer.x = 0; pointer.y = 0; };
  const onContextLost = (event: Event) => {
    event.preventDefault();
    contextAvailable = false;
    canvas.dataset.ready = "false";
    update();
  };
  const onContextRestored = () => {
    contextAvailable = true;
    canvas.dataset.ready = "true";
    resize();
    update();
  };
  canvas.addEventListener("pointermove", lookAtPointer);
  canvas.addEventListener("pointerleave", lookForward);
  canvas.addEventListener("webglcontextlost", onContextLost);
  canvas.addEventListener("webglcontextrestored", onContextRestored);
  document.addEventListener("visibilitychange", update);
  reduceMotion.addEventListener("change", update);
  resize();
  update();

  return () => {
    cancelAnimationFrame(frame);
    observer.disconnect();
    document.removeEventListener("visibilitychange", update);
    reduceMotion.removeEventListener("change", update);
    canvas.removeEventListener("pointermove", lookAtPointer);
    canvas.removeEventListener("pointerleave", lookForward);
    canvas.removeEventListener("webglcontextlost", onContextLost);
    canvas.removeEventListener("webglcontextrestored", onContextRestored);
    for (const geometry of geometries) geometry.dispose();
    for (const material of Object.values(materials)) material.dispose();
    renderer.dispose();
  };
}
