import json
import re

# Centralized Schema for Script Intelligence
# Both Parser and Ghost Engine will reference this or these patterns
DEFAULT_SCHEMA = {
    "image_prompt": ["image_prompt", "img_prompt", "prompt_image", "visual_prompt", "scene_visuals"],
    "image_prompt_start": ["image_prompt_start", "prompt_start", "start_image"],
    "image_prompt_end": ["image_prompt_end", "prompt_end", "end_image"],
    "video_prompt": ["video_motion_prompt", "video_prompt", "motion_prompt", "video_script", "action_prompt"],
    "transition_video_prompt": ["transition_video_prompt", "transition_prompt"]
}

class StoryboardParser:
    def __init__(self, storyboard_path):
        self.storyboard_path = storyboard_path
        self.data = self.load_json()

    def load_json(self):
        with open(self.storyboard_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def verify_compatibility(self):
        """
        Analyzes the JSON structure to find prompts and identify unknown synonyms.
        Returns a compatibility report.
        """
        scenes = self.data.get("storyboard", [])
        json_format = "Old Format (storyboard)"
        if not scenes:
            scenes = self.data.get("scenes", [])
            if scenes:
                json_format = "New Format (scenes)"

        report = {
            "scene_count": len(scenes),
            "mapped_keys": {"image_prompt": None, "image_prompt_start": None, "image_prompt_end": None, "video_prompt": None},
            "discovered_keys": [],
            "status": "READY",
            "json_format": json_format
        }
        
        if not scenes:
            report["status"] = "ERROR: No 'storyboard' or 'scenes' list found."
            return report

        # 1. Identify existing mapped keys
        sample_scene = scenes[0]
        for field, synonyms in DEFAULT_SCHEMA.items():
            for s in synonyms:
                if s in sample_scene:
                    report["mapped_keys"][field] = s
                    break

        # 2. Heuristic Discovery: Find long text fields that aren't mapped
        for key, value in sample_scene.items():
            # If it's a string, longer than 40 chars, and not already mapped
            if isinstance(value, str) and len(value) > 40:
                is_mapped = any(key == v for v in report["mapped_keys"].values())
                if not is_mapped:
                    report["discovered_keys"].append({
                        "key": key,
                        "sample": value[:50] + "...",
                        "suggestion": "image_prompt" if "visual" in key.lower() or "look" in key.lower() else "video_prompt"
                    })

        if not report["mapped_keys"]["image_prompt"] and not report["mapped_keys"]["image_prompt_start"]:
            report["status"] = "WARNING: No primary Image Prompt found."
            
        return report

    def extract_characters(self):
        """Identifies potential character names from prompts."""
        potential_characters = set()
        # Find which key contains our best text for extraction
        verify_report = self.verify_compatibility()
        text_keys = []
        if verify_report["mapped_keys"].get("image_prompt"):
            text_keys.append(verify_report["mapped_keys"]["image_prompt"])
        if verify_report["mapped_keys"].get("image_prompt_start"):
            text_keys.append(verify_report["mapped_keys"]["image_prompt_start"])
        if verify_report["mapped_keys"].get("image_prompt_end"):
            text_keys.append(verify_report["mapped_keys"]["image_prompt_end"])
            
        if not text_keys:
            text_keys = ["image_prompt"]
            
        scenes = self.data.get("storyboard", [])
        if not scenes:
            scenes = self.data.get("scenes", [])
        
        for scene in scenes:
            for text_key in text_keys:
                prompt = scene.get(text_key, "")
                matches = re.findall(r'\b([A-Z][a-z]+)\b', prompt)
                noise = ["The", "A", "And", "She", "It", "They", "Then", "When", "There", "He", "Her", "His"]
                for match in matches:
                    if match not in noise:
                        potential_characters.add(match)
                if "Mali" in prompt: potential_characters.add("Mali")
                if "Mom" in prompt: potential_characters.add("Mom")

        return sorted(list(potential_characters))
