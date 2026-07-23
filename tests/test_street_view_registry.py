import math
import unittest

from scripts.street_view_registry import (
    angle_diff,
    attach_active_photos,
    build_street_view_nodes,
    build_streets,
    choose_best_photo,
    group_segments_into_street_parts,
    harvest_mapillary_candidates,
    mapillary_images_url,
    registry_to_supabase_seed_sql,
)


def seg(seg_id, coords, score=80):
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            "id": seg_id,
            "kind": "route_segment",
            "feature_type": "footpath",
            "overall_accessibility_score": score,
            "metrics": {"length_m": 5.0},
            "component_scores": {"clear_width": 100},
        },
    }


class StreetViewRegistryTest(unittest.TestCase):
    def test_angle_diff_wraps_to_smallest_signed_difference(self):
        self.assertEqual(angle_diff(350, 10), -20)
        self.assertEqual(angle_diff(10, 350), 20)
        self.assertEqual(angle_diff(90, 90), 0)

    def test_groups_five_meter_segments_into_ten_meter_street_parts(self):
        segments = [
            seg("seg_0", [[103.0, 1.0], [103.000045, 1.0]]),
            seg("seg_1", [[103.000045, 1.0], [103.00009, 1.0]]),
            seg("seg_2", [[103.00009, 1.0], [103.000135, 1.0]]),
        ]

        parts = group_segments_into_street_parts(segments, target_length_m=10)

        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["route_segment_ids"], ["seg_0", "seg_1"])
        self.assertEqual(parts[1]["route_segment_ids"], ["seg_2"])
        self.assertAlmostEqual(parts[0]["length_m"], 10.0, delta=1.5)

    def test_best_photo_prefers_correct_heading_over_newer_wrong_direction(self):
        candidates = [
            {
                "id": "new-wrong",
                "computed_compass_angle": 270,
                "computed_geometry": {"coordinates": [103.0, 1.0]},
                "captured_at": "2026-07-01T00:00:00Z",
                "is_pano": False,
            },
            {
                "id": "older-correct",
                "computed_compass_angle": 90,
                "computed_geometry": {"coordinates": [103.0, 1.0]},
                "captured_at": "2024-01-01T00:00:00Z",
                "is_pano": False,
            },
        ]

        chosen = choose_best_photo(
            candidates,
            midpoint=[103.0, 1.0],
            desired_heading_deg=90,
            max_heading_delta=35,
        )

        self.assertEqual(chosen["source_image_id"], "older-correct")
        self.assertTrue(chosen["direction_valid"])

    def test_builds_prev_next_node_graph_for_curated_corridor(self):
        segments = [
            seg("seg_0", [[103.0, 1.0], [103.000045, 1.0]]),
            seg("seg_1", [[103.000045, 1.0], [103.00009, 1.0]]),
            seg("seg_2", [[103.00009, 1.0], [103.000135, 1.0]]),
            seg("seg_3", [[103.000135, 1.0], [103.00018, 1.0]]),
        ]
        parts = group_segments_into_street_parts(segments, target_length_m=10)

        nodes = build_street_view_nodes(parts)

        self.assertEqual(len(nodes), 2)
        self.assertIsNone(nodes[0]["prev_node_id"])
        self.assertEqual(nodes[0]["next_node_id"], nodes[1]["id"])
        self.assertEqual(nodes[1]["prev_node_id"], nodes[0]["id"])
        self.assertIsNone(nodes[1]["next_node_id"])
        self.assertEqual(nodes[0]["desired_orientation"], "road_right")

    def test_street_parts_belong_to_streets_and_turns_start_new_streets(self):
        segments = [
            seg("seg_0", [[103.0, 1.0], [103.000045, 1.0]]),
            seg("seg_1", [[103.000045, 1.0], [103.00009, 1.0]]),
            seg("seg_2", [[103.00009, 1.0], [103.00009, 1.000045]]),
            seg("seg_3", [[103.00009, 1.000045], [103.00009, 1.00009]]),
        ]
        parts = group_segments_into_street_parts(segments, target_length_m=10)
        streets = build_streets(parts, turn_threshold_deg=45)

        self.assertEqual(len(streets), 2)
        self.assertEqual(parts[0]["street_id"], "street_0000")
        self.assertEqual(parts[1]["street_id"], "street_0001")
        self.assertEqual(streets[0]["street_part_ids"], [parts[0]["id"]])
        self.assertEqual(streets[1]["street_part_ids"], [parts[1]["id"]])

    def test_nodes_do_not_link_prev_next_across_different_streets(self):
        parts = [
            {"id": "street_part_0000", "street_id": "street_0000", "midpoint": [103.0, 1.0], "direction_bearing_deg": 90, "desired_orientation": "road_right"},
            {"id": "street_part_0001", "street_id": "street_0001", "midpoint": [103.001, 1.0], "direction_bearing_deg": 0, "desired_orientation": "road_right"},
        ]
        nodes = build_street_view_nodes(parts)

        self.assertIsNone(nodes[0]["next_node_id"])
        self.assertIsNone(nodes[1]["prev_node_id"])
        self.assertEqual(nodes[0]["street_id"], "street_0000")
        self.assertEqual(nodes[1]["street_id"], "street_0001")

    def test_active_photo_registry_attaches_photo_to_part_and_node(self):
        segments = [
            seg("seg_0", [[103.0, 1.0], [103.000045, 1.0]]),
            seg("seg_1", [[103.000045, 1.0], [103.00009, 1.0]]),
        ]
        parts = group_segments_into_street_parts(segments, target_length_m=10)
        build_streets(parts)
        photos = attach_active_photos(
            parts,
            {
                "street_part_0000": [
                    {
                        "id": "mly-good",
                        "computed_compass_angle": parts[0]["direction_bearing_deg"],
                        "computed_geometry": {"coordinates": parts[0]["midpoint"]},
                        "captured_at": "2026-07-01T00:00:00Z",
                        "thumb_2048_url": "https://example.com/mly-good.jpg",
                        "is_pano": True,
                    }
                ]
            },
        )
        nodes = build_street_view_nodes(parts, {p["street_part_id"]: p for p in photos})

        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0]["street_part_id"], "street_part_0000")
        self.assertTrue(photos[0]["is_active"])
        self.assertEqual(nodes[0]["active_photo_id"], photos[0]["id"])
        self.assertEqual(nodes[0]["coverage_status"], "active")

    def test_mapillary_url_requests_metadata_without_printing_token(self):
        url = mapillary_images_url(103.123456789, 1.234567891, "tok/with spaces", radius_m=35, limit=7)

        self.assertIn("https://graph.mapillary.com/images?", url)
        self.assertIn("thumb_2048_url", url)
        self.assertIn("computed_geometry", url)
        self.assertIn("computed_compass_angle", url)
        self.assertIn("radius=35", url)
        self.assertIn("limit=7", url)
        self.assertIn("access_token=tok%2Fwith+spaces", url)

    def test_harvest_mapillary_candidates_keys_rows_by_street_part(self):
        import scripts.street_view_registry as svr

        original = svr.fetch_mapillary_images
        calls = []
        try:
            def fake_fetch(lng, lat, token, radius_m=45, limit=12, timeout_s=20):
                calls.append((round(lng, 6), round(lat, 6), token, radius_m, limit))
                return [
                    {"id": "same", "computed_geometry": {"coordinates": [lng, lat]}, "computed_compass_angle": 90},
                    {"id": "same", "computed_geometry": {"coordinates": [lng, lat]}, "computed_compass_angle": 90},
                ]
            svr.fetch_mapillary_images = fake_fetch
            parts = [{"id": "street_part_0000", "midpoint": [103.0, 1.0]}]
            rows = harvest_mapillary_candidates(parts, "secret-token", radius_m=20, limit_per_part=3, sleep_s=0)
        finally:
            svr.fetch_mapillary_images = original

        self.assertEqual(calls, [(103.0, 1.0, "secret-token", 20, 3)])
        self.assertEqual(len(rows["street_part_0000"]), 1)
        self.assertEqual(rows["street_part_0000"][0]["id"], "same")

    def test_registry_exports_supabase_seed_sql_for_streets_parts_nodes_and_photos(self):
        segments = [
            seg("seg_0", [[103.0, 1.0], [103.000045, 1.0]]),
            seg("seg_1", [[103.000045, 1.0], [103.00009, 1.0]]),
        ]
        parts = group_segments_into_street_parts(segments, target_length_m=10)
        streets = build_streets(parts)
        photos = attach_active_photos(
            parts,
            {"street_part_0000": [{"id": "mly-seed", "computed_compass_angle": parts[0]["direction_bearing_deg"], "computed_geometry": {"coordinates": parts[0]["midpoint"]}, "captured_at": "2026-07-01T00:00:00Z", "thumb_2048_url": "https://example.com/seed.jpg"}]},
        )
        nodes = build_street_view_nodes(parts, {p["street_part_id"]: p for p in photos})
        sql = registry_to_supabase_seed_sql({"streets": streets, "street_parts": parts, "street_photos": photos, "street_view_nodes": nodes})

        self.assertIn("insert into public.streets", sql)
        self.assertIn("street_0000", sql)
        self.assertIn("insert into public.street_parts", sql)
        self.assertIn("street_id", sql)
        self.assertIn("street_part_0000", sql)
        self.assertIn("insert into public.street_view_nodes", sql)
        self.assertIn("street_view_node_0000", sql)
        self.assertIn("insert into public.street_photos", sql)
        self.assertIn("photo_mapillary_mly-seed", sql)
        self.assertIn("active_photo_id =", sql)
        self.assertIn("on conflict (external_id) do update", sql)


if __name__ == "__main__":
    unittest.main()
