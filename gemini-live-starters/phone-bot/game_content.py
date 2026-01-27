"""Game content and utilities for Two Truths and a Lie."""

import random
from typing import List, Tuple

# 200 TRUE statements - detailed and interesting facts
TRUTHS = [
    # Animals & Nature (50)
    "The mantis shrimp can punch with the force of a bullet, creating underwater shockwaves that reach 8,000 degrees Fahrenheit",
    "A single colony of honey bees can produce up to 60 pounds of honey per year, visiting over 2 million flowers to do so",
    "Octopuses have three hearts - two pump blood to the gills while one pumps it to the rest of the body",
    "The tongue of a blue whale weighs as much as an adult elephant, approximately 6,000 pounds",
    "A flamingo can only eat when its head is upside down, using special filters in its beak to strain tiny organisms from water",
    "The heart of a shrimp is located in its head, along with most of its other vital organs",
    "A snail can sleep for three years straight without eating if conditions are too dry",
    "The box jellyfish has 24 eyes arranged in four clusters, giving it 360-degree vision despite having no brain",
    "Starfish can regenerate lost arms and some species can regrow an entire body from just one severed arm",
    "A grizzly bear's bite is strong enough to crush a bowling ball, with a force of over 1,200 PSI",
    "The Arctic tern migrates from Arctic to Antarctic and back each year, covering over 44,000 miles annually",
    "Dolphins sleep with only half their brain at a time, keeping one eye open to watch for predators",
    "A tiger's stripes are unique like human fingerprints, and the pattern extends to their skin beneath the fur",
    "The pistol shrimp creates a bubble that reaches 8,000 degrees Fahrenheit when it snaps its claw, louder than a gunshot",
    "Crows can hold grudges against individual humans for years and will teach their offspring to recognize those people",
    "An elephant's trunk contains over 40,000 individual muscles, compared to the entire human body's 600+ muscles",
    "The axolotl can regenerate not just limbs, but parts of its heart, spine, and even portions of its brain",
    "Hummingbirds are the only birds that can fly backwards, with wings that beat up to 80 times per second",
    "The bombardier beetle defends itself by mixing chemicals in its abdomen to create a boiling acid spray at 212 degrees Fahrenheit",
    "Sea otters hold hands while sleeping to prevent drifting apart, and have the densest fur of any mammal with up to 1 million hairs per square inch",
    "Koalas sleep up to 22 hours per day because eucalyptus leaves provide so little energy",
    "A woodpecker's tongue wraps around its skull to cushion its brain from up to 12,000 pecks per day",
    "Butterflies taste with their feet, using chemical receptors to determine if a leaf is suitable for laying eggs",
    "The Greenland shark can live for over 400 years, making it the longest-lived vertebrate known to science",
    "Cats have over 20 different vocalizations, but they primarily meow to communicate with humans, not other cats",
    "A group of flamingos is called a 'flamboyance,' and their pink color comes from beta carotene in the algae they eat",
    "The mimic octopus can impersonate over 15 different species, including lionfish, sea snakes, and jellyfish",
    "Giraffes have the same number of neck vertebrae as humans - seven - but each one can be over 10 inches long",
    "The Alpine swift can fly continuously for 200 days without landing, sleeping while gliding on air currents",
    "A chameleon's tongue can extend to twice its body length in just 0.07 seconds to catch prey",
    "Penguins propose to their mates by presenting them with a carefully selected pebble",
    "The leafcutter ant can carry objects 50 times its own body weight, equivalent to a human lifting a truck",
    "Bats are the only mammals capable of sustained flight, and some species can reach speeds of over 60 mph",
    "The sea cucumber can expel its internal organs to distract predators, then regenerate them within weeks",
    "Sperm whales can hold their breath for up to 90 minutes during dives that reach depths of 7,000 feet",
    "The lyrebird can accurately mimic almost any sound it hears, including chainsaws, car alarms, and camera shutters",
    "Tardigrades, or water bears, can survive extreme conditions including the vacuum of space, radiation 1,000 times higher than lethal doses for humans, and temperatures from -328°F to 300°F",
    "The Komodo dragon has venom glands that produce toxins to lower blood pressure and prevent blood clotting in prey",
    "Sloths move so slowly that algae grows on their fur, providing camouflage and nutrients they can lick off",
    "The peacock mantis shrimp can see colors humans can't perceive, detecting 12 color channels compared to our three",
    "Polar bears are nearly invisible to infrared cameras because their fur is so effective at retaining heat",
    "The sailfish is the fastest fish in the ocean, capable of swimming at speeds up to 68 miles per hour",
    "Wolves can hear sounds from up to 10 miles away in open terrain, six times farther than humans",
    "The glass frog has translucent skin on its belly, allowing you to see its internal organs including its beating heart",
    "Elephants can recognize themselves in mirrors, a sign of self-awareness shared by only a few species",
    "The hummingbird's heart beats up to 1,260 times per minute, and it must eat every 10-15 minutes to survive",
    "Cuttlefish can change the color and texture of their skin in 0.3 seconds, controlled by millions of pigment cells",
    "The proboscis monkey's nose can grow up to 7 inches long and amplifies its calls to attract mates and warn rivals",
    "Owls cannot move their eyes in their sockets, so they must turn their heads up to 270 degrees to look around",
    "The electric eel can generate shocks of up to 860 volts, enough to stun a horse",
    # Science & Technology (50)
    "A single bolt of lightning contains enough energy to toast 100,000 slices of bread",
    "The human brain generates about 23 watts of power, enough to power a small LED light bulb",
    "Diamond is the hardest natural material but graphite (pencil lead) is one of the softest, despite both being pure carbon",
    "A teaspoon of neutron star material would weigh about 6 billion tons on Earth",
    "The fingerprints of koalas are so similar to humans that they've confused crime scene investigators",
    "Water can boil and freeze at the same time in a phenomenon called the triple point, occurring at exactly 0.01°C and specific pressure",
    "The average smartphone today has more computing power than the computers used to send astronauts to the moon in 1969",
    "Glass is technically a liquid, not a solid, though it flows so slowly it appears solid at room temperature",
    "The human eye can distinguish approximately 10 million different colors",
    "Bananas are naturally radioactive due to their high potassium-40 content, emitting about one decay per second",
    "The speed of light is exactly 299,792,458 meters per second, and this defines the length of a meter",
    "A single gram of DNA can theoretically store 215 petabytes of data, or about 215 million gigabytes",
    "The average person produces enough saliva in their lifetime to fill two swimming pools",
    "Helium is the only element that cannot be solidified by lowering temperature alone - it requires pressure too",
    "The human body contains approximately 37.2 trillion cells, and we share 99.9% of our DNA with every other human",
    "Sound travels about 4.3 times faster through water than through air, at roughly 3,320 miles per hour underwater",
    "The smell of rain is caused by a chemical called geosmin, which humans can detect at concentrations as low as 5 parts per trillion",
    "Your stomach acid is strong enough to dissolve razor blades, with a pH between 1.5 and 3.5",
    "The International Space Station orbits Earth at 17,500 miles per hour, completing one orbit every 90 minutes",
    "Hot water can freeze faster than cold water under certain conditions, a phenomenon called the Mpemba effect",
    "The human nose can remember 50,000 different scents and detect some odors in concentrations as low as one part per trillion",
    "A single solar panel in space can generate about 100 times more energy than the same panel on Earth",
    "The coldest temperature ever recorded on Earth was -128.6°F in Antarctica in 1983",
    "Graphene is 200 times stronger than steel but is only one atom thick",
    "The human heart pumps about 2,000 gallons of blood through 60,000 miles of blood vessels every single day",
    "Rubber bands last longer when refrigerated because the cold temperature slows the polymer breakdown",
    "A photon takes about 8 minutes and 20 seconds to travel from the sun to Earth, covering 93 million miles",
    "The human body emits visible light that's about 1,000 times weaker than our eyes can detect",
    "Superglue was accidentally invented twice - first in 1942 and again in 1951 - before its usefulness was recognized",
    "The Earth's core is as hot as the surface of the sun, reaching temperatures of about 10,800°F",
    "A single CPU in a modern computer can perform billions of calculations per second",
    "Honey never spoils - archaeologists found 3,000-year-old honey in Egyptian tombs that was still perfectly edible",
    "The average lightning bolt is only about 1 inch wide but carries 300 million volts of electricity",
    "Your bones are about five times stronger than steel of the same weight",
    "The human brain uses 20% of the body's energy despite being only 2% of its weight",
    "Aerogel is 99.8% air and is the lightest solid material known, yet it can support 4,000 times its own weight",
    "A sunset on Mars appears blue due to the way dust particles scatter light in the Martian atmosphere",
    "The average person will walk the equivalent of five times around the Earth in their lifetime",
    "Batteries were invented before scientists understood how electricity worked",
    "The human eye can detect a candle flame from 30 miles away on a clear, dark night",
    "Helium changes your voice because sound travels faster through it than through air - about 3 times faster",
    "The Burj Khalifa in Dubai is so tall that you can watch the sunset from the base, then take the elevator up and watch it again",
    "A single strand of spider silk is stronger than steel of the same thickness and can stretch up to 40% longer than its original length",
    "The Earth's magnetic field flips every 200,000 to 300,000 years on average, though it's been 780,000 years since the last flip",
    "The human body contains enough iron to make a 3-inch nail",
    "Quantum entanglement allows two particles to instantly affect each other regardless of the distance between them",
    "The Great Barrier Reef is the largest living structure on Earth and is visible from space",
    "A single lightning strike can heat the air around it to 54,000°F, five times hotter than the surface of the sun",
    "The human immune system destroys at least one cell every day that would have become cancer if left alone",
    "Water expands by 9% when it freezes, which is why ice floats and pipes burst in winter",
    # History & Geography (50)
    "The Great Wall of China is not visible from space with the naked eye, contrary to popular belief",
    "Cleopatra lived closer in time to the Moon landing than to the construction of the Great Pyramid of Giza",
    "Oxford University is older than the Aztec Empire - teaching began at Oxford around 1096, while the Aztecs founded Tenochtitlan in 1325",
    "The shortest war in history lasted only 38 minutes between Britain and Zanzibar on August 27, 1896",
    "Mount Everest grows about 4 millimeters higher every year due to tectonic plate movement",
    "The Sahara Desert was a lush, green landscape with lakes and vegetation just 6,000 years ago",
    "More people live inside this circle around Southeast Asia than outside of it - containing 55% of the world's population",
    "The city of Istanbul is the only city in the world located on two continents - Europe and Asia",
    "There are more pyramids in Sudan (over 200) than in Egypt (around 138)",
    "The longest place name in the world is Taumatawhakatangihangakoauauotamateaturipukakapikimaungahoronukupokaiwhenuakitanatahu in New Zealand, with 85 letters",
    "Russia spans 11 time zones, the most of any country in the world",
    "The Dead Sea is so salty that you cannot sink in it - the water's density is 1.24 kg/L compared to regular seawater's 1.03 kg/L",
    "Antarctica is the driest continent on Earth, with some areas receiving no rainfall for over 2 million years",
    "The Roman Empire lasted over 1,000 years if you count the Byzantine Empire as its continuation, ending in 1453",
    "There are no rivers in Saudi Arabia - the entire country has no permanent rivers or lakes",
    "The Atlantic Ocean is growing wider by about 1.5 inches per year due to seafloor spreading",
    "Napoleon Bonaparte was actually of average height for his time at 5'7\", not short as commonly believed",
    "The ancient Egyptians used sleds and water to move massive pyramid stones, pouring water to reduce friction",
    "Vatican City is the smallest country in the world at only 0.17 square miles, smaller than most shopping malls",
    "The Mongol Empire was the largest contiguous land empire in history, covering over 9 million square miles at its peak",
    "Alaska is simultaneously the westernmost, easternmost, and northernmost state in the US due to the Aleutian Islands crossing the 180th meridian",
    "The oldest known musical instruments are flutes made from bird bones and mammoth ivory, dating back 43,000 years",
    "The city of Venice is built on over 100 small islands and has 400 bridges connecting them",
    "The Pacific Ocean is larger than all of Earth's land area combined, covering 63 million square miles",
    "The Declaration of Independence was written on hemp paper, not regular tree-based paper",
    "Maine is the closest US state to Africa, with the distance from Quoddy Head to El Beddouza, Morocco being about 3,154 miles",
    "The ancient city of Petra in Jordan was lost to the Western world for over 1,000 years until its rediscovery in 1812",
    "The Netherlands is below sea level for about 26% of its land area, protected by an extensive system of dikes",
    "The Hundred Years' War actually lasted 116 years, from 1337 to 1453",
    "Lake Baikal in Russia contains 20% of the world's fresh water and is the deepest lake on Earth at 5,387 feet",
    "The ancient Library of Alexandria is estimated to have contained between 400,000 and 1,000,000 scrolls before its destruction",
    "The Eiffel Tower can be 6 inches taller during summer due to thermal expansion of the iron",
    "The ancient Romans used urine as mouthwash due to its ammonia content, which whitens teeth",
    "More than 90% of the world's fresh water is locked in Antarctic ice",
    "The city of Constantinople (modern Istanbul) was besieged 23 times over its 1,600-year history",
    "The Inca Empire had no written language, instead using a system of knotted strings called quipu to record information",
    "The assassination of Archduke Franz Ferdinand started a chain reaction that led to World War I within six weeks",
    "The ancient Greeks used a computer-like device called the Antikythera mechanism to predict astronomical positions 2,000 years ago",
    "The Amazon River discharges more water than the next seven largest rivers combined, about 209,000 cubic meters per second",
    "Finland has more saunas than cars - approximately 3.3 million saunas for 5.5 million people",
    "The original Olympic Games were held for nearly 1,200 years before being banned by Roman Emperor Theodosius I in 393 AD",
    "The ancient Sumerian civilization invented writing, the wheel, and the concept of time divided into 60-second minutes around 3500 BC",
    "The Berlin Wall stood for 10,316 days, and as of 2018, it has been down longer than it was up",
    "The Grand Canyon is so vast that you could fit 19 Statue of Liberties stacked on top of each other inside it at its deepest point",
    "The Yellowstone supervolcano erupts roughly every 600,000 years, and it's been about 640,000 years since the last eruption",
    "The ancient city of Rome had a better water supply system than many modern cities, with 11 aqueducts delivering over 300 gallons per person daily",
    "The Great Pyramid of Giza was the tallest man-made structure for 3,800 years until the Lincoln Cathedral was completed in 1311",
    "The country of Liechtenstein once sent 80 soldiers to war and returned with 81 - they made a friend",
    "The island of Madagascar is home to 5% of all plant and animal species on Earth, with 80% found nowhere else",
    "The ancient city of Pompeii was preserved almost perfectly under volcanic ash for 1,700 years after Mount Vesuvius erupted in 79 AD",
    # Human Body & Health (25)
    "Your brain continues to develop and change throughout your entire life in a process called neuroplasticity",
    "Human bones are constantly being broken down and rebuilt, completely replacing themselves every 7-10 years",
    "The human body contains about 100,000 miles of blood vessels - enough to circle Earth four times",
    "Your liver can regenerate to its full size from as little as 25% of its original tissue",
    "The human eye has a resolution of about 576 megapixels, far superior to any camera",
    "Your stomach lining replaces itself every 3-4 days to prevent it from digesting itself",
    "Humans shed about 1.5 pounds of skin cells every year, replacing the entire outer layer every 28 days",
    "The human heart creates enough pressure to squirt blood 30 feet across a room",
    "Your left lung is smaller than your right lung to make room for your heart",
    "The acid in your stomach is strong enough to dissolve metal, but the stomach lining protects itself by secreting new mucus every two weeks",
    "Humans are bioluminescent and glow in the dark, but the light we emit is 1,000 times weaker than our eyes can detect",
    "The human brain can process images in as little as 13 milliseconds, faster than a single frame of most videos",
    "Your taste buds live for only about 10-14 days before being replaced by new ones",
    "The human sneeze travels at about 100 miles per hour and can spread droplets up to 26 feet away",
    "Babies are born with about 300 bones, but adults have only 206 because many fuse together during growth",
    "The human body produces about 25 million new cells every second",
    "Your ears never stop growing throughout your entire life, growing about 0.22 millimeters per year",
    "The strongest muscle in the human body relative to its size is the masseter, or jaw muscle",
    "Humans can distinguish between at least one trillion different smells, far more than previously thought",
    "Your brain uses about 400 calories per day, even when you're just sitting still",
    "The human appendix may actually help beneficial bacteria recover after intestinal infections",
    "Fingernails grow about four times faster than toenails, averaging 3.5 millimeters per month",
    "The human body has enough carbon to fill 900 pencils, enough iron for one 3-inch nail, and enough phosphorus for 2,200 match heads",
    "Your brain can survive for 4-6 minutes without oxygen before permanent damage begins",
    "Humans are the only animals that produce emotional tears - crying from sadness or joy rather than just eye irritation",
    # Space & Astronomy (25)
    "A day on Venus is longer than its year - Venus takes 243 Earth days to rotate but only 225 to orbit the sun",
    "There are more stars in the universe than grains of sand on all of Earth's beaches combined",
    "Neutron stars are so dense that a sugar-cube-sized amount would weigh about 1 billion tons on Earth",
    "The footprints on the moon will remain there for millions of years because there's no wind or water to erode them",
    "Saturn's rings are made of billions of pieces of ice and rock, some as small as grains of sand and others as large as mountains",
    "A year on Mercury is only 88 Earth days, making it the shortest year of any planet in our solar system",
    "The sun makes up 99.86% of the total mass of our entire solar system",
    "If you could compress Earth to the size of a marble, it would become a black hole",
    "The largest known star, UY Scuti, is about 1,700 times larger than our sun",
    "Space is completely silent because there's no atmosphere for sound waves to travel through",
    "The Voyager 1 spacecraft, launched in 1977, is now over 14 billion miles from Earth and still sending data",
    "Jupiter's Great Red Spot is a storm that has been raging for at least 400 years and is larger than Earth",
    "There are more than 200 billion galaxies in the observable universe, each containing billions of stars",
    "The coldest place in the universe that we know of is the Boomerang Nebula, at just 1 degree above absolute zero",
    "Mars has the largest volcano in the solar system - Olympus Mons stands 16 miles high, nearly three times the height of Mount Everest",
    "One million Earths could fit inside the sun, and the sun is considered a medium-sized star",
    "The universe is expanding at an accelerating rate of approximately 73 kilometers per second per megaparsec",
    "A full NASA spacesuit costs about $12 million, with the backpack alone costing $3.2 million",
    "The moon is moving away from Earth at a rate of about 1.5 inches per year",
    "On Neptune, winds can reach speeds of up to 1,200 miles per hour, the fastest in the solar system",
    "The Andromeda Galaxy is moving toward the Milky Way at 250,000 miles per hour and will collide with us in about 4 billion years",
    "Black holes can spin at nearly the speed of light, completing a rotation in milliseconds despite being millions of miles across",
    "The largest known structure in the universe is the Hercules-Corona Borealis Great Wall, spanning 10 billion light-years",
    "Time moves slower in stronger gravitational fields - astronauts on the ISS age very slightly slower than people on Earth",
    "The temperature at the core of the sun is about 27 million degrees Fahrenheit, hot enough for nuclear fusion",
]

# 100 FALSE statements - equally detailed but completely made up
LIES = [
    # Fake Animal Facts (25)
    "Dolphins can recognize their reflection and apply makeup using specialized glands that produce colored oils they spread with their flippers",
    "The extinct dodo bird could hold its breath for 45 minutes underwater to hunt for fish, despite being commonly depicted as land-based",
    "Giraffes sleep standing up for exactly 8 hours each night and will collapse if woken during their REM cycle",
    "Penguins have a specialized organ called a 'thermal compass' that vibrates to help them navigate by sensing Earth's magnetic fields",
    "Cats can see ultraviolet light and radio waves, allowing them to detect Wi-Fi signals within a 50-foot radius",
    "Elephants can communicate through infrasound at frequencies so low they can send messages up to 500 miles through solid rock",
    "The average housefly experiences time 10,000 times faster than humans, making a single human second feel like 3 hours to them",
    "Squirrels plant approximately 90% of the trees in North America by strategically burying seeds in optimal growing locations",
    "Sharks must swim backwards for at least 10 minutes each day to clean their gills, or they will suffocate within 24 hours",
    "Butterflies can taste sweetness 200,000 times better than humans and are used in Switzerland to quality-test chocolate",
    "Owls can rotate their heads 360 degrees and continue spinning in the same direction up to three full rotations",
    "The narwhal's tusk contains 10 million nerve endings and can detect changes in barometric pressure up to 1,000 miles away",
    "Chameleons change color based on their mood and can produce over 16 million different color combinations, more than a computer monitor",
    "Kangaroos cannot walk backwards due to the structure of their leg joints, which is why Australia chose them for their coat of arms",
    "Bees dance in different dialects depending on their geographic region, and bees from different continents cannot understand each other",
    "Sea turtles return to the exact GPS coordinates where they were born, accurate to within 3 feet, using magnetite crystals in their brains",
    "Woodpeckers have shock-absorbing cartilage that extends from their beaks through their entire skeletal system to prevent concussions",
    "Hummingbirds are the only birds that can fly upside down for extended periods, which they do to confuse predators",
    "Hermit crabs hold democratic elections when choosing new shells, with each crab casting a vote by tapping its claws",
    "The blue whale's heart is the size of a small car and beats only 8 times per minute, but each beat can be heard from 2 miles away through the water",
    "Zebras' stripes are bioluminescent and glow faintly in the dark to help the herd stay together at night",
    "Platypuses can detect electrical fields so precisely that they can find a battery in the ocean from 3 miles away",
    "Arctic foxes change their fur color seasonally because individual hair follicles contain color-changing proteins triggered by day length",
    "Crows can count up to 1,000 and have been observed solving calculus-level problems in laboratory settings",
    "Tardigrades communicate using quantum entanglement, allowing instant communication across any distance",
    # Fake Science & Tech (25)
    "Silicon chips in computers contain microscopic tubes of liquid mercury that flow to different sections based on electrical signals",
    "The human appendix was originally used to digest tree bark, and people who eat a lot of fiber can reactivate this function",
    "Microwaves work by causing water molecules to vibrate at exactly the same frequency as middle C on a piano",
    "The average person's DNA contains genetic code from at least 50 different species due to ancient viral infections",
    "LED lights emit a small amount of vitamin D-producing UV radiation, which is why night shift workers using LEDs are healthier",
    "The smell of freshly cut grass is actually a sophisticated chemical defense system that can cause mild hallucinations in humans",
    "Your smartphone's battery lasts longer if you store it in the freezer overnight once per month",
    "The human brain operates on quantum principles and can process information faster than light in certain conditions",
    "Aluminum foil is made from recycled airplane parts and maintains some of the original aircraft's aerodynamic properties",
    "The Earth's core contains a perfect crystal sphere that resonates at 7.83 Hz, creating the Schumann resonance",
    "Glass older than 100 years develops crystalline structures that make it stronger than modern glass",
    "The speed of sound changes based on the listener's emotional state due to psychological time dilation effects",
    "Rubber was originally harvested from a now-extinct tree that produced 10 times more latex than modern rubber trees",
    "The human body produces a small amount of gold as a byproduct of cellular metabolism, about 0.2 milligrams per year",
    "Batteries work better when they're warm because heat increases the number of electrons available for discharge",
    "The periodic table originally had 150 elements before scientists realized many were just measurement errors",
    "A photon travels faster when observed, which is why quantum mechanics seems counterintuitive - we're changing reality by measuring it",
    "Your fingerprints change every 7 years as your skin cells regenerate, which is why old criminal records need updating",
    "The first computers used vacuum tubes filled with specially bred fireflies that would light up to indicate binary ones",
    "Static electricity is actually tiny electrical beings called 'staticules' that feed on the friction between materials",
    "The concept of zero was discovered independently in every culture on exactly the same date: November 7th of different years",
    "Water molecules can remember chemical compounds they've been exposed to, which is the scientific basis for homeopathy",
    "The strongest material ever created is a spider silk-diamond hybrid that can only be manufactured in zero gravity",
    "Quantum computers use particles in superposition, meaning they exist in all possible states until a user gets frustrated and reboots them",
    "The human brain has a dedicated section for processing memes, which evolved in the last 30 years due to internet exposure",
    # Fake History & Geography (25)
    "The Leaning Tower of Pisa was intentionally built at an angle as a tribute to the designer's crooked walking staff",
    "Mount Everest was named after Sir George Everest, who was the first person to climb it in 1841",
    "The Great Wall of China was originally built as a massive musical instrument, with different sections producing different notes when struck",
    "Ancient Romans invented concrete so strong that modern engineers still can't replicate it because the recipe was written in a code never deciphered",
    "The Bermuda Triangle has unusual magnetic properties because a massive iron meteorite is buried beneath the ocean floor",
    "Vikings wore horned helmets into battle, and the horns were filled with mead so they could drink while fighting",
    "The Statue of Liberty was originally intended for Egypt and depicts an Egyptian peasant woman holding a torch to light the Suez Canal",
    "Cleopatra was Greek, not Egyptian, and never learned to speak Egyptian during her entire reign",
    "The Dead Sea is dying - it loses 10% of its salt content every year and will be freshwater by 2075",
    "Ancient Egyptians used cat mummies as currency, with the exchange rate being one cat equals three loaves of bread",
    "The Aztecs predicted the Spanish conquest to the exact day, month, and year based on astronomical calculations",
    "Mount Rushmore was carved by using targeted lightning strikes to shape the rock, not conventional tools",
    "The Panama Canal changes the Earth's rotation speed by 0.0003% because it redistributes ocean water",
    "Antarctica was ice-free until 1823 when a sudden climate shift froze the continent in just 72 hours",
    "The ancient Library of Alexandria was actually burned down by accident when a librarian's oil lamp exploded during late-night organizing",
    "The Sahara Desert turns green for exactly 3 days every 47 years due to a rare meteorological phenomenon",
    "Napoleon was actually 6'2\" tall but appeared short in paintings because artists were required by law to depict him as humble",
    "The Eiffel Tower was built as a giant radio antenna to communicate with Mars during a close approach in 1889",
    "The Great Pyramid was originally covered in glass panels that focused sunlight into a beam visible from the moon",
    "The Titanic sinking was a publicity stunt gone wrong - the ship was supposed to narrowly avoid the iceberg for dramatic effect",
    "The Hundred Years' War ended because both sides forgot what they were fighting about after 100 years",
    "Genghis Khan's empire spanned so much territory that he created four time zones to make administration easier",
    "The ancient Colosseum in Rome had a retractable roof made of silk that could be deployed in under 15 minutes",
    "The first maps of the world were intentionally distorted to hide the locations of treasure islands from rival nations",
    "The Great Fire of London in 1666 was started by a time traveler's malfunctioning hoverboard",
    # Fake Human Body (13)
    "Humans have a vestigial third eye in the center of their forehead that's covered by bone but can still detect light through the skull",
    "Your liver filters all the blood in your body exactly 100 times per day, completing one full cycle every 14.4 minutes",
    "The human body contains a small amount of gold concentrated in the left big toe, remnants of ancient evolutionary exposure",
    "Fingernails grow faster on your dominant hand because of increased electrical activity from nerve signals",
    "Humans can breathe through their skin in emergency situations, absorbing up to 15% of their oxygen needs this way",
    "Your stomach has taste buds inside it that detect protein content and signal your brain about nutritional value",
    "The human eye can see individual atoms if the lighting conditions are perfect and you're looking at a white background",
    "Your appendix serves as a 'backup drive' for beneficial gut bacteria, storing exact copies for up to 20 years",
    "Babies are born with the ability to breathe underwater for up to 30 minutes, but lose this ability by age 6 months",
    "The human brain doubles in size during REM sleep due to increased fluid intake from the spinal column",
    "Your lungs are different sizes not for your heart, but because the right lung specializes in oxygen while the left handles carbon dioxide",
    "Humans shed and regrow their stomach lining completely every 48 hours, going through over 180 stomachs in a lifetime",
    "Your ears grow throughout life because they're made of cartilage that absorbs sound waves and expands with each vibration",
    # Fake Space (12)
    "The moon is slowly turning green due to algae spores from Earth that reached it on Apollo missions and are now spreading",
    "Mars appears red because the entire planet is covered in rust from ancient oceans that contained dissolved iron",
    "The sun goes through a 'dark phase' for 3 minutes every century where it stops emitting light completely",
    "Jupiter's Great Red Spot is actually a portal to another dimension that opens and closes based on gravitational tides",
    "Saturn's rings will completely disappear by 2025 as they fall into the planet at an accelerating rate",
    "Black holes emit a sound at exactly 57 octaves below middle C, which can be heard with special space microphones",
    "The International Space Station has to dodge space debris an average of 47 times per day",
    "Pluto was reclassified as a dwarf planet because it started drifting out of its orbit toward the edge of the solar system",
    "The Milky Way galaxy smells like raspberries and rum due to ethyl formate in interstellar gas clouds",
    "Astronauts grow 6 inches taller in space permanently - the spine expansion doesn't reverse upon returning to Earth",
    "The sun is actually getting larger by 0.01% every year and will engulf Mercury by the year 2500",
    "Venus used to rotate normally but a massive asteroid impact reversed its direction 800 years ago",
]


class GameContent:
    """Generates randomized game rounds with 2 truths and 1 lie each.

    Usage:
        game = GameContent(num_rounds=5)
        rounds_text = game.get_formatted_rounds()
    """

    def __init__(self, num_rounds: int = 5):
        """Initialize and generate all rounds.

        Args:
            num_rounds: Number of rounds to pre-generate (default: 5)
        """
        self.num_rounds = num_rounds
        self.rounds = self._generate_rounds()

    def _generate_rounds(self) -> List[List[Tuple[str, bool]]]:
        """Generate all rounds with randomized truths and lies."""
        available_truths = TRUTHS.copy()
        available_lies = LIES.copy()
        random.shuffle(available_truths)
        random.shuffle(available_lies)

        rounds = []
        for _ in range(self.num_rounds):
            # Replenish if needed
            if len(available_truths) < 2:
                random.shuffle(available_truths)
            if len(available_lies) < 1:
                random.shuffle(available_lies)

            # Get 2 truths and 1 lie
            truth1 = available_truths.pop()
            truth2 = available_truths.pop()
            lie = available_lies.pop()

            # Randomize order
            statements = [(truth1, True), (truth2, True), (lie, False)]
            random.shuffle(statements)

            rounds.append(statements)

        return rounds

    def get_formatted_rounds(self) -> str:
        """Get all rounds formatted for the LLM system instruction.

        Returns:
            Formatted string with all rounds, including lie positions
        """
        rounds_text = []
        for i, statements in enumerate(self.rounds, 1):
            # Find lie position
            lie_num = next((j for j, (_, is_truth) in enumerate(statements, 1) if not is_truth), 1)

            # Format statements
            formatted = "\n".join(f"{j}. {stmt}" for j, (stmt, _) in enumerate(statements, 1))
            rounds_text.append(f"ROUND {i} (Lie is #{lie_num}):\n{formatted}")

        return "\n\n".join(rounds_text)
