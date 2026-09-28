# Production firmware

## Load assets

Erase the badge, then flash `badge-provisioning.uf2`. This image keeps the
same flash layout as production but leaves USB and the REPL available for the
asset transfer. Do not use the generic development UF2 for this step.

With the provisioning UF2 running, load the assets:

```powershell
.\provision_badge_assets.ps1 user -Port COM6
.\provision_badge_assets.ps1 staff -Port COM6
```

The script clears the filesystem and copies the card art, boot GIF, and sleep
image. It does not copy Python or saved state.

## Final flash

1. Disconnect USB after asset provisioning.
2. Hold BOOTSEL and reconnect USB.
3. Copy the production UF2 to `RPI-RP2` without erasing flash again.
4. Should be good.

