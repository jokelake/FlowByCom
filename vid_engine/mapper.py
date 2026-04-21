import json

class StoryboardMapper:
    def __init__(self, ledger_path="vid_engine/casting_ledger.json"):
        self.ledger_path = ledger_path

    def load_ledger(self):
        with open(self.ledger_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_suggestions(self, character_names):
        """
        Takes a list of character names extracted from storyboard.
        Returns a dictionary mapping each character to existing blueprints in the ledger.
        """
        ledger = self.load_ledger()
        suggestions = {}

        for name in character_names:
            # Check for existing blueprints across all series in the global registry
            existing_series = ledger.get("global_registry", {}).get(name, [])
            
            options = []
            for series in existing_series:
                blueprint = ledger["series"][series]["characters"][name]
                options.append({
                    "series_title": series,
                    "description": blueprint["physical_description"],
                    "seed": blueprint["fixed_seed"]
                })
            
            suggestions[name] = options
            
        return suggestions

    def create_run_config(self, mapping_choices):
        """
        Takes user choices (e.g., {'Mali': 'น้องมะลิจอมพลังแห่งความดี'}) 
        and creates a configuration for the Ghost Engine run.
        """
        ledger = self.load_ledger()
        run_config = {"characters": {}}
        
        for char_name, series_title in mapping_choices.items():
            if series_title == "New Character":
                run_config["characters"][char_name] = "RANDOM"
            else:
                blueprint = ledger["series"][series_title]["characters"][char_name]
                run_config["characters"][char_name] = blueprint

        return run_config

if __name__ == "__main__":
    # Test logic
    mapper = StoryboardMapper()
    extracted_names = ["Mali", "Mom"]
    results = mapper.get_suggestions(extracted_names)
    print("\n[Mapper] Identity Suggestions:")
    print(json.dumps(results, indent=4, ensure_ascii=False))
