# Control Binary Eye on Android with an AI agent — generate QR codes

Generate your own QR codes and barcodes in Binary Eye without camera, files, clipboard or sharing. Compose content, select format, generate, read UI state and return to edit.

Try asking: **Generate a QR Code for https://example.org/solar in Binary Eye and leave it visible. Do not use camera, files or clipboard.**

## Toolkit

| Action | Use |
|---|---|
| open_generator | Open the barcode composer directly, bypassing the scanner |
| set_content | Replace generator content exactly and disable escape-sequence expansion |
| set_format | Select and read back the barcode format |
| generate | Generate a barcode from the current literal composer state |
| read_state | Read composer controls or visible generated-image state without scanning |
| edit_code | Return from a generator-created barcode viewer to the composer |
| generate_qr | Compose literal content, select QR Code and generate it |

## Tested scope

Samsung SM-A156B Android 16, English. Package de.markusfisch.android.binaryeye, app 1.75.5. Official F-Droid signed-index SHA and APK signatures checked outside the repository. Maintainer-signed self-runs bind recorded outcomes to these files; they are not independent verification.

## Known failure modes

Generator only: direct exported EncodeActivity; no scanner, file picker, gallery, clipboard, history, save/export/share or external URL opening. Use edit_code only for a viewer opened from this composer. Runtime validators prove exact input/format readback and a generated image viewer; they do not independently decode its pixels. read_state labels the viewer as image-only and never invents decoded text. Samsung SM-A156B live verification independently decodes the demo QR screenshot with OpenCV; OpenCV is not a runtime skill dependency. Supported formats are Aztec, Code 128 and QR Code; other format-specific content constraints can fail honestly. Printable ASCII input only, maximum512; literal unsupported percent encodings fail exact readback before generation. An empty content field may expose its hint through accessibility, explicitly reported as displayed_content. Tested portrait layout only.

All seven actions passed three consecutive clean-reset replays on Samsung SM-A156B. Format selection exercised Code 128 and QR Code; each cycle independently decoded both generated QR screenshots back to the exact requested URL (six decodes total). Camera and clipboard app operations remained denied. Six focused input, ownership, state and validation tests passed. Barcode formats other than QR were selected but their pixels were not independently decoded.

The app matcher accepts the1.75 patch line from1.75.5; only1.75.5 has been tested. Hardware and OS remain scoped to the measured profile.
