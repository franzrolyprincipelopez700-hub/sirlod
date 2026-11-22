import {
  AmbientLight, CapsuleGeometry, CatmullRomCurve3, CylinderGeometry, DirectionalLight, Group,
  HemisphereLight, LatheGeometry, MathUtils, Mesh, MeshStandardMaterial, OrthographicCamera, Scene,
  SphereGeometry, TubeGeometry, Vector2, Vector3, WebGLRenderer, type BufferGeometry,
} from "three";

export type CoachPose = "idle" | "listening" | "thinking" | "speaking";
export type CoachGesture = "offer-left" | "offer-right" | "explain" | "point" | "count" | "cheer";
export interface CoachSpeechBeat {
  at: number;
  openness: number;
  rounded: boolean;
  gesture: CoachGesture;
  gestureAt: number;
}
export interface CoachMotion {
  pose: CoachPose;
  wave: number;
  speechBeat?: { readonly current: CoachSpeechBeat | null };
}
type Point = [number, number, number];
type HandShape = "relaxed" | "open" | "point" | "two" | "fist";
interface ArmPose {
  lift: number;
  forward: number;
  bend: number;
  flex: number;
  turn: number;
  wrist: number;
  shape: HandShape;
}

const rest: ArmPose = { lift: 0.105, forward: -0.04, bend: 0.04, flex: -0.20, turn: 0.36, wrist: 0, shape: "relaxed" };
const openPalm: ArmPose = { lift: 0.36, forward: -0.43, bend: 0.46, flex: -0.82, turn: 1.05, wrist: -0.22, shape: "open" };
const secondPalm: ArmPose = { ...openPalm, lift: 0.28, bend: 0.24, flex: -0.65, wrist: -0.07 };
const greeting: ArmPose = { lift: 1.36, forward: -0.12, bend: 1.22, flex: -0.20, turn: 0.15, wrist: 0, shape: "open" };
const explain: Record<CoachGesture, [ArmPose, ArmPose]> = {
  "offer-left": [openPalm, rest],
  "offer-right": [rest, openPalm],
  explain: [secondPalm, { ...openPalm, lift: 0.49, flex: -0.64 }],
  point: [rest, { lift: 0.84, forward: -0.30, bend: 0.38, flex: -0.45, turn: 0.32, wrist: 0.25, shape: "point" }],
  count: [{ lift: 0.60, forward: -0.16, bend: 1.23, flex: -0.26, turn: 0.22, wrist: 0.1, shape: "two" }, rest],
  cheer: [secondPalm, { lift: 0.62, forward: -0.35, bend: 0.92, flex: -0.70, turn: 0.54, wrist: 0, shape: "fist" }],
};

export function mountCoach(canvas: HTMLCanvasElement, motion: () => CoachMotion) {
  const renderer = new WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.65));
  const scene = new Scene();
  const camera = new OrthographicCamera(-1, 1, 1, -1, 0.1, 20);
  camera.position.set(0, 0.28, 5.5);
  camera.lookAt(0, 0.17, 0);

  scene.add(new HemisphereLight(0xf6ffff, 0x334468, 2.1), new AmbientLight(0xeaf7ff, 0.30));
  const key = new DirectionalLight(0xffe3c3, 2.45);
  key.position.set(-3, 4.5, 4);
  const rim = new DirectionalLight(0x7cf5d5, 2.1);
  rim.position.set(3, 1.7, -2.5);
  scene.add(key, rim);

  const materials = {
    skin: new MeshStandardMaterial({ color: 0xbd7c51, roughness: 0.70 }),
    warmSkin: new MeshStandardMaterial({ color: 0xb76a4f, roughness: 0.77 }),
    lips: new MeshStandardMaterial({ color: 0x774540, roughness: 0.65 }),
    mouth: new MeshStandardMaterial({ color: 0x38232a, roughness: 0.78 }),
    ink: new MeshStandardMaterial({ color: 0x161b23, roughness: 0.59 }),
    hair: new MeshStandardMaterial({ color: 0x221c21, roughness: 0.54 }),
    hairLight: new MeshStandardMaterial({ color: 0x33282a, roughness: 0.59 }),
    iris: new MeshStandardMaterial({ color: 0x51342a, roughness: 0.43 }),
    chalk: new MeshStandardMaterial({ color: 0xf5f0de, roughness: 0.68 }),
    shell: new MeshStandardMaterial({ color: 0x2c567d, roughness: 0.76 }),
    navy: new MeshStandardMaterial({ color: 0x182d46, roughness: 0.78 }),
    sky: new MeshStandardMaterial({ color: 0x8ad5e4, roughness: 0.67 }),
    accent: new MeshStandardMaterial({ color: 0xc7ee63, roughness: 0.49 }),
    steel: new MeshStandardMaterial({ color: 0x7e9f9d, roughness: 0.37, metalness: 0.32 }),
  };
  const geometries = new Set<BufferGeometry>();
  const sphere = new SphereGeometry(1, 26, 18);
  const fingerBone = new CapsuleGeometry(0.015, 0.024, 4, 10);
  const fingerTip = new CapsuleGeometry(0.0145, 0.016, 4, 10);

  function mesh(parent: Group, geo: BufferGeometry, material: MeshStandardMaterial, ...at: Point) {
    geometries.add(geo);
    const object = new Mesh(geo, material);
    object.position.set(...at);
    parent.add(object);
    return object;
  }

  function oval(parent: Group, material: MeshStandardMaterial, at: Point, size: Point) {
    const object = mesh(parent, sphere, material, ...at);
    object.scale.set(...size);
    return object;
  }

  function line(parent: Group, material: MeshStandardMaterial, points: Point[], radius: number) {
    const path = new CatmullRomCurve3(points.map((point) => new Vector3(...point)));
    return mesh(parent, new TubeGeometry(path, 18, radius, 6), material, 0, 0, 0);
  }

  function group(parent: Group, ...at: Point) {
    const child = new Group();
    child.position.set(...at);
    parent.add(child);
    return child;
  }

  function profile(parent: Group, material: MeshStandardMaterial, points: [number, number][], depth: number) {
    const geo = new LatheGeometry(points.map(([radius, height]) => new Vector2(radius, height)), 40);
    const object = mesh(parent, geo, material, 0, 0, 0);
    object.scale.z = depth;
    return object;
  }

  const body = new Group();
  scene.add(body);
  oval(body, materials.navy, [0, -0.89, 0], [0.355, 0.28, 0.212]);
  profile(body, materials.shell, [
    [0, -0.92], [0.32, -0.89], [0.345, -0.78], [0.333, -0.62], [0.365, -0.44],
    [0.419, -0.25], [0.476, -0.105], [0.487, 0.025], [0.428, 0.105], [0.33, 0.165], [0.146, 0.218], [0, 0.225],
  ], 0.65);
  oval(body, materials.navy, [0, 0.182, 0.017], [0.214, 0.080, 0.139]);
  mesh(body, new CylinderGeometry(0.107, 0.124, 0.29, 24), materials.skin, 0, 0.272, 0.038);
  line(body, materials.navy, [[0, 0.16, 0.139], [0, 0.015, 0.32], [0, -0.41, 0.256], [0, -0.83, 0.225]], 0.016);
  line(body, materials.sky, [
    [-0.414, 0.075, 0.142], [-0.365, 0.067, 0.215], [-0.301, 0.043, 0.259], [-0.239, -0.006, 0.286],
  ], 0.014);
  line(body, materials.sky, [
    [0.414, 0.075, 0.142], [0.365, 0.067, 0.215], [0.301, 0.043, 0.259], [0.239, -0.006, 0.286],
  ], 0.014);
  line(body, materials.accent, [
    [-0.103, 0.186, 0.163], [-0.139, 0.082, 0.286], [-0.117, -0.085, 0.313], [0.026, -0.255, 0.291],
    [0.135, -0.077, 0.306], [0.147, 0.079, 0.288], [0.112, 0.187, 0.162],
  ], 0.012);
  oval(body, materials.accent, [0.032, -0.275, 0.306], [0.052, 0.037, 0.022]);
  oval(body, materials.navy, [0.02, -0.275, 0.326], [0.015, 0.012, 0.006]);
  line(body, materials.chalk, [
    [-0.269, -0.218, 0.227], [-0.255, -0.228, 0.237], [-0.225, -0.192, 0.256],
  ], 0.013);
  line(body, materials.navy, [[-0.268, -0.58, 0.153], [-0.195, -0.458, 0.209]], 0.013);
  line(body, materials.navy, [[0.268, -0.58, 0.153], [0.195, -0.458, 0.209]], 0.013);

  const head = group(body, 0, 0.599, 0.032);
  const face = profile(head, materials.skin, [
    [0, -0.337], [0.111, -0.322], [0.165, -0.281], [0.214, -0.218], [0.247, -0.139],
    [0.272, -0.055], [0.285, 0.034], [0.277, 0.135], [0.256, 0.22], [0.198, 0.303],
    [0.11, 0.347], [0, 0.362],
  ], 0.96);
  face.geometry.rotateY(Math.PI);
  const vertices = face.geometry.attributes.position;
  for (let index = 0; index < vertices.count; index++) {
    const chin = Math.max(0, MathUtils.smoothstep(-vertices.getY(index), 0.1, 0.32));
    vertices.setZ(index, vertices.getZ(index) + 0.049 * chin);
  }
  face.geometry.computeVertexNormals();

  for (const side of [-1, 1]) {
    oval(head, materials.skin, [side * 0.279, -0.044, -0.012], [0.055, 0.092, 0.054]).rotation.z = side * -0.16;
    oval(head, materials.warmSkin, [side * 0.303, -0.041, 0.024], [0.025, 0.055, 0.018]);
    oval(head, materials.skin, [side * 0.287, -0.062, 0.041], [0.018, 0.029, 0.01]);
  }
  const cap = mesh(head, new SphereGeometry(1, 32, 18, 0, Math.PI * 2, 0, 1.48), materials.hair, 0, 0.078, -0.021);
  cap.scale.set(0.288, 0.326, 0.283);
  oval(head, materials.hair, [-0.247, 0.109, 0.009], [0.039, 0.112, 0.145]).rotation.z = -0.14;
  oval(head, materials.hairLight, [0.249, 0.117, 0.007], [0.037, 0.105, 0.143]).rotation.z = 0.16;
  oval(head, materials.hair, [-0.067, 0.316, 0.139], [0.216, 0.127, 0.169]).rotation.z = 0.36;
  oval(head, materials.hairLight, [-0.10, 0.368, 0.119], [0.203, 0.094, 0.155]).rotation.z = 0.41;
  oval(head, materials.hair, [0.121, 0.279, 0.133], [0.161, 0.099, 0.157]).rotation.z = -0.39;
  line(head, materials.hairLight, [
    [0.161, 0.208, 0.238], [0.097, 0.289, 0.277], [-0.033, 0.334, 0.276], [-0.174, 0.30, 0.249],
  ], 0.012);

  const eyes = [-1, 1].map((side) => {
    const eye = group(head, side * 0.104, 0.031, 0.246);
    eye.rotation.y = side * 0.20;
    oval(eye, materials.lips, [0, 0, -0.005], [0.071, 0.041, 0.025]);
    oval(eye, materials.chalk, [0, -0.002, 0.005], [0.059, 0.033, 0.021]);
    const pupil = group(eye, 0, 0, 0.022);
    oval(pupil, materials.iris, [0, 0, 0], [0.023, 0.025, 0.008]);
    oval(pupil, materials.ink, [0, 0, 0.008], [0.012, 0.014, 0.004]);
    oval(pupil, materials.chalk, [-0.007, 0.009, 0.012], [0.0065, 0.007, 0.003]);
    const brow = group(head, side * 0.108, 0.102, 0.248);
    line(brow, materials.hair, [[side * -0.061, -0.008, 0.009], [0, 0.011, 0.006], [side * 0.059, -0.003, -0.032]], 0.014);
    return { eye, pupil, brow };
  });
  const noseBridge = oval(head, materials.skin, [0, -0.013, 0.254], [0.027, 0.067, 0.042]);
  noseBridge.rotation.x = -0.26;
  oval(head, materials.skin, [0, -0.062, 0.286], [0.043, 0.032, 0.045]);
  for (const side of [-1, 1]) {
    oval(head, materials.warmSkin, [side * 0.031, -0.076, 0.292], [0.019, 0.012, 0.017]);
  }
  const smile = line(head, materials.lips, [
    [-0.083, -0.133, 0.235], [-0.035, -0.157, 0.261], [0.024, -0.159, 0.266], [0.082, -0.136, 0.239],
  ], 0.010);
  const talking = oval(head, materials.mouth, [0, -0.153, 0.264], [0.074, 0.029, 0.017]);
  const teeth = oval(head, materials.chalk, [0, -0.138, 0.279], [0.051, 0.009, 0.006]);
  const tongue = oval(head, materials.warmSkin, [0, -0.173, 0.278], [0.033, 0.008, 0.006]);

  function arm(side: number) {
    const shoulder = group(body, side * 0.408, 0.020, 0.002);
    oval(shoulder, materials.shell, [0, -0.059, 0], [0.147, 0.165, 0.152]);
    mesh(shoulder, new CapsuleGeometry(0.105, 0.213, 5, 16), materials.skin, 0, -0.223, 0);
    mesh(shoulder, new CapsuleGeometry(0.137, 0.115, 5, 18), materials.navy, 0, -0.111, 0.005);
    mesh(shoulder, new CylinderGeometry(0.124, 0.115, 0.035, 22), materials.sky, 0, -0.214, 0.005);
    const elbow = group(shoulder, 0, -0.397, 0.002);
    oval(elbow, materials.skin, [0, -0.113, 0.012], [0.101, 0.172, 0.095]);
    mesh(elbow, new CylinderGeometry(0.088, 0.064, 0.206, 20), materials.skin, 0, -0.193, 0.014);
    const wrist = group(elbow, 0, -0.289, 0.014);
    oval(wrist, materials.skin, [0, -0.047, 0.007], [0.057, 0.069, 0.035]);
    const fingers = Array.from({ length: 4 }, (_, index) => {
      const finger = group(wrist, side * ((index - 1.5) * 0.029), -0.095 + (index === 3 ? 0.012 : 0), 0.007);
      const scale = [0.95, 1.05, 0.98, 0.79][index];
      finger.scale.setScalar(scale);
      mesh(finger, fingerBone, materials.skin, 0, -0.023, 0);
      const tip = group(finger, 0, -0.046, 0);
      mesh(tip, fingerTip, materials.skin, 0, -0.018, 0);
      return { finger, tip };
    });
    const thumb = group(wrist, -side * 0.044, -0.043, 0.015);
    mesh(thumb, fingerBone, materials.skin, 0, -0.022, 0);
    const thumbTip = group(thumb, 0, -0.042, 0);
    mesh(thumbTip, fingerTip, materials.skin, 0, -0.014, 0);
    return { side, shoulder, elbow, wrist, fingers, thumb, thumbTip };
  }
  const left = arm(-1);
  const right = arm(1);
  mesh(left.elbow, new CylinderGeometry(0.076, 0.071, 0.055, 20), materials.navy, 0, -0.260, 0.014);
  oval(left.elbow, materials.steel, [0, -0.255, 0.082], [0.046, 0.040, 0.014]);
  oval(left.elbow, materials.ink, [0, -0.255, 0.093], [0.033, 0.031, 0.009]);
  oval(left.elbow, materials.accent, [0, -0.255, 0.102], [0.012, 0.006, 0.002]);

  function poseArm(
    rig: ReturnType<typeof arm>, target: ArmPose, strength: number, damping: number, salute = 0,
  ) {
    const { side, shoulder, elbow, wrist, fingers, thumb, thumbTip } = rig;
    const blend = (original: number, next: number) => MathUtils.lerp(original, next, strength);
    const approach = (start: number, end: number) => MathUtils.lerp(start, end, damping);
    shoulder.rotation.x = approach(shoulder.rotation.x, blend(rest.forward, target.forward));
    shoulder.rotation.z = approach(shoulder.rotation.z, side * blend(rest.lift, target.lift));
    elbow.rotation.x = approach(elbow.rotation.x, blend(rest.flex, target.flex));
    elbow.rotation.z = approach(elbow.rotation.z, side * blend(rest.bend, target.bend));
    wrist.rotation.x = approach(wrist.rotation.x, -0.12 * strength);
    wrist.rotation.y = approach(wrist.rotation.y, side * blend(rest.turn, target.turn) + 0.18 * salute);
    wrist.rotation.z = approach(wrist.rotation.z, side * blend(rest.wrist, target.wrist) + 0.30 * salute);

    const opened = target.shape === "open" ? 4 : target.shape === "two" ? 2 : target.shape === "point" ? 1 : 0;
    fingers.forEach(({ finger, tip }, index) => {
      const curl = target.shape === "relaxed" ? 0.42 : index < opened ? 0.05 : 1.04;
      const angle = blend(0.42, curl);
      finger.rotation.x = approach(finger.rotation.x, -angle);
      finger.rotation.z = approach(finger.rotation.z, side * (index - 1.5) * blend(0.035, opened === 4 ? 0.16 : 0.075));
      tip.rotation.x = approach(tip.rotation.x, -angle * 0.78);
    });
    thumb.rotation.z = approach(thumb.rotation.z, -side * blend(0.44, opened === 4 ? 0.64 : 0.29));
    thumb.rotation.x = approach(thumb.rotation.x, blend(-0.23, opened === 4 ? -0.05 : -0.65));
    thumbTip.rotation.x = approach(thumbTip.rotation.x, blend(-0.31, opened === 4 ? -0.10 : -0.69));
  }

  const pointer = { x: 0, y: 0 };
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const start = performance.now();
  let observedWave = -1;
  let waveAt = -1e5;
  let frame = 0;
  let renderedAt = 0;
  let contextAvailable = true;

  function render(now: number) {
    const state = motion();
    const seconds = (now - start) / 1000;
    const still = reduceMotion.matches;
    const delta = Math.min((now - renderedAt) / 1000, 0.16);
    const damping = still || renderedAt === 0 ? 1 : 1 - Math.exp(-13 * delta);
    renderedAt = now;
    if (state.wave !== observedWave) {
      observedWave = state.wave;
      waveAt = now;
    }

    const elapsed = (now - waveAt) / 1000;
    const wave = state.wave > 0 && !still
      ? MathUtils.smoothstep(elapsed, 0, 0.24) * (1 - MathUtils.smoothstep(elapsed, 1.15, 1.65))
      : 0;
    const speaking = state.pose === "speaking" && !still;
    const listening = state.pose === "listening" && !still;
    const thinking = state.pose === "thinking" && !still;
    const beat = state.speechBeat?.current;
    const emphasis = speaking && beat ? Math.max(0, 1 - (now - beat.at) / 350) * beat.openness : 0;
    const articulation = speaking
      ? Math.min(1, Math.max(0, 0.40 + 0.40 * Math.sin(seconds * 18) + 0.35 * emphasis))
      : 0;

    const beatAge = beat ? (now - beat.gestureAt) / 1000 : 0;
    const gestureStrength = speaking && beat
      ? MathUtils.smoothstep(beatAge, 0, 0.19) * (1 - MathUtils.smoothstep(beatAge, 0.92, 1.65))
      : 0;
    const [leftPose, rightPose] = beat ? explain[beat.gesture] ?? explain.explain : [rest, rest];
    poseArm(left, leftPose, gestureStrength * (1 - wave * 0.7), damping);
    poseArm(right, wave > 0.05 ? greeting : rightPose, Math.max(wave, gestureStrength), damping,
      wave * Math.sin(elapsed * 17) * (1 - MathUtils.smoothstep(elapsed, 0.95, 1.3)));

    body.position.y = still ? 0 : 0.010 * Math.sin(seconds * 2.1) + 0.017 * emphasis;
    body.rotation.y = MathUtils.lerp(
      body.rotation.y, -0.10 + (still ? 0 : pointer.x * 0.067 + 0.06 * gestureStrength), damping,
    );
    head.rotation.y = MathUtils.lerp(head.rotation.y, still ? 0 : pointer.x * 0.22 + 0.045 * Math.sin(seconds), damping);
    head.rotation.x = MathUtils.lerp(
      head.rotation.x, still ? 0 : -pointer.y * 0.08 + 0.086 * emphasis + (listening ? 0.13 : 0.025), damping,
    );
    head.rotation.z = MathUtils.lerp(
      head.rotation.z, thinking ? -0.12 : listening ? 0.105 : wave > 0 ? -0.08 * wave : 0.018, damping,
    );
    const blinkCycle = (seconds + 1.7) % 4.2;
    const blink = still ? 1 : 1 - 0.96 * Math.exp(-((blinkCycle - 2.96) ** 2) / 0.004);
    for (const { eye, pupil, brow } of eyes) {
      eye.scale.y = blink;
      pupil.position.x = still ? 0 : pointer.x * 0.013;
      pupil.position.y = still ? 0 : pointer.y * 0.008;
      brow.position.y = (thinking || listening ? 0.115 : 0.102) + 0.012 * emphasis;
    }
    talking.visible = speaking;
    teeth.visible = speaking && articulation > 0.32;
    tongue.visible = speaking && articulation > 0.60;
    smile.visible = !speaking;
    talking.scale.x = beat?.rounded && emphasis > 0.16 ? 0.045 : 0.075 - 0.012 * articulation;
    talking.scale.y = 0.008 + 0.034 * articulation;
    renderer.render(scene, camera);
  }

  function draw(now: number) {
    frame = requestAnimationFrame(draw);
    if (now - renderedAt >= 1000 / 30) render(now);
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
    const aspect = clientWidth / clientHeight;
    const halfHeight = Math.max(1.10, 1.27 / aspect);
    camera.top = halfHeight;
    camera.bottom = -halfHeight;
    camera.left = -halfHeight * aspect;
    camera.right = halfHeight * aspect;
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
