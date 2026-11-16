// Everything about the pill's look and feel that can be tuned. Each pill
// starts from a copy of these defaults; nothing here is shared between pills.

export type Light = {
  name: string;
  enabled: boolean;
  yaw: number;
  pitch: number;
  roll: number;
  width: number;
  height: number;
  soft: number;
  /** 1 = top-to-bottom ramp across the whole light, smaller = sharper */
  gradient: number;
  intensity: number;
  colorTop: string;
  colorBottom: string;
};

// Lights are invisible to camera rays, so the background stays black and
// they only show up through reflection and refraction in the glass.
//
// Whatever sits straight behind the dish is seen through its flat floor at
// every angle, so it reads as a fixed backdrop and is kept nearly black.
// The look comes from lights the glass reflects: the big pink softbox paints
// the floor, the strips catch the curved walls and rims, and all of them
// slide across the dish as it turns.
export const defaultLights: readonly Light[] = [
  {
    name: 'Backdrop',
    enabled: true,
    yaw: 180, pitch: 0, roll: -60,
    width: 0.9, height: 0.9, soft: 0.8, gradient: 0.4,
    intensity: 0.12,
    colorTop: '#7040c0', colorBottom: '#1a10a0',
  },
  {
    name: 'Left softbox',
    enabled: true,
    yaw: -73.5, pitch: -12, roll: 0,
    width: 0.42, height: 0.3, soft: 0.25, gradient: 1,
    intensity: 30,
    colorTop: '#ffd0f0', colorBottom: '#c070ff',
  },
  {
    name: 'Right strip',
    enabled: true,
    yaw: 82, pitch: 0, roll: -16,
    width: 0.12, height: 1.2, soft: 0.3, gradient: 1,
    intensity: 60,
    colorTop: '#ffffff', colorBottom: '#e2d6ff',
  },
  {
    name: 'Top back softbox',
    enabled: true,
    yaw: 140, pitch: 35, roll: 0,
    width: 0.35, height: 0.3, soft: 0.25, gradient: 1,
    intensity: 20,
    colorTop: '#ffe0f4', colorBottom: '#ffb0e0',
  },
  {
    // Sits a little off the camera's axis and fades out softly, so face-on
    // it lays a sheen across one side of the floor instead of mirroring off
    // all of it, which would hide the light inside.
    name: 'Front softbox',
    enabled: true,
    yaw: 9, pitch: 13, roll: -35,
    width: 0.35, height: 0.3, soft: 0.9, gradient: 0.8,
    intensity: 16,
    colorTop: '#ffe4f6', colorBottom: '#c890ff',
  },
  {
    name: 'Right softbox',
    enabled: true,
    yaw: 80, pitch: 0, roll: 0,
    width: 0.3, height: 0.5, soft: 0.25, gradient: 1,
    intensity: 18,
    colorTop: '#f0c8ff', colorBottom: '#9a80ff',
  },
  {
    name: 'Top softbox',
    enabled: true,
    yaw: 0, pitch: 65, roll: 0,
    width: 0.6, height: 0.3, soft: 0.25, gradient: 1,
    intensity: 15,
    colorTop: '#ffc8ec', colorBottom: '#ffc8ec',
  },
  // Behind and to one side: the walls look straight through to it, which
  // fills them with the scheme's deep colour, while the floor, looking
  // directly behind, stays dark.
  {
    name: 'Back kicker',
    enabled: true,
    yaw: -152, pitch: 2, roll: 0,
    width: 0.35, height: 0.7, soft: 0.6, gradient: 1,
    intensity: 10,
    colorTop: '#3b2bff', colorBottom: '#3b2bff',
  },
];

export const defaultSettings = {
  /**
   * 'Live' follows the pill's motion states. 'Reference pose' holds one fixed
   * pose instead (see refYaw / refPitch / refRoll), for comparing against a
   * reference image.
   */
  mode: 'Live' as 'Live' | 'Reference pose',
  /** degrees its face wanders while idle */
  idleSway: 20,
  idleSpeed: 1,
  /** how far it floats up and down */
  bob: 0.035,
  /** degrees it nods with the voice it hears */
  listenNod: 11,
  /** how far it comes forward on a loud syllable */
  listenPunch: 0.42,
  /** one turn while spinning */
  spinSeconds: 1.5,
  /**
   * One slow turn while idle, in seconds; 0 to hold its place and look about
   * instead. A spin that ends then slows into this turn rather than coming
   * round to face front.
   */
  idleTurnSeconds: 0,
  /** the single turn it makes as the mood changes */
  turnSeconds: 1.3,
  /** seconds with nothing happening before it comes to rest */
  restAfter: 4,
  /** 0 settles dead, 1 overshoots freely */
  bounce: 0.5,
  /**
   * Degrees it turns to look at the pointer as it moves about the page; it
   * straightens up a while after the pointer stops. 0 for none.
   */
  pointerTilt: 11,
  /** The entrance: it spins in from the dark and from further off. */
  introSeconds: 1.8,
  /** how many turns it makes on the way in */
  introTurns: 1.25,
  /** how much further back it starts */
  introDepth: 3,
  /**
   * Without motion it holds still: no drift, turns or spins, and it fades in
   * rather than spinning in. The light inside still answers a voice. 'auto'
   * follows the system's "reduce motion" setting.
   */
  reducedMotion: 'auto' as 'auto' | boolean,
  refYaw: -48,
  refPitch: -10,
  refRoll: 0,

  // camera. The view is fitted to the canvas: the pill's diameter takes
  // `fill` of the canvas's shorter side, which leaves room for it to come
  // forward and for its glow.
  camDistance: 5.4,
  fill: 0.78,

  // shape (radius is fixed at 1). The edges are only just rounded: a generous
  // rounding turns each rim into a lens that squeezes every light into a
  // thin line, where a nearly flat rim shows broad, calm bands.
  height: 0.4,
  wall: 0.11,
  floor: 0.06,
  bevel: 0.01,
  fillet: 0.02,

  // glass
  ior: 1.5,
  dispersion: 1,
  absorbColor: '#b48cff',
  absorbDensity: 1.5,
  roughness: 0.0,
  /** more than a little fogs the walls and flattens their colour */
  glow: 0.05,
  glowColor: '#d070ff',
  glowDensity: 1.5,

  // A thin coating that tints reflections by interference, like oil on water.
  /** how strongly */
  film: 0.55,
  /** microns */
  filmThickness: 0.36,
  /** how much the thickness wanders across the glass */
  filmVariation: 0.18,
  /** reflectance it adds */
  filmShine: 0.012,

  // surface wear
  /** How many scratches: the chance each possible one is there. A few read as wear; many read as damage. */
  scratchDensity: 0.08,
  wallScratches: 0.3,
  scratchWidth: 0.0016,
  scratchSlope: 1.4,
  scratchStrength: 0.3,
  scratchScale: 1,
  scratchLength: 0.6,
  smudge: 0.2,
  smudgeScale: 2.5,
  haze: 0.005,

  // The studio lights' overall level. They are held back so their reflections
  // don't drown the light inside; 1 is the level the reference image was
  // matched at.
  rig: 0.55,

  // mood and voice
  moodSeconds: 1.2,
  voiceGain: 1,

  // the light inside
  soul: true,
  soulIntensity: 1.6,
  /** the core on the axis */
  soulCore: 1,
  /** the ripples the voice sends out from it */
  soulRipple: 1,
  /** core radius at rest */
  soulRadius: 0.2,
  /** seconds for a ripple to reach the wall */
  soulTravel: 1.1,
  /** how far the ripple fronts bend out of round */
  soulWarp: 0.22,
  /** how bright it breathes when no one is talking */
  soulIdle: 0.16,
  /** the glass's own glow, which swells with the voice */
  soulBody: 0.35,
  /** how much of the pulse's light the glass picks up */
  soulGlass: 0.15,
  /** ... and its scratches and smudges */
  soulSurface: 0.25,
  /** the slow strands wound round the core */
  soulWisps: 0.8,
  /** how far the voice's spectrum pulls the core's edge out of round */
  soulFlare: 0.3,
  /** how bright the drifting specks are */
  soulMotes: 0.8,
  soulSteps: 6,

  // render. The canvas is drawn at its CSS size times renderScale, times the
  // screen's pixel ratio up to maxPixelRatio (more costs a lot of pixels for
  // little visible gain), and never more than maxPixels in all.
  renderScale: 1,
  maxPixelRatio: 1.25,
  maxPixels: 2_000_000,
  spp: 1,
  /** samples a pixel while it moves */
  motionSpp: 4,
  /**
   * Auto pacing keeps frames evenly spaced at a rate the GPU can hold. When a
   * frame at full quality won't fit in one refresh, 'frame rate' keeps the
   * display's rate and takes fewer samples (the still it settles into is
   * refined to full quality either way); 'fidelity' keeps the samples and
   * draws on every second (or third) refresh.
   */
  autoQuality: true,
  prefer: 'frame rate' as 'fidelity' | 'frame rate',
  taaBlend: 0.25,
  clipGamma: 1.25,
  maxSamples: 512,
  maxDepth: 10,
  maxSegments: 18,
  minWeight: 0.004,

  // post
  exposure: 1,
  bloomStrength: 0.12,
  bloomRadius: 1,
  toneMap: 'AgX punchy' as 'AgX' | 'AgX punchy' | 'ACES',
  saturation: 1.15,
  grain: 0.012,
  /** rays of light fanning out from the light inside */
  shafts: 0.35,
  shaftReach: 0.45,
  /** a lens streak across the brightest parts */
  streak: 0.25,
  /** a faint glow of the pill's colour in the air round it */
  halo: 0.25,
  /** a lens's colour fringing towards the picture's edge */
  aberration: 0.012,
};

export type PillSettings = typeof defaultSettings;
