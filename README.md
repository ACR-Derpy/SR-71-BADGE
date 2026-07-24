<h1><p align="center">SR-71 BADGE</p></h1>

<p align="center">
~A User Guide~
</p>

-----
<p align="center">
A Lockheed Martin Aeronautics Cyber Range (ACR) project.<br>
Join us on <a href="https://discord.gg/sgUe73dNS8">discord</a><br><br>
<img src="images/badgeSpoiler.gif" width="350" height="200" border="10"/>
</p>

> Disclaimer
>> [!NOTE]
>> Everything about this badge was made using open-source and public information.
>>
>> This badge is for fun and educational purposes :smile:
-----
# ACR SR-71 Badge User Guide

> Firmware guide updated July 24, 2026.

The ACR SR-71 badge is an interactive electronic badge built around collectible aircraft cards, peer-to-peer NFC trading, passive NFC sticker unlocks, customizable LEDs, and a touch-screen interface.

## Quick Start

1. Power on the badge and allow the boot sequence to finish.
2. Use the touch screen to select **CARD DISPLAY**, **INITIATE TRADE**, or **SETTINGS**...
3. Swipe up from the bottom edge on most screens to return to the main menu.
4. Tap the top-left **BACK** button when one is shown.
5. Tap the screen once to wake the badge if it has entered low-power mode.

On its first boot, the badge automatically unlocks a small set of starter cards. Card unlocks and settings are saved and remain available after restarting the badge.

## Main Menu

### Card Display

Open your card collection.

### Initiate Trade

Open the NFC menu to exchange a card with another badge or scan an official passive NFC sticker.

### Settings

Adjust LED behavior, screen brightness, and low-power behavior.

## Card Display

The card carousel contains both locked and unlocked cards.

### Browsing Cards

- Swipe left or right across the card to move through the collection.
- The left and right arrow buttons can also be used.
- Allow the card artwork a moment to load after changing cards.
- Locked cards appear redacted until they are unlocked.

### Card Details

Tap the centered card to open its information screen.

Unlocked cards may show:

- Aircraft name and card ID
- Mission or use case
- Maximum speed
- Aircraft facts and background information

Tap anywhere on the details screen to close it.

## Unlocking Cards

Cards can be unlocked in three ways:

1. Starter cards assigned on first boot
2. Peer-to-peer trades with another badge
3. Official passive NFC stickers or authorized ACR badges

Special ACR-designated cards are not available through the random starter-card system and cannot be traded between normal badges. They must be received from an authorized source, such as an NFC sticker found around the Con or staff badge.

## Peer-to-Peer NFC Trading

A peer trade exchanges one selected card from each badge. Both participants receive the other person's card without losing the card they offered.

### Before Starting

- Both badges must select an unlocked, tradeable card.
- ACR-designated cards cannot be selected for peer trading.
- Keep the two badge antenna areas very close together.
- Hold the badges parallel and steady throughout the full trade.
- Metal objects, batteries, hands, or cables directly behind the antennas may reduce range.

### How to Trade

On both badges:

1. Open **INITIATE TRADE**.
2. Select **PEER TO PEER**.
3. Choose one unlocked card to offer.
4. Confirm the selection.
5. Select **START PEER TRADE**.
6. Place the NFC antenna areas directly over each other.
7. Hold both badges still until both show a result.

The badges automatically decide which one starts the exchange. Do not separate them when the first badge changes screens; wait until both badges report completion.

A peer trade may take several seconds. The operation can remain active for up to approximately 30 seconds before timing out.

### Improving Trade Reliability

For the best NFC connection:

- Start with the badges nearly touching.
- Keep both badges on the same flat plane.
- Align the antenna sections, not only the outside edges of the badge.
- Avoid rotating one badge 90 degrees relative to the other.
- Hold both badges still until both display **TRADE COMPLETE**.
- If a trade fails, return to the trade menu and restart the process on both badges.

If one badge reports success and the other reports failure, check both card collections before trying again. A card that was already saved will remain unlocked.

## Passive NFC Sticker Scanning

Official NFC stickers can unlock designated cards.

### How to Scan a Sticker

1. Open **INITIATE TRADE**.
2. Select **TAG READER**.
3. Select **START TAG READER**.
4. Hold the sticker directly against or immediately above the badge's NFC antenna area.
5. Keep the sticker still until the badge reports success or failure.

The reader may remain active for up to approximately 30 seconds.

Only properly programmed official stickers are accepted. A normal NFC tag, URL tag, contact card, or plain-text card ID will not unlock a card.

If the sticker is not detected:

- Move it slowly across the NFC antenna area.
- Flip the sticker over.
- Remove nearby metal objects.
- Hold it flat against the badge.
- Restart the tag reader and try again.

## LED Settings

Open **SETTINGS** and select **LED CONFIG**.

Available controls include:

- **Pattern**: Select the active animation.
- **Color**: Select the main color for patterns that use one.
- **Brightness**: Adjust LED brightness.
- **Off**: Select the `NONE` pattern to disable the LEDs.

Some patterns use their own colors and will not display the color selector.

LED settings are saved automatically.

## Display Brightness

Open **SETTINGS** and select **DISPLAY BRIGHTNESS**.

Use the on-screen controls to raise or lower the normal screen brightness. The selected level is saved and restored after reboot.

## Low-Power Settings

Open **SETTINGS** and select **LOW POWER CONFIG**.

Available modes:

- **Disabled**: The screen remains active.
- **Static Logo**: The badge displays a low-power image after the idle timeout.
- **Screen Off**: The backlight turns off after the idle timeout.

The idle timeout can also be adjusted. Touching the screen wakes the badge.

Low-power mode does not change the active LED pattern.

## Navigation

### Back Button

Nested menus normally provide a **BACK** button in the upper-left corner.

### Swipe-Up Shortcut

On most feature screens, swipe upward from the bottom portion of the display to return to the main menu.

The swipe-up shortcut is intentionally disabled on some overlays, including the card details screen. Tap the overlay to close it first.

### During NFC Operations

The active NFC screen displays **PLEASE WAIT** while the radio operation is running. The interface will not respond to navigation gestures until the operation finishes or times out.

## Saved Data

The badge stores the following information locally:

- Unlocked card IDs
- Current card-carousel position
- LED pattern, color, and brightness
- Screen brightness
- Low-power mode and timeout

A normal restart or power cycle should not erase this information.

## Troubleshooting

### The Screen Is Dark

- Tap the screen once in case the badge is in low-power mode.
- Disconnect and reconnect power if the badge does not wake.
- Allow the full boot sequence to finish before interacting with the screen.

### Touch Input Is Inconsistent

- Tap near the center of buttons.
- Use deliberate swipes rather than very small/fast movements.
- Clean the screen if moisture or debris is present.
- Power cycle the badge if touch stops responding completely.

### A Card Image Appears Late

The badge delays loading full artwork until the carousel finishes moving. A brief placeholder after a swipe is normal, but if there is noticable lag between swipes, a power cycle should fix the issue. 

### Peer Trade Does Not Start

- Start peer trade on both badges.
- Put the NFC antennas nearly in contact.
- Keep the badges parallel.
- Hold them still for the full exchange.
- Move away from metal surfaces/sources of interference.
- Restart the trade on both badges after a timeout (15 seconds).

### A Sticker Is Not Detected

- Confirm it is an official badge sticker.
- Hold it directly against the NFC antenna area.
- Try both sides of the sticker.
- Move the sticker slowly instead of repeatedly tapping it.
- Restart the tag reader after a timeout.

### NFC Appears Frozen

Wait for the current operation timeout. If the badge remains stuck afterward, perform a full power cycle by disconnecting all power (battery and USB-C) and reconnecting it.

A power cycle resets the NFC controller but does not remove saved card unlocks or settings.

### LEDs Stop or Look Incorrect

- Open **LED CONFIG** and select the desired pattern again.
- Verify that brightness is above zero.
- Select a different pattern and switch back.
- Power cycle the badge if the LED animation does not recover.

## Care and Handling

- Do not bend the circuit.
- Keep conductive objects away from exposed electronics.
- Avoid liquid, excessive heat, and direct impact.
- Do not place the badge against exposed metal while powered.
- Disconnect power before attaching, removing, or inspecting hardware connections.
- We support modding the badge (and would love to see your "alterations" in the photos channel on discord) and the firmware will be released sometime after the conference ends. However, the user assumes responsibility for a damaged or bricked badge and we cannot provide replacements.




## Support

For badge problems during the event, bring the badge to an ACR or Aerospace Village staff member. Describe what happened immediately before the problem and whether a power cycle changed the behavior.
