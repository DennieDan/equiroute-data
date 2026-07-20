import math
import unittest

from scripts.street_view_registry import (
    angle_diff,
    build_street_view_nodes,
    choose_best_photo,
    group_segments_into_street_parts,
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


if __name__ == "__main__":
    unittest.main()
