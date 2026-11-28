# Code map: Sky, weather, atmosphere and render

sky, clouds, weather, atmosphere, mist, camera, lights, previews, final renders, floating origin. Part of [the code map index](../CODEMAP.md).

One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (smoke, describe, crate, scene).

### bridge/blendworks_bridge/ (30)

- `atmosphere_haze`: Haze maths: extinction, layered density, optical depth and transmittance. | fn: extinction layers_of + | test: atmosphere landscape_air +1
- `camera_exposure`: Photographic exposure: EV100 to exposure, the view transform and a report of the look applied. | fn: ev100 exposure_from_ev + | test: camera_setup
- `camera_reach`: Far clips that cover the scene. A camera's far clip is raised to reach the farthest corner of every visible object's | fn: scene_reach covering_clip + | test: camera_setup
- `cloud_field`: Cloud field coordinates: seeds, wind frame, layer coordinates and column coverage. | fn: seed_offset wind_frame + | test: cloud_look clouds
- `cloud_forms`: Final cloud forms: volume switches and the cloud report. | fn: stored switches + | test: cloud_look clouds
- `cloud_genera`: Cloud genus presets (cumulus to cumulonimbus) and their thresholds. | fn: threshold genus | test: cloud_look clouds
- `cloud_layers`: Cloud layers: observer, resolution against the sky and light at a layer. | fn: observer view_heading + | test: cloud_look clouds
- `cloud_sheet`: Cloud sheet radiance: transmittance, phase function and sun terms for a layer. | fn: direction shell_distance + | test: cloud_look clouds
- `cloud_volume`: Cloud volume domains: bounds, radial fade, scattering lobes and the domain material. | fn: domain_bounds radial_fade + | test: cloud_look clouds
- `floating_origin`: Camera-relative rendering for worlds far larger than float32 keeps precise. | fn: begin report + | test: floating_origin
- `floating_shaders`: World-space shader coordinates during a camera-relative render. | fn: shader_trees world_outputs + | test: floating_origin
- `mist_depth`: Valley mist in the depth method of atmosphere: when the haze is applied per pixel from the depth pass, the mist volumes | fn: mist_objects top_grid + | test: valley_mist
- `preview`: Preview helpers: framing, aiming, pixel size and the flat colour materials. | fn: half_angle aim + | test: preview
- `render_outputs`: Render output settings and passes, restored after a render. | fn: SettingsScope keep_image_settings + | test: atmosphere render_final +1
- `render_view`: A rendered view: the objects shown and the run of all views. | fn: rendered_objects run_all + | test: render_views render_views_copies +3
- `rig`: Preview rig of camera and lights, and the render settings it sets. | fn: PreviewRig sphere_of + | test: objects
- `sky_measure`: Measures the sky: sun irradiance, hemisphere and luminance with a probe scene. | fn: copy_sky ProbeScene + | test: sky
- `sky_nodes`: Node graph helper for the sky shader. | fn: Graph | test: sky
- `sky_sun`: Solar position from date, time and place. | fn: direction angles + | test: sky
- `sky_world`: Sky world nodes: build, store and place the sun lamp. | fn: node_settings build + | test: sky
- `valley_mist`: Mist that lies in low ground. The ground under a square around a centre is measured on a grid by ray casts; the low | fn: sliding_minimum box_blur + | test: valley_mist
- `view_materials`: Temporary shaders for preview shadings (clay, normals and so on). | fn: temporary_material Shader + | test: render_views
- `view_surfaces`: Swaps surface shaders of materials while a preview renders. | fn: surface_output volume_only + | test: render_views_surfaces
- `weather_build`: Weather assembly: calls the sky, clouds and rain commands for a weather state. | fn: call clear_extras + | test: weather
- `weather_continuum`: The weather continuum: presets and the state between them. | fn: curve layers + | test: weather
- `weather_lightning`: Lightning bolt paths and materials. | fn: zigzag bolt_paths + | test: weather
- `weather_objects`: Tagging and removal of the objects a weather call creates. | fn: tag kind_of + | test: weather
- `weather_rain`: Rain: extinction, veil, shafts and streaks. | fn: extinction mask + | test: weather
- `weather_wet`: Wet surface look: darkening and shore wetness. | fn: principled clear + | test: liquid_scene
- `world_background`: World background surface: reads, describes and replaces it. | fn: output_node upstream + | test: world_hdri world_scale +1

### bridge/blendworks_bridge/commands/ (9)

- `atmosphere`: The atmosphere command: aerial perspective and haze as a volume with a stated visibility. | fn: plan_atmosphere check_arguments + | cmd: atmosphere | test: atmosphere
- `camera_setup`: The camera_setup command: lens, sensor, depth of field, clip range and exposure of a camera. | fn: check_arguments set_lens + | cmd: camera_setup | test: camera_setup
- `clouds`: The clouds command: procedural cloud layers by genus, as sky settings and volume domains. | fn: remove rebuild_clear + | cmd: clouds | test: clouds
- `lights`: Lighting and view commands: add_light, add_camera, look_at, set_world and set_world_hdri. | fn: aim uniform_values + | cmd: add_light add_camera look_at set_world set_world_hdri | test: lights world_hdri
- `render`: The render_preview command: camera, turntable and close-up previews in several shadings. | fn: PreviewHaze check_arguments + | cmd: render_preview | test: render
- `render_final`: The render_final command: a final-quality render with passes written into the workspace. | fn: chosen_camera check_arguments + | cmd: render_final | test: render_final render_views_match
- `sky`: The sky command: a physical procedural sky with the sun by angles or by date, time and place. | fn: report | cmd: sky | test: sky
- `valley_mist`: The valley_mist command: a mist layer that lies in valleys and over water. | fn: plan_mist remove | cmd: valley_mist | test: valley_mist
- `weather`: The weather command: whole weather (sky, clouds, rain, lightning, wetness) in one call from presets. | fn: plan_weather resolve | cmd: weather | test: weather
