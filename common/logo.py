"""Converts an arbitrary school logo image (png/jpg/gif/webp/svg, any size)
into this app's single canonical web format: RGBA WebP, capped at
CONST.SCHOOL_LOGO_MAX_DIMENSION on its longest side, encoded at
CONST.SCHOOL_LOGO_WEBP_QUALITY. WebP was chosen over PNG after measuring the
actual logo set: most of these are photographic/gradient-heavy crests (not
flat-color vector art), where lossless PNG ran 5-30x larger than WebP at
quality 82 for no visible difference at logo display sizes -- and ~37% of
the set uses real (non-uniform) alpha transparency, which WebP still
supports losslessly even in lossy color mode. Used by both the one-time
logo migration and standalone/notebooks/Load Schools in DB.ipynb's ongoing
logo-scraping cell, so every school.school_id.webp on disk is always
already in this format -- no per-school extension/size bookkeeping needed.
"""

from io import BytesIO

from PIL import Image

from common.const import CONST


def convert_logo_to_webp(image_bytes: bytes, is_svg: bool = False) -> bytes:
    if is_svg:
        # Pillow can't rasterize SVG itself -- svglib/reportlab do the
        # vector-to-raster step (pure-Python + prebuilt pycairo wheel, no
        # system Cairo install required), then Pillow takes over for the
        # resize/format/optimize step shared with every other source format.
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM

        drawing = svg2rlg(BytesIO(image_bytes))
        raster = BytesIO()
        renderPM.drawToFile(drawing, raster, fmt="PNG")
        raster.seek(0)
        img = Image.open(raster)
    else:
        img = Image.open(BytesIO(image_bytes))

    img = img.convert("RGBA")
    if max(img.size) > CONST.SCHOOL_LOGO_MAX_DIMENSION:
        img.thumbnail(
            (CONST.SCHOOL_LOGO_MAX_DIMENSION, CONST.SCHOOL_LOGO_MAX_DIMENSION),
            Image.LANCZOS,
        )

    out = BytesIO()
    img.save(out, format="WEBP", quality=CONST.SCHOOL_LOGO_WEBP_QUALITY, method=6)
    return out.getvalue()
