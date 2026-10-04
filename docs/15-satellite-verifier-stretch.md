# 15. Satellite verifier (stretch goal, Oct 14 only if everything else is green)

## Judgment

Keep it, but as a stretch goal with a narrow job. All free satellite imagery has a delay: Sentinel-1 radar revisits a place every 6 to 12 days and reaches Earth Engine with a further lag, so "flood in Bengaluru today" usually cannot be confirmed from space on the same day. Any other free satellite has the same physics. What satellite data does well is the opposite question: did this event happen at this place around the claimed date at all. That is exactly the reused-old-footage problem.

## Narrow job

- Fires: NASA FIRMS active fire data (VIIRS and MODIS) is near-real-time, roughly 3 hours, and is also in Earth Engine with some lag. Check whether there was a fire detection within 5 km of the claimed place within 2 days of the claimed date
- Floods: Sentinel-1 radar (works through cloud) via Earth Engine. Compare water extent before and after the claimed date for the claimed area. Only answer when an image exists within 6 days after the claimed date; otherwise return NO_IMAGERY_YET
- Output is one more Evidence item with tier TIER_1 (data, not opinion) and stance SUPPORTS, CONTRADICTS or NO_DATA, plus a before/after image rendered by code from real imagery (no generated imagery)

## Trigger

Only when the extractor tags `claim_type == EVENT` and the event is a flood or fire with a resolvable place (geocode with Gemini to a bounding box, then sanity-check size). Runs as a fifth parallel agent with a 25 s timeout.

## Setup

Register the Cloud project for Earth Engine (non-commercial use for the competition), use the Earth Engine Python API with the `api-sa` service account. Limit to these two dataset families for the demo.

If not built by Oct 14, it goes on the Future slide with a one-paragraph explanation and a static before/after example.
