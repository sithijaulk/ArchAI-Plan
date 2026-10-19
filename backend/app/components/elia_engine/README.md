# ELIA-Engine

ELIA plans exterior residential space from an existing Centralized Master JSON. It does not parse deeds, generate rooms, change interiors, or run a trained AI model.

## Coordinates and rules

All planning geometry is converted to meters. `units` at the Master JSON root declares its source length unit; when absent, `data/elia_rules.json` configures the default as meters. User requirement dimensions use meters unless `requirements.units` says otherwise. Latitude and longitude must be supplied in the request or the Master JSON; ELIA never guesses a site location.

ELIA consumes an existing constructed-house exterior footprint and land boundary; a buildable zone is not a substitute for the house footprint. The input adapter accepts `land_info.mathematical_polygon`, legacy boundary fields, and supported house-exterior fields from the floor-plan and structural layers. It also maps `floor_plan.ground_floor.utilities.water_well` and `septic_tank`, including `center`, `position`, or `x`/`y` coordinates. Polygon interior rings are preserved. Input snapshots are not rewritten by normalization.

North is inherited from the upstream Master JSON (`land_info.calculated_north_bearing`, `calculated_north_bearing`, or the existing `north_angle`). ELIA does not redetect north. The normalized angle is degrees clockwise from local `+Y` toward local `+X`; zero means local `+Y` is north. Conflicting angles or missing required orientation produce explicit validation errors. North is omitted from the request examples below because it is inherited.

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

`generation_mode` defaults to `trained_model`. Until an inference adapter is installed, this returns HTTP 503 with `ELIA_MODEL_UNAVAILABLE`; ELIA never silently substitutes the procedural baseline. Set `generation_mode` to `baseline` to explicitly request the deterministic demo planner. Its output is labeled `baseline_demo`, is not a trained-model prediction, and does not claim structural-load or full swept-path vehicle feasibility.

### Example with inherited north

```json
{
	"generation_mode": "baseline",
	"master_json": {
		"units": "m",
		"location": {"latitude": 6.9, "longitude": 79.8},
		"land_info": {
			"mathematical_polygon": {
				"type": "Polygon",
				"coordinates": [[[0, 0], [30, 0], [30, 20], [0, 20], [0, 0]]]
			},
			"calculated_north_bearing": 18.5,
			"road_facing": "south"
		},
		"house": {"exterior_polygon": [[10, 7], [18, 7], [18, 14], [10, 14]]},
		"floor_plan": {"ground_floor": {"utilities": {
			"water_well": {"center": {"x": 2, "y": 18}},
			"septic_tank": {"position": {"x": 25, "y": 18}}
		}}}
	},
	"requirements": {
		"access": {"road_side": "south", "garage_required": false, "driveway_required": false}
	}
}
```

`POST /api/elia-engine/preview` returns the full non-persisted geometry; a shortened response shape is shown here:

```json
{
	"generation_mode": "baseline",
	"status": "completed",
	"outcome": "valid",
	"persisted": false,
	"exterior_landscape": {
		"generation_mode": "baseline_demo",
		"environment": {
			"north_angle": 18.5,
			"north_orientation_convention": "degrees clockwise from local +Y toward local +X; 0 means local +Y is north"
		},
		"validation_summary": {"valid": true, "violations": []},
		"structural_load_assessed": false
	}
}
```

For model integration, implement `ModelAdapter.infer(prepared_input)` in `model_adapter.py` and register it at application startup with `configure_model_adapter`. The input has `schema_version`, meter-normalized land and house geometry (including holes), normalized requirements, and the inherited north angle. Output must include `schema_version`, `coordinate_reference`, `access`, `site_analysis`, `utility_safety`, `environment`, `metrics`, typed object IDs/positions or geometry, meter units, and exterior collections. ELIA independently validates geometry and requirements and replaces model `valid` flags. Configure the future connection with `ELIA_MODEL_ARTIFACT_PATH` or `ELIA_MODEL_SERVICE_URL`; these settings do not load artifacts or call a service yet.

The current-solar endpoint requests Open-Meteo current-condition shortwave, direct, diffuse, and direct-normal irradiance, plus cloud cover and daylight state. It also calculates azimuth/elevation for the provider timestamp with pvlib. The provider's current values are weather-model estimates (typically 15-minute current-condition intervals), not ground-station measurements; requests are cached for 15 minutes. Open-Meteo's public endpoint is subject to its non-commercial and daily-call limits; configure an eligible customer endpoint/plan before commercial use.

The ELIA page searches Sri Lankan city/locality names through OpenStreetMap Nominatim, filtered to `LK`. Search is explicit (not autocomplete), results are cached for 24 hours, and requests are spaced to at most one per second. The interface displays OpenStreetMap attribution. Nominatim's public service is intended for moderate, user-triggered use and can be changed through `live_solar_api` configuration if deployment volume or service policy requires another provider.

## Persistence and tests

Project runs use the existing MySQL `projects` and `component_runs` tables. A source snapshot and monotonically increasing project revision are recorded for each run. Compare-and-swap checks protect the processing transition and final update. `GET /api/projects/{project_id}/master-json` returns the unchanged JSON body with `ETag` and `X-Project-Revision` headers. Only a valid candidate replaces `exterior_landscape`; infeasible candidates and model/schema failures remain in run history while the accepted design is preserved. Processing metadata updates only `processing.elia_engine`. Applying a supplied project snapshot requires its current `source_revision`.

Install test tools from `backend` with `pip install -r requirements-dev.txt`, then run `python -m pytest tests`. Persistence regression tests use isolated SQLite data. The MySQL persistence integration test is opt-in and uses only `ELIA_TEST_MYSQL_URL`, which must point to a disposable MySQL test schema.
