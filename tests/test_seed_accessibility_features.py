import unittest

from scripts.seed_accessibility_features import extract_accessibility_features, features_to_seed_sql


class SeedAccessibilityFeaturesTest(unittest.TestCase):
    def test_extracts_point_pois_and_derived_ramp_tactile(self):
        world = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [103.76, 1.31]},
                    "properties": {
                        "kind": "bus_stop",
                        "name": "Bus stop 1",
                        "selectable": True,
                        "source_properties": {"BUS_STOP_N": "100"},
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[103.76, 1.31], [103.7601, 1.3101]],
                    },
                    "properties": {
                        "id": "seg_1",
                        "kind": "route_segment",
                        "name": "Crossing 1",
                        "feature_type": "crossing",
                        "overall_accessibility_score": 70,
                        "rag": "amber",
                        "metrics": {
                            "kerb_ramp_present": True,
                            "tactile_guidance": True,
                        },
                        "component_scores": {"tactile_guidance": 90},
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[103.76, 1.31], [103.7602, 1.31]],
                    },
                    "properties": {
                        "id": "seg_2",
                        "kind": "route_segment",
                        "name": "Footpath",
                        "metrics": {
                            "kerb_ramp_present": False,
                            "tactile_guidance": False,
                        },
                    },
                },
            ],
        }

        rows = extract_accessibility_features(world)
        kinds = {r["kind"] for r in rows}
        self.assertEqual(kinds, {"bus_stop", "kerb_ramp", "tactile_guidance"})
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["external_id"], "bus_stop_100")
        self.assertEqual(rows[1]["external_id"], "kerb_ramp_seg_1")
        self.assertEqual(rows[2]["external_id"], "tactile_guidance_seg_1")

        sql = features_to_seed_sql(rows)
        self.assertIn("insert into public.accessibility_features", sql)
        self.assertIn("on conflict (external_id) do update", sql)
        self.assertIn("bus_stop_100", sql)
        self.assertIn("kerb_ramp_seg_1", sql)


if __name__ == "__main__":
    unittest.main()
