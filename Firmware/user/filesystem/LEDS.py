
import uasyncio as asyncio
from time import ticks_ms,ticks_add,ticks_diff
import neopixel
from machine import Pin
from random import randint



# some const rgb colors
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
CYAN = (0, 255, 255)

AMBER = (255, 100, 0)
GOLD = (255, 222, 30)
JADE = (0, 255, 40)
MAGENTA = (255, 0, 20)
WARM_WHITE = (253, 245, 230)
ORANGE = (255, 40, 0)
PINK = (242, 90, 255)
PURPLE = (180, 0, 255)
# Create a list with each variable
LED_COLOR_LIST = [
    RED, GREEN, BLUE, YELLOW, CYAN, AMBER, GOLD, JADE, MAGENTA, WARM_WHITE, ORANGE, PINK, PURPLE
]
LED_COLOR_LIST_NAMES = [
    "RED", "GREEN", "BLUE", "YELLOW", "CYAN", "AMBER", "GOLD", "JADE", "MAGENTA", "WARM WHITE", "ORANGE", "PINK", "PURPLE"
]
OFF = const((0,0,0))





class badge(object):
    def __init__(self) -> None:
        self.MainLEDChain_NUM_LEDS = 10
        self.MainLEDChain = 0
        #self.FrontLEDChain = 10
        self.np_main = neopixel.NeoPixel(Pin(self.MainLEDChain),self.MainLEDChain_NUM_LEDS)
        #self.np_front = neopixel.NeoPixel(Pin(self.MainLEDChain),self.MainLEDChain_NUM_LEDS)
        #self.np_front[0]=OFF
        #self.np_front.write()
        self._frame_seq=0
        self.lightsOff()
        self._lights_flag = False
        self.currentPassiveLightColor="PURPLE"
        self.brightness=10
        self.golden_shimmer="NORMAL"
        
        




        ########################

###############NEOPIXEL CONTROLS######################################
    def set_led_brightness(self, brightness):
        try:
            brightness = int(brightness)
        except Exception:
            brightness = 10

        if brightness < 0:
            brightness = 0
        if brightness > 100:
            brightness = 100

        self.brightness = brightness
        return True

    def set_brightness(self, color):
        brightness=self.brightness/100
        r, g, b = color
        r = int(r * brightness)
        g = int(g * brightness)
        b = int(b * brightness)
        # changed from 0 to 1, to have 1 be lowest setting. 0 will now not flash leds
        return (r, g, b)

    def lightsOff(self):
        # cleanup neopixels
        for i in range(self.MainLEDChain_NUM_LEDS):
            self.np_main[i]=(0,0,0)
        self._write_main()

    def _write_main(self):
        self.np_main.write()
        self._frame_seq += 1

    def scale_color(self,color, scale):
        return (color[0] * scale // 255, color[1] * scale // 255, color[2] * scale // 255)

##PASSIVE LIGHT PATTERNS
###############
    def wheel(self,pos):
        # Generate rainbow colors across 0-255 positions.
        if pos < 85:
            return (pos * 3, 255 - pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return (255 - pos * 3, 0, pos * 3)
        else:
            pos -= 170
            return (0, pos * 3, 255 - pos * 3)

    async def rainbow_cycle(self,wait=20):
        try:
            while self._lights_flag:
                for j in range(255):
                    for i in range(self.MainLEDChain_NUM_LEDS):
                        rc_index = (i * 256 // self.MainLEDChain_NUM_LEDS) + j
                        self.np_main[i] = self.set_brightness(self.wheel(rc_index & 255))
                    self._write_main()
                    await asyncio.sleep_ms(wait)
        except asyncio.CancelledError:
            self.lightsOff()
###############
    async def theater_chase(self, wait=150):
        try:
            while self._lights_flag:
                color=self.getLEDColor(self.currentPassiveLightColor)
                for q in range(3):
                    for i in range(0, self.MainLEDChain_NUM_LEDS, 3):
                        self.np_main[(i + q)%self.MainLEDChain_NUM_LEDS] = self.set_brightness(color)
                    self._write_main()
                    await asyncio.sleep_ms(wait)
                    for i in range(0, self.MainLEDChain_NUM_LEDS, 3):
                        self.np_main[(i + q)%self.MainLEDChain_NUM_LEDS] = OFF
        except asyncio.CancelledError:
            self.lightsOff()

    async def larson_scanner(self, wait=150):
        try:
            while self._lights_flag:
                color=self.getLEDColor(self.currentPassiveLightColor)
                for i in range(self.MainLEDChain_NUM_LEDS):
                    self.np_main.fill((0, 0, 0))
                    self.np_main[i] = self.set_brightness(color)
                    self._write_main()
                    await asyncio.sleep_ms(wait)
                for i in range(self.MainLEDChain_NUM_LEDS - 1, -1, -1):
                    self.np_main.fill((0, 0, 0))
                    self.np_main[i] = self.set_brightness(color)
                    self._write_main()
                    await asyncio.sleep_ms(wait)
        except asyncio.CancelledError:
            self.lightsOff()

    async def breathe(self, wait=50):
        try:
        # maxBrightness=int(self.brightness*256)
            while self._lights_flag:
                color=self.getLEDColor(self.currentPassiveLightColor)
                for j in range(127):
                    for i in range(self.MainLEDChain_NUM_LEDS):
                        self.np_main[i] = self.set_brightness((color[0] * j // 255, color[1] * j // 255, color[2] * j // 255))
                    self._write_main()
                    await asyncio.sleep_ms(wait)
                for j in range(127, -1, -1):
                    for i in range(self.MainLEDChain_NUM_LEDS):
                        self.np_main[i] = self.set_brightness((color[0] * j // 255, color[1] * j // 255, color[2] * j // 255))
                    self._write_main()
                    await asyncio.sleep_ms(wait)
        except asyncio.CancelledError:
            self.lightsOff()

    async def twinkle(self, wait=250):
        try:
            while self._lights_flag:
                color=self.getLEDColor(self.currentPassiveLightColor)
                for i in range(self.MainLEDChain_NUM_LEDS):
                    if randint(0, 1):
                        self.np_main[i] = self.set_brightness(color)
                    else:
                        self.np_main[i] = OFF
                self._write_main()
                await asyncio.sleep_ms(wait)
        except asyncio.CancelledError:
            self.lightsOff()

    async def allColorsBreathe(self,wait=20):
        try:
            while self._lights_flag:
                for color in LED_COLOR_LIST:
                    for j in range(77):
                        for i in range(self.MainLEDChain_NUM_LEDS):
                            self.np_main[i] = self.set_brightness((color[0] * j // 255, color[1] * j // 255, color[2] * j // 255))
                        self._write_main()
                        await asyncio.sleep_ms(wait)
                    for j in range(76, -1, -1):
                        for i in range(self.MainLEDChain_NUM_LEDS):
                            self.np_main[i] = self.set_brightness((color[0] * j // 255, color[1] * j // 255, color[2] * j // 255))
                        self._write_main()
                        await asyncio.sleep_ms(wait)
        except asyncio.CancelledError:
            self.lightsOff()
    async def flame_effect(self, wait=70):
        """
        Flame effect on physical LEDs 1, 2, 9, and 10.

        Physical LED numbers are usually 1-based:
        LED 1  -> index 0
        LED 2  -> index 1
        LED 9  -> index 8
        LED 10 -> index 9
        """

        target_led_numbers = (1, 2, 9, 10)
        target_indexes = tuple(led_number - 1 for led_number in target_led_numbers)
        body_color = self.set_brightness(
            self.getLEDColor(self.currentPassiveLightColor)
        )

        flame_colors = (
            (255, 20, 0),    # deep red-orange
            (255, 45, 0),    # orange-red
            (255, 80, 0),    # orange
            (255, 120, 10),  # bright orange
            (180, 20, 0),    # dark red
            (80, 5, 0),      # ember
        )

        try:
            while self._lights_flag:
                # Hold the non-engine LEDs at the selected body color.
                for led_index in range(self.MainLEDChain_NUM_LEDS):
                    if led_index in target_indexes:
                        self.np_main[led_index] = OFF
                    else:
                        self.np_main[led_index] = body_color

                # Flicker only LEDs 1, 2, 9, and 10
                for led_index in target_indexes:
                    if 0 <= led_index < self.MainLEDChain_NUM_LEDS:
                        color = flame_colors[randint(0, len(flame_colors) - 1)]

                        # Random brightness flicker.
                        # Scale is 0-255, so this stays fairly power-safe.
                        intensity = randint(40, 150)
                        self.np_main[led_index] = self.set_brightness(self.scale_color(color, intensity))

                # Occasional brighter spark
                if randint(0, 8) == 0:
                    spark_index = target_indexes[randint(0, len(target_indexes) - 1)]

                    if 0 <= spark_index < self.MainLEDChain_NUM_LEDS:
                        self.np_main[spark_index] = self.set_brightness((180, 80, 10))

                self._write_main()
                await asyncio.sleep_ms(wait)

        except asyncio.CancelledError:
            self.lightsOff()

    async def cold_start_afterburner(self, wait=45):
        """
        SR-71 cold start into blue afterburner.

        Physical LED numbers:
        Engines/output:   1, 2, 9, 10
        Opposite engines: 5, 6
        Left side/body:   3, 4
        Right side/body:  7, 8
        """

        engines = (1, 2, 9, 10)
        nose_or_opposite = (5, 6)
        left_side = (3, 4)
        right_side = (7, 8)
        body = left_side + right_side + nose_or_opposite
        accent_route = (3, 4, 7, 8, 5, 6, 5, 8, 7, 4, 3)
        next_accent = ticks_add(ticks_ms(), randint(18000, 32000))
        accent_step = -1

        def led_index(led_number):
            return led_number - 1

        def safe_set(led_number, color):
            index = led_index(led_number)
            if 0 <= index < self.MainLEDChain_NUM_LEDS:
                self.np_main[index] = color

        def clear_main():
            for i in range(self.MainLEDChain_NUM_LEDS):
                self.np_main[i] = OFF

        def dim(color, amount):
            # amount is 0-255
            return self.set_brightness(self.scale_color(color, amount))

        def body_dim(amount):
            return dim(self.getLEDColor(self.currentPassiveLightColor), amount)

        try:
            clear_main()
            self._write_main()

            # Phase 1: cold dark body wake-up
            # Dim blue/purple body pulse, engines still dark.
            for brightness in range(0, 80, 4):
                clear_main()

                for led in body:
                    safe_set(led, body_dim(brightness))

                self._write_main()
                await asyncio.sleep_ms(wait)

            for brightness in range(80, 10, -4):
                clear_main()

                for led in body:
                    safe_set(led, body_dim(brightness))

                self._write_main()
                await asyncio.sleep_ms(wait)

            # Phase 2: engine ignition, red/orange flicker
            for _ in range(45):
                clear_main()

                # Body stays low stealth purple
                for led in body:
                    safe_set(led, body_dim(35))

                # Engines flicker like startup combustion
                for led in engines:
                    flicker = randint(35, 130)
                    flame_color = (
                        255,
                        randint(20, 90),
                        0
                    )
                    safe_set(led, dim(flame_color, flicker))

                self._write_main()
                await asyncio.sleep_ms(randint(35, 90))

            # Final state: stay in flame-colored engine flicker
            while self._lights_flag:
                clear_main()

                # Body stays low stealth purple
                for led in body:
                    safe_set(led, body_dim(35))

                # Occasional body-color ripple.
                now = ticks_ms()
                if accent_step < 0 and ticks_diff(now, next_accent) >= 0:
                    accent_step = 0
                if accent_step >= 0:
                    pulse_led = accent_route[accent_step]
                    safe_set(pulse_led, body_dim(92))
                    accent_step += 1
                    if accent_step >= len(accent_route):
                        accent_step = -1
                        next_accent = ticks_add(now, randint(18000, 32000))

                # Engines keep flickering flame color
                for led in engines:
                    flicker = randint(35, 130)
                    flame_color = (
                        255,
                        randint(20, 90),
                        0
                    )
                    safe_set(led, dim(flame_color, flicker))

                self._write_main()
                await asyncio.sleep_ms(randint(35, 90))

        except asyncio.CancelledError:
            self.lightsOff()

    def _render_blackbird_frame(self, step):
        engines = (0, 1, 8, 9)
        intakes = (4, 5)
        body = (2, 3, 6, 7)
        engine_colors = (
            (30, 40, 255),
            (100, 20, 255),
            (40, 100, 255),
            (185, 205, 255),
        )

        for index in range(self.MainLEDChain_NUM_LEDS):
            self.np_main[index] = OFF

        breath = step % 64
        if breath > 31:
            breath = 63 - breath
        intake_level = 30 + breath * 3
        intake_color = self.set_brightness(
            self.scale_color(CYAN, intake_level)
        )
        for index in intakes:
            self.np_main[index] = intake_color

        sweep = (step // 3) % len(body)
        for position, index in enumerate(body):
            distance = (position - sweep) % len(body)
            level = 105 if distance == 0 else 52 if distance == 1 else 24
            purple = self.getLEDColor(self.currentPassiveLightColor)
            self.np_main[index] = self.set_brightness(
                self.scale_color(purple, level)
            )

        for index in engines:
            source = engine_colors[randint(0, len(engine_colors) - 1)]
            level = randint(105, 210)
            self.np_main[index] = self.set_brightness(
                self.scale_color(source, level)
            )

    async def blackbird_pattern(self):
        next_accent = ticks_add(ticks_ms(), randint(20000, 40000))
        accent_step = -1
        step = 0
        try:
            while self._lights_flag:
                self._render_blackbird_frame(step)
                self._write_main()

                now = ticks_ms()
                if accent_step < 0 and ticks_diff(now, next_accent) >= 0:
                    accent_step = 0
                if accent_step >= 0:
                    route = (0, 2, 4, 6, 8, 9, 7, 5, 3, 1)
                    color = self.getLEDColor(self.currentPassiveLightColor)
                    self.np_main[route[accent_step]] = self.set_brightness(
                        self.scale_color(color, 145)
                    )
                    self._write_main()
                    accent_step += 1
                    if accent_step >= len(route):
                        accent_step = -1
                        next_accent = ticks_add(now, randint(20000, 40000))

                await asyncio.sleep_ms(80)

                step += 1
        except asyncio.CancelledError:
            self.lightsOff()

    async def afterburner_steady(self, wait=45):
        engines = (1, 2, 9, 10)
        body = (3, 4, 7, 8, 5, 6)
        accent_route = (3, 4, 7, 8, 5, 6, 5, 8, 7, 4, 3)
        next_accent = ticks_add(ticks_ms(), randint(18000, 32000))
        accent_step = -1

        def safe_set(led_number, color):
            index = led_number - 1
            if 0 <= index < self.MainLEDChain_NUM_LEDS:
                self.np_main[index] = color

        def dim(color, amount):
            return self.set_brightness(self.scale_color(color, amount))

        try:
            while self._lights_flag:
                for i in range(self.MainLEDChain_NUM_LEDS):
                    self.np_main[i] = OFF

                body_color = self.getLEDColor(self.currentPassiveLightColor)
                for led in body:
                    safe_set(led, dim(body_color, 35))

                now = ticks_ms()
                if accent_step < 0 and ticks_diff(now, next_accent) >= 0:
                    accent_step = 0
                if accent_step >= 0:
                    safe_set(accent_route[accent_step], dim(body_color, 92))
                    accent_step += 1
                    if accent_step >= len(accent_route):
                        accent_step = -1
                        next_accent = ticks_add(now, randint(18000, 32000))

                for led in engines:
                    flame_color = (255, randint(20, 90), 0)
                    safe_set(led, dim(flame_color, randint(35, 130)))

                self._write_main()
                await asyncio.sleep_ms(randint(35, 90))
        except asyncio.CancelledError:
            self.lightsOff()
            raise

    async def golden_gem(self, wait=105):
        """Deep-gold gemstone facets with slow, sparse glimmers."""
        route = (0, 2, 4, 6, 8, 9, 7, 5, 3, 1)
        glint_step = -1
        def next_glint_delay():
            if self.golden_shimmer == "RARE":
                return randint(12000, 20000)
            if self.golden_shimmer == "OFTEN":
                return randint(3500, 6500)
            return randint(7000, 12000)

        next_glint = ticks_add(ticks_ms(), next_glint_delay())
        step = 0

        try:
            while self._lights_flag:
                breath = step % 72
                if breath > 35:
                    breath = 71 - breath
                base_level = 42 + breath

                for position, index in enumerate(route):
                    facet = base_level + ((position * 13 + step) % 18)
                    self.np_main[index] = self.set_brightness(
                        self.scale_color((255, 125, 4), facet)
                    )

                now = ticks_ms()
                if glint_step < 0 and ticks_diff(now, next_glint) >= 0:
                    glint_step = 0

                if glint_step >= 0:
                    glint_index = route[glint_step]
                    self.np_main[glint_index] = self.set_brightness(
                        self.scale_color((255, 225, 95), 175)
                    )
                    if glint_step > 0:
                        trail_index = route[glint_step - 1]
                        self.np_main[trail_index] = self.set_brightness(
                            self.scale_color((255, 180, 35), 105)
                        )
                    glint_step += 1
                    if glint_step >= len(route):
                        glint_step = -1
                        next_glint = ticks_add(now, next_glint_delay())

                self._write_main()
                step += 1
                await asyncio.sleep_ms(wait)
        except asyncio.CancelledError:
            self.lightsOff()
            raise

    async def blackbird_ascension(self):
        engines = (0, 1, 8, 9)
        intakes = (4, 5)
        body = (2, 3, 6, 7)
        systems_pairs = ((4, 5), (3, 6), (2, 7))
        lit = []

        def clear():
            for index in range(self.MainLEDChain_NUM_LEDS):
                self.np_main[index] = OFF

        def scaled(rgb, level):
            return self.set_brightness(self.scale_color(rgb, level))

        try:
            clear()
            self._write_main()

            # Systems check: illuminate the airframe from the center outward.
            for pair in systems_pairs:
                lit.extend(pair)
                clear()
                for index in lit:
                    self.np_main[index] = scaled(
                        self.getLEDColor(self.currentPassiveLightColor), 62
                    )
                self._write_main()
                await asyncio.sleep_ms(240)

            # Intake ignition: three progressively brighter, faster pulses.
            pulse_levels = (85, 145, 220)
            pulse_delays = (170, 130, 90)
            for pulse in range(3):
                for index in body:
                    self.np_main[index] = scaled(
                        self.getLEDColor(self.currentPassiveLightColor), 45
                    )
                for index in intakes:
                    self.np_main[index] = scaled(CYAN, pulse_levels[pulse])
                self._write_main()
                await asyncio.sleep_ms(pulse_delays[pulse])
                for index in intakes:
                    self.np_main[index] = scaled(CYAN, 25)
                self._write_main()
                await asyncio.sleep_ms(pulse_delays[pulse] // 2)

            # Engine start: each output advances independently through ignition.
            ignition = (
                (90, 0, 0),
                (255, 40, 0),
                (255, 125, 0),
                (160, 195, 255),
                (95, 120, 255),
            )
            for frame in range(35):
                for index in body:
                    self.np_main[index] = scaled(
                        self.getLEDColor(self.currentPassiveLightColor), 42
                    )
                for index in intakes:
                    self.np_main[index] = scaled(CYAN, 42)
                stage = min(len(ignition) - 1, frame // 7)
                for index in engines:
                    source_index = stage + randint(-1, 1)
                    if source_index < 0:
                        source_index = 0
                    if source_index >= len(ignition):
                        source_index = len(ignition) - 1
                    self.np_main[index] = scaled(
                        ignition[source_index], randint(95, 215)
                    )
                self._write_main()
                await asyncio.sleep_ms(randint(38, 78))

            afterburner = scaled((115, 95, 255), 220)
            for index in engines:
                self.np_main[index] = afterburner
            self._write_main()
            await asyncio.sleep_ms(220)

            # Mach run: accelerating pale-blue laps over an engine underglow.
            route = (0, 2, 4, 6, 8, 9, 7, 5, 3, 1)
            for delay in (75, 58, 42, 30):
                for pulse_index in route:
                    clear()
                    for index in engines:
                        self.np_main[index] = scaled((55, 45, 210), 72)
                    self.np_main[pulse_index] = scaled((210, 230, 255), 235)
                    self._write_main()
                    await asyncio.sleep_ms(delay)

            # Directional completion ripple.
            clear()
            self._write_main()
            await asyncio.sleep_ms(150)
            reward_color = self.getLEDColor(self.currentPassiveLightColor)
            for index in route:
                self.np_main[index] = scaled(reward_color, 135)
                self._write_main()
                await asyncio.sleep_ms(38)

            # Completion hold.
            hold_end = ticks_add(ticks_ms(), 8000)
            step = 0
            while self._lights_flag and ticks_diff(hold_end, ticks_ms()) > 0:
                self._render_blackbird_frame(step)
                self._write_main()
                step += 1
                await asyncio.sleep_ms(80)

        except asyncio.CancelledError:
            self.lightsOff()
            raise

    def getLEDColor(self,colorName):
        return LED_COLOR_LIST[LED_COLOR_LIST_NAMES.index(colorName)]

# Do not auto-run tests on import.
# Run manually from REPL only if needed:
# import uasyncio as asyncio
# import LEDS
# asyncio.run(LEDS.verify_leds())

try:
    import _thread
except Exception:
    _thread = None


ALL_LED_PATTERNS = (
    "NONE",
    "Solid",
    "Rainbow",
    "Theater",
    "Scanner",
    "Breathe",
    "Twinkle",
    "Rainbow Breathe",
    "Flame",
    "Afterburner",
    "BLACKBIRD",
    "GOLDEN",
)


def _run_led_runtime(runtime):
    """Module-level core-2 entry point required by this MicroPython port."""
    try:
        asyncio.run(runtime._runner())
    except Exception as exc:
        print("LED runtime crashed:", exc)
        try:
            runtime.b.lightsOff()
        except Exception:
            pass


class LEDRuntime:
    """
    Background LED runtime.

    main.py calls this from LVGL button callbacks.
    This class owns the LED animation loop.

    Important:
    - Do not call LVGL from here.
    - Do not update labels from here.
    - This only writes NeoPixels.
    """

    def __init__(self):
        self.b = badge()

        self.pattern = "NONE"
        self.color = "PURPLE"
        self.enabled = False
        self.brightness = 10
        self.golden_shimmer = "NORMAL"

        self._running = False
        self._started = False
        self._seq = 0
        self._reward_requested = False
        self._reward_running = False
        self._recover_steady = False
        self._watch_frame_seq = self.b._frame_seq
        self._watch_last_progress_ms = ticks_ms()
        self._watch_cooldown_until_ms = 0
        self.watchdog_restarts = 0

        try:
            import _thread
            self._thread = _thread
        except Exception:
            self._thread = None


    def start(self):
        if self._started:
            return True

        if self._thread is None:
            print("LEDRuntime requires _thread; no LED background thread available")
            return False

        self._running = True
        try:
            # Passing a bound method fails on this firmware build with
            # "Cannot convert 'bound_method' to pointer". Use a module-level
            # function as the core-2 entry point.
            self._thread.start_new_thread(_run_led_runtime, (self,))
        except Exception as exc:
            self._running = False
            self._started = False
            print("LED second-core launch failed:", exc)
            return False

        self._started = True
        print("Original LED runtime scheduled on second core")
        return True


    def set(
        self,
        pattern="NONE",
        color="PURPLE",
        enabled=False,
        brightness=None,
        golden_shimmer=None,
    ):
        if pattern not in ALL_LED_PATTERNS:
            print("Unknown LED pattern:", pattern)
            return False

        if color not in LED_COLOR_LIST_NAMES:
            print("Unknown LED color:", color)
            return False

        if brightness is not None:
            try:
                brightness = int(brightness)
            except Exception:
                brightness = self.brightness

            if brightness < 0:
                brightness = 0
            if brightness > 100:
                brightness = 100

            self.brightness = brightness

        if golden_shimmer in ("RARE", "NORMAL", "OFTEN"):
            self.golden_shimmer = golden_shimmer
            self.b.golden_shimmer = golden_shimmer

        # No lock. On this badge these are tiny assignments, and this avoids
        # failures on firmware builds where _thread locks are missing or return None.
        self.pattern = pattern
        self.color = color
        self.enabled = enabled
        self._seq += 1

        return True


    def off(self):
        return self.set("NONE", self.color, False)

    def play_collection_reward(self):
        if self._reward_requested or self._reward_running:
            return False
        self._reward_requested = True
        self._reward_running = True
        self._seq += 1
        return True


    def _snapshot(self):
        return self.enabled, self.pattern, self.color, self.brightness, self._seq

    def health_check(self, now=None):
        if now is None:
            now = ticks_ms()

        frame_seq = self.b._frame_seq
        active = (
            self._started
            and self._running
            and self.enabled
            and self.pattern not in ("NONE", "Solid")
        )
        if not active:
            self._watch_frame_seq = frame_seq
            self._watch_last_progress_ms = now
            return False

        if frame_seq != self._watch_frame_seq:
            self._watch_frame_seq = frame_seq
            self._watch_last_progress_ms = now
            return False

        if ticks_diff(now, self._watch_last_progress_ms) < 2000:
            return False
        if ticks_diff(now, self._watch_cooldown_until_ms) < 0:
            return False

        self._recover_steady = self.pattern == "Afterburner"
        self.watchdog_restarts += 1
        self._watch_last_progress_ms = now
        self._watch_cooldown_until_ms = ticks_add(now, 3000)
        self._seq += 1
        print("LED watchdog restart:", self.pattern, self.watchdog_restarts)
        return True

    async def _runner(self):
        task = None
        last_seq = -1

        while self._running:
            enabled, pattern, color, brightness, seq = self._snapshot()

            if seq != last_seq:
                reward_requested = self._reward_requested
                self._reward_requested = False

                if task is not None:
                    self.b._lights_flag = False
                    task.cancel()

                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        print("LED task stop error:", exc)

                    task = None

                self.b.lightsOff()
                last_seq = seq

                self.b.set_led_brightness(brightness)

                if reward_requested:
                    self.b._lights_flag = True
                    task = asyncio.create_task(self._run_collection_reward())

                elif enabled and pattern != "NONE":
                    self.b.currentPassiveLightColor = color
                    self.b._lights_flag = True

                    coro = self._make_pattern_coro(pattern)

                    if coro is not None:
                        task = asyncio.create_task(coro)

            await asyncio.sleep_ms(50)

        if task is not None:
            self.b._lights_flag = False
            task.cancel()

            try:
                await task
            except Exception:
                pass

        self.b.lightsOff()

    def _make_pattern_coro(self, pattern):
        if pattern == "Solid":
            return self._solid()

        if pattern == "Rainbow":
            return self.b.rainbow_cycle()

        if pattern == "Theater":
            return self.b.theater_chase()

        if pattern == "Scanner":
            return self.b.larson_scanner()

        if pattern == "Breathe":
            return self.b.breathe()

        if pattern == "Twinkle":
            return self.b.twinkle()

        if pattern == "Rainbow Breathe":
            return self.b.allColorsBreathe()

        if pattern == "Flame":
            return self.b.flame_effect()

        if pattern == "Afterburner":
            if self._recover_steady:
                self._recover_steady = False
                return self.b.afterburner_steady()
            return self.b.cold_start_afterburner()

        if pattern == "BLACKBIRD":
            return self.b.blackbird_pattern()

        if pattern == "GOLDEN":
            return self.b.golden_gem()

        return None

    async def _run_collection_reward(self):
        try:
            await self.b.blackbird_ascension()
        finally:
            self._reward_running = False
            # Re-enter the runner and restore the latest selected mode. If a
            # user change canceled the reward this may cause one harmless
            # restart of that newly selected mode.
            self._seq += 1

    async def _solid(self):
        while self.b._lights_flag:
            color = self.b.getLEDColor(self.b.currentPassiveLightColor)
            color = self.b.set_brightness(color)

            for i in range(self.b.MainLEDChain_NUM_LEDS):
                self.b.np_main[i] = color

            self.b._write_main()
            await asyncio.sleep_ms(250)
