"""Card carousel with two-shell transit and post-snap artwork restoration."""

import lvgl as lv
import random
from time import ticks_ms
try:
    from time import ticks_diff
except ImportError:
    def ticks_diff(new, old):
        return new - old

WIDTH = 240
HEIGHT = 280

# Keep full card art pre-sized to the card art window for best badge performance.
# Recommended full art size: 142 x 198, RGB565 .bin, LVGL compatible path.
LOCKED_IMAGE_SRC = "A:/cards/cover.bin"
UNLOCKED_IMAGE_SRC = LOCKED_IMAGE_SRC

ACR_FOIL_COLORS = (
    0x38E8FF,
    0x4D7CFF,
    0xBF5FFF,
    0xFF4FD8,
    0xFFD45C,
    0x45F0A0,
)
ACR_EFFECT_TIMER_MS = 50
ACR_GLINT_SRC = "A:/cards/acr_glint.bin"
ACR_GLINT_SOURCES = (
    "A:/cards/acr_glint_left.bin",
    ACR_GLINT_SRC,
    "A:/cards/acr_glint_right.bin",
)

COLORS = {
    "black": 0x03070A,
    "panel": 0x08131A,
    "panel_2": 0x0C2027,
    "panel_3": 0x102A33,
    "green": 0xBF5FFF,
    "green_dim": 0x5C2499,
    "cyan": 0x38E8FF,
    "amber": 0xFFB000,
    "red": 0xFF3B45,
    "white": 0xD8F3E2,
    "muted": 0x6C9384,
}

# Replace the image_src values with your final card art paths.
# Locked cards still keep their real image_src, but the carousel shows
# LOCKED_IMAGE_SRC until unlocked.
CARDS = [
    {
        'id': 'F35-01',
        'title': 'F-35 LIGHTNING II',
        'subtitle': 'MULTIROLE',
        'max_speed': 'Mach 1.6',
        'use_case': 'Stealth multirole strike, sensing, and networked operations.',
        'facts': [
            'The F-35A, F-35B, and F-35C share one design for three basing needs.',
            'Sensor fusion combines onboard sensor data into a single tactical picture.',
            'The F-35B can perform short takeoffs and vertical landings.',
        ],
        'detail': 'The F-35 Lightning II is a family of fifth-generation aircraft built around '
                  'stealth, sensor fusion, electronic warfare, and secure data sharing. Its three '
                  'variants support conventional runways, short or vertical operations, and '
                  'aircraft-carrier operations.',
        'unlocked': False,
        'image_src': 'A:/cards/F35.bin',
        'thumb_src': None,
    },
    {
        'id': 'F22-02',
        'title': 'F-22 RAPTOR',
        'subtitle': 'AIR SUPERIORITY',
        'max_speed': 'Mach 2+',
        'use_case': 'Stealth air superiority and first-look air dominance.',
        'facts': [
            'The F-22 became operational with the U.S. Air Force in 2005.',
            'Supercruise allows sustained supersonic flight without afterburner.',
            'Two-dimensional thrust-vectoring nozzles improve maneuverability.',
        ],
        'detail': 'The F-22 Raptor combines stealth, supercruise, advanced sensors, and high '
                  'maneuverability for air-dominance missions. Lockheed Martin produced 195 F-22 '
                  'aircraft, including test aircraft, for the U.S. Air Force.',
        'unlocked': False,
        'image_src': 'A:/cards/F22.bin',
        'thumb_src': None,
    },
    {
        'id': 'F16-03',
        'title': 'F-16 FIGHTING FALCON',
        'subtitle': 'MULTIROLE FIGHTER',
        'max_speed': 'Mach 2',
        'use_case': 'Air-to-air combat and precision strike.',
        'facts': [
            'The F-16 uses a fly-by-wire flight-control system and a side-stick controller.',
            'Block 70/72 aircraft use the APG-83 active electronically scanned array radar.',
            'New Block 70/72 airframes are designed for a 12,000-hour service life.',
        ],
        'detail': 'The F-16 Fighting Falcon is a lightweight multirole fighter used by operators '
                  'around the world. Modern Block 70/72 aircraft add an advanced radar, updated '
                  'avionics, and an extended structural service life.',
        'unlocked': False,
        'image_src': 'A:/cards/F16.bin',
        'thumb_src': None,
    },
    {
        'id': 'C130-04',
        'title': 'C-130 HERCULES',
        'subtitle': 'TACTICAL AIRLIFT',
        'max_speed': 'Approx. 417 mph',
        'use_case': 'Tactical airlift and specialized mission support.',
        'facts': [
            'The Hercules has remained in continuous production since 1954.',
            'C-130 variants have been adapted for more than 20 different mission sets.',
            'The C-130J uses four Rolls-Royce AE 2100D3 turboprop engines.',
        ],
        'detail': 'The C-130 Hercules family supports tactical airlift, aerial refueling, search '
                  'and rescue, firefighting, special operations, weather reconnaissance, and '
                  'numerous other missions from established or austere airfields.',
        'unlocked': False,
        'image_src': 'A:/cards/C130.bin',
        'thumb_src': None,
    },
    {
        'id': 'VEC-05',
        'title': 'VECTIS',
        'subtitle': 'COLLABORATIVE COMBAT',
        'max_speed': 'Not publicly disclosed',
        'use_case': 'Uncrewed collaborative combat operations.',
        'facts': [
            'Vectis is being developed by Lockheed Martin Skunk Works.',
            'It is designed to operate independently or team with crewed aircraft.',
            'Its open mission architecture is intended to support rapid capability updates.',
        ],
        'detail': 'Vectis is a survivable collaborative combat aircraft designed to work alongside '
                  'platforms such as the F-35 and future crewed aircraft. Its design emphasizes '
                  'autonomy, mission-system flexibility, and affordable mass.',
        'unlocked': False,
        'image_src': 'A:/cards/Vectis.bin',
        'thumb_src': None,
    },
    {
        'id': 'NASA-06',
        'title': 'ORION CAPSULE',
        'subtitle': 'DEEP-SPACE CREW',
        'use_case': 'Crew transport for lunar exploration and other deep-space missions.',
        'facts': [
            'The crew module provides a pressurized space where astronauts live and work.',
            'Its heat shield protects the capsule from temperatures near 5,000 degrees Fahrenheit during reentry.',
            'A system of parachutes slows Orion to about 20 mph before ocean splashdown.',
        ],
        'detail': 'Orion is a deep-space spacecraft developed by NASA with Lockheed Martin as '
                'the lead contractor. It carries and sustains astronauts during Artemis '
                'missions to the Moon, withstands high-speed atmospheric reentry, and '
                'returns its crew safely to Earth by parachute-assisted splashdown.',
        'unlocked': False,
        'image_src': 'A:/cards/Orion.bin',
        'thumb_src': None,
    },
    {
        'id': 'U2-07',
        'title': 'U-2 DRAGON LADY',
        'subtitle': 'HIGH ALT RECON',
        'max_speed': 'Approx. 410 mph',
        'use_case': 'High-altitude intelligence, surveillance, and reconnaissance.',
        'facts': [
            'The first U-2 flew in 1955 after development by Skunk Works.',
            'Its sailplane-like wings allow operation above 70,000 feet.',
            'Pilots wear pressure suits because the aircraft operates near the edge of space.',
        ],
        'detail': 'The U-2 Dragon Lady is a high-altitude intelligence, surveillance, and '
                  'reconnaissance aircraft with a service history spanning more than seven '
                  'decades. Its modular payloads support imagery, signals, and electronic sensing.',
        'unlocked': False,
        'image_src': 'A:/cards/U2 Dragon.bin',
        'thumb_src': None,
    },
    {
        'id': 'DSTAR-08',
        'title': 'DARK STAR',
        'subtitle': 'HYPERSONIC CONCEPT',
        'max_speed': 'Mach 10 in film',
        'use_case': 'Fictional high-speed reconnaissance concept.',
        'facts': [
            'Darkstar was created as a fictional aircraft for Top Gun: Maverick.',
            "Skunk Works engineers collaborated with the film's production team.",
            'The full-size movie prop was designed to look like a plausible hypersonic aircraft.',
        ],
        'detail': 'Darkstar is a fictional hypersonic aircraft created for Top Gun: Maverick with '
                  'help from Lockheed Martin Skunk Works. It was a cinematic design concept, not a '
                  'publicly acknowledged operational aircraft program.',
        'unlocked': False,
        'image_src': 'A:/cards/Darkstar.bin',
        'thumb_src': None,
    },
    {
        'id': 'F117-09',
        'title': 'F-117 NIGHTHAWK',
        'subtitle': 'STEALTH ATTACK',
        'max_speed': 'High subsonic',
        'use_case': 'Low-observable precision strike.',
        'facts': [
            "The F-117 was the world's first operational stealth aircraft.",
            'Its first flight occurred in 1981, and it became operational in 1983.',
            'Lockheed Martin built 59 production aircraft and five development aircraft.',
        ],
        'detail': 'The F-117 Nighthawk used faceted surfaces and radar-absorbent materials to '
                  'reduce its radar signature. Developed in secrecy by Skunk Works, it '
                  'demonstrated the operational value of stealth during precision-strike missions.',
        'unlocked': False,
        'image_src': 'A:/cards/F117.bin',
        'thumb_src': None,
    },
    {
        'id': 'X59-10',
        'title': 'X-59 QUESST',
        'subtitle': 'LOW-BOOM X-PLANE',
        'max_speed': 'Supersonic',
        'use_case': 'Quiet-supersonic flight research.',
        'facts': [
            "Lockheed Martin Skunk Works built the X-59 for NASA's Quesst mission.",
            'Its shape is designed to produce a quiet sonic thump instead of a loud boom.',
            'The X-59 completed its first supersonic flight on June 5, 2026.',
        ],
        'detail': "The X-59 is NASA's experimental quiet-supersonic research aircraft. NASA plans "
                  'to use flight and community-response data to help regulators evaluate rules '
                  'that currently restrict civilian supersonic flight over land.',
        'unlocked': False,
        'image_src': 'A:/cards/X59.bin',
        'thumb_src': None,
    },
    {
        'id': 'C5-11',
        'title': 'C-5 GALAXY',
        'subtitle': 'HEAVY AIRLIFT',
        'max_speed': 'Approx. 518 mph',
        'use_case': 'Strategic transport of oversized and heavy cargo.',
        'facts': [
            'The C-5 can load cargo through both its raised nose and rear doors.',
            'Its kneeling landing gear lowers the cargo deck for loading and unloading.',
            'C-5M upgrades added modern engines, avionics, and reliability improvements.',
        ],
        'detail': 'The C-5 Galaxy is a strategic airlifter built to transport oversized equipment '
                  'across intercontinental distances. The modernized C-5M Super Galaxy provides '
                  'greater range, reliability, and fuel efficiency.',
        'unlocked': False,
        'image_src': 'A:/cards/C-5 Galaxy.bin',
        'thumb_src': None,
    },
    {
        'id': 'SR71-12',
        'title': 'SR-71 BLACKBIRD',
        'subtitle': 'STRAT RECON',
        'max_speed': 'Mach 3.2+',
        'use_case': 'High-altitude strategic reconnaissance.',
        'facts': [
            'The SR-71 first flew on December 22, 1964.',
            'It routinely operated above Mach 3 and at altitudes above 80,000 feet.',
            'An SR-71 set a 2,193.64 mph absolute speed record in 1976.',
        ],
        'detail': 'The SR-71 Blackbird was a long-range reconnaissance aircraft developed by '
                  'Skunk Works. Its titanium structure, specialized fuel, inlet system, and '
                  'heat-dissipating black finish supported sustained flight above Mach 3.',
        'unlocked': False,
        'image_src': 'A:/cards/SR-71 Blackbird.bin',
        'thumb_src': None,
    },
    {
        'id': 'APY9-13',
        'title': 'AN/APY-9 RADAR',
        'subtitle': 'AIRBORNE EARLY WARN',
        'use_case': 'Carrier-based airborne early warning and surveillance.',
        'facts': [
            "The AN/APY-9 is the primary radar aboard the Navy's E-2D Advanced Hawkeye.",
            'Its UHF electronically scanned array provides continuous 360-degree coverage.',
            'The radar is designed to track aircraft and cruise-missile threats over land and sea.',
        ],
        'detail': 'The Lockheed Martin AN/APY-9 combines electronic and mechanical scanning to '
                  'provide long-range airborne surveillance. It gives E-2D crews a wide-area '
                  'picture of air and surface activity in demanding littoral environments.',
        'unlocked': False,
        'image_src': 'A:/cards/AN APY-9 Radar.bin',
        'thumb_src': None,
    },
    {
        'id': 'FPS117-14',
        'title': 'AN/FPS-117 RADAR',
        'subtitle': 'LONG-RANGE RADAR',
        'use_case': 'Long-range ground-based air surveillance.',
        'facts': [
            'The AN/FPS-117 is a three-dimensional L-band solid-state radar.',
            'It can provide air surveillance at ranges out to approximately 250 miles.',
            'The radar was designed for reliable operation at remote, minimally attended sites.',
        ],
        'detail': 'The AN/FPS-117 is a fixed long-range surveillance radar used for airspace '
                  'monitoring and early warning. Its solid-state design and remote-operation '
                  'features have supported installations in harsh environments worldwide.',
        'unlocked': False,
        'image_src': 'A:/cards/FPS-117.bin',
        'thumb_src': None,
    },
    {
        'id': 'GPS3-15',
        'title': 'GPS III',
        'subtitle': 'NAVIGATION SATELLITE',
        'use_case': 'Global positioning, navigation, and precision timing.',
        'facts': [
            'GPS III provides up to three times better accuracy than earlier GPS spacecraft.',
            'It offers up to eight times greater anti-jamming capability.',
            'Its L1C civil signal improves compatibility with other navigation constellations.',
        ],
        'detail': 'Lockheed Martin-built GPS III satellites modernize the Global Positioning '
                  'System with stronger military signals, improved accuracy, greater resilience, '
                  'and a modular design prepared for future upgrades.',
        'unlocked': False,
        'image_src': 'A:/cards/GPS III.bin',
        'thumb_src': None,
    },
    {
        'id': 'HIMARS-16',
        'title': 'HIMARS',
        'subtitle': 'ROCKET ARTILLERY',
        'use_case': 'Mobile long-range precision fires.',
        'facts': [
            'HIMARS carries one interchangeable rocket or missile launch pod.',
            'The launcher is transportable aboard a C-130 aircraft.',
            'Its supported munitions span rockets and tactical missiles for varied ranges.',
        ],
        'detail': 'The High Mobility Artillery Rocket System combines a wheeled vehicle with the '
                  'MLRS family of precision munitions. Its mobility lets crews fire, relocate, '
                  'reload, and support dispersed operations.',
        'unlocked': False,
        'image_src': 'A:/cards/HIMARS.bin',
        'thumb_src': None,
    },
    {
        'id': 'FIREHERC-17',
        'title': 'LM-100J FIREHERC',
        'subtitle': 'AERIAL FIREFIGHTER',
        'max_speed': 'Approx. 417 mph',
        'use_case': 'Low-level aerial delivery of wildfire retardant.',
        'facts': [
            'FireHerc is a firefighting airtanker based on the civil-certified LM-100J.',
            'It builds on more than 40 years of Hercules firefighting operations.',
            'The aircraft can support gravity-fed RADS or pressurized MAFFS II retardant systems.',
        ],
        'detail': 'The LM-100J FireHerc adapts the Super Hercules design for aerial firefighting. '
                  'Its straight wing, turboprop power, modern flight deck, and austere-field '
                  'heritage suit demanding low-altitude and low-speed missions.',
        'unlocked': False,
        'image_src': 'A:/cards/LM-100J FireHerc.bin',
        'thumb_src': None,
    },
    {
        'id': 'LRASM-18',
        'title': 'LRASM',
        'subtitle': 'ANTI-SHIP MISSILE',
        'use_case': 'Long-range precision strike against defended surface ships.',
        'facts': [
            'LRASM is derived from the AGM-158B JASSM-ER airframe.',
            'Its multimode sensor suite supports operations in contested environments.',
            'The missile is operationally integrated on the B-1B and F/A-18E/F.',
        ],
        'detail': 'The AGM-158C Long Range Anti-Ship Missile is a survivable, precision-guided '
                  'standoff weapon. It combines long range, autonomous targeting features, and a '
                  'low-observable airframe for maritime strike missions.',
        'unlocked': False,
        'image_src': 'A:/cards/LRASM.bin',
        'thumb_src': None,
    },
    {
        'id': 'NGSRI-19',
        'title': 'NGSRI QUADSTAR',
        'subtitle': 'SHORT-RANGE DEFENSE',
        'use_case': 'Portable defense against aircraft and uncrewed systems.',
        'facts': [
            "QuadStar is Lockheed Martin's offering for the Army's NGSRI competition.",
            'The program is intended to replace the legacy Stinger missile.',
            'QuadStar completed its first flight test in January 2026.',
        ],
        'detail': 'The Next-Generation Short-Range Interceptor is designed to counter uncrewed '
                  'aircraft, helicopters, and fixed-wing threats. The QuadStar design uses a '
                  'modern open architecture and modular components for future upgrades.',
        'unlocked': False,
        'image_src': 'A:/cards/NGSRI.bin',
        'thumb_src': None,
    },
    {
        'id': 'NOMAD-20',
        'title': 'SIKORSKY NOMAD',
        'subtitle': 'AUTONOMOUS VTOL',
        'max_speed': 'Not publicly disclosed',
        'use_case': 'Runway-independent reconnaissance, logistics, and light attack.',
        'facts': [
            'Nomad uses a twin-proprotor rotor-blown-wing design.',
            'It takes off and lands vertically, then cruises efficiently on its wing.',
            "The aircraft family uses Sikorsky's MATRIX autonomy technology.",
        ],
        'detail': 'Nomad is a scalable family of uncrewed aircraft combining helicopter-like '
                  'hover with fixed-wing speed, range, and endurance. The Nomad 100 completed its '
                  'initial ground and flight-test phase in 2026.',
        'unlocked': False,
        'image_src': 'A:/cards/Nomad.bin',
        'thumb_src': None,
    },
    {
        'id': 'PAC3-21',
        'title': 'PAC-3 MSE',
        'subtitle': 'MISSILE DEFENSE',
        'use_case': 'Terminal defense against ballistic missiles and airborne threats.',
        'facts': [
            'PAC-3 MSE destroys threats through direct hit-to-kill impact.',
            'Its two-pulse solid rocket motor increases interceptor range and altitude.',
            'Larger fins and upgraded actuators improve agility against advanced threats.',
        ],
        'detail': 'The PAC-3 Missile Segment Enhancement is a Patriot-system interceptor designed '
                  'to defeat tactical ballistic missiles, cruise missiles, aircraft, and other '
                  'advanced threats through body-to-body kinetic impact.',
        'unlocked': False,
        'image_src': 'A:/cards/PAC-3.bin',
        'thumb_src': None,
    },
    {
        'id': 'S97-22',
        'title': 'S-97 RAIDER',
        'subtitle': 'COMPOUND ROTORCRAFT',
        'max_speed': '207+ knots demonstrated',
        'use_case': 'High-speed armed reconnaissance and technology demonstration.',
        'facts': [
            'The S-97 uses coaxial counter-rotating rotors and a rear pusher propeller.',
            'It has demonstrated level-flight speeds above 200 knots.',
            'The aircraft served as a flying technology demonstrator for RAIDER X.',
        ],
        'detail': "Sikorsky's S-97 Raider demonstrates X2 compound-helicopter technology. Its "
                  'configuration combines precise low-speed handling with rapid acceleration, '
                  'tight high-speed turns, and speeds beyond conventional helicopters.',
        'unlocked': False,
        'image_src': 'A:/cards/S-97 Raider.bin',
        'thumb_src': None,
    },
    {
        'id': 'STALKER-23',
        'title': 'STALKER VXE30',
        'subtitle': 'SMALL UAS',
        'max_speed': 'Up to 58 mph',
        'use_case': 'Long-endurance portable intelligence and surveillance.',
        'facts': [
            'The Stalker VXE30 is a Group 2 vertical-takeoff-and-landing uncrewed aircraft.',
            'Its typical endurance is up to four hours on battery power.',
            'A propane fuel-cell configuration can extend endurance to eight hours.',
        ],
        'detail': 'Stalker VXE30 provides runway-independent imaging and surveillance in a '
                  'portable package. Its modular payloads, weather tolerance, and battery or '
                  'fuel-cell power options support extended field operations.',
        'unlocked': False,
        'image_src': 'A:/cards/Stalker VXE30.bin',
        'thumb_src': None,
    },
    {
        'id': 'THAAD-24',
        'title': 'THAAD',
        'subtitle': 'AREA MISSILE DEFENSE',
        'use_case': 'Terminal defense against ballistic missile threats.',
        'facts': [
            'THAAD counters short-, medium-, and intermediate-range ballistic missiles.',
            'Its interceptor uses hit-to-kill kinetic energy rather than an explosive warhead.',
            'THAAD can intercept threats inside or outside the atmosphere.',
        ],
        'detail': 'Terminal High Altitude Area Defense is a mobile missile-defense system built '
                  'around truck-mounted launchers, interceptors, radar, fire control, and support '
                  'equipment. It provides an upper tier of terminal-phase defense.',
        'unlocked': False,
        'image_src': 'A:/cards/THAAD.bin',
        'thumb_src': None,
    },
    {
        'id': 'UH60-25',
        'title': 'UH-60 BLACK HAWK',
        'subtitle': 'UTILITY HELICOPTER',
        'max_speed': 'Approx. 159 knots',
        'use_case': 'Tactical transport, assault, rescue, and mission support.',
        'facts': [
            'The Black Hawk family has accumulated more than 15 million flight hours.',
            'UH-60 variants serve in utility, medevac, special-operations, and rescue roles.',
            'The UH-60M adds digital avionics, improved engines, and wide-chord rotor blades.',
        ],
        'detail': 'The Sikorsky UH-60 Black Hawk is a twin-engine utility helicopter designed for '
                  'survivability and mission flexibility. Its adaptable airframe supports troop '
                  'transport, external lift, medical evacuation, and many specialized missions.',
        'unlocked': False,
        'image_src': 'A:/cards/UH-60.bin',
        'thumb_src': None,
    },

    # Blank ACR cards. The ACR-prefixed IDs preserve the badge's ACR-card handling.

    {
        'id': 'ACR-27',
        'title': 'SoFi',
        'detail': 'Currently she is trying to convince Lockheed Martin to put a padded cell at the ACR. #quiettime ',
        'unlocked': False,
        'image_src': 'A:/cards/SoFi.bin',
        'thumb_src': None,
    },
    {
        'id': 'ACR-29',
        'title': 'Beans',
        'detail': 'Beans. Just Beans.',
        'unlocked': False,
        'image_src': 'A:/cards/Beans.bin',
        'thumb_src': None,
    },
    {
        'id': 'ACR-30',
        'title': 'Jerry',
        'detail': 'Interests: Big Boats, Planes, and TUMS ',
        'unlocked': False,
        'image_src': 'A:/cards/Jerry.bin',
        'thumb_src': None,
    },
    {
        'id': 'ACR-31',
        'title': 'Broski',
        'detail': 'Everyone say hi Glock Bot ',
        'unlocked': False,
        'image_src': 'A:/cards/Glock Bot.bin',
        'thumb_src': None,
    },

    {
        'id': 'ACR-34',
        'title': 'Numbers',
        'detail': 'If you hear a high-pitched mechanical noise during a meeting, it is probably "Numbers". ',
        'unlocked': False,
        'image_src': 'A:/cards/Loud Fidget.bin',
        'thumb_src': None,
    },
    {
        'id': 'ACR-40',
        'title': 'myx',
        'detail': 'I\'m a big man Sponge, a big, big man',
        'unlocked': False,
        'image_src': 'A:/cards/mcx.bin',
        'thumb_src': None,
    },
    {
        'id': 'ACR-35',
        'title': 'Nyquist',
        'detail': '"The world will be right, if we are kind and polite." - Aunt Lucy',
        'unlocked': False,
        'image_src': 'A:/cards/Nyquist.bin',
        'thumb_src': None,
    },
    {
        'id': 'ACR-36',
        'title': 'Phlux',
        'detail': 'Phlux bought a $100 box of Riftbound cards on the company card ("by accident")',
        'unlocked': False,
        'image_src': 'A:/cards/Phlux.bin',
        'thumb_src': None,
    },
    {
        'id': 'ACR-37',
        'title': 'RiskyBlooky',
        'detail': 'If it ain\'t broke, nobody has tested it yet ',
        'unlocked': False,
        'image_src': 'A:/cards/Risky.bin',
        'thumb_src': None,
    },
    {
        'id': 'ACR-38',
        'title': 'Sharpie',
        'detail': 'Shit show Supervisor: Everyone say thank you Sharpie for sending the ACR team to DEFCON 34',
        'unlocked': False,
        'image_src': 'A:/cards/Sharpie n lil Sharpie.bin',
        'thumb_src': None,
    },
    {
        'id': 'ACR-39',
        'title': 'Synaptic Rodeo',
        'detail': 'Mother of dragons, architect of elegance, forging resilience one challenge at a time.',
        'unlocked': False,
        'image_src': 'A:/cards/Synaptic Rodeo.bin',
        'thumb_src': None,
    },
        {
        'id': 'ACR-26',
        'title': 'MAGIC SKUNK',
        'detail': 'This is truly a magic skunk. Said to be able to achieve the impossible',
        'sticker_only': True,
        'unlocked': False,
        'image_src': 'A:/cards/ADP Skunk.bin',
        'thumb_src': None,
    },
        {
        'id': 'ACR-33',
        'title': 'ORANGE CHICKEN',
        'detail': 'The ACR runs on Orange Chicken. ',
        'sticker_only': True,
        'unlocked': False,
        'image_src': 'A:/cards/Orange Chicken.bin',
        'thumb_src': None,
    },
        {
        'id': 'ACR-32',
        'title': 'FIRE ELMO',
        'detail': 'IYKYK',
        'sticker_only': True,
        'unlocked': False,
        'image_src': 'A:/cards/Fire Elmo.bin',
        'thumb_src': None,
    },
    {
        'id': 'ACR-28',
        'title': 'BIG BOOTIE MIX',
        'detail': 'This mix can be heard through the walls of Lockheed Martin. ',
        'sticker_only': True,
        'unlocked': False,
        'image_src': 'A:/cards/Big Bootie Mix.bin',
        'thumb_src': None,
    },
]



def color(name):
    return lv.color_hex(COLORS[name])


def plain_obj(parent):
    obj = lv.obj(parent)
    obj.set_style_border_width(0, 0)
    obj.set_style_radius(0, 0)
    obj.set_style_pad_all(0, 0)
    obj.remove_flag(lv.obj.FLAG.SCROLLABLE)
    obj.remove_flag(lv.obj.FLAG.CLICKABLE)
    return obj


def make_label(parent, text, text_color="white"):
    label = lv.label(parent)
    label.set_text(text)
    label.set_style_text_color(color(text_color), 0)
    return label


def constrain_label(label, width, height, clip=True):
    label.set_size(width, height)
    if clip:
        label.set_long_mode(lv.label.LONG_MODE.CLIP)
    else:
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
    return label


def card_image_src(card):
    if card.get("unlocked", False):
        src = card.get("image_src")
        return src or UNLOCKED_IMAGE_SRC
    return LOCKED_IMAGE_SRC


def find_card_index(card_id):
    for index, card_data in enumerate(CARDS):
        if card_data["id"] == card_id:
            return index
    return -1


def unlock_card_data(card_id):
    index = find_card_index(card_id)
    if index < 0:
        print("Unknown card ID")
        return -1

    if not CARDS[index]["unlocked"]:
        CARDS[index]["unlocked"] = True

    print("Card unlocked")
    return index


def _remove_flag(obj, flag):
    """Remove an LVGL flag, trying both API spellings."""
    try:
        obj.remove_flag(flag)
    except Exception:
        try:
            obj.clear_flag(flag)
        except Exception:
            pass


def _make_button(parent):
    """Create a button compatible with both lv.button and lv.btn APIs."""
    if hasattr(lv, "button"):
        return lv.button(parent)
    if hasattr(lv, "btn"):
        return lv.btn(parent)
    return lv.obj(parent)


class CardCollectionView:
    """Two-slot strip carousel with real-time drag following.

    The strip moves with the user's finger in real time.  On release, if travel
    exceeds SNAP_THRESHOLD the carousel commits to the new card; otherwise it
    animates back to the current card.

    Layout
    ------
    root (240 × 280)
      header (240 × 37)
      viewport (240 × 243)    ← clips the strip; owns all touch events
        strip  (360 × 243)    ← only set_x() changes during drag and animation
          card_a  x = 0       ← reusable slot
          card_b  x = PITCH   ← reusable slot
      btn_left / btn_right    ← on root, above the viewport
      details_overlay         ← fullscreen overlay on root

    Idle state
      strip.x = NEUTRAL_X (43)  →  card_a centred
      card_a = CARDS[index]  |  card_b = CARDS[index+1] or empty

    Left drag (next card)
      card_a = current, card_b = next
      strip.x: NEUTRAL_X → NEUTRAL_X − PITCH   as finger moves left

    Right drag (prev card)
      card_a = prev, card_b = current
      strip jumps to NEUTRAL_X − PITCH (card_b centred)
      strip.x: NEUTRAL_X − PITCH → NEUTRAL_X   as finger moves right
    """

    HEADER_H    = 37
    CAROUSEL_Y  = 37
    CAROUSEL_H  = HEIGHT - 37

    CARD_W      = 154
    CARD_H      = 224
    CARD_ART_W  = 142
    CARD_ART_H  = 198
    CARD_NAME_Y = 200
    CARD_Y      = 5  # keep the top fixed; trimmed ID row becomes bottom clearance

    LOCKED_CARD_TITLE = "REDACTED"

    CARD_GAP    = 30
    CARD_PITCH  = CARD_W + CARD_GAP    # 166
    NEUTRAL_X   = (WIDTH - CARD_W) // 2  # 43
    CARD_BLEED  = 5  # card background extends this many px beyond content on each side

    # STRIP_IDLE_X: strip x when the current card is centred.
    # Shifted left by 2×CARD_PITCH + CARD_BLEED so the 5-slot layout is:
    #   slot_before | slot_prev | slot_curr | slot_next | slot_after
    # All slot objects start at strip x >= 0 (no negative child coordinates).
    # slot_before peeks on the left edge during a right swipe (prev direction),
    # slot_after peeks on the right edge during a left swipe (next direction).
    STRIP_IDLE_X   = NEUTRAL_X - CARD_PITCH * 2 - CARD_BLEED  # -294
    ANIM_DURATION  = 170              # ms — snap or cancel animation (full pitch)
    SNAP_THRESHOLD = 24               # px minimum drag to commit on slow drags
    TAP_THRESHOLD  = 16               # px max delta to treat release as a tap

    # Fast swipe tuning.  Some users flick quickly enough that LVGL may deliver
    # PRESSED -> RELEASED with too few PRESSING samples for _drag_dir to be set.
    # Treat those short/fast releases as intentional card changes.
    QUICK_SWIPE_MIN_TRAVEL = 14        # px; short, deliberate flick distance
    QUICK_SWIPE_VEL        = 0.14      # px/ms; 140 px/s
    DETAIL_TAP_MAX_MOVE    = 5         # px; scrolling must never close details

    # After a swipe, do not restore full bitmap art inside the release/anim
    # callback. First snap the strip into its idle position and draw the cheap
    # placeholder frame. Then load/restore the full image shortly after that.
    # This is what keeps touch release from feeling like the card froze halfway.
    IMAGE_RESTORE_DELAY_MS = 25

    # The idle side cards only show narrow slivers, so do not decode/render
    # their full bitmap art. They stay as cheap edge previews. During drag,
    # they temporarily expand back into full placeholder cards, then the newly
    # centered card loads its bitmap after snap.
    LOAD_SIDE_IMAGES_IDLE = False
    RENDER_SIDE_SLIVERS_IDLE = True

    # ------------------------------------------------------------------ init

    def __init__(self, parent, on_back=None, initial_index=0, on_index_changed=None, on_card_unlocked=None, on_details_open=None, on_details_close=None, on_unlock_animation_complete=None):
        self.parent    = parent
        self.on_back   = on_back
        self.on_index_changed = on_index_changed
        self.on_card_unlocked = on_card_unlocked
        self.on_details_open = on_details_open
        self.on_details_close = on_details_close
        self.on_unlock_animation_complete = on_unlock_animation_complete

        try:
            initial_index = int(initial_index)
        except Exception:
            initial_index = 0

        if not CARDS:
            initial_index = 0
        elif initial_index < 0:
            initial_index = 0
        elif initial_index >= len(CARDS):
            initial_index = len(CARDS) - 1

        self.index     = initial_index
        self.animating = False
        self.details_open = False
        self.callbacks = []
        self._detail_press_x = 0
        self._detail_press_y = 0
        self._detail_press_moved = False
        self._detail_press_active = False

        # Drag-follow state
        self.dragging       = False   # True while a finger is actively pressed
        self._drag_dir      = 0      # 0 = undecided, 1 = next, -1 = prev
        self._drag_start_x  = 0      # indev X recorded on PRESSED
        self._drag_start_y  = 0      # indev Y recorded on PRESSED
        self._drag_last_x   = 0      # last valid PRESSING sample
        self._drag_last_y   = 0
        self._last_strip_x  = self.STRIP_IDLE_X  # logical moving-pair position
        self._art_hidden    = False  # True while drag/snap art is hidden
        self._moving_slots  = ()     # (slot, fixed_x) pairs during transit

        # Deferred image restore state.  These refs are kept so callbacks/timers
        # are not garbage-collected by MicroPython.
        self._pending_image_restore = False
        self._image_restore_timer = None
        self._image_restore_cb = None
        self._unlock_timer = None
        self._unlock_cb = None
        self._unlock_objects = []
        self._unlock_tick = 0
        self._acr_timer = None
        self._acr_timer_cb = self._update_acr_foil_effect
        self._acr_paused_for_touch = False
        self._acr_test_forced = False
        self._acr_tick = 0
        self._acr_color_index = 0
        self._acr_next_sparkle_ms = 0
        self._acr_next_glint_ms = 0
        self._acr_glint_peak_ms = 0
        self._acr_glint_until_ms = 0
        self._acr_foil_colors = ()
        self._acr_sparkles = []
        self._acr_border = None
        self._acr_glint = None

        # Velocity sampling for flick detection
        self._press_t       = 0      # ticks_ms() at PRESSED

        # Pre-allocate touch point to avoid per-frame Python object allocation.
        try:
            self._pt = lv.point_t()
        except Exception:
            self._pt = None

        self._build()

        # Initial paint follows the same two-phase path as swipe release:
        # draw cheap placeholders/slivers first, then load only the centered
        # card image after LVGL has had a chance to paint the locked position.
        self._refresh_slots(load_art=False)
        self._schedule_image_restore()

    # ------------------------------------------------------------------ build

    def _build(self):
        self.root = lv.obj(self.parent)
        self.root.set_size(WIDTH, HEIGHT)
        self.root.set_pos(0, 0)
        self.root.set_style_bg_color(color("black"), 0)
        self.root.set_style_bg_opa(0, 0)
        self.root.set_style_border_width(0, 0)
        self.root.set_style_radius(0, 0)
        self.root.set_style_pad_all(0, 0)
        _remove_flag(self.root, lv.obj.FLAG.SCROLLABLE)

        self._build_header()
        self._build_viewport()
        self._build_acr_foil_effect()
        self._build_details_overlay()

    def _build_acr_foil_effect(self):
        """Allocate the centered-card foil primitives once for reuse."""
        parent = self.slot_curr["object"]
        self._acr_foil_colors = (
            lv.color_hex(ACR_FOIL_COLORS[0]),
            lv.color_hex(ACR_FOIL_COLORS[1]),
            lv.color_hex(ACR_FOIL_COLORS[2]),
            lv.color_hex(ACR_FOIL_COLORS[3]),
            lv.color_hex(ACR_FOIL_COLORS[4]),
            lv.color_hex(ACR_FOIL_COLORS[5]),
        )

        sparkles = []
        for _index in range(3):
            sparkle = lv.image(parent)
            sparkle.set_src(ACR_GLINT_SOURCES[_index])
            sparkle.set_size(16, 16)
            sparkle.set_style_opa(0, 0)
            sparkle.add_flag(lv.obj.FLAG.HIDDEN)
            _remove_flag(sparkle, lv.obj.FLAG.CLICKABLE)
            _remove_flag(sparkle, lv.obj.FLAG.SCROLLABLE)
            sparkles.append({"image": sparkle, "born": 0, "peak": 0, "until": 0})

        glint = lv.image(parent)
        glint.set_src(ACR_GLINT_SRC)
        glint.set_size(16, 16)
        glint.set_style_opa(0, 0)
        glint.add_flag(lv.obj.FLAG.HIDDEN)
        _remove_flag(glint, lv.obj.FLAG.CLICKABLE)
        _remove_flag(glint, lv.obj.FLAG.SCROLLABLE)

        self._acr_border = None
        self._acr_sparkles = sparkles
        self._acr_glint = glint

    def _is_acr_card(self, card):
        try:
            return (
                str(card.get("id", "")).upper().startswith("ACR-")
                and card.get("unlocked", False) is True
            )
        except Exception:
            return False

    def _start_acr_foil_effect(self, force=False):
        if self.dragging or self.animating or self.details_open or self._art_hidden:
            return False
        if not CARDS or self.index < 0 or self.index >= len(CARDS):
            return False
        if not force and not self._is_acr_card(CARDS[self.index]):
            return False
        if force:
            self._acr_test_forced = True
        if self._acr_timer is not None:
            if self._acr_paused_for_touch:
                try:
                    self._acr_timer.resume()
                except Exception:
                    pass
                self._acr_paused_for_touch = False
            return True

        now = ticks_ms()
        self._acr_tick = 0
        self._acr_color_index = 0
        self._acr_next_sparkle_ms = now + random.randint(700, 1200)
        self._acr_next_glint_ms = now + random.randint(6000, 10000)
        self._acr_glint_peak_ms = 0
        self._acr_glint_until_ms = 0
        try:
            self._acr_timer = lv.timer_create(
                self._acr_timer_cb, ACR_EFFECT_TIMER_MS, None
            )
            return True
        except Exception:
            self._stop_acr_foil_effect(clear_test=True)
            return False

    def _stop_acr_foil_effect(self, clear_test=False):
        timer = self._acr_timer
        self._acr_timer = None
        self._acr_paused_for_touch = False
        if clear_test:
            self._acr_test_forced = False
        if timer is not None:
            for name in ("delete", "_del", "del_"):
                try:
                    getattr(timer, name)()
                    break
                except Exception:
                    pass
            else:
                try:
                    lv.timer_delete(timer)
                except Exception:
                    pass

        for obj in (
            self._acr_border,
            self._acr_glint,
        ):
            if obj is not None:
                obj.add_flag(lv.obj.FLAG.HIDDEN)
        for state in self._acr_sparkles:
            state["born"] = 0
            state["peak"] = 0
            state["until"] = 0
            state["image"].add_flag(lv.obj.FLAG.HIDDEN)
        self._acr_glint_until_ms = 0
        self._acr_glint_peak_ms = 0

    def _pause_acr_foil_for_touch(self):
        """Suspend decorative redraws while the input device tracks a finger."""
        if self._acr_timer is None or self._acr_paused_for_touch:
            return
        try:
            self._acr_timer.pause()
            self._acr_paused_for_touch = True
        except Exception:
            # Older bindings without timer pause still get the safe behavior.
            self._stop_acr_foil_effect(clear_test=False)

    def _refresh_acr_foil_effect(self):
        should_run = (
            not self.dragging
            and not self.animating
            and not self.details_open
            and not self._art_hidden
            and CARDS
            and 0 <= self.index < len(CARDS)
            and (self._acr_test_forced or self._is_acr_card(CARDS[self.index]))
        )
        if should_run:
            self._start_acr_foil_effect(force=self._acr_test_forced)
        else:
            self._stop_acr_foil_effect()

    def _update_acr_foil_effect(self, _timer):
        if (
            self.dragging
            or self.animating
            or self.details_open
            or self._art_hidden
        ):
            self._stop_acr_foil_effect(clear_test=True)
            return

        now = ticks_ms()
        tick = self._acr_tick + 1
        self._acr_tick = tick

        for state in self._acr_sparkles:
            until = state["until"]
            if until and ticks_diff(now, until) >= 0:
                state["born"] = 0
                state["peak"] = 0
                state["until"] = 0
                state["image"].add_flag(lv.obj.FLAG.HIDDEN)
            elif until:
                peak = state["peak"]
                if ticks_diff(now, peak) < 0:
                    fade_span = max(1, ticks_diff(peak, state["born"]))
                    fade_pos = max(0, ticks_diff(now, state["born"]))
                    sparkle_opa = min(210, 210 * fade_pos // fade_span)
                else:
                    fade_span = max(1, ticks_diff(until, peak))
                    fade_left = max(0, ticks_diff(until, now))
                    sparkle_opa = min(210, 210 * fade_left // fade_span)
                state["image"].set_style_opa(sparkle_opa, 0)

        if ticks_diff(now, self._acr_next_sparkle_ms) >= 0:
            for state in self._acr_sparkles:
                if state["until"] == 0:
                    x = self.CARD_BLEED + random.randint(8, self.CARD_W - 20)
                    y = random.randint(8, self.CARD_H - 28)
                    sparkle = state["image"]
                    sparkle.set_pos(x - 8, y - 8)
                    sparkle.set_style_opa(0, 0)
                    sparkle.remove_flag(lv.obj.FLAG.HIDDEN)
                    state["born"] = now
                    state["peak"] = now + random.randint(700, 1000)
                    state["until"] = state["peak"] + random.randint(1000, 1400)
                    break
            self._acr_next_sparkle_ms = now + random.randint(600, 1000)

        if self._acr_glint_until_ms:
            remaining = ticks_diff(self._acr_glint_until_ms, now)
            if remaining <= 0:
                self._acr_glint_until_ms = 0
                self._acr_glint.add_flag(lv.obj.FLAG.HIDDEN)
                self._acr_next_glint_ms = now + random.randint(6000, 10000)
            else:
                if ticks_diff(now, self._acr_glint_peak_ms) < 0:
                    rise_left = ticks_diff(self._acr_glint_peak_ms, now)
                    opa = max(0, 230 - rise_left * 230 // 350)
                else:
                    fade_span = max(
                        1,
                        ticks_diff(
                            self._acr_glint_until_ms,
                            self._acr_glint_peak_ms,
                        ),
                    )
                    opa = max(0, min(230, remaining * 230 // fade_span))
                self._acr_glint.set_style_opa(opa, 0)
        elif ticks_diff(now, self._acr_next_glint_ms) >= 0:
            x = self.CARD_BLEED + random.randint(12, self.CARD_W - 24)
            y = random.randint(12, self.CARD_H - 30)
            self._acr_glint.set_pos(x - 8, y - 8)
            self._acr_glint.set_style_opa(0, 0)
            self._acr_glint.remove_flag(lv.obj.FLAG.HIDDEN)
            self._acr_glint_peak_ms = now + 550
            self._acr_glint_until_ms = self._acr_glint_peak_ms + 1200

    def test_acr_foil_effect(self):
        """REPL hook: preview foil without changing unlock or card state."""
        self._stop_acr_foil_effect(clear_test=True)
        return self._start_acr_foil_effect(force=True)

    def stop_acr_foil_effect(self):
        """REPL hook: stop a forced or automatic foil preview."""
        self._stop_acr_foil_effect(clear_test=True)

    def _build_header(self):
        hdr = lv.obj(self.root)
        hdr.set_size(WIDTH, self.HEADER_H)
        hdr.set_pos(0, 0)
        hdr.set_style_bg_color(color("panel"), 0)
        hdr.set_style_bg_opa(lv.OPA.COVER, 0)
        hdr.set_style_border_width(0, 0)
        hdr.set_style_radius(0, 0)
        hdr.set_style_pad_all(0, 0)
        _remove_flag(hdr, lv.obj.FLAG.SCROLLABLE)

        # back_btn = _make_button(hdr)
        # back_btn.set_size(66, 30)
        # back_btn.set_pos(4, 4)
        # back_btn.set_style_bg_color(color("panel_2"), 0)
        # back_btn.set_style_bg_opa(lv.OPA.COVER, 0)
        # back_btn.set_style_border_color(color("green_dim"), 0)
        # back_btn.set_style_border_width(1, 0)
        # back_btn.set_style_radius(2, 0)
        # back_btn.set_style_shadow_width(0, 0)
        # back_btn.set_style_pad_all(0, 0)
        # _remove_flag(back_btn, lv.obj.FLAG.SCROLLABLE)
        # try:
        #     back_btn.set_ext_click_area(8, 8, 8, 10)
        # except Exception:
        #     try:
        #         back_btn.set_ext_click_area(10)
        #     except Exception:
        #         pass
        # back_lbl = lv.label(back_btn)
        # back_lbl.set_text("BACK")
        # back_lbl.set_style_text_color(color("white"), 0)
        # back_lbl.center()
        # back_cb = self._on_back_clicked
        # self.callbacks.append(back_cb)
        # back_btn.add_event_cb(back_cb, lv.EVENT.CLICKED, None)

        # cls_lbl = lv.label(hdr)
        # cls_lbl.set_text("// NIGHT RECON")
        # cls_lbl.set_style_text_color(color("green"), 0)
        # cls_lbl.set_pos(72, 4)
        # cls_lbl.set_size(116, 16)
        # cls_lbl.set_long_mode(lv.label.LONG_MODE.CLIP)

        self.counter_label = lv.label(hdr)
        self.counter_label.set_style_text_color(color("cyan"), 0)
        self.counter_label.set_pos(180, 4)
        self.counter_label.set_size(44, 16)
        self.counter_label.set_long_mode(lv.label.LONG_MODE.CLIP)

        sep = lv.obj(self.root)
        sep.set_size(WIDTH, 1)
        sep.set_pos(0, self.HEADER_H - 1)
        sep.set_style_bg_color(color("green"), 0)
        sep.set_style_bg_opa(lv.OPA.COVER, 0)
        sep.set_style_border_width(0, 0)
        sep.set_style_radius(0, 0)
        sep.set_style_pad_all(0, 0)

    def _build_viewport(self):
        # Viewport — clips the strip and receives all touch events.
        self.viewport = lv.obj(self.root)
        self.viewport.set_size(WIDTH, self.CAROUSEL_H)
        self.viewport.set_pos(0, self.CAROUSEL_Y)
        self.viewport.set_style_bg_color(color("black"), 0)
        # Stop movement invalidations at this opaque surface instead of
        # repainting the animated tactical background underneath every frame.
        self.viewport.set_style_bg_opa(lv.OPA.COVER, 0)
        self.viewport.set_style_border_width(0, 0)
        self.viewport.set_style_radius(0, 0)
        self.viewport.set_style_pad_all(0, 0)
        _remove_flag(self.viewport, lv.obj.FLAG.SCROLLABLE)
        self.viewport.add_flag(lv.obj.FLAG.CLICKABLE)
        # LVGL clips children to their parent by default; corner clipping would
        # add layer work and this viewport has square corners.

        # 5 slots: slot_before | slot_prev | slot_curr | slot_next | slot_after
        # strip_w covers all 5 objects including their CARD_BLEED overhangs.
        strip_w = self.CARD_PITCH * 4 + self.CARD_W + self.CARD_BLEED * 2
        self.strip = lv.obj(self.viewport)
        self.strip.set_size(strip_w, self.CARD_Y + self.CARD_H)
        self.strip.set_pos(self.STRIP_IDLE_X, 0)
        self.strip.set_style_bg_color(color("black"), 0)
        self.strip.set_style_bg_opa(0, 0)
        self.strip.set_style_border_width(0, 0)
        self.strip.set_style_radius(0, 0)
        self.strip.set_style_pad_all(0, 0)
        _remove_flag(self.strip, lv.obj.FLAG.SCROLLABLE)
        _remove_flag(self.strip, lv.obj.FLAG.CLICKABLE)

        card_y = self.CARD_Y
        # All x_in_strip values start at CARD_BLEED so slot objects (positioned
        # at x_in_strip - CARD_BLEED) begin at strip x=0, never negative.
        self.slot_before = self._create_card_slot(self.CARD_BLEED,                          card_y)
        self.slot_prev   = self._create_card_slot(self.CARD_BLEED + self.CARD_PITCH,        card_y)
        self.slot_curr   = self._create_card_slot(self.CARD_BLEED + self.CARD_PITCH * 2,    card_y)
        self.slot_next   = self._create_card_slot(self.CARD_BLEED + self.CARD_PITCH * 3,    card_y)
        self.slot_after  = self._create_card_slot(self.CARD_BLEED + self.CARD_PITCH * 4,    card_y)

        for slot in (self.slot_before, self.slot_prev, self.slot_curr, self.slot_next, self.slot_after):
            _remove_flag(slot["object"], lv.obj.FLAG.CLICKABLE)

        # All drag interaction is handled through these four viewport events.
        press_cb    = self._on_press
        pressing_cb = self._on_pressing
        release_cb  = self._on_release
        lost_cb     = self._on_press_lost
        self.callbacks.extend([press_cb, pressing_cb, release_cb, lost_cb])
        self.viewport.add_event_cb(press_cb,    lv.EVENT.PRESSED,    None)
        self.viewport.add_event_cb(pressing_cb, lv.EVENT.PRESSING,   None)
        self.viewport.add_event_cb(release_cb,  lv.EVENT.RELEASED,   None)
        self.viewport.add_event_cb(lost_cb,     lv.EVENT.PRESS_LOST, None)

        # Arrow buttons sit on root (not viewport) so they are never clipped.
        # Center them vertically beside the card. The tall/narrow shape reads
        # more like carousel rails than small bottom buttons.
        BTN_W, BTN_H = 30, 72
        btn_y = self.CAROUSEL_Y + (self.CAROUSEL_H - BTN_H) // 2
        btn_left  = _make_button(self.root)
        btn_left.set_size(BTN_W, BTN_H)
        btn_left.set_pos(4, btn_y)
        btn_left.set_style_bg_color(color("panel_2"), 0)
        btn_left.set_style_bg_opa(lv.OPA.COVER, 0)
        btn_left.set_style_border_color(color("green_dim"), 0)
        btn_left.set_style_border_width(1, 0)
        btn_left.set_style_radius(4, 0)
        btn_left.set_style_shadow_width(0, 0)
        btn_left.set_style_pad_all(0, 0)
        _remove_flag(btn_left, lv.obj.FLAG.SCROLLABLE)
        lbl_l = lv.label(btn_left)
        lbl_l.set_text("<")
        lbl_l.set_style_text_color(color("white"), 0)
        lbl_l.center()
        cb_left = lambda e: self.go_prev()
        self.callbacks.append(cb_left)
        btn_left.add_event_cb(cb_left, lv.EVENT.CLICKED, None)

        btn_right = _make_button(self.root)
        btn_right.set_size(BTN_W, BTN_H)
        btn_right.set_pos(WIDTH - BTN_W - 4, btn_y)
        btn_right.set_style_bg_color(color("panel_2"), 0)
        btn_right.set_style_bg_opa(lv.OPA.COVER, 0)
        btn_right.set_style_border_color(color("green_dim"), 0)
        btn_right.set_style_border_width(1, 0)
        btn_right.set_style_radius(4, 0)
        btn_right.set_style_shadow_width(0, 0)
        btn_right.set_style_pad_all(0, 0)
        _remove_flag(btn_right, lv.obj.FLAG.SCROLLABLE)
        lbl_r = lv.label(btn_right)
        lbl_r.set_text(">")
        lbl_r.set_style_text_color(color("white"), 0)
        lbl_r.center()
        cb_right = lambda e: self.go_next()
        self.callbacks.append(cb_right)
        btn_right.add_event_cb(cb_right, lv.EVENT.CLICKED, None)

    def _create_card_slot(self, x_in_strip, y_in_strip):
        card_obj = _make_button(self.strip)
        # Wider by CARD_BLEED on each side so the background fills the gap
        # between cards during transit instead of showing a black strip.
        # All child positions are offset by CARD_BLEED to stay visually aligned.
        card_obj.set_size(self.CARD_W + self.CARD_BLEED * 2, self.CARD_H)
        card_obj.set_pos(x_in_strip - self.CARD_BLEED, y_in_strip)
        card_obj.set_style_bg_color(color("panel_2"), 0)
        card_obj.set_style_bg_opa(lv.OPA.COVER, 0)
        card_obj.set_style_border_color(color("green_dim"), 0)
        card_obj.set_style_border_width(2, 0)
        card_obj.set_style_radius(0, 0)  # flat rectangle = no anti-aliased corners
        card_obj.set_style_shadow_width(0, 0)
        card_obj.set_style_pad_all(0, 0)
        _remove_flag(card_obj, lv.obj.FLAG.SCROLLABLE)

        art = lv.obj(card_obj)
        art.set_pos(5 + self.CARD_BLEED, 4)
        art.set_size(self.CARD_ART_W, self.CARD_ART_H)
        art.set_style_bg_color(color("panel"), 0)
        art.set_style_bg_opa(lv.OPA.COVER, 0)
        art.set_style_border_width(0, 0)  # no border = one fewer draw pass
        art.set_style_radius(0, 0)
        art.set_style_pad_all(0, 0)
        _remove_flag(art, lv.obj.FLAG.SCROLLABLE)
        _remove_flag(art, lv.obj.FLAG.CLICKABLE)

        art_image = lv.image(art)
        # Fixed position and size avoids the layout recompute that center()
        # triggers after every set_src call.  The .bin files are pre-sized
        # to CARD_ART_W × CARD_ART_H so no auto-resize is needed.
        art_image.set_pos(0, 0)
        art_image.set_size(self.CARD_ART_W, self.CARD_ART_H)
        art_image.add_flag(lv.obj.FLAG.HIDDEN)

        art_placeholder = lv.label(art)
        art_placeholder.set_text("")
        art_placeholder.set_style_text_color(color("cyan"), 0)
        art_placeholder.set_size(self.CARD_ART_W - 4, 18)
        art_placeholder.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        art_placeholder.center()

        title_lbl = lv.label(card_obj)
        title_lbl.set_pos(3 + self.CARD_BLEED, self.CARD_NAME_Y)
        title_lbl.set_size(self.CARD_W - 6, 16)
        title_lbl.set_style_text_color(color("white"), 0)
        title_lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        title_lbl.set_long_mode(lv.label.LONG_MODE.CLIP)
        title_lbl.set_text("")

        # Keep a hidden ID label object so older helper code can still call
        # slot["id"].set_text(""), but the carousel face no longer reveals IDs.
        id_lbl = lv.label(card_obj)
        id_lbl.set_pos(0, 0)
        id_lbl.set_size(1, 1)
        id_lbl.set_text("")
        id_lbl.add_flag(lv.obj.FLAG.HIDDEN)

        return {
            "object":          card_obj,
            "art":             art,
            "art_image":       art_image,
            "art_placeholder": art_placeholder,
            "title":           title_lbl,
            "id":              id_lbl,
            "_img_src":        None,   # tracks loaded src to skip redundant set_src
        }

    def _build_details_overlay(self):
        self.details_overlay = lv.obj(self.root)
        self.details_overlay.set_size(WIDTH, HEIGHT)
        self.details_overlay.set_pos(0, 0)
        self.details_overlay.set_style_bg_color(color("panel"), 0)
        # Fully opaque background.  A transparent overlay forces LVGL to
        # composite every pixel behind it (card image + overlay) on every frame,
        # which is why opening the details panel redraws the image slowly.
        self.details_overlay.set_style_bg_opa(lv.OPA.COVER, 0)
        self.details_overlay.add_flag(lv.obj.FLAG.HIDDEN)
        self.details_overlay.add_flag(lv.obj.FLAG.CLICKABLE)
        self.details_overlay.set_style_border_width(0, 0)
        self.details_overlay.set_style_radius(0, 0)
        self.details_overlay.set_style_pad_all(0, 0)
        _remove_flag(self.details_overlay, lv.obj.FLAG.SCROLLABLE)

        panel = lv.obj(self.details_overlay)
        panel.set_pos(8, 8)
        panel.set_size(224, 264)
        panel.set_style_bg_color(color("panel"), 0)
        panel.set_style_bg_opa(lv.OPA.COVER, 0)
        panel.set_style_border_width(1, 0)
        panel.set_style_border_color(color("green_dim"), 0)
        panel.set_style_radius(6, 0)
        panel.set_style_pad_all(0, 0)
        panel.add_flag(lv.obj.FLAG.CLICKABLE)
        _remove_flag(panel, lv.obj.FLAG.SCROLLABLE)
        self.detail_panel = panel

        accent = lv.obj(panel)
        accent.set_pos(0, 0)
        accent.set_size(4, 264)
        accent.set_style_bg_color(color("green"), 0)
        accent.set_style_bg_opa(lv.OPA.COVER, 0)
        accent.set_style_border_width(0, 0)
        accent.set_style_radius(0, 0)
        accent.set_style_pad_all(0, 0)
        self.detail_accent = accent

        self.detail_id = lv.label(panel)
        self.detail_id.set_pos(11, 7)
        self.detail_id.set_size(203, 16)
        self.detail_id.set_style_text_color(color("cyan"), 0)
        self.detail_id.set_long_mode(lv.label.LONG_MODE.CLIP)

        self.detail_title = lv.label(panel)
        self.detail_title.set_pos(11, 27)
        self.detail_title.set_size(203, 18)
        self.detail_title.set_style_text_color(color("white"), 0)
        self.detail_title.set_style_text_letter_space(1, 0)
        self.detail_title.set_long_mode(lv.label.LONG_MODE.CLIP)

        # One lightweight scrollable information window. All detail text is
        # rendered by one plain label; terminal-style headings and whitespace
        # separate sections without LVGL recolor parsing or extra text objects.
        self.detail_scroll = lv.obj(panel)
        self.detail_scroll.set_pos(10, 50)
        self.detail_scroll.set_size(204, 189)
        self.detail_scroll.set_style_bg_color(color("panel_2"), 0)
        self.detail_scroll.set_style_bg_opa(lv.OPA.COVER, 0)
        self.detail_scroll.set_style_border_width(1, 0)
        self.detail_scroll.set_style_border_color(color("green_dim"), 0)
        self.detail_scroll.set_style_radius(3, 0)
        self.detail_scroll.set_style_pad_left(6, 0)
        self.detail_scroll.set_style_pad_right(6, 0)
        self.detail_scroll.set_style_pad_top(6, 0)
        self.detail_scroll.set_style_pad_bottom(6, 0)
        self.detail_scroll.add_flag(lv.obj.FLAG.CLICKABLE)

        try:
            self.detail_scroll.set_scroll_dir(lv.DIR.VER)
        except Exception:
            pass

        try:
            # Hiding the scrollbar avoids another redraw while dragging.
            self.detail_scroll.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        except Exception:
            pass

        self.detail_text = lv.label(self.detail_scroll)
        self.detail_text.set_pos(0, 0)
        self.detail_text.set_width(188)
        self.detail_text.set_style_text_color(color("white"), 0)
        self.detail_text.set_long_mode(lv.label.LONG_MODE.WRAP)

        try:
            self.detail_text.set_height(lv.SIZE_CONTENT)
        except Exception:
            # All current card text fits comfortably inside this content
            # height; only the parent window scrolls.
            self.detail_text.set_height(340)

        _remove_flag(self.detail_text, lv.obj.FLAG.SCROLLABLE)
        _remove_flag(self.detail_text, lv.obj.FLAG.CLICKABLE)

        hint = lv.label(panel)
        hint.set_pos(104, 246)
        hint.set_size(110, 13)
        hint.set_text("TAP TO CLOSE")
        hint.set_style_text_color(color("green_dim"), 0)
        hint.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
        hint.set_long_mode(lv.label.LONG_MODE.CLIP)
        hint.add_flag(lv.obj.FLAG.CLICKABLE)

        press_cb = self._on_detail_pressed
        pressing_cb = self._on_detail_pressing
        close_cb = self._on_close_details
        self.callbacks.extend((press_cb, pressing_cb, close_cb))
        for obj in (
            self.details_overlay, panel,
            self.detail_id, self.detail_title,
            self.detail_scroll, hint,
        ):
            obj.add_flag(lv.obj.FLAG.CLICKABLE)
            obj.add_event_cb(press_cb, lv.EVENT.PRESSED, None)
            obj.add_event_cb(pressing_cb, lv.EVENT.PRESSING, None)
            obj.add_event_cb(close_cb, lv.EVENT.RELEASED, None)

    # ------------------------------------------------------------------ card fill

    def _fill_card(self, slot, card_data, load_art=True, sliver=False):
        slot["object"].remove_flag(lv.obj.FLAG.HIDDEN)
        unlocked = card_data.get("unlocked", False)

        if sliver:
            # Idle side cards only expose a thin edge. Hide text and bitmap
            # children so LVGL only draws the cheap card shell/art panel sliver.
            slot["title"].add_flag(lv.obj.FLAG.HIDDEN)
        else:
            slot["title"].remove_flag(lv.obj.FLAG.HIDDEN)
        unlocked = card_data.get("unlocked", False)
        is_acr_card = str(card_data.get("id", "")).startswith("ACR")

        display_title = card_data["title"] #if unlocked else self.LOCKED_CARD_TITLE
        slot["title"].set_style_text_letter_space(
            -1 if len(display_title) >= 18 else 0, 0
        )
        slot["title"].set_text(display_title)
        slot["id"].set_text("")
        slot["id"].add_flag(lv.obj.FLAG.HIDDEN)

        if unlocked:
            # ACR cards show orange once unlocked.
            accent_color = "amber" if is_acr_card else "green_dim"
            title_color = "amber" if is_acr_card else "white"

            slot["title"].set_style_text_color(color(title_color), 0)
            slot["object"].set_style_border_color(color(accent_color), 0)
            slot["art"].set_style_border_color(color(accent_color), 0)
        else:
            slot["title"].set_style_text_color(color("white"), 0)
            slot["object"].set_style_border_color(color("white"), 0)
            slot["art"].set_style_border_color(color("white"), 0)

        # Always write placeholder text so the art area is identifiable when
        # art is hidden during transit. Locked cards must not reveal the real
        # aircraft name before trade/unlock.
        ph_text = card_data["title"] if unlocked else "LOCKED"
        ph_color = "amber" if unlocked and is_acr_card else ("cyan" if unlocked else "white")

        slot["art_placeholder"].set_text(ph_text)
        slot["art_placeholder"].set_style_text_color(color(ph_color), 0)
        if sliver:
            slot["art_image"].add_flag(lv.obj.FLAG.HIDDEN)
            slot["art_placeholder"].add_flag(lv.obj.FLAG.HIDDEN)
            return

        src = card_image_src(card_data)

        # Text/style can be refreshed during drag/release, but image loading must
        # be optional.  Calling set_src() here during a release callback is the
        # thing that makes the carousel appear to freeze before it centers.
        if not load_art or self._art_hidden:
            slot["art_image"].add_flag(lv.obj.FLAG.HIDDEN)
            slot["art_placeholder"].remove_flag(lv.obj.FLAG.HIDDEN)
            return

        if src:
            try:
                # Only call set_src when the source actually changes.
                # set_src on an already-loaded image re-decodes and redraws.
                if slot["_img_src"] != src:
                    slot["art_image"].set_src(src)
                    slot["_img_src"] = src
                slot["art_image"].remove_flag(lv.obj.FLAG.HIDDEN)
                slot["art_placeholder"].add_flag(lv.obj.FLAG.HIDDEN)
                return
            except Exception as exc:
                print("Card image load failed:", src, exc)
                slot["_img_src"] = None

        slot["art_image"].add_flag(lv.obj.FLAG.HIDDEN)
        slot["art_placeholder"].remove_flag(lv.obj.FLAG.HIDDEN)

    def _fill_card_empty(self, slot):
        slot["object"].add_flag(lv.obj.FLAG.HIDDEN)
        slot["title"].set_text("")
        slot["id"].set_text("")
        slot["id"].add_flag(lv.obj.FLAG.HIDDEN)
        slot["art_image"].add_flag(lv.obj.FLAG.HIDDEN)
        slot["art_placeholder"].add_flag(lv.obj.FLAG.HIDDEN)
        slot["_img_src"] = None

    def _refresh_slots(self, load_art=True):
        """Fill all five slots from current index.

        load_art=False updates labels/borders/placeholders only.  Use that in
        snap completion paths so the carousel can draw its locked-in position
        before any bitmap source is decoded/restored.

        In the idle locked position, the neighboring cards are only visible as
        narrow edge slivers.  Keep those side slots in sliver mode so LVGL does
        not decode or draw large side images that the user mostly cannot see.
        """
        before_i = self.index - 2
        prev_i   = self.index - 1
        next_i   = self.index + 1
        after_i  = self.index + 2

        # Far slots are outside the idle viewport, but they become useful during
        # a swipe. Keep them populated as cheap shells/placeholders.
        if before_i >= 0:
            self._fill_card(self.slot_before, CARDS[before_i], load_art=False, sliver=self.RENDER_SIDE_SLIVERS_IDLE)
        else:
            self._fill_card_empty(self.slot_before)

        if prev_i >= 0:
            self._fill_card(self.slot_prev, CARDS[prev_i], load_art=(load_art and self.LOAD_SIDE_IMAGES_IDLE), sliver=self.RENDER_SIDE_SLIVERS_IDLE)
        else:
            self._fill_card_empty(self.slot_prev)

        if CARDS:
            self._fill_card(self.slot_curr, CARDS[self.index], load_art)

        if next_i < len(CARDS):
            self._fill_card(self.slot_next, CARDS[next_i], load_art=(load_art and self.LOAD_SIDE_IMAGES_IDLE), sliver=self.RENDER_SIDE_SLIVERS_IDLE)
        else:
            self._fill_card_empty(self.slot_next)

        if after_i < len(CARDS):
            self._fill_card(self.slot_after, CARDS[after_i], load_art=False, sliver=self.RENDER_SIDE_SLIVERS_IDLE)
        else:
            self._fill_card_empty(self.slot_after)

        self._update_counter()

    def _update_counter(self):
        self.counter_label.set_text("%02d/%02d" % (self.index + 1, len(CARDS)))

    def _notify_index_changed(self):
        if self.on_index_changed is None:
            return

        try:
            self.on_index_changed(self.index)
        except Exception as exc:
            print("Card index save failed:", exc)

    def _notify_card_unlocked(self, card_id):
        if self.on_card_unlocked is None:
            return

        try:
            self.on_card_unlocked(card_id)
        except Exception as exc:
            print("Card unlock save failed:", exc)

    # ------------------------------------------------------------------ deferred art restore

    def _visible_slots(self):
        return (
            self.slot_before,
            self.slot_prev,
            self.slot_curr,
            self.slot_next,
            self.slot_after,
        )

    def _hide_all_art(self):
        self._art_hidden = True
        for slot in self._visible_slots():
            # Keep each visible card identifiable throughout the gesture. Only
            # file-backed artwork is removed from transit frames.
            slot["title"].remove_flag(lv.obj.FLAG.HIDDEN)
            slot["art_image"].add_flag(lv.obj.FLAG.HIDDEN)
            slot["art_placeholder"].remove_flag(lv.obj.FLAG.HIDDEN)

    def _prepare_card_pair(self, direction):
        """Hide unused slots and stage only the outgoing/incoming card shells."""
        if direction not in (-1, 1):
            return
        self._hide_all_art()
        if direction > 0:
            active = (self.slot_curr, self.slot_next)
        else:
            active = (self.slot_prev, self.slot_curr)

        moving = []
        for slot in self._visible_slots():
            if slot is active[0] or slot is active[1]:
                slot["object"].remove_flag(lv.obj.FLAG.HIDDEN)
                moving.append((slot, slot["object"].get_x()))
            else:
                slot["object"].add_flag(lv.obj.FLAG.HIDDEN)
        self._moving_slots = tuple(moving)

    def _move_card_pair(self, logical_x):
        """Move two card objects while the oversized strip remains stationary."""
        logical_x = int(logical_x)
        if logical_x == self._last_strip_x:
            return
        delta = logical_x - self.STRIP_IDLE_X
        for slot, fixed_x in self._moving_slots:
            slot["object"].set_x(fixed_x + delta)
        self._last_strip_x = logical_x

    def _reset_card_pair(self):
        for slot, fixed_x in self._moving_slots:
            slot["object"].set_x(fixed_x)
        self._moving_slots = ()

    def _cancel_image_restore_timer(self):
        self._pending_image_restore = False
        timer = self._image_restore_timer
        self._image_restore_timer = None
        if timer is None:
            return
        for name in ("delete", "_del"):
            try:
                getattr(timer, name)()
                return
            except Exception:
                pass

    def _cancel_unlock_animation(self, restore=True):
        timer = self._unlock_timer
        active = timer is not None or bool(self._unlock_objects)
        if not active:
            return
        self._unlock_timer = None
        self._unlock_cb = None
        if timer is not None:
            for name in ("delete", "_del", "del_"):
                try:
                    getattr(timer, name)()
                    break
                except Exception:
                    pass
            else:
                try:
                    lv.timer_delete(timer)
                except Exception:
                    pass

        for obj in self._unlock_objects:
            for name in ("delete", "del_", "delete_async", "del_async"):
                try:
                    getattr(obj, name)()
                    break
                except Exception:
                    pass
        self._unlock_objects = []
        self.slot_curr["object"].set_style_border_width(2, 0)

        if restore and CARDS and 0 <= self.index < len(CARDS):
            self._fill_card(self.slot_curr, CARDS[self.index], load_art=True)

    def play_unlock_animation(self, card_id):
        index = find_card_index(card_id)
        if (
            index < 0
            or index != self.index
            or self.dragging
            or self.animating
            or self.details_open
        ):
            return False

        self._stop_acr_foil_effect(clear_test=True)
        self._cancel_image_restore_timer()
        self._cancel_unlock_animation(restore=False)
        # focus_card() leaves art hidden for its deferred restore. This
        # animation cancels that restore and owns the reveal at tick 17.
        self._art_hidden = False
        slot = self.slot_curr
        card_data = CARDS[index]

        self._fill_card(slot, card_data, load_art=False)
        slot["art_image"].add_flag(lv.obj.FLAG.HIDDEN)
        slot["art_placeholder"].remove_flag(lv.obj.FLAG.HIDDEN)
        slot["art_placeholder"].set_text("DECRYPTING...")
        slot["art_placeholder"].set_style_text_color(color("cyan"), 0)
        slot["object"].set_style_border_color(color("white"), 0)
        slot["object"].set_style_border_width(3, 0)

        scan_a = lv.obj(slot["art"])
        scan_a.set_size(self.CARD_ART_W, 3)
        scan_a.set_pos(0, 0)
        scan_a.set_style_bg_color(color("green"), 0)
        scan_a.set_style_bg_opa(lv.OPA.COVER, 0)
        scan_a.set_style_border_width(0, 0)
        scan_a.set_style_radius(0, 0)
        scan_a.set_style_pad_all(0, 0)
        _remove_flag(scan_a, lv.obj.FLAG.CLICKABLE)
        _remove_flag(scan_a, lv.obj.FLAG.SCROLLABLE)

        scan_b = lv.obj(slot["art"])
        scan_b.set_size(self.CARD_ART_W, 1)
        scan_b.set_pos(0, 18)
        scan_b.set_style_bg_color(color("white"), 0)
        scan_b.set_style_bg_opa(lv.OPA.COVER, 0)
        scan_b.set_style_border_width(0, 0)
        scan_b.set_style_radius(0, 0)
        scan_b.set_style_pad_all(0, 0)
        _remove_flag(scan_b, lv.obj.FLAG.CLICKABLE)
        _remove_flag(scan_b, lv.obj.FLAG.SCROLLABLE)

        banner = lv.obj(slot["object"])
        banner.set_pos(self.CARD_BLEED + 8, 82)
        banner.set_size(self.CARD_W - 16, 38)
        banner.set_style_bg_color(color("black"), 0)
        banner.set_style_bg_opa(lv.OPA.COVER, 0)
        banner.set_style_border_color(color("green"), 0)
        banner.set_style_border_width(1, 0)
        banner.set_style_radius(2, 0)
        banner.set_style_pad_all(0, 0)
        banner.set_style_opa(0, 0)
        _remove_flag(banner, lv.obj.FLAG.CLICKABLE)
        _remove_flag(banner, lv.obj.FLAG.SCROLLABLE)
        banner.add_flag(lv.obj.FLAG.HIDDEN)

        banner_label = lv.label(banner)
        banner_label.set_text("CARD UNLOCKED")
        banner_label.set_size(self.CARD_W - 24, 20)
        banner_label.set_style_text_color(color("green"), 0)
        banner_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        banner_label.center()

        self._unlock_objects = [scan_a, scan_b, banner]
        self._unlock_tick = 0

        def unlock_tick(_timer):
            tick = self._unlock_tick
            self._unlock_tick = tick + 1

            if tick < 5:
                border = "white" if tick % 2 == 0 else "green"
                slot["object"].set_style_border_color(color(border), 0)

            if tick <= 16:
                scan_y = min(self.CARD_ART_H - 3, tick * 12)
                scan_a.set_y(scan_y)
                scan_b.set_y(max(0, scan_y - 16))

            if tick == 17:
                self._fill_card(slot, card_data, load_art=True)
                for scan in (scan_a, scan_b):
                    for name in ("delete", "del_", "delete_async", "del_async"):
                        try:
                            getattr(scan, name)()
                            break
                        except Exception:
                            pass
                self._unlock_objects = [banner]
                try:
                    banner.move_foreground()
                except Exception:
                    pass
                banner.remove_flag(lv.obj.FLAG.HIDDEN)

            if 17 <= tick <= 21:
                banner.set_style_opa(min(255, (tick - 16) * 51), 0)
                border = "white" if tick in (17, 20) else "green"
                slot["object"].set_style_border_color(color(border), 0)

            if tick == 22:
                banner.set_style_opa(255, 0)
                slot["object"].set_style_border_color(color("green"), 0)

            if 30 <= tick <= 35:
                banner.set_style_opa(max(0, (35 - tick) * 42), 0)

            if tick >= 36:
                accent = (
                    "amber"
                    if str(card_data.get("id", "")).startswith("ACR")
                    else "green_dim"
                )
                slot["object"].set_style_border_color(color(accent), 0)
                self._cancel_unlock_animation(restore=False)
                if self.on_unlock_animation_complete is not None:
                    self.on_unlock_animation_complete(card_id)
                if self._unlock_timer is None:
                    self._refresh_acr_foil_effect()

        self._unlock_cb = unlock_tick
        try:
            self._unlock_timer = lv.timer_create(unlock_tick, 40, None)
            return True
        except Exception:
            self._cancel_unlock_animation(restore=True)
            return False

    def focus_card(self, index):
        """Immediately center a card so a queued unlock can be presented."""
        if not CARDS or index < 0 or index >= len(CARDS):
            return False
        self._cancel_image_restore_timer()
        self._cancel_unlock_animation(restore=False)
        self._finish_snap(index, notify_index_changed=True)
        return True

    def _schedule_image_restore(self):
        """Load/restore card art after the snapped placeholder frame is visible."""
        self._pending_image_restore = True
        cb = self._on_image_restore_ready
        self._image_restore_cb = cb

        # A short one-shot timer gives LVGL one normal handler pass to paint the
        # locked-in skeleton before the potentially slow set_src() call happens.
        try:
            timer = lv.timer_create(cb, self.IMAGE_RESTORE_DELAY_MS, None)
            self._image_restore_timer = timer
            try:
                timer.set_repeat_count(1)
            except Exception:
                pass
            return
        except Exception:
            pass

        # Fallback for bindings that expose async_call but not timer_create.
        try:
            lv.async_call(cb, None)
            return
        except Exception:
            pass

        # Last-resort fallback: still force the placeholder refresh first, then
        # restore art immediately.
        self._on_image_restore_ready(None)

    def _on_image_restore_ready(self, _arg):
        # If this was a repeating timer on an older binding, kill it manually.
        timer = self._image_restore_timer
        self._image_restore_timer = None
        if timer is not None:
            for name in ("delete", "_del"):
                try:
                    getattr(timer, name)()
                    break
                except Exception:
                    pass

        if not self._pending_image_restore:
            return
        if self.dragging or self.animating:
            return

        self._pending_image_restore = False
        self._art_hidden = False

        # Load only the centered card. Side cards remain cheap idle slivers;
        # transit itself draws no image or label content.
        if CARDS:
            self._fill_card(self.slot_curr, CARDS[self.index], load_art=True)

        if self.LOAD_SIDE_IMAGES_IDLE:
            # Optional escape hatch: set LOAD_SIDE_IMAGES_IDLE=True if you later
            # decide the side bitmap art is worth the extra decode/draw cost.
            if self.index - 1 >= 0:
                self._fill_card(self.slot_prev, CARDS[self.index - 1], load_art=True, sliver=False)
            if self.index + 1 < len(CARDS):
                self._fill_card(self.slot_next, CARDS[self.index + 1], load_art=True, sliver=False)
        self._refresh_acr_foil_effect()

    def _finish_snap(self, new_index, notify_index_changed):
        """Commit the selected card, draw the lock position, then load art."""
        self._stop_acr_foil_effect(clear_test=True)
        self._reset_card_pair()
        self.index = new_index
        self._last_strip_x = self.STRIP_IDLE_X

        # Phase 1: lock the card into place using text/placeholders only.
        self._art_hidden = True
        self._refresh_slots(load_art=False)

        self.animating = False

        if notify_index_changed:
            self._notify_index_changed()

        # Phase 2: restore/load the image after the lock frame has been drawn.
        self._schedule_image_restore()

    # ------------------------------------------------------------------ details

    def _fill_detail_panel(self, card_data):
        unlocked = card_data.get("unlocked", False)
        is_acr_card = str(card_data.get("id", "")).strip().upper().startswith(
            "ACR-"
        )
        accent = "green" if unlocked else "amber"
        self.detail_panel.set_style_border_color(color(accent), 0)
        self.detail_accent.set_style_bg_color(color(accent), 0)
        self.detail_id.set_style_text_color(color("cyan" if unlocked else "amber"), 0)

        if not unlocked:
            self.detail_id.set_text("// LOCKED")
            self.detail_title.set_text(self.LOCKED_CARD_TITLE)
            if is_acr_card:
                self.detail_text.set_text(
                    "This ACR card is locked.\n\n"
                    "Use an official NFC sticker or supported transfer to unlock it."
                )
            else:
                locked_text = (
                    "// CLEARANCE REQUIRED\n"
                    "--------------------\n"
                    "STATUS       ENCRYPTED\n"
                )
                if card_data.get("max_speed"):
                    locked_text += "MAX SPEED    REDACTED\n"
                locked_text += (
                    "\n"
                    "// ACCESS INSTRUCTIONS\n"
                    "Trade with another badge to identify and unlock this card."
                )
                self.detail_text.set_text(locked_text)
            try:
                self.detail_scroll.scroll_to_y(0, lv.ANIM.OFF)
            except Exception:
                pass
            return

        self.detail_id.set_text("// UNLOCKED")
        self.detail_title.set_text(card_data["title"])

        if is_acr_card:
            self.detail_text.set_text(str(card_data.get("detail", "")))
            try:
                self.detail_scroll.scroll_to_y(0, lv.ANIM.OFF)
            except Exception:
                pass
            return

        facts = card_data.get("facts", [])
        if facts:
            facts_lines = []
            for index, fact in enumerate(facts[:3], 1):
                facts_lines.append("%02d  %s" % (index, str(fact)))
            facts_text = "\n\n".join(facts_lines)
        else:
            facts_text = ""

        detail_text = (
            "// DETAIL\n"
            "---------\n"
            + str(card_data.get("detail", ""))
        )
        use_case = card_data.get("use_case")
        if use_case:
            detail_text += (
                "\n\n"
                "// MISSION PROFILE\n"
                "------------------\n"
                + str(use_case)
            )
        max_speed = card_data.get("max_speed")
        if max_speed:
            detail_text += (
                "\n\n"
                "// PERFORMANCE\n"
                "--------------\n"
                "MAX SPEED    "
                + str(max_speed)
            )
        if facts_text:
            detail_text += (
                "\n\n"
                "// FACTS\n"
                "--------\n"
                + facts_text
            )
        self.detail_text.set_text(detail_text)

        try:
            self.detail_scroll.scroll_to_y(0, lv.ANIM.OFF)
        except Exception:
            pass

    def _open_details(self):
        self._stop_acr_foil_effect(clear_test=True)
        self._cancel_unlock_animation(restore=True)
        self.details_open = True

        if self.on_details_open is not None:
            try:
                self.on_details_open()
            except Exception:
                pass

        self._fill_detail_panel(CARDS[self.index])
        self.details_overlay.remove_flag(lv.obj.FLAG.HIDDEN)

    def _open_details_for_tap(self, tx, ty):
        """Open details when a tap lands on the centered card face.

        Universal navigation observes the input device without covering this
        viewport, so taps at the bottom of a card arrive here normally.
        """
        if self.animating or self.dragging or self.details_open:
            return False
        if tx is None:
            return False

        card_left = self.NEUTRAL_X
        card_right = card_left + self.CARD_W
        if tx < card_left or tx >= card_right:
            return False

        card_top = self.CAROUSEL_Y + self.CARD_Y
        card_bot = card_top + self.CARD_H
        if ty is not None and not (card_top <= ty < card_bot):
            return False

        self._open_details()
        return True

    def _close_details(self):
        self.details_open = False
        self.details_overlay.add_flag(lv.obj.FLAG.HIDDEN)
        self._refresh_acr_foil_effect()

        if self.on_details_close is not None:
            try:
                self.on_details_close()
            except Exception:
                pass

    def _on_detail_pressed(self, event):
        del event
        x, y = self._get_touch_xy()
        self._detail_press_active = x is not None and y is not None
        self._detail_press_moved = False
        if self._detail_press_active:
            self._detail_press_x = x
            self._detail_press_y = y

    def _on_detail_pressing(self, event):
        del event
        if not self._detail_press_active or self._detail_press_moved:
            return
        x, y = self._get_touch_xy()
        if x is None or y is None:
            self._detail_press_moved = True
            return
        if (
            abs(x - self._detail_press_x) > self.DETAIL_TAP_MAX_MOVE
            or abs(y - self._detail_press_y) > self.DETAIL_TAP_MAX_MOVE
        ):
            self._detail_press_moved = True

    def _on_close_details(self, event):
        del event
        if not self._detail_press_active:
            return
        x, y = self._get_touch_xy()
        moved = self._detail_press_moved
        if x is None or y is None:
            moved = True
        elif (
            abs(x - self._detail_press_x) > self.DETAIL_TAP_MAX_MOVE
            or abs(y - self._detail_press_y) > self.DETAIL_TAP_MAX_MOVE
        ):
            moved = True
        self._detail_press_active = False
        if not moved and self.details_open:
            self._close_details()

    # ------------------------------------------------------------------ events

    def _on_back_clicked(self, event):
        if self.details_open:
            self._close_details()
            return
        if self.on_back:
            self.on_back()

    # ------------------------------------------------------------------ drag events

    def _get_touch_x(self):
        """Return current indev X in screen coordinates, or None on failure."""
        try:
            try:
                indev = lv.indev_get_act()
            except AttributeError:
                indev = lv.indev_active()
            if indev is None:
                return None
            pt = self._pt
            if pt is None:
                pt = lv.point_t()
            indev.get_point(pt)
            return pt.x
        except Exception:
            return None

    def _get_touch_xy(self):
        """Return (x, y) in screen coordinates, or (None, None) on failure."""
        try:
            try:
                indev = lv.indev_get_act()
            except AttributeError:
                indev = lv.indev_active()
            if indev is None:
                return None, None
            pt = self._pt
            if pt is None:
                pt = lv.point_t()
            indev.get_point(pt)
            return pt.x, pt.y
        except Exception:
            return None, None

    def _on_press(self, event):
        if self.animating:
            return
        self._pause_acr_foil_for_touch()
        self._cancel_unlock_animation(restore=True)
        self._cancel_image_restore_timer()
        tx, ty = self._get_touch_xy()
        if tx is None:
            self._schedule_image_restore()
            return
        now = ticks_ms()
        self._drag_start_x  = tx
        self._drag_start_y  = ty if ty is not None else 0
        self._drag_last_x   = self._drag_start_x
        self._drag_last_y   = self._drag_start_y
        self._drag_dir      = 0
        self._press_t       = now
        self.dragging       = True

    def _on_pressing(self, event):
        if not self.dragging:
            return
        tx, ty = self._get_touch_xy()
        if tx is None:
            return
        self._drag_last_x = tx
        if ty is not None:
            self._drag_last_y = ty
        delta = tx - self._drag_start_x

        if self._drag_dir == 0:
            # Determine drag direction once the finger has moved enough.
            if abs(delta) < 5:
                return
            if delta < 0:
                # Moving left → next card.  Abort if already at last card.
                if self.index >= len(CARDS) - 1:
                    self.dragging = False
                    self._schedule_image_restore()
                    return
                self._drag_dir = 1
            else:
                # Moving right → previous card.  Abort if already at first.
                if self.index <= 0:
                    self.dragging = False
                    self._schedule_image_restore()
                    return
                self._drag_dir = -1
            self._stop_acr_foil_effect(clear_test=True)
            self._prepare_card_pair(self._drag_dir)

        # Follow the finger only in the direction selected for this gesture.
        new_x = self.STRIP_IDLE_X + delta
        if self._drag_dir > 0:
            new_x = max(self.STRIP_IDLE_X - self.CARD_PITCH,
                        min(self.STRIP_IDLE_X, new_x))
        else:
            new_x = max(self.STRIP_IDLE_X,
                        min(self.STRIP_IDLE_X + self.CARD_PITCH, new_x))
        if new_x != self._last_strip_x:
            self._move_card_pair(new_x)

    def _on_release(self, event, prefer_last_sample=False):
        if not self.dragging:
            return
        self.dragging = False

        drag_dir = self._drag_dir
        self._drag_dir = 0

        tx, ty = self._get_touch_xy()
        if prefer_last_sample:
            tx = self._drag_last_x
            ty = self._drag_last_y
        delta = (tx - self._drag_start_x) if tx is not None else 0
        dy = (ty - self._drag_start_y) if ty is not None else 0

        now = ticks_ms()
        dt = ticks_diff(now, self._press_t)
        dx = delta
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        vel = abs_dx / max(abs(dt), 1)   # px/ms; avoid div-by-zero/wrap issues
        horizontal_intent = (
            abs_dx >= 8
            and abs_dx > abs_dy
        )
        is_quick_swipe = horizontal_intent and (
            abs_dx >= self.QUICK_SWIPE_MIN_TRAVEL
            or (abs_dx >= 10 and vel >= self.QUICK_SWIPE_VEL)
        )

        if drag_dir == 0:
            # A very fast flick can skip PRESSING samples, so _drag_dir never
            # gets set.  Infer direction on release and commit the card change
            # instead of doing nothing.
            if is_quick_swipe and not self.animating:
                if dx < 0 and self.index < len(CARDS) - 1:
                    self._stop_acr_foil_effect(clear_test=True)
                    self.animating = True
                    self._start_strip_anim(
                        self.STRIP_IDLE_X,
                        self.STRIP_IDLE_X - self.CARD_PITCH,
                        self._on_next_complete,
                    )
                elif dx > 0 and self.index > 0:
                    self._stop_acr_foil_effect(clear_test=True)
                    self.animating = True
                    self._start_strip_anim(
                        self.STRIP_IDLE_X,
                        self.STRIP_IDLE_X + self.CARD_PITCH,
                        self._on_prev_complete,
                    )
                if self.animating:
                    return

            # Pure tap — route by touch zone.
            if abs_dx < self.TAP_THRESHOLD and abs_dy < self.TAP_THRESHOLD and not self.animating:
                if tx is not None and tx < self.NEUTRAL_X:
                    self.go_prev()           # tapped left peek
                elif tx is not None and tx >= self.NEUTRAL_X + self.CARD_W:
                    self.go_next()           # tapped right peek
                elif tx is not None:
                    self._open_details_for_tap(tx, ty)
            if not self.animating:
                self._schedule_image_restore()
            return

        current_x = self._last_strip_x

        # Average velocity in px/ms over the whole gesture.  The old
        # calculation divided full travel by only the final sample interval,
        # which made slow drags look like flicks when release happened right
        # after a PRESSING event.
        is_flick = horizontal_intent and vel >= self.QUICK_SWIPE_VEL and (
            (drag_dir > 0 and dx < 0) or (drag_dir < 0 and dx > 0)
        )

        if drag_dir == 1:
            # Dragging next (left); measure how far left strip moved from idle.
            displacement = self.STRIP_IDLE_X - current_x
            if displacement >= self.SNAP_THRESHOLD or is_flick:
                self.animating = True
                self._start_strip_anim(
                    current_x,
                    self.STRIP_IDLE_X - self.CARD_PITCH,
                    self._on_next_complete,
                )
            else:
                self.animating = True
                self._start_strip_anim(current_x, self.STRIP_IDLE_X, self._on_drag_cancel)
        else:
            # Dragging prev (right); measure how far right from idle.
            displacement = current_x - self.STRIP_IDLE_X
            if displacement >= self.SNAP_THRESHOLD or is_flick:
                self.animating = True
                self._start_strip_anim(
                    current_x,
                    self.STRIP_IDLE_X + self.CARD_PITCH,
                    self._on_prev_complete,
                )
            else:
                self.animating = True
                self._start_strip_anim(current_x, self.STRIP_IDLE_X, self._on_drag_cancel)

    def _on_press_lost(self, event):
        """Finish a flick that leaves the viewport instead of snapping back."""
        if not self.dragging:
            return
        self._on_release(event, prefer_last_sample=True)

    # ------------------------------------------------------------------ navigation

    def go_next(self):
        self._stop_acr_foil_effect(clear_test=True)
        self._cancel_unlock_animation(restore=True)
        if self.animating or self.dragging:
            return
        if self.index >= len(CARDS) - 1:
            return
        if self.details_open:
            self._close_details()
        self.animating = True
        self._start_strip_anim(
            self.STRIP_IDLE_X,
            self.STRIP_IDLE_X - self.CARD_PITCH,
            self._on_next_complete,
        )

    def go_prev(self):
        self._stop_acr_foil_effect(clear_test=True)
        self._cancel_unlock_animation(restore=True)
        if self.animating or self.dragging:
            return
        if self.index <= 0:
            return
        if self.details_open:
            self._close_details()
        self.animating = True
        self._start_strip_anim(
            self.STRIP_IDLE_X,
            self.STRIP_IDLE_X + self.CARD_PITCH,
            self._on_prev_complete,
        )

    # ------------------------------------------------------------------ animation

    def _on_next_complete(self, _anim):
        self._finish_snap(self.index + 1, True)

    def _on_prev_complete(self, _anim):
        self._finish_snap(self.index - 1, True)

    def _on_drag_cancel(self, _anim):
        """Strip returned to STRIP_IDLE_X; draw lock frame before art restore."""
        self._finish_snap(self.index, False)

    def _start_strip_anim(self, start_x, end_x, done_cb):
        self._cancel_image_restore_timer()
        if not self._moving_slots:
            direction = 1 if end_x < start_x else -1 if end_x > start_x else 0
            self._prepare_card_pair(direction)

        # This firmware build cannot convert bound Python methods into LVGL
        # animation callback pointers. The previous path always raised and
        # immediately performed this same snap as its fallback.
        self._move_card_pair(end_x)
        done_cb(None)

    # ------------------------------------------------------------------ public API

    def unlock_card(self, card_id):
        """Refresh the display when a card becomes unlocked."""
        index = find_card_index(card_id)
        if index < 0:
            return False
        newly_unlocked = not bool(CARDS[index].get("unlocked", False))
        unlock_card_data(card_id)

        self._notify_card_unlocked(card_id)

        if index == self.index:
            if newly_unlocked and self.play_unlock_animation(card_id):
                pass
            else:
                self._fill_card(self.slot_curr, CARDS[self.index], load_art=(not self.dragging and not self.animating))
            if self.details_open:
                self._fill_detail_panel(CARDS[self.index])
        elif index == self.index - 2:
            self._fill_card(self.slot_before, CARDS[index], load_art=False, sliver=self.RENDER_SIDE_SLIVERS_IDLE)
        elif index == self.index - 1:
            self._fill_card(self.slot_prev, CARDS[index], load_art=False, sliver=self.RENDER_SIDE_SLIVERS_IDLE)
        elif index == self.index + 1:
            self._fill_card(self.slot_next, CARDS[index], load_art=False, sliver=self.RENDER_SIDE_SLIVERS_IDLE)
        elif index == self.index + 2:
            self._fill_card(self.slot_after, CARDS[index], load_art=False, sliver=self.RENDER_SIDE_SLIVERS_IDLE)
        return True

    def delete(self):
        self.stop()
        try:
            self.root.add_flag(lv.obj.FLAG.HIDDEN)
        except Exception:
            pass
        for name in ("delete_async", "del_async", "delete", "del"):
            try:
                getattr(self.root, name)()
                return
            except Exception:
                pass

    def stop(self):
        """Cancel standalone callbacks before the owning screen is deleted."""
        self._stop_acr_foil_effect(clear_test=True)
        self._cancel_unlock_animation(restore=False)
        self._cancel_image_restore_timer()

    def suspend_for_low_power(self):
        """Quiesce transient carousel work while the sleep overlay is visible."""
        self.dragging = False
        self.animating = False
        self._drag_dir = 0
        self._reset_card_pair()
        self._cancel_image_restore_timer()
        self._cancel_unlock_animation(restore=True)
        self._stop_acr_foil_effect(clear_test=True)

    def resume_from_low_power(self):
        """Restore the stable card view after the sleep overlay is removed."""
        self.dragging = False
        self.animating = False
        self._drag_dir = 0
        self._reset_card_pair()
        self._last_strip_x = self.STRIP_IDLE_X
        if CARDS:
            self._fill_card(self.slot_curr, CARDS[self.index], load_art=True)
        self._refresh_acr_foil_effect()
