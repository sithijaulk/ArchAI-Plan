# ELIA-Engine

ELIA plans exterior residential space from an existing Centralized Master JSON. It does not parse deeds, generate rooms, change interiors, or run a trained AI model.

## Coordinates and rules

All planning geometry is converted to meters. `units` at the Master JSON root declares its source length unit; when absent, `data/elia_rules.json` configures the default as meters. User requirement dimensions use meters unless `requirements.units` says otherwise. Latitude and longitude must be supplied in the request or the Master JSON; ELIA never guesses a site location.

The default solar samples use 09:00, 12:00, and 15:00 local time on the configured fixed date `2026-03-20` (March equinox), making runs reproducible. Set `solar_analysis_date` and `solar_analysis_time_range` to analyze another period. Shadow geometry is an analytical directional-prism approximation, not ray tracing.

The current configurable well-to-septic separation is 50 ft. The default 5.5 m turning radius is a clearly recorded project configuration fallback, not a universal vehicle fact; vehicle-specific data should be supplied when known. Generic vegetation catalogue entries intentionally have null species measurements. Their configurable plan-view envelopes are rendering/planning envelopes, not verified botanical properties.

## API

Project endpoints require the existing authenticated administrator role because this shared project model has no owner/permission field:

- `POST /api/projects/{project_id}/elia-engine/run`
- `GET /api/projects/{project_id}/elia-engine/context`
- `POST /api/projects/{project_id}/elia-engine/validate-input`
- `GET /api/projects/{project_id}/elia-engine/result`
- `GET /api/projects/{project_id}/elia-engine/solar/current`

Reference endpoints provide rules, vehicle profiles, vegetation categories, and lighting rules under `/api/elia-engine/*`. `POST /api/elia-engine/preview` accepts a supplied `master_json`, returns a non-persisted enriched copy, and creates no project history. In a project run, a supplied Master JSON is not applied unless `apply_to_project` is true.

The current-solar endpoint requests Open-Meteo current-condition shortwave, direct, diffuse, and direct-normal irradiance, plus cloud cover and daylight state. It also calculates azimuth/elevation for the provider timestamp with pvlib. The provider's current values are weather-model estimates (typically 15-minute current-condition intervals), not ground-station measurements; requests are cached for 15 minutes. Open-Meteo's public endpoint is subject to its non-commercial and daily-call limits; configure an eligible customer endpoint/plan before commercial use.

The ELIA page searches Sri Lankan city/locality names through OpenStreetMap Nominatim, filtered to `LK`. Search is explicit (not autocomplete), results are cached for 24 hours, and requests are spaced to at most one per second. The interface displays OpenStreetMap attribution. Nominatim's public service is intended for moderate, user-triggered use and can be changed through `live_solar_api` configuration if deployment volume or service policy requires another provider.

## Persistence and tests

Project runs use the existing MySQL `projects` and `component_runs` tables. `master_json` is deep-copied and only `exterior_landscape` and `processing.elia_engine` are replaced. `infeasible` is a completed deterministic planning result; input/backend errors are recorded as failed runs.

Install test tools from `backend` with `pip install -r requirements-dev.txt`, then run `python -m pytest tests`. The MySQL persistence integration test is opt-in and uses only `ELIA_TEST_MYSQL_URL`, which must point to a disposable MySQL test schema.
