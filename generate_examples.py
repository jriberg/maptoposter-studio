import os

from create_map_poster import (
    create_poster,
    get_available_themes,
    get_coordinates,
    load_theme,
)

EXAMPLES_DIR = "examples"
CITY = "Råcksta"
COUNTRY = "Stockholm"
DISTANCE = 1000
FILENAME_PREFIX = "racksta_1000m"


def main():
    os.makedirs(EXAMPLES_DIR, exist_ok=True)
    themes = get_available_themes()
    if not themes:
        raise SystemExit("No themes found in themes/")

    coords = get_coordinates(CITY, COUNTRY)

    for theme_name in themes:
        theme = load_theme(theme_name)
        filename = f"{FILENAME_PREFIX}_{theme_name}.png"
        output_file = os.path.join(EXAMPLES_DIR, filename)
        create_poster(
            CITY,
            COUNTRY,
            coords,
            DISTANCE,
            output_file,
            theme,
            show_progress=False,
        )
        print(f"Saved {output_file}")


if __name__ == "__main__":
    main()
