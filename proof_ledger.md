# AccessTwin Proof Ledger

Track every judge-visible claim with evidence before pitch polish.

| Claim | Evidence path/link | Verification command / source | Measured value | Pitch line | Status |
|---|---|---|---:|---|---|
| Street-view navigation uses a deterministic node graph instead of random nearest-photo lookup | `data/street_view_registry.json` | `python3 scripts/street_view_registry.py --max-parts 30 --target-length-m 10` | 30 nodes | "AccessTwin creates its own Street View graph for accessibility auditing, rather than trusting arbitrary photo lookup." | built |
| Street-view graph has stable prev/next links | `tests/test_street_view_registry.py` | `python3 -m unittest tests.test_street_view_registry -v` | 4 tests pass | "Navigation is graph-driven, so adjacent street parts preserve route order." | built |
| Photo selector prioritizes correct heading over newer wrong-direction images | `tests/test_street_view_registry.py` | `python3 -m unittest tests.test_street_view_registry -v` | 1 heading test pass | "The system prefers direction-consistent accessibility evidence over blindly choosing the latest photo." | built |
| Supabase schema supports public feedback, photos, upvotes, authority recommendations, and persona journeys | `supabase/schema.sql`, `supabase/rls.sql` | Manual schema review; run in Supabase SQL editor once project exists | pending | "The hack backend is multi-user ready and portable to Huawei Cloud Postgres later." | ready-to-apply |

## Next proof targets

- Direction-consistent Mapillary/crowd photo corridor: 15–30 active photos, road-on-right.
- CV road-on-right validation: sample images with pass/fail evidence.
- CV feature pin placement: bus stop/ramp/walkway bounding boxes on 5–10 showcase photos.
- Consumer feedback flow: one duplicate blocked, one upvote counted once.
- Authority persona journey: wheelchair/PMA score with blockers and before/after recommendation.
