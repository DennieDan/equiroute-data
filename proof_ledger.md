# JalanLens Proof Ledger

Track every judge-visible claim with evidence before pitch polish.

| Claim | Evidence path/link | Verification command / source | Measured value | Pitch line | Status |
|---|---|---|---:|---|---|
| Street-view navigation uses a deterministic node graph instead of random nearest-photo lookup | `data/street_view_registry.json` | `python3 scripts/street_view_registry.py --max-parts 30 --target-length-m 10` | 30 nodes | "JalanLens creates its own Street View graph for accessibility auditing, rather than trusting arbitrary photo lookup." | built |
| Street-view graph has stable prev/next links | `tests/test_street_view_registry.py` | `python3 -m unittest tests.test_street_view_registry -v` | 4 tests pass | "Navigation is graph-driven, so adjacent street parts preserve route order." | built |
| Photo selector prioritizes correct heading over newer wrong-direction images | `tests/test_street_view_registry.py` | `python3 -m unittest tests.test_street_view_registry -v` | 1 heading test pass | "The system prefers direction-consistent accessibility evidence over blindly choosing the latest photo." | built |
| Supabase schema supports public feedback, photos, upvotes, authority recommendations, and persona journeys | `supabase/schema.sql`, `supabase/rls.sql` | Applied in Supabase SQL Editor for `JalanLens Tech4City` | 10 tables | "The hack backend is multi-user ready and portable to Huawei Cloud Postgres later." | built |

| Supabase project created and schema applied | Project `JalanLens Tech4City` / `https://fhsnfvhydwtmdlrxokur.supabase.co`, SQL editor query `90536509-d594-4e6c-a718-ec54e27581b7` | Supabase SQL Editor showed `Success. No rows returned`; verification query returned `10 rows` for expected public tables | 10 tables | "JalanLens now has a real free-tier Supabase backend for photos, feedback, upvotes, and authority recommendations." | built |
| Curated corridor seeded into Supabase | `supabase/seed_street_view_registry.sql` | Supabase SQL Editor seed run showed `Success. No rows returned`; follow-up count query returned `1 row` | 30 street parts + 30 street-view nodes expected from seed SQL | "The demo corridor already has a backend street-view graph that can power stable navigation." | built |

| Street hierarchy supports many streets, each with many street parts | `scripts/street_view_registry.py`, `supabase/schema.sql`, `data/street_view_registry.json` | `python3 -m unittest tests.test_street_view_registry -v`; REST smoke showed `streets 0-5/6`, `street_parts 0-29/30`, `street_view_nodes 0-29/30` | 6 streets, 30 parts, 30 nodes | "JalanLens models the city as streets made of granular street parts, not one flat route." | built |
| Frontend reads registry from Supabase with local fallback | `street-intelligence/` | Headless Chrome smoke on local server showed `Loaded 220 street parts, 17 streets, 30 street-view nodes from Supabase` | Supabase source active | "The demo is now backed by the live Supabase street registry while still demo-safe offline." | built |

| Active photo registry schema/read path exists | `supabase/schema.sql`, `scripts/street_view_registry.py`, `street-intelligence/` | `python3 -m unittest tests.test_street_view_registry -v`; REST query `street_photos?select=external_id,street_view_node_id,validation_status,selected_reason,replaces_photo_id&limit=0` returned HTTP 200 | 8 tests pass, active photo columns readable | "Each street part can now own one active photo while preserving history/comments when photos are replaced." | built |

| Mapillary candidate harvester exists for active photo curation | `scripts/street_view_registry.py`, `tests/test_street_view_registry.py`, `data/mapillary_candidates.json`, `data/street_view_registry.json` | `python3 -m unittest tests.test_street_view_registry tests.test_seed_accessibility_features -v`; browser smoke on local registry | 30 ~25 m street parts; 40 active photos selected across canonical/opposite directions; 16 street parts have both views | "Street mode uses curated active photos and can swap direction where both pavement-side views exist." | built; Supabase seed SQL ready |

| CV-localized photo feature pins | `scripts/cv_localize_photo_features.py`, `data/photo_feature_instances_cv.json`, `supabase/seed_photo_feature_instances.sql`, `street-intelligence/` | OWLv2 baseline remains available with `--provider owlvit`; current script default switched to Agnes AI `agnes-2.5-flash` and was smoke-tested through Agnes' OpenAI-compatible image-understanding API | 229 matched baseline instances remain in committed data until a full Agnes rerun is accepted; Agnes smoke was conservative and avoids duplicate shelter pins | "Pins can now be regenerated with Agnes AI for stricter Singapore street-scene feature understanding." | built; Agnes API key stored outside git |

## Next proof targets

- Direction-consistent Mapillary/crowd photo corridor: 15–30 active photos, road-on-right.
- CV road-on-right validation: sample images with pass/fail evidence.
- CV feature pin placement: bus stop/ramp/walkway bounding boxes on 5–10 showcase photos.
- Consumer feedback flow: one duplicate blocked, one upvote counted once.
- Authority persona journey: wheelchair/PMA score with blockers and before/after recommendation.
