import argparse
import os
import unicodedata

from create_map_poster import (
    create_poster,
    get_available_themes,
    get_coordinates,
    load_theme,
)


def slugify(value):
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = ascii_value.strip().lower().replace(" ", "_")
    return "".join(ch for ch in cleaned if ch.isalnum() or ch in ("_", "-"))


def main():
    parser = argparse.ArgumentParser(
        description="Generate example posters for every available theme."
    )
    parser.add_argument("--city", required=True, help="City name, e.g. 'Råcksta'")
    parser.add_argument("--country", required=True, help="Country name, e.g. 'Stockholm'")
    parser.add_argument("--distance", type=int, default=1000, help="Map radius in meters")
    parser.add_argument(
        "--output-dir",
        default="examples",
        help="Output folder for example images",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Filename prefix; defaults to <city>_<distance>m",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    themes = get_available_themes()
    if not themes:
        raise SystemExit("No themes found in themes/")

    coords = get_coordinates(args.city, args.country)
    prefix = args.prefix or f"{slugify(args.city)}_{args.distance}m"

    for theme_name in themes:
        theme = load_theme(theme_name)
        filename = f"{prefix}_{theme_name}.png"
        output_file = os.path.join(args.output_dir, filename)
        create_poster(
            args.city,
            args.country,
            coords,
            args.distance,
            output_file,
            theme,
            show_progress=False,
        )
        print(f"Saved {output_file}")


if __name__ == "__main__":
    main()
