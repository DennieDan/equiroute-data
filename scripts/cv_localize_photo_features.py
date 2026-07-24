#!/usr/bin/env python3
"""Zero-shot CV localization for AccessTwin street photos.

Uses OWL-ViT to detect pedestrian/accessibility objects in active Mapillary
photos, then links detections back to nearby/expected accessibility_features.
This produces local JSON, visual QA overlays, and idempotent Supabase seed SQL
for public.photo_feature_instances.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "data" / "street_view_registry.json"
DEFAULT_WORLD = ROOT / "accessibility_world.geojson"
DEFAULT_OUT = ROOT / "data" / "photo_feature_instances_cv.json"
DEFAULT_SQL_OUT = ROOT / "supabase" / "seed_photo_feature_instances.sql"
DEFAULT_OVERLAY_DIR = ROOT / "data" / "cv_overlays"

PROMPTS_BY_KIND = {
    "kerb_ramp": ["curb ramp", "kerb ramp", "sloped curb", "pedestrian crossing"],
    "tactile_guidance": ["tactile paving", "yellow tactile paving", "tactile guidance", "sidewalk"],
    "bollard": ["bollard", "post", "pole"],
    "covered_linkway": ["covered walkway", "sheltered walkway", "covered sidewalk", "roof canopy"],
    "bus_stop": ["bus stop", "bus shelter", "bus stop sign"],
    "pedestrian_overhead_bridge": ["pedestrian bridge", "overhead bridge", "footbridge"],
    "mrt_station": ["train station entrance", "metro station entrance", "station sign"],
}
GENERAL_PROMPTS = ["sidewalk", "footpath", "road", "crosswalk", "pedestrian", "car", "traffic lane"]


def sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def jsonb_literal(value: Any) -> str:
    return sql_literal(json.dumps(value, separators=(",", ":"))) + "::jsonb"


def haversine_m(a: list[float], b: list[float]) -> float:
    lon1, lat1 = a[:2]
    lon2, lat2 = b[:2]
    radius_m = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * radius_m * math.asin(math.sqrt(h))


def line_midpoint(coords: list[list[float]]) -> list[float]:
    if not coords:
        return [0.0, 0.0]
    if len(coords) == 1:
        return list(coords[0][:2])
    mid_i = (len(coords) - 1) // 2
    a, b = coords[mid_i], coords[min(mid_i + 1, len(coords) - 1)]
    return [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]


def geometry_point(geometry: dict[str, Any]) -> list[float] | None:
    if not geometry:
        return None
    if geometry.get("type") == "Point":
        coords = geometry.get("coordinates") or []
        return list(coords[:2]) if len(coords) >= 2 else None
    if geometry.get("type") == "LineString":
        return line_midpoint(geometry.get("coordinates") or [])
    return None


def load_accessibility_features(world_path: Path) -> list[dict[str, Any]]:
    from scripts.seed_accessibility_features import extract_accessibility_features

    world = json.loads(world_path.read_text())
    rows = extract_accessibility_features(world)
    for row in rows:
        row["point"] = geometry_point(row.get("geometry") or {})
    return rows


def nearby_features(photo: dict[str, Any], part: dict[str, Any], features: list[dict[str, Any]], radius_m: float) -> list[dict[str, Any]]:
    photo_point = [float(photo["lng"]), float(photo["lat"])]
    route_ids = set(part.get("route_segment_ids") or [])
    selected = []
    for feat in features:
        props = feat.get("properties") or {}
        seg_id = props.get("source_segment_id")
        point = feat.get("point")
        dist = haversine_m(photo_point, point) if point else 999_999
        if seg_id in route_ids or dist <= radius_m:
            row = dict(feat)
            row["distance_to_photo_m"] = round(dist, 2)
            selected.append(row)
    selected.sort(key=lambda f: (f.get("distance_to_photo_m", 999_999), f.get("external_id", "")))
    return selected[:16]


def download_image(url: str) -> Image.Image:
    data = urllib.request.urlopen(url, timeout=25).read()
    return Image.open(io.BytesIO(data)).convert("RGB")


def load_model(model_name: str):
    from transformers import OwlViTForObjectDetection, OwlViTProcessor

    processor = OwlViTProcessor.from_pretrained(model_name)
    model = OwlViTForObjectDetection.from_pretrained(model_name)
    model.eval()
    return processor, model


def run_owlvit(image: Image.Image, prompts: list[str], model_name: str, processor: Any, model: Any, threshold: float) -> list[dict[str, Any]]:
    import torch

    inputs = processor(text=[prompts], images=image, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    target_sizes = torch.tensor([image.size[::-1]])
    if hasattr(processor, "post_process_object_detection"):
        results = processor.post_process_object_detection(outputs=outputs, target_sizes=target_sizes, threshold=threshold)[0]
        label_names = prompts
    else:
        results = processor.post_process_grounded_object_detection(outputs=outputs, target_sizes=target_sizes, threshold=threshold, text_labels=[prompts])[0]
        label_names = results.get("text_labels") or prompts
    detections = []
    for i, (score, box) in enumerate(zip(results["scores"], results["boxes"])):
        if "text_labels" in results:
            label_text = str(results["text_labels"][i])
        elif "labels" in results:
            label_val = results["labels"][i]
            try:
                label_text = label_names[int(label_val)]
            except Exception:
                label_text = str(label_val)
        else:
            label_text = str(label_names[i])
        x1, y1, x2, y2 = [round(float(v), 2) for v in box.tolist()]
        detections.append(
            {
                "label": label_text,
                "score": round(float(score), 4),
                "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "model": model_name,
            }
        )
    detections.sort(key=lambda d: d["score"], reverse=True)
    return detections


def prompts_for_features(features: list[dict[str, Any]]) -> list[str]:
    prompts = list(GENERAL_PROMPTS)
    for feat in features:
        prompts.extend(PROMPTS_BY_KIND.get(feat.get("kind"), []))
    return sorted(set(prompts))


def match_feature_detection(feature: dict[str, Any], detections: list[dict[str, Any]], min_score: float) -> dict[str, Any] | None:
    prompts = set(PROMPTS_BY_KIND.get(feature.get("kind"), []))
    if not prompts:
        return None
    matches = [d for d in detections if d["label"] in prompts and d["score"] >= min_score]
    return max(matches, key=lambda d: d["score"]) if matches else None


def draw_overlay(image: Image.Image, detections: list[dict[str, Any]], out_path: Path) -> None:
    img = image.copy()
    draw = ImageDraw.Draw(img)
    colors = ["#38bdf8", "#a7f3d0", "#facc15", "#f472b6", "#fb7185", "#c4b5fd"]
    for i, det in enumerate(detections[:14]):
        box = det["bbox"]
        color = colors[i % len(colors)]
        xy = [box["x1"], box["y1"], box["x2"], box["y2"]]
        draw.rectangle(xy, outline=color, width=4)
        label_y0 = max(0, xy[1] - 22)
        label_y1 = max(label_y0 + 18, xy[1])
        draw.rectangle([xy[0], label_y0, min(img.width, xy[0] + 260), label_y1], fill=(0, 0, 0))
        draw.text((xy[0] + 4, label_y0 + 2), f"{det['label']} {det['score']:.2f}", fill=color)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, quality=90)


def instances_to_seed_sql(instances: list[dict[str, Any]]) -> str:
    lines = ["-- Generated OWL-ViT photo_feature_instances seed.", "begin;"]
    for inst in instances:
        lines.append(
            "insert into public.photo_feature_instances "
            "(photo_id, feature_id, street_part_id, visible, pixel_x, pixel_y, bbox, detection_method, detection_model, detection_label, confidence) values ("
            f"(select id from public.street_photos where external_id={sql_literal(inst['photo_external_id'])}), "
            f"(select id from public.accessibility_features where external_id={sql_literal(inst['feature_external_id'])}), "
            f"(select id from public.street_parts where external_id={sql_literal(inst['street_part_id'])}), "
            f"{str(bool(inst.get('visible', True))).lower()}, {inst.get('pixel_x')}, {inst.get('pixel_y')}, "
            f"{jsonb_literal(inst.get('bbox'))}, {sql_literal(inst.get('detection_method'))}, "
            f"{sql_literal(inst.get('detection_model'))}, {sql_literal(inst.get('label'))}, {inst.get('confidence', 0)}) "
            "on conflict (photo_id, feature_id) do update set visible=excluded.visible, pixel_x=excluded.pixel_x, "
            "pixel_y=excluded.pixel_y, bbox=excluded.bbox, detection_method=excluded.detection_method, "
            "detection_model=excluded.detection_model, detection_label=excluded.detection_label, confidence=excluded.confidence;"
        )
    lines.append("commit;")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sql-out", type=Path, default=DEFAULT_SQL_OUT)
    parser.add_argument("--overlay-dir", type=Path, default=DEFAULT_OVERLAY_DIR)
    parser.add_argument("--model", default="google/owlvit-base-patch32")
    parser.add_argument("--threshold", type=float, default=0.08)
    parser.add_argument("--feature-match-threshold", type=float, default=0.07)
    parser.add_argument("--nearby-radius-m", type=float, default=35)
    parser.add_argument("--max-photos", type=int, default=None)
    args = parser.parse_args()

    registry = json.loads(args.registry.read_text())
    parts = {p["id"]: p for p in registry.get("street_parts", [])}
    photos = registry.get("street_photos", [])[: args.max_photos]
    features = load_accessibility_features(args.world)
    processor, model = load_model(args.model)

    photo_results = []
    instances = []
    for index, photo in enumerate(photos, start=1):
        part = parts.get(photo.get("street_part_id"), {})
        expected = nearby_features(photo, part, features, args.nearby_radius_m)
        prompts = prompts_for_features(expected)
        image = download_image(photo["image_url"])
        detections = run_owlvit(image, prompts, args.model, processor, model, args.threshold)
        overlay_path = args.overlay_dir / f"{index:02d}_{photo['street_part_id']}_{photo['source_image_id']}.jpg"
        draw_overlay(image, detections, overlay_path)
        matched = []
        for feat in expected:
            det = match_feature_detection(feat, detections, args.feature_match_threshold)
            if not det:
                continue
            box = det["bbox"]
            pixel_x = round((box["x1"] + box["x2"]) / 2, 2)
            pixel_y = round((box["y1"] + box["y2"]) / 2, 2)
            inst = {
                "photo_external_id": photo["external_id"],
                "feature_external_id": feat["external_id"],
                "street_part_id": photo["street_part_id"],
                "feature_kind": feat["kind"],
                "image_width": image.width,
                "image_height": image.height,
                "pixel_x": pixel_x,
                "pixel_y": pixel_y,
                "bbox": box,
                "detection_method": f"cv:{args.model}:zero_shot_owlvit",
                "detection_model": args.model,
                "confidence": det["score"],
                "label": det["label"],
                "feature_distance_to_photo_m": feat.get("distance_to_photo_m"),
            }
            instances.append(inst)
            matched.append(inst)
        photo_results.append(
            {
                "photo_external_id": photo["external_id"],
                "street_part_id": photo["street_part_id"],
                "source_image_id": photo.get("source_image_id"),
                "model": args.model,
                "overlay_path": str(overlay_path),
                "expected_feature_count": len(expected),
                "detection_count": len(detections),
                "matched_feature_count": len(matched),
                "detections": detections[:30],
                "matched_instances": matched,
            }
        )
        print(f"{index:02d}/{len(photos)} {photo['street_part_id']}: detections={len(detections)} matched={len(matched)}")

    result = {"model": args.model, "photos": photo_results, "instances": instances}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    args.sql_out.parent.mkdir(parents=True, exist_ok=True)
    args.sql_out.write_text(instances_to_seed_sql(instances))
    print(f"wrote {args.out} with {len(instances)} matched feature instances")
    print(f"wrote {args.sql_out}")


if __name__ == "__main__":
    main()
