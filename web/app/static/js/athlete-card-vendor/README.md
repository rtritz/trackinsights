# Athlete card QR dependency

`qrcode.js` is the browser build of qrcode-generator 2.0.4 by Kazuhiko Arase,
vendored from the npm package. Its MIT license notice is preserved in the file.

Source: https://github.com/kazuhikoarase/qrcode-generator

This script is loaded only by the athlete dashboard. QR codes are generated
locally; no athlete information is sent to a third-party QR service.
