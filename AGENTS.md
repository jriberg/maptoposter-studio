# Repository Guidelines

## Project Structure & Module Organization
- `create_map_poster.py` contains the CLI and rendering pipeline.
- `themes/` holds JSON theme definitions used to style posters.
- `fonts/` stores bundled Roboto TTF files.
- `posters/` is the default output directory for generated PNGs.
- `README.md` documents usage examples and theme catalog.

## Build, Test, and Development Commands
- `pip install -r requirements.txt` installs Python dependencies (OSMnx, matplotlib, etc.).
- `python create_map_poster.py -c "City" -C "Country" -t noir -d 12000` generates a poster for a specific city/theme/distance.
- `python create_map_poster.py --list-themes` prints available themes from `themes/`.

## Coding Style & Naming Conventions
- Follow existing Python style in `create_map_poster.py` (4-space indentation, module-level functions).
- Use `snake_case` for functions and variables, and uppercase constants when adding new theme defaults.
- Keep new theme files in `themes/` with lowercase names (e.g., `warm_beige.json`).

## Testing Guidelines
- No automated test suite is present in this repository.
- If adding tests, place them under a new `tests/` directory and document how to run them in `README.md`.

## Commit & Pull Request Guidelines
- Recent commits use short, imperative summaries (e.g., “Add example images to README”).
- Keep commit messages concise and scoped to a single change.
- For PRs, include a brief description, example output images when visual changes are made, and note any new dependencies.

## Configuration & Data Notes
- Poster generation calls external geocoding and map data services (Nominatim/OSMnx), so an internet connection is required.
- Output filenames follow `{city}_{theme}_{YYYYMMDD_HHMMSS}.png` and are written to `posters/` by default.
