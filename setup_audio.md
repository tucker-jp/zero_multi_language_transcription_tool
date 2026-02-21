# Audio Setup Guide (macOS)

This app captures system audio using **BlackHole**, a free virtual audio driver.

## 1. Install BlackHole

```bash
brew install blackhole-2ch
```

Or download from: https://existential.audio/blackhole/

## 2. Create a Multi-Output Device

This lets you hear audio through your speakers **and** route it to BlackHole simultaneously.

1. Open **Audio MIDI Setup** (search in Spotlight or find in `/Applications/Utilities/`)
2. Click the **+** button in the bottom-left corner
3. Select **Create Multi-Output Device**
4. Check both:
   - **BlackHole 2ch**
   - Your speakers/headphones (e.g., "MacBook Pro Speakers" or "External Headphones")
5. Make sure your speakers are listed **first** (drag to reorder if needed) — this ensures audio plays through them
6. Optionally rename it to "Multi-Output (BlackHole)" by double-clicking the name

## 3. Set as System Output

1. Open **System Settings** → **Sound** → **Output**
2. Select your new **Multi-Output Device**

Or from the menu bar: click the speaker icon while holding Option, then select the Multi-Output Device.

## 4. Verify

Play any audio in your browser. You should:
- Still hear it through your speakers
- See the app detecting audio when you run it

## Troubleshooting

- **No audio detected**: Make sure the Multi-Output Device is set as system output, not just in Audio MIDI Setup
- **No sound from speakers**: Ensure your speakers are checked in the Multi-Output Device and listed before BlackHole
- **Volume control doesn't work**: This is a macOS limitation with Multi-Output Devices. Use the app's volume or the source volume instead
- **After restart**: macOS may reset the output device. Re-select the Multi-Output Device in Sound settings
