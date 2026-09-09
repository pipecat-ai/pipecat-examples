# Writing a voice description

Gradium expands the description into a fuller voice specification and then
samples complete voices from it. The model responds to the same attributes a
casting brief would carry, so naming more of them gives a tighter result. Up
to 500 characters, and the full 500 are usable.

## Attributes to name

| Attribute | Examples |
|---|---|
| Gender | female, male, androgynous |
| Age | 20 to 30, middle aged, elderly |
| Accent or origin | British, Southern US, Parisian, Brazilian, Irish, Bristolian |
| Pitch | high pitch, deep, mid range, mid-low |
| Pace | fast pacing, measured, unhurried, steady natural pacing |
| Energy | high energy, calm, subdued, boisterous |
| Timbre and resonance | glossy, gravelly, breathy, bright sparkling resonance, warm rounded resonance, vocal fry |
| Register and manner | confident, girly chatter, formal, conspiratorial, crisp, deliberate |
| Intended use | a friendly receptionist, an audiobook narrator, a news anchor, de-escalation on a support line |

Put the intended use at the end. It steers delivery and register, not only
the colour of the voice.

## Four descriptions that work

These are the exact prompts behind the four demo voices in the launch
material. Use them as templates: same shape, different attributes.

**Receptionist** (British, female, 20 to 30)

> A British female voice, 20 to 30, glossy and confident, with girly chatter,
> high pitch, fast pacing, high energy and bright sparkling resonance. Ideal
> for a friendly receptionist or assistant.

**Customer service** (Irish, male, 40 to 55)

> An Irish English male voice, 40 to 55, for customer service: calm and crisp,
> with mid-low pitch, steady natural pacing, medium energy and warm rounded
> resonance. Ideal for reassuring walkthroughs, empathic de-escalation and
> complex IT support.

**Narrator** (American, male, 55 to 65)

> An American English male voice, 55 to 65: clean, deliberate and precise,
> with low pitch, slow pacing and low-to-mid energy, resonant timbre and a
> gentle low-to-high flow. Ideal for projecting academic authority.

**Character** (Bristolian pirate, male, 45 to 60)

> A gruff Bristolian English male pirate voice, 45 to 60, for game and
> character narration: weathered low pitch, gravelly timbre with heavy vocal
> fry, strong projection, at a steady, unhurried pace, boisterous and
> commanding energy.

## From a reference image

When the user drops a picture of the character into the project root, the
brief comes from the picture. Open it with the Read tool and work through the
attribute table above, one row at a time, taking each value from a cue you
can point at:

| What you see | What it gives you |
|---|---|
| The person or creature: build, face, hair, apparent age | Gender as presented, and an apparent age range ("40 to 55"). |
| Clothing, props, setting: a headset and a desk, a helm and a sea, a lab coat, a stage | The intended use and the register: receptionist, ship's captain, scientist, narrator. Put it at the end of the brief. |
| Expression and posture: a grin, a scowl, a raised eyebrow, slumped shoulders | Energy and manner: bright and high-energy, gruff and blunt, wry, weary. |
| Era and art style: a sepia portrait, pixel art, a cartoon, a fantasy painting | Character voices: go bold on timbre and manner (weathered, gravelly, theatrical, squeaky). |
| Text in the image, flags, landmarks, and the file name | Accent and origin, and the name (`declan.png` is probably Declan). |

Two rules:

- **Accent only from explicit cues.** Signage, a flag, a landmark, the file
  name, or what the user said. Never from someone's appearance. With no cue,
  use the default for the use case (American for an assistant, British for a
  narrator, and so on) and say it was a guess when you show the brief.
- **Pitch, pace and timbre are your casting choices**, not facts in the
  picture: an image has no sound. Choose what the character calls for, and
  list those as your choices when you show the brief so the user can steer.

Describe the voice, not the picture. "A woman in a red coat at a reception
desk" tells the voice model nothing; "A warm British female voice, 30 to 40,
mid pitch, quick and bright, crisp and welcoming, for a hotel receptionist"
does. Do not mention the image in the brief.

The picture also gives you the two other things the bot needs: a working
name (the character's name if the file or the image says it, otherwise the
role) and a persona line for the bot's system prompt ("You are Declan, the
innkeeper at the Crossroads Inn."). The client shows the image in place of
the audio visualizer, so the voice and the face are seen together; make
sure they match.

## Defaults by use, when the user did not say

| Use | Reasonable defaults |
|---|---|
| Receptionist, assistant, booking | 25 to 35, mid-high pitch, quick pace, high energy, bright and warm, friendly and confident |
| Support agent, help desk | 35 to 50, mid-low pitch, steady pace, medium energy, warm rounded resonance, calm and clear |
| Narrator, explainer, tutorial | 40 to 60, low-mid pitch, measured pace, low-to-mid energy, resonant, deliberate |
| Character, game | Whatever the character calls for; go bold on timbre and manner |

Tell the user which defaults you filled in, in a few words, when you show the
brief.

## Practical notes

- **Describe the voice, not the script.** Words to be spoken belong in the
  audition line, not in the description.
- **Nothing is reproducible.** The same description gives a new voice every
  time, because it is expanded before sampling. If the user likes a take, the
  move is "keep it", never "make that one again".
- **Three takes are one character.** All candidates from one request come
  from the same description, so they are variations on a single character.
  A genuinely different voice needs a different description, not more takes.
- **Language shapes accent and delivery**, not only the words. Supported:
  `en`, `fr`, `es`, `pt`, `de`. A voice that will speak English stays `en`
  whatever its origin.

## The audition line

Up to 100 characters, spoken by every take. Pick something the bot will
actually say, in the language the voice will speak, so the user judges the
voice in context:

| Use | Example line |
|---|---|
| Receptionist | Hi there, thanks so much for calling! How can I help you today? |
| Support agent | I completely understand your concern, and we'll take care of this properly. |
| Narrator | Imagine a problem so stubborn that it went unsolved for decades. |
| Pirate | Listen here, ye sea-bitten scallywags. |

Count the characters; the API rejects longer lines with a 400.
