from __future__ import annotations

from pathlib import Path

from PIL import Image


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / "images" / "demo_preview.gif"
    img = Image.open(path)

    frames = []
    i = 0
    while True:
        try:
            img.seek(i)
        except EOFError:
            break
        fr = img.convert("RGBA")
        fr = fr.resize((640, 228), Image.Resampling.LANCZOS)
        frames.append(fr.convert("P", palette=Image.Palette.ADAPTIVE))
        i += 2  # keep every other frame to reduce size

    duration = img.info.get("duration", 40)
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=duration * 2,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"frames={len(frames)} bytes={path.stat().st_size}")


if __name__ == "__main__":
    main()

