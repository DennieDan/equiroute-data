# AccessTwin Proof Ledger

Track every judge-visible claim with evidence before pitch polish.

| Claim | Evidence path/link | Verification command / source | Measured value | Pitch line | Status |
|---|---|---|---:|---|---|
| Street-view navigation uses a deterministic node graph instead of random nearest-photo lookup | `data/street_view_registry.json` | `python3 scripts/street_view_registry.py --max-parts 30 --target-length-m 10` | 30 nodes | "AccessTwin creates its own Street View graph for accessibility auditing, rather than trusting arbitrary photo lookup." | built |
| Street-view graph has stable prev/next links | `tests/test_street_view_registry.py` | `python3 -m unittest tests.test_street_view_registry -v` | 4 tests pass | "Navigation is graph-driven, so adjacent street parts preserve route order." | built |
| Photo selector prioritizes correct heading over newer wrong-direction images | `tests/test_street_view_registry.py` | `python3 -m unittest tests.test_street_view_registry -v` | 1 heading test pass | "The system prefers direction-consistent accessibility evidence over blindly choosing the latest photo." | built |
| Supabase schema supports public feedback, photos, upvotes, authority recommendations, and persona journeys | `supabase/schema.sql`, `supabase/rls.sql` | Applied in Supabase SQL Editor for `AccessTwin Tech4City` | 10 tables | "The hack backend is multi-user ready and portable to Huawei Cloud Postgres later." | built |

| Supabase project created and schema applied | Project `AccessTwin Tech4City` / `https://fhsnfvhydwtmdlrxokur.supabase.co`, SQL editor query `90536509-d594-4e6c-a718-ec54e27581b7` | Supabase SQL Editor showed `Success. No rows returned`; verification query returned `10 rows` for expected public tables | 10 tables | "AccessTwin now has a real free-tier Supabase backend for photos, feedback, upvotes, and authority recommendations." | built |
| Curated corridor seeded into Supabase | `supabase/seed_street_view_registry.sql` | Supabase SQL Editor seed run showed `Success. No rows returned`; follow-up count query returned `1 row` | 30 street parts + 30 street-view nodes expected from seed SQL | "The demo corridor already has a backend street-view graph that can power stable navigation." | built |

| Street hierarchy supports many streets, each with many street parts | `scripts/street_view_registry.py`, `supabase/schema.sql`, `data/street_view_registry.json` | `python3 -m unittest tests.test_street_view_registry -v`; REST smoke showed `streets 0-5/6`, `street_parts 0-29/30`, `street_view_nodes 0-29/30` | 6 streets, 30 parts, 30 nodes | "AccessTwin models the city as streets made of granular street parts, not one flat route." | built |
| Frontend reads registry from Supabase with local fallback | `earth_accessibility.html` | Headless Chrome smoke on local server showed `Loaded 576 5 m segments, 6 streets, 30 street-view nodes from Supabase` | Supabase source active | "The demo is now backed by the live Supabase street registry while still demo-safe offline." | built |

| Active photo registry schema/read path exists | `supabase/schema.sql`, `scripts/street_view_registry.py`, `earth_accessibility.html` | `python3 -m unittest tests.test_street_view_registry -v`; REST query `street_photos?select=external_id,street_view_node_id,validation_status,selected_reason,replaces_photo_id&limit=0` returned HTTP 200 | 8 tests pass, active photo columns readable | "Each street part can now own one active photo while preserving history/comments when photos are replaced." | built |

| Mapillary candidate harvester exists for active photo curation | `scripts/street_view_registry.py`, `tests/test_street_view_registry.py`, `data/mapillary_candidates.json`, `data/street_view_registry.json` | `python3 -m unittest tests.test_street_view_registry tests.test_seed_accessibility_features -v`; browser smoke on `earth_accessibility.html?activephotos=2` | Harvested 435 raw Mapillary candidates; 29/30 street parts selected active photos; frontend loaded 29 active photos and rendered Mapillary photo from registry | "Street mode now uses curated active photos for almost every demo street part instead of random live lookup." | built; Supabase SQL ready but dashboard write blocked for `khdds...` project |

| CV-localized photo feature pins | `scripts/cv_localize_photo_features.py`, `data/photo_feature_instances_cv.json`, `supabase/seed_photo_feature_instances.sql`, `earth_accessibility.html` | OWL-ViT run with `google/owlvit-base-patch32`; browser smoke on `earth_accessibility.html?cv=2`; unit tests | 164 matched photo-feature instances across 20 photos; frontend loaded 164 CV instances and showed `4 CV-localized feature pins` on street_part_0005 | "Pins can now come from image-space object detections rather than only map projection." | built; Supabase SQL ready but dashboard session still needs login |

## Next proof targets

- Direction-consistent Mapillary/crowd photo corridor: 15–30 active photos, road-on-right.
- CV road-on-right validation: sample images with pass/fail evidence.
- CV feature pin placement: bus stop/ramp/walkway bounding boxes on 5–10 showcase photos.
- Consumer feedback flow: one duplicate blocked, one upvote counted once.
- Authority persona journey: wheelchair/PMA score with blockers and before/after recommendation.
