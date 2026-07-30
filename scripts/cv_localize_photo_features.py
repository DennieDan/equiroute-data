#!/usr/bin/env python3
"""Computer-vision localization for JalanLens street photos.

Default provider is Agnes AI (`agnes-2.5-flash`) because it gives better
Singapore street-scene understanding than the earlier open-vocabulary OWLv2
boxes. OWLv2 remains available with `--provider owlvit` for offline fallback.
This produces local JSON, visual QA overlays, and idempotent Supabase seed SQL
for public.photo_feature_instances.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
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
    """Load an open-vocabulary detector.

    OWL-ViT base was too loose for our street photos: it produced giant road/car
    boxes and then the old matcher reused one box for many nearby features. Prefer
    OWLv2 when available, while keeping OWL-ViT compatibility for older cached runs.
    """
    from transformers import Owlv2ForObjectDetection, Owlv2Processor, OwlViTForObjectDetection, OwlViTProcessor

    if "owlv2" in model_name.lower():
        processor = Owlv2Processor.from_pretrained(model_name)
        model = Owlv2ForObjectDetection.from_pretrained(model_name)
    else:
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


def env_value(name: str, default: str | None = None) -> str | None:
    """Read env first, then ~/.hermes/.env without sourcing shell fragments."""
    if os.environ.get(name):
        return os.environ[name]
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for raw in env_path.read_text().splitlines():
            if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    return default


def json_from_model_text(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def normalize_agnes_box(box: dict[str, Any] | list[Any], width: int, height: int) -> dict[str, float]:
    if isinstance(box, list):
        if len(box) >= 4:
            box = {"x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3]}
        else:
            box = {}
    vals = {k: float(box.get(k, 0)) for k in ("x1", "y1", "x2", "y2")}
    # Agnes is prompted for normalized 0..1 boxes; accept pixel boxes too for robustness.
    if max(vals.values() or [0]) <= 1.5:
        vals = {"x1": vals["x1"] * width, "x2": vals["x2"] * width, "y1": vals["y1"] * height, "y2": vals["y2"] * height}
    return clamp_box(vals, width, height)


def run_agnes_vision(photo_url: str, image: Image.Image, expected: list[dict[str, Any]], model_name: str, min_confidence: float) -> list[dict[str, Any]]:
    api_key = env_value("AGNES_API_KEY")
    if not api_key:
        raise RuntimeError("AGNES_API_KEY is not set; create an Agnes API key and store it outside git")
    base_url = (env_value("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1") or "https://apihub.agnes-ai.com/v1").rstrip("/")
    candidates = [
        {
            "feature_external_id": f.get("external_id"),
            "kind": f.get("kind"),
            "name": f.get("name") or f.get("kind"),
            "distance_m": f.get("distance_to_photo_m"),
        }
        for f in expected
    ]
    prompt = (
        "You are localizing accessibility features in a Singapore street-level photo for JalanLens. "
        "Inspect the image directly and detect visible accessibility-relevant objects/features: sheltered/covered walkway, tactile paving, bollard/post, kerb ramp/curb cut, bus stop/shelter, footbridge, station entrance. "
        "Use the candidate list only to link visible objects back to map features when there is a plausible same-kind candidate nearby. "
        "Avoid duplicates: one physical shelter/covered walkway should be one detection even if the candidate list has multiple covered_linkway IDs. "
        "Return JSON only with key detections. Each detection should include kind, label, confidence 0..1, bbox with normalized coordinates x1,y1,x2,y2 in 0..1, "
        "and feature_external_id if a candidate same-kind feature is plausible. If useful objects are visible but no candidate ID fits, omit feature_external_id but still include the detection kind. "
        "If nothing relevant is visible, return {\"detections\":[]}.\n\n"
        f"Candidate nearby map features:\n{json.dumps(candidates, ensure_ascii=False)}"
    )
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": photo_url}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 1200,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read())
    content = data["choices"][0]["message"]["content"]
    parsed = json_from_model_text(content)
    feature_ids = {f.get("external_id") for f in expected}
    detections: list[dict[str, Any]] = []
    for det in parsed.get("detections", []):
        fid = det.get("feature_external_id")
        if fid and fid not in feature_ids:
            fid = None
        confidence = float(det.get("confidence", 0))
        if confidence < min_confidence:
            continue
        box = normalize_agnes_box(det.get("bbox") or {}, image.width, image.height)
        if box_area_ratio(box, image.width, image.height) <= 0:
            continue
        detections.append(
            {
                "feature_external_id": fid,
                "kind": str(det.get("kind") or ""),
                "label": str(det.get("label") or det.get("kind") or "visible feature"),
                "score": round(confidence, 4),
                "bbox": box,
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


def box_center(box: dict[str, Any]) -> tuple[float, float]:
    return ((float(box["x1"]) + float(box["x2"])) / 2, (float(box["y1"]) + float(box["y2"])) / 2)


def box_area_ratio(box: dict[str, Any], image_width: float, image_height: float) -> float:
    width = max(0.0, min(image_width, float(box["x2"])) - max(0.0, float(box["x1"])))
    height = max(0.0, min(image_height, float(box["y2"])) - max(0.0, float(box["y1"])))
    return (width * height) / max(1.0, image_width * image_height)


def clamp_box(box: dict[str, Any], image_width: float, image_height: float) -> dict[str, float]:
    return {
        "x1": round(max(0.0, min(image_width, float(box["x1"]))), 2),
        "y1": round(max(0.0, min(image_height, float(box["y1"]))), 2),
        "x2": round(max(0.0, min(image_width, float(box["x2"]))), 2),
        "y2": round(max(0.0, min(image_height, float(box["y2"]))), 2),
    }


def detection_matches_feature(feature: dict[str, Any], det: dict[str, Any], min_score: float, image_width: float, image_height: float) -> bool:
    """Reject generic/oversized detections before linking them to map features."""
    prompts = set(PROMPTS_BY_KIND.get(feature.get("kind"), []))
    if not prompts or det.get("label") not in prompts or float(det.get("score", 0)) < min_score:
        return False
    area = box_area_ratio(det["bbox"], image_width, image_height)
    if area <= 0 or area > 0.42:
        return False
    # Ground-plane objects should not be floating in the sky/building band.
    _, cy = box_center(det["bbox"])
    y_ratio = cy / max(1.0, image_height)
    if feature.get("kind") in {"kerb_ramp", "tactile_guidance", "bollard"} and y_ratio < 0.38:
        return False
    return True


def assign_feature_detections(
    features: list[dict[str, Any]],
    detections: list[dict[str, Any]],
    min_score: float,
    image_width: float,
    image_height: float,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """One-to-one feature↔detection matching.

    The earlier matcher picked the best same-label box independently for every
    nearby feature, so one shelter/sidewalk box could become 3-14 duplicate pins.
    Assign each detection at most once, prioritising closer map features and higher
    confidence boxes, so photo-feature positions become distinct and reviewable.
    """
    candidates: list[tuple[float, float, str, int, int]] = []
    for feature_i, feature in enumerate(features):
        for detection_i, det in enumerate(detections):
            if detection_matches_feature(feature, det, min_score, image_width, image_height):
                distance = float(feature.get("distance_to_photo_m", 999_999))
                score = float(det.get("score", 0))
                candidates.append((distance, -score, feature.get("external_id", ""), feature_i, detection_i))
    candidates.sort()

    used_features: set[int] = set()
    used_detections: set[int] = set()
    assignments: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for _distance, _neg_score, _external_id, feature_i, detection_i in candidates:
        if feature_i in used_features or detection_i in used_detections:
            continue
        used_features.add(feature_i)
        used_detections.add(detection_i)
        assignments.append((features[feature_i], detections[detection_i]))
    return assignments


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
    lines = [
        "-- Generated OWL-ViT photo_feature_instances seed.",
        "begin;",
        "delete from public.photo_feature_instances where photo_id in (select id from public.street_photos where source='mapillary' and external_id like 'photo_mapillary_%');",
    ]
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
    parser.add_argument("--model", default="agnes-2.5-flash")
    parser.add_argument("--provider", choices=["agnes", "owlvit"], default="agnes")
    parser.add_argument("--threshold", type=float, default=0.10)
    parser.add_argument("--feature-match-threshold", type=float, default=0.10)
    parser.add_argument("--nearby-radius-m", type=float, default=35)
    parser.add_argument("--max-photos", type=int, default=None)
    args = parser.parse_args()

    registry = json.loads(args.registry.read_text())
    parts = {p["id"]: p for p in registry.get("street_parts", [])}
    photos = registry.get("street_photos", [])[: args.max_photos]
    features = load_accessibility_features(args.world)
    processor = model = None
    if args.provider == "owlvit":
        processor, model = load_model(args.model)

    photo_results = []
    instances = []
    for index, photo in enumerate(photos, start=1):
        part = parts.get(photo.get("street_part_id"), {})
        expected = nearby_features(photo, part, features, args.nearby_radius_m)
        image = download_image(photo["image_url"])
        if args.provider == "agnes":
            detections = run_agnes_vision(photo["image_url"], image, expected, args.model, args.threshold)
            expected_by_id = {f.get("external_id"): f for f in expected}
            used_feature_ids: set[str] = set()
            assignments = []
            for det in detections:
                fid = det.get("feature_external_id")
                feat = expected_by_id.get(fid)
                if feat is None:
                    kind = det.get("kind")
                    feat = next((f for f in expected if f.get("kind") == kind and f.get("external_id") not in used_feature_ids), None)
                if feat is not None:
                    if feat.get("external_id"):
                        used_feature_ids.add(feat["external_id"])
                    assignments.append((feat, det))
            detection_method = f"cv:agnes:{args.model}:vision_candidate_json"
        else:
            prompts = prompts_for_features(expected)
            detections = run_owlvit(image, prompts, args.model, processor, model, args.threshold)
            assignments = assign_feature_detections(expected, detections, args.feature_match_threshold, image.width, image.height)
            detection_method = f"cv:{args.model}:one_to_one_open_vocab"
        overlay_path = args.overlay_dir / f"{index:02d}_{photo['street_part_id']}_{photo['source_image_id']}.jpg"
        draw_overlay(image, detections, overlay_path)
        matched = []
        used_physical_labels: set[tuple[str, str]] = set()
        for feat, det in assignments:
            physical_key = (feat.get("kind", ""), det.get("label", "").lower().strip())
            if args.provider == "agnes" and physical_key in used_physical_labels and feat.get("kind") == "covered_linkway":
                continue
            used_physical_labels.add(physical_key)
            box = clamp_box(det["bbox"], image.width, image.height)
            pixel_x, pixel_y = [round(v, 2) for v in box_center(box)]
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
                "detection_method": detection_method,
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
